"""Persist LLM review output onto a review run."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.review_agent import ReviewAgentError, generate_structured_review
from app.core.llm import LLMConfigError, llm_is_configured
from app.core.logging import get_logger, log_event, set_review_run_id
from app.database.models import Finding, Review, ReviewRun, ReviewRunStatus
from app.schemas.analysis import RepositoryContextResponse
from app.schemas.findings import StructuredReview
from app.schemas.github import PullRequestSnapshot
from app.schemas.rag import RetrievedChunk
from app.schemas.static_analysis import StaticAnalysisReport

logger = get_logger(__name__)


def persist_structured_review(session: Session, review_run: ReviewRun, review: StructuredReview) -> None:
    session.add(
        Review(
            review_run_id=review_run.id,
            summary=review.summary,
            posted_to_github=False,
        )
    )
    for finding in review.findings:
        session.add(
            Finding(
                review_run_id=review_run.id,
                file_path=finding.file,
                line=finding.line,
                category=finding.category,
                severity=finding.severity,
                title=finding.title,
                description=finding.description,
                evidence=finding.evidence,
                suggested_fix=finding.suggested_fix,
                confidence=finding.confidence,
                verified=finding.verified,
                verification_reason=finding.verification_reason,
            )
        )
    session.flush()


def run_structured_review(
    session: Session,
    review_run_id: UUID,
    snapshot: PullRequestSnapshot,
    repository_context: RepositoryContextResponse | None,
    *,
    retrieved_context: list[RetrievedChunk] | None = None,
    static_analysis: StaticAnalysisReport | None = None,
    llm: object | None = None,
) -> ReviewRun:
    """Generate and store structured findings. Does not post to GitHub."""

    review_run = session.scalar(
        select(ReviewRun).options(selectinload(ReviewRun.findings), selectinload(ReviewRun.reviews)).where(
            ReviewRun.id == review_run_id
        )
    )
    if review_run is None:
        raise ValueError("review run not found")

    set_review_run_id(str(review_run.id))
    if llm is None and not llm_is_configured():
        log_event(logger, "llm_skipped_not_configured")
        return review_run

    review_run.status = ReviewRunStatus.RUNNING
    review_run.started_at = datetime.now(UTC)
    session.flush()
    started = datetime.now(UTC)
    try:
        review = generate_structured_review(
            snapshot,
            repository_context,
            llm=llm,
            retrieved_context=retrieved_context,
            static_analysis=static_analysis,
        )
        persist_structured_review(session, review_run, review)
        review_run.status = ReviewRunStatus.COMPLETED
        log_event(logger, "review_persisted", finding_count=len(review.findings))
    except (LLMConfigError, ReviewAgentError) as exc:
        log_event(logger, "review_failed", error_type=type(exc).__name__)
        review_run.status = ReviewRunStatus.FAILED
        errors = list(review_run.errors) if isinstance(review_run.errors, list) else []
        errors.append({"component": "review_agent", "message": "LLM structured review failed"})
        review_run.errors = errors
    finally:
        finished = datetime.now(UTC)
        review_run.finished_at = finished
        review_run.execution_time_ms = int((finished - started).total_seconds() * 1000)
        session.flush()
    return review_run
