"""Verification agent tests. No LLM provider calls."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.verification import load_prior_finding_keys, verify_finding, verify_review
from app.database.models import Finding, PullRequest, Repository, ReviewRun, ReviewRunStatus
from app.schemas.findings import FindingCategory, FindingSeverity, StructuredReview
from app.schemas.static_analysis import StaticAnalysisReport, ToolIssue, ToolRun
from tests.test_review_agent import _finding, _snapshot


def test_accepts_finding_backed_by_diff() -> None:
    result = verify_finding(
        _finding(),
        snapshot=_snapshot(),
        retrieved=[],
        static_report=None,
        accepted=[],
        prior=[],
    )
    assert result.verified is True
    assert result.verification_reason is not None
    assert "corpus" in result.verification_reason


def test_rejects_line_outside_diff() -> None:
    result = verify_finding(
        _finding(line=999),
        snapshot=_snapshot(),
        retrieved=[],
        static_report=None,
        accepted=[],
        prior=[],
    )
    assert result.verified is False
    assert "line" in (result.verification_reason or "")


def test_rejects_invented_evidence() -> None:
    result = verify_finding(
        _finding(evidence="eval(user_supplied_payload_from_nowhere)"),
        snapshot=_snapshot(),
        retrieved=[],
        static_report=None,
        accepted=[],
        prior=[],
    )
    assert result.verified is False
    assert "evidence" in (result.verification_reason or "")


def test_rejects_near_duplicate_on_same_run() -> None:
    first = verify_finding(
        _finding(),
        snapshot=_snapshot(),
        retrieved=[],
        static_report=None,
        accepted=[],
        prior=[],
    )
    second = verify_finding(
        _finding(title="SQL built from user input!", line=12, evidence="db.execute(query, (user_id,))"),
        snapshot=_snapshot(),
        retrieved=[],
        static_report=None,
        accepted=[first],
        prior=[],
    )
    assert first.verified is True
    assert second.verified is False
    assert "duplicate" in (second.verification_reason or "")


def test_rejects_prior_verified_duplicate(db_session: Session) -> None:
    repository = Repository(full_name="acme/api")
    pull_request = PullRequest(repository=repository, number=12, title="old", head_sha="oldsha")
    run = ReviewRun(
        pull_request=pull_request,
        commit_sha="oldsha",
        status=ReviewRunStatus.COMPLETED,
        trigger="manual",
    )
    db_session.add_all(
        [
            repository,
            pull_request,
            run,
            Finding(
                review_run=run,
                file_path="backend/services/user_service.py",
                line=11,
                category=FindingCategory.SECURITY,
                severity=FindingSeverity.HIGH,
                title="SQL built from user input",
                description="old",
                evidence="db.execute",
                suggested_fix="bind",
                confidence=0.9,
                verified=True,
            ),
        ]
    )
    db_session.flush()
    prior = load_prior_finding_keys(db_session, "acme/api", "abc123def456")
    result = verify_finding(
        _finding(),
        snapshot=_snapshot(),
        retrieved=[],
        static_report=None,
        accepted=[],
        prior=prior,
    )
    assert result.verified is False
    assert "previously verified" in (result.verification_reason or "")


def test_static_analysis_corroboration_noted() -> None:
    report = StaticAnalysisReport(
        runs=[
            ToolRun(
                tool="bandit",
                command=["bandit"],
                issues=[
                    ToolIssue(
                        tool="bandit",
                        file="backend/services/user_service.py",
                        line=11,
                        rule="B608",
                        message="Possible SQL injection",
                    )
                ],
            )
        ]
    )
    result = verify_finding(
        _finding(),
        snapshot=_snapshot(),
        retrieved=[],
        static_report=report,
        accepted=[],
        prior=[],
    )
    assert result.verified is True
    assert "static analysis" in (result.verification_reason or "")


def test_verify_review_annotates_summary() -> None:
    review = StructuredReview(
        summary="Look at SQL.",
        findings=[_finding(), _finding(line=999, title="Ghost line")],
    )
    verified = verify_review(review, snapshot=_snapshot())
    assert verified.findings[0].verified is True
    assert verified.findings[1].verified is False
    assert "1 accepted, 1 rejected" in verified.summary
