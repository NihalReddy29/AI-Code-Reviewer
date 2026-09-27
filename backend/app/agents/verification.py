"""Deterministic verification of LLM findings against the PR corpus.

This is not an LLM step. Evidence must appear in the diff, retrieved chunks, or
static-analysis output. Duplicates (this run and prior verified runs) are rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger, log_event
from app.database.models import Finding, PullRequest, Repository, ReviewRun, ReviewRunStatus
from app.schemas.findings import ReviewFinding, StructuredReview
from app.schemas.github import ChangedFile, PullRequestSnapshot
from app.schemas.rag import RetrievedChunk
from app.schemas.static_analysis import StaticAnalysisReport
from app.schemas.tests import TestRunReport

logger = get_logger(__name__)


def _as_test_report(value: TestRunReport | dict | None) -> TestRunReport | None:
    if value is None:
        return None
    if isinstance(value, TestRunReport):
        return value
    if isinstance(value, dict):
        return TestRunReport.model_validate(value)
    return None

_TOKEN = re.compile(r"[a-z0-9_]{3,}")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
LINE_SLACK = 3
TITLE_JACCARD = 0.5


@dataclass(frozen=True)
class PriorFindingKey:
    file_path: str
    title_key: str
    line: int | None
    category: str


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def normalize_title(title: str) -> str:
    return _NON_ALNUM.sub(" ", title.lower()).strip()


def tokenize(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _hunk_lines(item: ChangedFile) -> set[int]:
    lines: set[int] = set()
    for hunk in item.hunks:
        lines.update(hunk.added_line_numbers)
        lines.update(hunk.removed_line_numbers)
        lines.update(range(hunk.new_start, hunk.new_start + max(hunk.new_count, 1)))
    return lines


def line_supported(item: ChangedFile, line: int | None) -> bool:
    if line is None:
        return True
    supported = _hunk_lines(item)
    if line in supported:
        return True
    added = {number for hunk in item.hunks for number in hunk.added_line_numbers}
    return any(abs(line - number) <= LINE_SLACK for number in added)


def _corpus_for_file(
    path: str,
    snapshot: PullRequestSnapshot,
    retrieved: list[RetrievedChunk],
    static_report: StaticAnalysisReport | None,
    test_report: TestRunReport | None = None,
) -> str:
    parts: list[str] = []
    for item in snapshot.changed_files:
        if normalize_path(item.path) == path or (item.previous_path and normalize_path(item.previous_path) == path):
            if item.patch:
                parts.append(item.patch)
            for hunk in item.hunks:
                if hunk.header:
                    parts.append(hunk.header)
        if path in {normalize_path(related) for related in item.related_paths} and item.patch:
            parts.append(item.patch)
    if snapshot.diff:
        parts.append(snapshot.diff)
    for chunk in retrieved:
        if normalize_path(chunk.file_path) == path:
            parts.append(chunk.text)
    if static_report is not None:
        for issue in static_report.issues:
            if normalize_path(issue.file) == path:
                parts.append(f"{issue.rule or ''} {issue.message}")
    if test_report is not None:
        report = test_report if isinstance(test_report, TestRunReport) else TestRunReport.model_validate(test_report)
        for case in report.cases:
            case_file = normalize_path(case.file or "")
            if case_file == path or path.rstrip(".py").replace("/", ".") in case.nodeid.replace("::", "."):
                parts.append(f"{case.nodeid} {case.outcome} {case.message or ''}")
    return "\n".join(parts)


def evidence_supported(evidence: str, corpus: str) -> bool:
    needle = " ".join(evidence.lower().split())
    haystack = " ".join(corpus.lower().split())
    if len(needle) >= 8 and needle in haystack:
        return True
    tokens = tokenize(evidence)
    if len(tokens) < 2:
        return False
    present = tokenize(corpus)
    overlap = tokens & present
    return len(overlap) / len(tokens) >= 0.6


def static_corroborates(finding: ReviewFinding, report: StaticAnalysisReport | None) -> bool:
    if report is None:
        return False
    path = normalize_path(finding.file)
    for issue in report.issues:
        if normalize_path(issue.file) != path:
            continue
        if finding.line is not None and issue.line is not None and abs(finding.line - issue.line) <= LINE_SLACK:
            return True
        if evidence_supported(finding.evidence, f"{issue.rule or ''} {issue.message}"):
            return True
    return False


def is_near_duplicate(candidate: ReviewFinding, accepted: list[ReviewFinding]) -> ReviewFinding | None:
    title_key = normalize_title(candidate.title)
    title_tokens = tokenize(candidate.title)
    path = normalize_path(candidate.file)
    for existing in accepted:
        if normalize_path(existing.file) != path:
            continue
        if normalize_title(existing.title) == title_key:
            if candidate.line is None or existing.line is None or abs(candidate.line - existing.line) <= LINE_SLACK:
                return existing
        same_category = existing.category == candidate.category
        close_line = (
            candidate.line is not None
            and existing.line is not None
            and abs(candidate.line - existing.line) <= LINE_SLACK
        )
        similar_title = _jaccard(title_tokens, tokenize(existing.title)) >= TITLE_JACCARD
        if same_category and close_line and similar_title:
            return existing
    return None


def matches_prior(finding: ReviewFinding, prior: list[PriorFindingKey]) -> bool:
    path = normalize_path(finding.file)
    title_key = normalize_title(finding.title)
    for item in prior:
        if item.file_path != path or item.title_key != title_key:
            continue
        if finding.line is None or item.line is None or abs(finding.line - item.line) <= LINE_SLACK:
            return True
    return False


def load_prior_finding_keys(session: Session, repository: str, commit_sha: str) -> list[PriorFindingKey]:
    rows = session.scalars(
        select(Finding)
        .join(ReviewRun, Finding.review_run_id == ReviewRun.id)
        .join(PullRequest, ReviewRun.pull_request_id == PullRequest.id)
        .join(Repository, PullRequest.repository_id == Repository.id)
        .where(
            Repository.full_name == repository,
            ReviewRun.status == ReviewRunStatus.COMPLETED,
            ReviewRun.commit_sha != commit_sha,
            Finding.verified.is_(True),
        )
        .limit(50)
    ).all()
    return [
        PriorFindingKey(
            file_path=normalize_path(row.file_path),
            title_key=normalize_title(row.title),
            line=row.line,
            category=row.category.value if hasattr(row.category, "value") else str(row.category),
        )
        for row in rows
    ]


def verify_finding(
    finding: ReviewFinding,
    *,
    snapshot: PullRequestSnapshot,
    retrieved: list[RetrievedChunk],
    static_report: StaticAnalysisReport | None,
    accepted: list[ReviewFinding],
    prior: list[PriorFindingKey],
    test_report: TestRunReport | None = None,
) -> ReviewFinding:
    path = normalize_path(finding.file)
    files = {normalize_path(item.path): item for item in snapshot.changed_files}
    for item in snapshot.changed_files:
        if item.previous_path:
            files.setdefault(normalize_path(item.previous_path), item)

    if path not in files and not any(path == normalize_path(rel) for item in snapshot.changed_files for rel in item.related_paths):
        return finding.model_copy(update={"verified": False, "verification_reason": "file is not in the pull request snapshot"})

    duplicate = is_near_duplicate(finding, accepted)
    if duplicate is not None:
        return finding.model_copy(
            update={"verified": False, "verification_reason": f"duplicate of '{duplicate.title}' on this run"}
        )
    if matches_prior(finding, prior):
        return finding.model_copy(update={"verified": False, "verification_reason": "duplicate of a previously verified finding"})

    changed = files.get(path)
    if changed is not None and not line_supported(changed, finding.line):
        return finding.model_copy(update={"verified": False, "verification_reason": "line is not in the pull request diff"})

    corpus = _corpus_for_file(path, snapshot, retrieved, static_report, _as_test_report(test_report))
    if not evidence_supported(finding.evidence, corpus):
        return finding.model_copy(update={"verified": False, "verification_reason": "evidence was not found in the diff, retrieval, or static analysis"})

    reason = "evidence matches the pull request corpus"
    if static_corroborates(finding, static_report):
        reason = "evidence matches the corpus and is corroborated by static analysis"
    return finding.model_copy(update={"verified": True, "verification_reason": reason})


def verify_review(
    review: StructuredReview,
    *,
    snapshot: PullRequestSnapshot,
    retrieved: list[RetrievedChunk] | None = None,
    static_report: StaticAnalysisReport | None = None,
    test_report: TestRunReport | None = None,
    prior: list[PriorFindingKey] | None = None,
) -> StructuredReview:
    """Mark each finding verified/unverified. Unverified findings are kept for the dashboard."""

    chunks = retrieved or []
    prior_keys = prior or []
    verified_keep: list[ReviewFinding] = []
    annotated: list[ReviewFinding] = []
    for finding in review.findings:
        result = verify_finding(
            finding,
            snapshot=snapshot,
            retrieved=chunks,
            static_report=static_report,
            test_report=test_report,
            accepted=verified_keep,
            prior=prior_keys,
        )
        annotated.append(result)
        if result.verified:
            verified_keep.append(result)
        log_event(
            logger,
            "finding_verified" if result.verified else "finding_rejected",
            file=result.file,
            line=result.line,
            reason=result.verification_reason,
        )
    accepted = sum(1 for item in annotated if item.verified)
    rejected = len(annotated) - accepted
    suffix = f" Verification: {accepted} accepted, {rejected} rejected as false positives or duplicates."
    summary = review.summary.strip()
    if "Verification:" not in summary:
        summary = f"{summary}{suffix}"
    return StructuredReview(summary=summary, findings=annotated)
