"""Discover pytest targets from a pull-request snapshot. No execution."""

from __future__ import annotations

from pathlib import PurePosixPath

from app.analyzers.language import classify_file
from app.schemas.github import PullRequestSnapshot

MAX_TEST_FILES = 12


def _add(seen: set[str], selected: list[str], path: str) -> None:
    normalized = path.replace("\\", "/").lstrip("/")
    if not normalized or normalized in seen:
        return
    seen.add(normalized)
    selected.append(normalized)


def discover_pytest_files(snapshot: PullRequestSnapshot) -> list[str]:
    """Return repo-relative pytest modules related to the changed files."""

    seen: set[str] = set()
    selected: list[str] = []
    for item in snapshot.changed_files:
        if classify_file(item.path).is_test and item.path.endswith(".py"):
            _add(seen, selected, item.path)
        for related in item.related_paths:
            if classify_file(related).is_test and related.endswith(".py"):
                _add(seen, selected, related)
    return selected[:MAX_TEST_FILES]


def select_test_workspace_paths(snapshot: PullRequestSnapshot) -> list[str]:
    """Tests plus the source files they are likely to import, plus sibling conftest."""

    seen: set[str] = set()
    selected: list[str] = []
    tests = discover_pytest_files(snapshot)
    for path in tests:
        _add(seen, selected, path)
        parent = PurePosixPath(path).parent.as_posix()
        if parent not in {".", ""}:
            _add(seen, selected, f"{parent}/conftest.py")
    for item in snapshot.changed_files:
        if item.path.endswith(".py"):
            _add(seen, selected, item.path)
        for related in item.related_paths:
            if related.endswith(".py"):
                _add(seen, selected, related)
    return selected[:40]
