"""Manual review trigger and stored review lookup."""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.database.models import Finding, PullRequest, Repository, ReviewRun, ReviewRunStatus
from app.database.session import get_db
from app.schemas.analysis import RepositoryContextResponse
from app.schemas.findings import FindingListResponse, FindingResponse
from app.schemas.github import ChangedFile
from app.schemas.rag import RetrievedChunk
from app.schemas.static_analysis import StaticAnalysisReport
from app.schemas.tests import TestRunReport
from app.schemas.review import (
    RepositoryListResponse,
    RepositorySummary,
    ReviewIngestResponse,
    ReviewListResponse,
    ReviewRunResponse,
    ReviewRunSummary,
)
from app.services.ingestion import ingest_pull_request, to_response
from app.services.scoring import calculate_review_score
from app.tools.github import GitHubAPIError, GitHubAuthError, build_github_client, github_is_configured

router = APIRouter(tags=["reviews"])
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_name(value: str, label: str) -> str:
    if not _NAME_RE.match(value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"invalid {label}")
    return value


@router.post(
    "/reviews/{owner}/{repo}/{pr_number}",
    response_model=ReviewIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def trigger_review(
    owner: str,
    repo: str,
    pr_number: int,
    db: Session = Depends(get_db),
) -> ReviewIngestResponse:
    owner = _validate_name(owner, "owner")
    repo = _validate_name(repo, "repository")
    if pr_number <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid pull request number")

    settings = get_settings()
    if not github_is_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub API credentials are not configured",
        )
    try:
        with build_github_client(owner, repo, settings=settings) as client:
            result = ingest_pull_request(
                db,
                client,
                owner=owner,
                repo=repo,
                number=pr_number,
                trigger="manual",
            )
    except GitHubAuthError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GitHub authentication failed") from exc
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="failed to fetch pull request from GitHub",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is unavailable. Start Postgres with docker compose.",
        ) from exc
    return to_response(result, trigger="manual")


def _finding_response(row: Finding) -> FindingResponse:
    return FindingResponse(
        id=row.id,
        file=row.file_path,
        line=row.line,
        category=row.category,
        severity=row.severity,
        title=row.title,
        description=row.description,
        evidence=row.evidence,
        suggested_fix=row.suggested_fix,
        confidence=row.confidence,
        verified=row.verified,
        verification_reason=row.verification_reason,
    )


def _review_summary(review_run: ReviewRun) -> ReviewRunSummary:
    pull_request = review_run.pull_request
    posted = review_run.reviews[0].posted_to_github if review_run.reviews else False
    github_review_id = review_run.reviews[0].github_review_id if review_run.reviews else None
    return ReviewRunSummary(
        id=review_run.id,
        status=review_run.status.value,
        trigger=review_run.trigger,
        commit_sha=review_run.commit_sha,
        repository=pull_request.repository.full_name,
        pull_request=pull_request.number,
        title=pull_request.title,
        author=pull_request.author,
        source_branch=pull_request.source_branch,
        target_branch=pull_request.target_branch,
        finding_count=len(review_run.findings),
        verified_count=sum(1 for item in review_run.findings if item.verified is True),
        score=calculate_review_score(review_run.findings),
        posted_to_github=posted,
        github_review_id=github_review_id,
        execution_time_ms=review_run.execution_time_ms,
        created_at=review_run.created_at,
        finished_at=review_run.finished_at,
    )


def _review_detail(review_run: ReviewRun) -> ReviewRunResponse:
    pull_request = review_run.pull_request
    repository = pull_request.repository
    raw_files = review_run.changed_files or []
    changed_files = [ChangedFile.model_validate(item) for item in raw_files] if isinstance(raw_files, list) else []
    return ReviewRunResponse(
        id=review_run.id,
        status=review_run.status.value,
        trigger=review_run.trigger,
        commit_sha=review_run.commit_sha,
        repository=repository.full_name,
        pull_request=pull_request.number,
        title=pull_request.title,
        author=pull_request.author,
        source_branch=pull_request.source_branch,
        target_branch=pull_request.target_branch,
        changed_files=changed_files,
        repository_context=RepositoryContextResponse.model_validate(review_run.repository_context)
        if isinstance(review_run.repository_context, dict)
        else None,
        retrieved_context=[RetrievedChunk.model_validate(item) for item in review_run.retrieved_context]
        if isinstance(review_run.retrieved_context, list)
        else [],
        static_analysis=StaticAnalysisReport.model_validate(review_run.static_analysis_results)
        if isinstance(review_run.static_analysis_results, dict)
        else None,
        test_results=TestRunReport.model_validate(review_run.test_results)
        if isinstance(review_run.test_results, dict)
        else None,
        agent_trace=review_run.agent_trace if isinstance(review_run.agent_trace, list) else [],
        summary=review_run.reviews[0].summary if review_run.reviews else None,
        posted_to_github=review_run.reviews[0].posted_to_github if review_run.reviews else False,
        github_review_id=review_run.reviews[0].github_review_id if review_run.reviews else None,
        findings=[_finding_response(item) for item in review_run.findings],
        errors=review_run.errors,
        resolved_config=review_run.resolved_config,
        config_sha=review_run.config_sha,
        score=calculate_review_score(review_run.findings),
        execution_time_ms=review_run.execution_time_ms,
        created_at=review_run.created_at,
        started_at=review_run.started_at,
        finished_at=review_run.finished_at,
    )


@router.get("/reviews", response_model=ReviewListResponse)
def list_reviews(
    repository: str | None = None,
    run_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ReviewListResponse:
    stmt = (
        select(ReviewRun)
        .join(PullRequest)
        .join(Repository)
        .options(
            selectinload(ReviewRun.pull_request).selectinload(PullRequest.repository),
            selectinload(ReviewRun.findings),
            selectinload(ReviewRun.reviews),
        )
        .order_by(ReviewRun.created_at.desc())
        .limit(limit)
    )
    if repository:
        stmt = stmt.where(Repository.full_name == repository)
    if run_status:
        try:
            status_value = ReviewRunStatus(run_status)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid review status") from exc
        stmt = stmt.where(ReviewRun.status == status_value)
    rows = db.scalars(stmt).unique().all()
    return ReviewListResponse(reviews=[_review_summary(row) for row in rows])


@router.get("/reviews/{review_id}", response_model=ReviewRunResponse)
def get_review(review_id: UUID, db: Session = Depends(get_db)) -> ReviewRunResponse:
    review_run = db.scalar(
        select(ReviewRun)
        .options(
            selectinload(ReviewRun.pull_request).selectinload(PullRequest.repository),
            selectinload(ReviewRun.findings),
            selectinload(ReviewRun.reviews),
        )
        .where(ReviewRun.id == review_id)
    )
    if review_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review run not found")
    return _review_detail(review_run)


@router.get("/reviews/{review_id}/findings", response_model=FindingListResponse)
def get_review_findings(review_id: UUID, db: Session = Depends(get_db)) -> FindingListResponse:
    review_run = db.scalar(select(ReviewRun).options(selectinload(ReviewRun.findings)).where(ReviewRun.id == review_id))
    if review_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review run not found")
    return FindingListResponse(
        review_run_id=review_run.id,
        findings=[_finding_response(item) for item in review_run.findings],
    )


@router.get("/repositories", response_model=RepositoryListResponse)
def list_repositories(db: Session = Depends(get_db)) -> RepositoryListResponse:
    rows = db.scalars(select(Repository).order_by(Repository.full_name)).all()
    return RepositoryListResponse(
        repositories=[
            RepositorySummary(
                id=row.id,
                full_name=row.full_name,
                default_branch=row.default_branch,
                html_url=row.html_url,
            )
            for row in rows
        ]
    )
