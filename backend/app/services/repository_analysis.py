"""Load a commit tree and produce repository/changed-file analysis."""

from __future__ import annotations

from app.analyzers.dependencies import analyze_dependencies, find_manifest_paths
from app.analyzers.repository import analyze_changed_files, analyze_repository
from app.core.logging import get_logger, log_event
from app.schemas.analysis import RepositoryContextResponse
from app.schemas.github import ChangedFile
from app.tools.github import GitHubAPIError, GitHubClient

logger = get_logger(__name__)


def analyze_pull_request_repository(
    client: GitHubClient,
    *,
    owner: str,
    repo: str,
    commit_sha: str,
    changed_files: list[ChangedFile],
) -> tuple[list[ChangedFile], RepositoryContextResponse, list[dict[str, str]]]:
    """Fetch the git tree, classify files, and enrich the PR diff.

    Tree fetch failures are recorded and the diff is still classified from paths.
    """

    errors: list[dict[str, str]] = []
    paths: list[str] = []
    truncated = False
    try:
        paths, truncated = client.get_git_tree(owner, repo, commit_sha)
    except GitHubAPIError as exc:
        log_event(
            logger,
            "repository_tree_fetch_failed",
            error_type=type(exc).__name__,
            status_code=exc.status_code,
        )
        errors.append({"component": "repository_analyzer", "message": "failed to fetch git tree"})

    layout = analyze_repository(paths, truncated=truncated)
    manifest_contents: dict[str, str] = {}
    for path in find_manifest_paths(paths):
        try:
            text = client.get_text_file(owner, repo, path, ref=commit_sha)
        except GitHubAPIError:
            logger.exception("manifest_fetch_failed")
            errors.append({"component": "dependency_analyzer", "message": f"failed to fetch {path}"})
            continue
        if text is not None:
            manifest_contents[path] = text

    dependencies = analyze_dependencies(paths, manifest_contents)
    enriched = analyze_changed_files(changed_files, paths)
    log_event(
        logger,
        "repository_analyzed",
        primary_language=layout.primary_language,
        project_types=layout.project_types,
        changed_files=len(enriched),
    )
    context = RepositoryContextResponse(
        commit_sha=commit_sha,
        truncated=layout.truncated,
        primary_language=layout.primary_language,
        languages=layout.languages,
        project_types=layout.project_types,
        package_managers=dependencies.package_managers,
        test_frameworks=dependencies.test_frameworks,
        source_roots=layout.source_roots,
        test_directories=layout.test_directories,
        python_packages=dependencies.python_packages,
        node_packages=dependencies.node_packages,
        file_count=layout.file_count,
    )
    return enriched, context, errors
