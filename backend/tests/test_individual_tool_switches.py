"""Phase 1: individual static-analysis tool switches. No real subprocesses."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.analyzers.static import run_static_analyzers
from app.schemas.static_analysis import StaticAnalysisReport, ToolRun


def _fake_run(name: str) -> ToolRun:
    return ToolRun(tool=name, command=[name], available=True, exit_code=0)


def _patched_analyzers(tmp_path, enabled_tools):
    """Run run_static_analyzers with mocked tool runners. Returns the report."""
    fake_runs = {}

    def make_runner(name):
        def runner(workspace, timeout):
            fake_runs[name] = True
            return _fake_run(name)

        return runner

    from app.analyzers import static as static_mod

    originals = dict(static_mod.PYTHON_ANALYZERS)

    patched = [
        ("ruff", make_runner("ruff")),
        ("pyright", make_runner("pyright")),
        ("bandit", make_runner("bandit")),
        ("semgrep", make_runner("semgrep")),
    ]

    with patch.object(static_mod, "PYTHON_ANALYZERS", patched):
        report = run_static_analyzers(
            tmp_path,
            {"sample.py": "x = 1\n"},
            languages={"python"},
            timeout_seconds=5,
            enabled_tools=enabled_tools,
        )

    return report, fake_runs


def test_ruff_only_skips_others(tmp_path):
    report, ran = _patched_analyzers(tmp_path, {"ruff"})
    assert ran.get("ruff") is True
    assert "pyright" not in ran
    assert "bandit" not in ran
    assert "semgrep" not in ran
    skipped = [r for r in report.runs if r.error == "skipped_by_config"]
    assert len(skipped) == 3


def test_bandit_semgrep_enabled(tmp_path):
    report, ran = _patched_analyzers(tmp_path, {"bandit", "semgrep"})
    assert ran.get("bandit") is True
    assert ran.get("semgrep") is True
    assert "ruff" not in ran
    skipped = [r for r in report.runs if r.error == "skipped_by_config"]
    assert len(skipped) == 2


def test_none_enabled_tools_runs_all(tmp_path):
    """None means no filtering — all tools run."""
    report, ran = _patched_analyzers(tmp_path, None)
    assert len(ran) == 4
    skipped = [r for r in report.runs if r.error == "skipped_by_config"]
    assert len(skipped) == 0


def test_skipped_tool_is_not_available(tmp_path):
    """A tool disabled by config is recorded as available=False."""
    report, _ = _patched_analyzers(tmp_path, {"ruff"})
    for run in report.runs:
        if run.tool != "ruff":
            assert run.available is False
            assert run.error == "skipped_by_config"


def test_nodes_run_static_analysis_passes_enabled_tools(monkeypatch):
    """nodes.run_static_analysis builds the correct enabled set from repo_config."""
    from types import SimpleNamespace

    import app.agents.nodes as nodes_mod
    from app.agents.nodes import build_nodes
    from app.schemas.repo_config import RepoConfig, ToolsConfig

    captured = {}

    def fake_run(client, snapshot, *, enabled_tools=None, timeout_seconds=None):
        captured["enabled_tools"] = enabled_tools
        return StaticAnalysisReport(), []

    monkeypatch.setattr(nodes_mod, "run_pull_request_static_analysis", fake_run)

    nodes = build_nodes(SimpleNamespace(session=None, client=None, llm=None))
    config = RepoConfig(tools=ToolsConfig(ruff=True, pyright=False, bandit=True, semgrep=False))
    nodes["run_static_analysis"]({"snapshot": None, "repo_config": config})

    assert captured["enabled_tools"] == {"ruff", "bandit"}
