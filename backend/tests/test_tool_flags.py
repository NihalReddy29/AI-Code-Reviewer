from types import SimpleNamespace

from app.agents.nodes import build_nodes
from app.schemas.repo_config import RepoConfig, ToolsConfig


def _nodes():
    return build_nodes(SimpleNamespace(session=None, client=None, llm=None))


def test_pytest_disabled_skips_tests():
    config = RepoConfig(tools=ToolsConfig(pytest=False))
    out = _nodes()["run_tests"]({"snapshot": None, "repo_config": config})
    assert out["test_results"]["skipped"] is True


def test_all_static_tools_off_skips_static_analysis():
    tools = ToolsConfig(ruff=False, pyright=False, bandit=False, semgrep=False)
    out = _nodes()["run_static_analysis"]({"snapshot": None, "repo_config": RepoConfig(tools=tools)})
    assert len(out["static_analysis"].issues) == 0