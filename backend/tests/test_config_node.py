import hashlib
from types import SimpleNamespace

from app.agents.config_node import make_load_config_node


class FakeClient:
    def __init__(self, text):
        self.text = text

    def get_text_file(self, owner, repo, path, *, ref, max_bytes):
        return self.text


def _state():
    pr = SimpleNamespace(base_sha="abc123", target_branch="main")
    return {"owner": "o", "repo": "r", "snapshot": SimpleNamespace(pull_request=pr)}


def test_node_loads_config():
    raw_yaml = "tools:\n  pytest: false\n"
    deps = SimpleNamespace(client=FakeClient(raw_yaml))
    out = make_load_config_node(deps)(_state())
    assert out["repo_config"].tools.pytest is False
    assert out["config_warnings"] == []
    assert out["resolved_config"] is not None
    assert out["resolved_config"]["tools"]["pytest"] is False
    expected_sha = hashlib.sha256(raw_yaml.encode("utf-8")).hexdigest()
    assert out["config_sha"] == expected_sha


def test_node_missing_file_uses_defaults():
    deps = SimpleNamespace(client=FakeClient(None))
    out = make_load_config_node(deps)(_state())
    assert out["repo_config"].tools.pytest is True
    assert out["resolved_config"] is None
    assert out["config_sha"] is None