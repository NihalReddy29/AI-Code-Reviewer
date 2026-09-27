"""Repository layout and changed-file analysis tests. No GitHub calls."""

from app.analyzers.diff import changed_file_from_github
from app.analyzers.repository import analyze_changed_files, analyze_repository, related_test_paths
from tests.github_fixtures import FILES_JSON, TREE_PATHS


def test_analyze_repository_detects_python_layout() -> None:
    layout = analyze_repository(TREE_PATHS + ["node_modules/left-pad/index.js"])
    assert layout.primary_language == "python"
    assert "python" in layout.project_types
    assert "backend" in layout.source_roots
    assert "backend/tests" in layout.test_directories
    assert layout.has_github_actions is True
    assert layout.skipped_vendor_files == 1


def test_changed_file_analysis_finds_related_tests_and_language() -> None:
    changed = [changed_file_from_github(FILES_JSON[0])]
    enriched = analyze_changed_files(changed, TREE_PATHS)
    item = enriched[0]
    assert item.language == "python"
    assert item.kind == "source"
    assert item.is_test is False
    assert "backend/tests/test_user_service.py" in item.related_paths
    assert "sql" in item.sensitive_areas
    assert item.hunk_count == 1


def test_related_test_paths_uses_tree() -> None:
    tree = set(TREE_PATHS)
    related = related_test_paths("backend/services/user_service.py", tree)
    assert "backend/tests/test_user_service.py" in related
