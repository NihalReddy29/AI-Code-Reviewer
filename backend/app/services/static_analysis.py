"""Fetch PR files and run deterministic static analyzers off the host working tree."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.analyzers.language import detect_language
from app.analyzers.static import run_static_analyzers
from app.core.config import get_settings
from app.core.logging import get_logger, log_event
from app.schemas.github import PullRequestSnapshot
from app.schemas.static_analysis import StaticAnalysisReport
from app.services.rag import fetch_index_files
from app.tools.github import GitHubClient

logger = get_logger(__name__)

MAX_STATIC_FILES = 40


def select_static_analysis_paths(snapshot: PullRequestSnapshot) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        normalized = path.replace("\\", "/").lstrip("/")
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        selected.append(normalized)

    for item in snapshot.changed_files:
        add(item.path)
        for related in item.related_paths:
            add(related)
    return selected[:MAX_STATIC_FILES]


def run_pull_request_static_analysis(
    client: GitHubClient,
    snapshot: PullRequestSnapshot,
    *,
    timeout_seconds: int | None = None,
) -> tuple[StaticAnalysisReport, list[dict[str, str]]]:
    """Analyze a temp copy of PR files. Does not execute repository code."""

    errors: list[dict[str, str]] = []
    ref = snapshot.pull_request
    paths = select_static_analysis_paths(snapshot)
    files, fetch_errors = fetch_index_files(
        client,
        owner=ref.owner,
        repo=ref.repo,
        commit_sha=ref.head_sha,
        paths=paths,
    )
    errors.extend(
        {"component": "static_analysis", "message": item.get("message", "file fetch failed")}
        for item in fetch_errors
    )
    languages = {detect_language(path) for path in files if detect_language(path)}
    settings = get_settings()
    timeout = timeout_seconds if timeout_seconds is not None else min(settings.tool_timeout_seconds, 60)
    if settings.environment == "test":
        timeout = min(timeout, 20)
    try:
        with tempfile.TemporaryDirectory(prefix="ai-code-reviewer-static-") as tmp:
            report = run_static_analyzers(Path(tmp), files, languages=languages, timeout_seconds=timeout)
        log_event(logger, "static_analysis_completed", issue_count=len(report.issues), tools=len(report.runs))
        return report, errors
    except Exception:
        logger.exception("static_analysis_pipeline_failed")
        errors.append({"component": "static_analysis", "message": "static analysis failed"})
        return StaticAnalysisReport(), errors
