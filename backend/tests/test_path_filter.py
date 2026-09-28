from types import SimpleNamespace

from app.agents.config_node import make_load_config_node
from app.analyzers.path_filter import build_ignore_spec, filter_diff, filter_snapshot

DIFF = (
    "diff --git a/src/app.py b/src/app.py\n+print('keep')\n"
    "diff --git a/docs/guide.md b/docs/guide.md\n+ignored text\n"
)


def test_no_patterns_means_no_spec():
    assert build_ignore_spec([]) is None


def test_docs_are_ignored_source_is_kept():
    spec = build_ignore_spec(["docs/**"])
    assert spec.match_file("docs/guide.md")
    assert not spec.match_file("src/app.py")


def test_lock_files_match_at_any_depth():
    spec = build_ignore_spec(["*.lock"])
    assert spec.match_file("poetry.lock")
    assert spec.match_file("frontend/yarn.lock")


def test_filter_diff_drops_ignored_sections():
    spec = build_ignore_spec(["docs/**"])
    out = filter_diff(DIFF, spec)
    assert "keep" in out
    assert "ignored text" not in out


class FakeSnapshot:
    def __init__(self, files, diff, pull_request=None):
        self.changed_files = files
        self.diff = diff
        self.pull_request = pull_request

    def model_copy(self, update):
        copy = FakeSnapshot(self.changed_files, self.diff, self.pull_request)
        for key, value in update.items():
            setattr(copy, key, value)
        return copy


def test_filter_snapshot_removes_files_and_diff():
    files = [SimpleNamespace(path="src/app.py"), SimpleNamespace(path="docs/guide.md")]
    updated, removed = filter_snapshot(FakeSnapshot(files, DIFF), build_ignore_spec(["docs/**"]))
    assert removed == 1
    assert [f.path for f in updated.changed_files] == ["src/app.py"]
    assert "ignored text" not in updated.diff


class FakeClient:
    def get_text_file(self, owner, repo, path, *, ref, max_bytes):
        return "paths:\n  ignore:\n    - 'docs/**'\n"


def test_node_applies_ignore_from_config():
    files = [SimpleNamespace(path="src/app.py"), SimpleNamespace(path="docs/guide.md")]
    pr = SimpleNamespace(base_sha="abc", target_branch="main")
    state = {"owner": "o", "repo": "r", "snapshot": FakeSnapshot(files, DIFF, pr)}
    out = make_load_config_node(SimpleNamespace(client=FakeClient()))(state)
    assert [f.path for f in out["snapshot"].changed_files] == ["src/app.py"]