"""Fetch a pull request, extract the diff, and persist a review run."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analyzers.diff import snapshot_to_dict
from app.core.logging import get_logger, log_event, set_review_run_id
from app.database.models import PullRequest, Repository, ReviewRun, ReviewRunStatus
from app.schemas.github import PullRequestSnapshot
from app.schemas.review import ReviewIngestResponse
from app.tools.github import GitHubClient

logger = get_logger(__name__)

_ACTIVE_STATUSES = {ReviewRunStatus.PENDING, ReviewRunStatus.RUNNING, ReviewRunStatus.COMPLETED}


@dataclass(frozen=True)
class IngestResult:
    review_run_id: UUID
    duplicate: bool
    snapshot: PullRequestSnapshot
    status: ReviewRunStatus


def _upsert_repository(session: Session, snapshot: PullRequestSnapshot) -> Repository:
    ref = snapshot.pull_request
    full_name = f"{ref.owner}/{ref.repo}"
    repository = session.scalar(select(Repository).where(Repository.full_name == full_name))
    if repository is None:
        repository = Repository(full_name=full_name)
        session.add(repository)
    repository.github_id = ref.github_repo_id
    repository.default_branch = ref.default_branch
    repository.html_url = f"https://github.com/{full_name}" if ref.html_url is None else _repo_html_url(ref.html_url)
    session.flush()
    return repository


def _repo_html_url(pull_html_url: str) -> str:
    if "/pull/" in pull_html_url:
        return pull_html_url.split("/pull/")[0]
    return pull_html_url


def _upsert_pull_request(session: Session, repository: Repository, snapshot: PullRequestSnapshot) -> PullRequest:
    ref = snapshot.pull_request
    pull_request = session.scalar(
        select(PullRequest).where(
            PullRequest.repository_id == repository.id,
            PullRequest.number == ref.number,
        )
    )
    if pull_request is None:
        pull_request = PullRequest(repository_id=repository.id, number=ref.number, title=ref.title)
        session.add(pull_request)
    pull_request.title = ref.title
    pull_request.author = ref.author
    pull_request.source_branch = ref.source_branch
    pull_request.target_branch = ref.target_branch
    pull_request.head_sha = ref.head_sha
    pull_request.html_url = ref.html_url
    session.flush()
    return pull_request


def find_duplicate_run(
    session: Session,
    pull_request: PullRequest,
    commit_sha: str,
    *,
    delivery_id: str | None = None,
) -> ReviewRun | None:
    if delivery_id:
        by_delivery = session.scalar(select(ReviewRun).where(ReviewRun.github_delivery_id == delivery_id))
        if by_delivery is not None:
            return by_delivery
    return session.scalar(
        select(ReviewRun)
        .where(
            ReviewRun.pull_request_id == pull_request.id,
            ReviewRun.commit_sha == commit_sha,
            ReviewRun.status.in_(_ACTIVE_STATUSES),
        )
        .order_by(ReviewRun.created_at.desc())
    )


def persist_snapshot(
    session: Session,
    snapshot: PullRequestSnapshot,
    *,
    trigger: str,
    delivery_id: str | None = None,
    repository_context: dict | None = None,
    retrieved_context: list | dict | None = None,
    static_analysis_results: dict | None = None,
    test_results: dict | None = None,
    errors: list | dict | None = None,
) -> IngestResult:
    repository = _upsert_repository(session, snapshot)
    pull_request = _upsert_pull_request(session, repository, snapshot)
    existing = find_duplicate_run(session, pull_request, snapshot.pull_request.head_sha, delivery_id=delivery_id)
    if existing is not None:
        set_review_run_id(str(existing.id))
        log_event(
            logger,
            "review_run_duplicate_skipped",
            review_run_id=str(existing.id),
            commit_sha=existing.commit_sha,
        )
        return IngestResult(
            review_run_id=existing.id,
            duplicate=True,
            snapshot=snapshot,
            status=existing.status,
        )

    review_run = ReviewRun(
        pull_request_id=pull_request.id,
        commit_sha=snapshot.pull_request.head_sha,
        status=ReviewRunStatus.PENDING,
        trigger=trigger,
        github_delivery_id=delivery_id,
        changed_files=snapshot_to_dict(snapshot),
        repository_context=repository_context,
        retrieved_context=retrieved_context,
        static_analysis_results=static_analysis_results,
        test_results=test_results,
        errors=errors,
    )
    session.add(review_run)
    session.flush()
    set_review_run_id(str(review_run.id))
    log_event(
        logger,
        "review_run_created",
        repository=repository.full_name,
        pull_request=pull_request.number,
        commit_sha=review_run.commit_sha,
        trigger=trigger,
        changed_files=len(snapshot.changed_files),
    )
    return IngestResult(
        review_run_id=review_run.id,
        duplicate=False,
        snapshot=snapshot,
        status=review_run.status,
    )


def ingest_pull_request(
    session: Session,
    client: GitHubClient,
    *,
    owner: str,
    repo: str,
    number: int,
    trigger: str,
    delivery_id: str | None = None,
    llm: object | None = None,
) -> IngestResult:
    from app.agents.graph import run_review_graph

    log_event(logger, "review_started", repository=f"{owner}/{repo}", pull_request=number, trigger=trigger)
    return run_review_graph(
        session,
        client,
        owner=owner,
        repo=repo,
        number=number,
        trigger=trigger,
        delivery_id=delivery_id,
        llm=llm,
    )


def to_response(result: IngestResult, trigger: str) -> ReviewIngestResponse:
    ref = result.snapshot.pull_request
    return ReviewIngestResponse(
        review_run_id=result.review_run_id,
        status=result.status.value,
        duplicate=result.duplicate,
        repository=f"{ref.owner}/{ref.repo}",
        pull_request=ref.number,
        commit_sha=ref.head_sha,
        changed_file_count=len(result.snapshot.changed_files),
        trigger=trigger,
    )
