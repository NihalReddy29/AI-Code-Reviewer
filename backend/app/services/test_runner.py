"""Fetch PR files and run related tests off the host working tree."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.analyzers.tests import discover_pytest_files, select_test_workspace_paths
from app.analyzers.workspace import materialize_files
from app.core.config import get_settings
from app.core.logging import get_logger, log_event
from app.schemas.github import PullRequestSnapshot
from app.schemas.tests import TestRunReport
from app.services.rag import fetch_index_files
from app.tools.github import GitHubClient
from app.tools.testing import run_pytest

logger = get_logger(__name__)


def run_pull_request_tests(
    client: GitHubClient,
    snapshot: PullRequestSnapshot,
    *,
    timeout_seconds: int | None = None,
) -> tuple[TestRunReport, list[dict[str, str]]]:
    """Discover related pytest files, copy them to a temp dir, and execute pytest."""

    errors: list[dict[str, str]] = []
    discovered = discover_pytest_files(snapshot)
    if not discovered:
        log_event(logger, "tests_skipped", reason="no_related_tests")
        return TestRunReport(skipped=True, skip_reason="no related pytest files"), errors

    ref = snapshot.pull_request
    files, fetch_errors = fetch_index_files(
        client,
        owner=ref.owner,
        repo=ref.repo,
        commit_sha=ref.head_sha,
        paths=select_test_workspace_paths(snapshot),
    )
    errors.extend(
        {"component": "test_agent", "message": item.get("message", "file fetch failed")}
        for item in fetch_errors
    )
    present = [path for path in discovered if path in files]
    if not present:
        return (
            TestRunReport(discovered=discovered, skipped=True, skip_reason="related tests could not be fetched"),
            errors,
        )

    settings = get_settings()
    timeout = timeout_seconds if timeout_seconds is not None else min(settings.tool_timeout_seconds, 60)
    if settings.environment == "test":
        timeout = min(timeout, 25)
    try:
        with tempfile.TemporaryDirectory(prefix="ai-code-reviewer-tests-") as tmp:
            root = Path(tmp)
            materialize_files(root, files)
            report = run_pytest(root, present, timeout)
        log_event(
            logger,
            "tests_completed",
            passed=report.passed,
            failed=report.failed,
            discovered=len(report.discovered),
        )
        return report, errors
    except Exception:
        logger.exception("test_pipeline_failed")
        errors.append({"component": "test_agent", "message": "test execution failed"})
        return TestRunReport(discovered=discovered, error="test execution failed"), errors
