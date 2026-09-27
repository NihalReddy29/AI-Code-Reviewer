"""Index PR-related files and retrieve surrounding code for the review agent."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analyzers.language import detect_language
from app.core.config import get_settings
from app.core.logging import get_logger, log_event
from app.database.models import Finding, PullRequest, Repository, ReviewRun, ReviewRunStatus
from app.rag.chunking import chunk_file
from app.rag.embeddings import Embedder, build_embedder
from app.rag.indexer import QdrantStore, build_qdrant_store, index_chunks, select_index_paths
from app.rag.retriever import retrieve_for_pull_request
from app.schemas.github import PullRequestSnapshot
from app.schemas.rag import CodeChunk, RetrievedChunk
from app.tools.github import GitHubAPIError, GitHubClient

logger = get_logger(__name__)


def _prior_review_chunks(session: Session, repository: str, commit_sha: str) -> list[CodeChunk]:
    rows = session.scalars(
        select(Finding)
        .join(ReviewRun, Finding.review_run_id == ReviewRun.id)
        .join(PullRequest, ReviewRun.pull_request_id == PullRequest.id)
        .join(Repository, PullRequest.repository_id == Repository.id)
        .where(
            Repository.full_name == repository,
            ReviewRun.status == ReviewRunStatus.COMPLETED,
            ReviewRun.commit_sha != commit_sha,
        )
        .limit(15)
    ).all()
    chunks: list[CodeChunk] = []
    for finding in rows:
        text = f"{finding.title}\n{finding.description}\n{finding.evidence or ''}"
        chunks.append(
            CodeChunk(
                repository=repository,
                commit_sha=commit_sha,
                file_path=finding.file_path,
                language=detect_language(finding.file_path),
                kind="prior_review",
                symbol=finding.title[:120],
                start_line=finding.line or 1,
                end_line=finding.line or 1,
                text=text,
            )
        )
    return chunks


def fetch_index_files(
    client: GitHubClient,
    *,
    owner: str,
    repo: str,
    commit_sha: str,
    paths: list[str],
) -> tuple[dict[str, str], list[dict[str, str]]]:
    files: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    for path in paths:
        try:
            text = client.get_text_file(owner, repo, path, ref=commit_sha)
        except GitHubAPIError:
            logger.exception("rag_file_fetch_failed")
            errors.append({"component": "rag", "message": f"failed to fetch {path}"})
            continue
        if text:
            files[path] = text
    return files, errors


def run_repository_rag(
    session: Session,
    client: GitHubClient,
    snapshot: PullRequestSnapshot,
    tree_paths: list[str] | None = None,
    *,
    store: QdrantStore | None = None,
    embedder: Embedder | None = None,
) -> tuple[list[RetrievedChunk], list[dict[str, str]]]:
    """Index PR-related files and retrieve chunks around changed symbols.

    Vector store and embedding failures are returned as errors; callers keep reviewing.
    """

    settings = get_settings()
    errors: list[dict[str, str]] = []
    ref = snapshot.pull_request
    repository = f"{ref.owner}/{ref.repo}"
    try:
        embedder = embedder or build_embedder(settings)
        store = store or build_qdrant_store(embedder.dimensions, settings)
        if tree_paths is None:
            try:
                tree_paths, _truncated = client.get_git_tree(ref.owner, ref.repo, ref.head_sha)
            except GitHubAPIError:
                logger.exception("rag_tree_fetch_failed")
                tree_paths = [item.path for item in snapshot.changed_files]
                errors.append({"component": "rag", "message": "failed to fetch git tree for indexing"})
        paths = select_index_paths(tree_paths, snapshot.changed_files)
        files, fetch_errors = fetch_index_files(
            client,
            owner=ref.owner,
            repo=ref.repo,
            commit_sha=ref.head_sha,
            paths=paths,
        )
        errors.extend(fetch_errors)
        chunks: list[CodeChunk] = []
        for path, text in files.items():
            chunks.extend(chunk_file(path, text, repository=repository, commit_sha=ref.head_sha))
        chunks.extend(_prior_review_chunks(session, repository, ref.head_sha))
        indexed = index_chunks(store, embedder, chunks)
        log_event(logger, "rag_executed", indexed=indexed, files=len(files))
        retrieved = retrieve_for_pull_request(
            store,
            embedder,
            repository=repository,
            changed_files=snapshot.changed_files,
        )
        return retrieved, errors
    except Exception:
        logger.exception("rag_pipeline_failed")
        errors.append({"component": "rag", "message": "repository retrieval failed"})
        return [], errors
