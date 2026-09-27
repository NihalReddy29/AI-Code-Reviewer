"""Unified diff and GitHub patch parsing tests."""

from app.analyzers.diff import changed_file_from_github, parse_patch, parse_unified_diff
from tests.github_fixtures import FILE_PATCH, FILES_JSON, UNIFIED_DIFF


def test_parse_patch_records_added_and_removed_lines() -> None:
    hunks = parse_patch(FILE_PATCH)
    assert len(hunks) == 1
    assert hunks[0].old_start == 10
    assert hunks[0].new_start == 10
    assert hunks[0].removed_line_numbers == [11]
    assert hunks[0].added_line_numbers == [11]


def test_changed_file_from_github_includes_hunks() -> None:
    changed = changed_file_from_github(FILES_JSON[0])
    assert changed.path == "backend/services/user_service.py"
    assert changed.status == "modified"
    assert changed.hunks[0].added_line_numbers == [11]


def test_parse_unified_diff_extracts_file_and_hunks() -> None:
    files = parse_unified_diff(UNIFIED_DIFF)
    assert len(files) == 1
    assert files[0].path == "backend/services/user_service.py"
    assert files[0].additions == 1
    assert files[0].deletions == 1


def test_parse_unified_diff_handles_new_file() -> None:
    diff = (
        "diff --git a/app.py b/app.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/app.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+print('ok')\n"
        "+print('done')\n"
    )
    files = parse_unified_diff(diff)
    assert files[0].status == "added"
    assert files[0].previous_path is None
    assert files[0].hunks[0].added_line_numbers == [1, 2]


def test_empty_diff_returns_no_files() -> None:
    assert parse_unified_diff("") == []
    assert parse_patch(None) == []
