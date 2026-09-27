"""LangGraph nodes. Closures capture GitHub, DB, and optional LLM dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.prompts import QUALITY_SYSTEM_PROMPT, SECURITY_SYSTEM_PROMPT
from app.agents.review_agent import ReviewAgentError, generate_structured_review
from app.agents.verification import load_prior_finding_keys, verify_review
from app.core.config import get_settings
from app.core.llm import llm_is_configured
from app.core.logging import get_logger, log_event, set_review_run_id
from app.database.models import ReviewRun, ReviewRunStatus
from app.schemas.findings import ReviewFinding, StructuredReview
from app.schemas.static_analysis import StaticAnalysisReport
from app.schemas.tests import TestRunReport
from app.services.github_comments import post_verified_review
from app.services.ingestion import persist_snapshot
from app.services.rag import run_repository_rag
from app.services.repository_analysis import analyze_pull_request_repository
from app.services.review import persist_structured_review
from app.services.static_analysis import run_pull_request_static_analysis
from app.services.test_runner import run_pull_request_tests
from app.tools.github import GitHubAPIError, GitHubClient

logger = get_logger(__name__)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

RouteAfterPersist = Literal["start_reviews", "skip_review"]


@dataclass
class ReviewGraphDeps:
    session: Session
    client: GitHubClient
    llm: Any | None = None


def _event(node: str, status: str, **extra: Any) -> dict[str, Any]:
    payload = {"node": node, "status": status}
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def route_after_persist(state: dict[str, Any]) -> RouteAfterPersist:
    """Skip LLM nodes when this commit was already reviewed or no model is configured."""

    if state.get("duplicate"):
        return "skip_review"
    if not state.get("llm_ready"):
        return "skip_review"
    return "start_reviews"


def merge_structured_reviews(*reviews: StructuredReview | None) -> StructuredReview:
    """Combine parallel review passes. Same file + line + title is treated as a duplicate."""

    seen: set[tuple[str, int | None, str]] = set()
    findings: list[ReviewFinding] = []
    summaries: list[str] = []
    for review in reviews:
        if review is None:
            continue
        if review.summary.strip() and review.summary.strip() not in summaries:
            summaries.append(review.summary.strip())
        for finding in review.findings:
            key = (finding.file, finding.line, finding.title.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            findings.append(finding)
    summary = " ".join(summaries) if summaries else "No findings were produced."
    return StructuredReview(summary=summary, findings=findings)


def build_nodes(deps: ReviewGraphDeps) -> dict[str, Any]:
    def fetch_snapshot(state: dict[str, Any]) -> dict[str, Any]:
        snapshot = deps.client.fetch_pull_request_snapshot(state["owner"], state["repo"], state["number"])
        log_event(logger, "diff_analyzed", changed_files=len(snapshot.changed_files))
        return {
            "snapshot": snapshot,
            "events": [_event("fetch_snapshot", "ok", changed_files=len(snapshot.changed_files))],
        }

    def analyze_repository(state: dict[str, Any]) -> dict[str, Any]:
        snapshot = state["snapshot"]
        ref = snapshot.pull_request
        enriched, context, errors = analyze_pull_request_repository(
            deps.client,
            owner=ref.owner,
            repo=ref.repo,
            commit_sha=ref.head_sha,
            changed_files=snapshot.changed_files,
        )
        updated = snapshot.model_copy(update={"changed_files": enriched})
        return {
            "snapshot": updated,
            "repository_context": context,
            "errors": errors or [],
            "events": [_event("analyze_repository", "ok")],
        }

    def retrieve_context(state: dict[str, Any]) -> dict[str, Any]:
        retrieved, errors = run_repository_rag(deps.session, deps.client, state["snapshot"])
        return {
            "retrieved_context": retrieved,
            "errors": errors or [],
            "events": [_event("retrieve_context", "ok", chunks=len(retrieved))],
        }

    def run_static_analysis(state: dict[str, Any]) -> dict[str, Any]:
        report, errors = run_pull_request_static_analysis(deps.client, state["snapshot"])
        return {
            "static_analysis": report,
            "errors": errors or [],
            "events": [_event("run_static_analysis", "ok", issues=len(report.issues))],
        }

    def run_tests(state: dict[str, Any]) -> dict[str, Any]:
        report, errors = run_pull_request_tests(deps.client, state["snapshot"])
        return {
            "test_results": report.model_dump(),
            "errors": errors or [],
            "events": [
                _event(
                    "run_tests",
                    "skipped" if report.skipped else "ok",
                    passed=report.passed,
                    failed=report.failed,
                    discovered=len(report.discovered),
                )
            ],
        }

    def join_analysis(state: dict[str, Any]) -> dict[str, Any]:
        return {"events": [_event("join_analysis", "ok")]}

    def persist_run(state: dict[str, Any]) -> dict[str, Any]:
        snapshot = state["snapshot"]
        context = state.get("repository_context")
        retrieved = state.get("retrieved_context") or []
        static_report = state.get("static_analysis")
        if isinstance(static_report, dict):
            static_report = StaticAnalysisReport.model_validate(static_report)
        static_report = static_report or StaticAnalysisReport()
        raw_tests = state.get("test_results")
        if isinstance(raw_tests, TestRunReport):
            test_report = raw_tests
        elif isinstance(raw_tests, dict):
            test_report = TestRunReport.model_validate(raw_tests)
        else:
            test_report = TestRunReport(skipped=True, skip_reason="not run")
        result = persist_snapshot(
            deps.session,
            snapshot,
            trigger=state["trigger"],
            delivery_id=state.get("delivery_id"),
            repository_context=context.model_dump() if context is not None else None,
            retrieved_context=[item.model_dump() for item in retrieved] or None,
            static_analysis_results=static_report.model_dump(),
            test_results=test_report.model_dump(),
            errors=state.get("errors") or None,
        )
        llm_ready = deps.llm is not None or llm_is_configured()
        if not result.duplicate:
            stored = deps.session.get(ReviewRun, result.review_run_id)
            if stored is not None:
                stored.agent_trace = list(state.get("events") or []) + [_event("persist_run", "ok")]
                deps.session.flush()
        return {
            "review_run_id": result.review_run_id,
            "duplicate": result.duplicate,
            "status": result.status.value,
            "llm_ready": llm_ready,
            "events": [_event("persist_run", "duplicate" if result.duplicate else "ok")],
        }

    def start_reviews(state: dict[str, Any]) -> dict[str, Any]:
        review_run_id: UUID = state["review_run_id"]
        set_review_run_id(str(review_run_id))
        review_run = deps.session.get(ReviewRun, review_run_id)
        if review_run is not None:
            review_run.status = ReviewRunStatus.RUNNING
            review_run.started_at = datetime.now(UTC)
            deps.session.flush()
        return {"status": ReviewRunStatus.RUNNING.value, "events": [_event("start_reviews", "ok")]}

    def skip_review(state: dict[str, Any]) -> dict[str, Any]:
        review_run_id = state.get("review_run_id")
        if review_run_id is not None and not state.get("duplicate"):
            stored = deps.session.get(ReviewRun, review_run_id)
            if stored is not None:
                stored.agent_trace = list(state.get("events") or []) + [_event("skip_review", "ok")]
                deps.session.flush()
        return {"events": [_event("skip_review", "ok")]}

    def _focused_review(node: str, system_prompt: str, state: dict[str, Any]) -> StructuredReview | None:
        try:
            return generate_structured_review(
                state["snapshot"],
                state.get("repository_context"),
                llm=deps.llm,
                retrieved_context=state.get("retrieved_context") or [],
                static_analysis=state.get("static_analysis"),
                test_results=state.get("test_results"),
                system_prompt=system_prompt,
            )
        except ReviewAgentError:
            logger.exception("%s_failed", node)
            return None

    def review_security(state: dict[str, Any]) -> dict[str, Any]:
        review = _focused_review("review_security", SECURITY_SYSTEM_PROMPT, state)
        errors = [] if review is not None else [{"component": "review_agent", "message": "LLM structured review failed"}]
        return {
            "security_review": review,
            "errors": errors,
            "events": [_event("review_security", "ok" if review is not None else "failed")],
        }

    def review_quality(state: dict[str, Any]) -> dict[str, Any]:
        review = _focused_review("review_quality", QUALITY_SYSTEM_PROMPT, state)
        errors = [] if review is not None else [{"component": "review_agent", "message": "LLM structured review failed"}]
        return {
            "quality_review": review,
            "errors": errors,
            "events": [_event("review_quality", "ok" if review is not None else "failed")],
        }

    def synthesize(state: dict[str, Any]) -> dict[str, Any]:
        merged = merge_structured_reviews(state.get("security_review"), state.get("quality_review"))
        return {"review": merged, "events": [_event("synthesize", "ok", finding_count=len(merged.findings))]}

    def verify_findings(state: dict[str, Any]) -> dict[str, Any]:
        review = state.get("review")
        snapshot = state["snapshot"]
        if review is None:
            return {"events": [_event("verify_findings", "skipped")]}
        ref = snapshot.pull_request
        prior = load_prior_finding_keys(deps.session, f"{ref.owner}/{ref.repo}", ref.head_sha)
        verified = verify_review(
            review,
            snapshot=snapshot,
            retrieved=state.get("retrieved_context") or [],
            static_report=state.get("static_analysis"),
            test_report=state.get("test_results"),
            prior=prior,
        )
        accepted = sum(1 for item in verified.findings if item.verified)
        return {
            "review": verified,
            "events": [_event("verify_findings", "ok", accepted=accepted, total=len(verified.findings))],
        }

    def persist_findings(state: dict[str, Any]) -> dict[str, Any]:
        review_run_id: UUID = state["review_run_id"]
        review_run = deps.session.scalar(
            select(ReviewRun)
            .options(selectinload(ReviewRun.findings), selectinload(ReviewRun.reviews))
            .where(ReviewRun.id == review_run_id)
        )
        if review_run is None:
            raise ValueError("review run not found")
        started = _as_utc(review_run.started_at) if review_run.started_at is not None else datetime.now(UTC)
        review = state.get("review")
        security_ok = state.get("security_review") is not None
        quality_ok = state.get("quality_review") is not None
        errors = list(state.get("errors") or [])
        if not security_ok and not quality_ok:
            review_run.status = ReviewRunStatus.FAILED
            review_run.errors = errors or [{"component": "review_agent", "message": "LLM structured review failed"}]
            log_event(logger, "review_failed", error_type="ReviewAgentError")
        else:
            persist_structured_review(deps.session, review_run, review)
            review_run.status = ReviewRunStatus.COMPLETED
            if errors:
                review_run.errors = errors
            log_event(logger, "review_persisted", finding_count=len(review.findings) if review else 0)
        finished = datetime.now(UTC)
        review_run.finished_at = finished
        review_run.execution_time_ms = int((finished - started).total_seconds() * 1000)
        review_run.agent_trace = list(state.get("events") or []) + [_event("persist_findings", review_run.status.value)]
        deps.session.flush()
        return {
            "status": review_run.status.value,
            "events": [_event("persist_findings", review_run.status.value)],
        }

    def post_github_review(state: dict[str, Any]) -> dict[str, Any]:
        def record(event: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
            review_run_id = state.get("review_run_id")
            if review_run_id is not None:
                stored = deps.session.scalar(
                    select(ReviewRun).options(selectinload(ReviewRun.reviews)).where(ReviewRun.id == review_run_id)
                )
                if stored is not None:
                    if extra:
                        if extra.get("posted_to_github") and stored.reviews:
                            stored.reviews[0].posted_to_github = True
                            github_review_id = extra.get("github_review_id")
                            if isinstance(github_review_id, int):
                                stored.reviews[0].github_review_id = github_review_id
                        if extra.get("errors"):
                            existing = list(stored.errors) if isinstance(stored.errors, list) else []
                            stored.errors = existing + extra["errors"]
                    stored.agent_trace = list(state.get("events") or []) + [event]
                    deps.session.flush()
            payload = {"events": [event]}
            if extra:
                payload.update({key: value for key, value in extra.items() if key != "posted_to_github"})
            return payload

        settings = get_settings()
        if not settings.github_post_reviews:
            return record(_event("post_github_review", "skipped", reason="disabled"))
        if state.get("status") != ReviewRunStatus.COMPLETED.value:
            return record(_event("post_github_review", "skipped", reason="not_completed"))
        raw_review = state.get("review")
        if raw_review is None:
            return record(_event("post_github_review", "skipped", reason="no_review"))
        review = raw_review if isinstance(raw_review, StructuredReview) else StructuredReview.model_validate(raw_review)
        try:
            payload = post_verified_review(deps.client, state["snapshot"], review)
        except GitHubAPIError:
            errors = [{"component": "github_comments", "message": "failed to post GitHub review"}]
            return record(_event("post_github_review", "failed"), {"errors": errors})
        if payload is None:
            return record(_event("post_github_review", "skipped", reason="nothing_to_post"))
        github_review_id = payload.get("id")
        return record(
            _event("post_github_review", "ok", github_review_id=github_review_id),
            {"github_review_id": github_review_id, "posted_to_github": True},
        )

    return {
        "fetch_snapshot": fetch_snapshot,
        "analyze_repository": analyze_repository,
        "retrieve_context": retrieve_context,
        "run_static_analysis": run_static_analysis,
        "run_tests": run_tests,
        "join_analysis": join_analysis,
        "persist_run": persist_run,
        "start_reviews": start_reviews,
        "skip_review": skip_review,
        "review_security": review_security,
        "review_quality": review_quality,
        "synthesize": synthesize,
        "verify_findings": verify_findings,
        "persist_findings": persist_findings,
        "post_github_review": post_github_review,
    }
