"""Static analysis parsers, path confinement, and ingest wiring. No GitHub/LLM APIs."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analyzers.static import analyzers_for_languages
from app.analyzers.workspace import UnsafePathError, confined_path, materialize_files
from app.agents.prompts import build_review_user_prompt
from app.schemas.static_analysis import StaticAnalysisReport, ToolIssue, ToolRun
from app.tools.lint import parse_pyright_json, parse_ruff_json, run_ruff
from app.tools.process import ToolRefusedError, resolve_tool
from app.tools.security import parse_bandit_json, parse_semgrep_json, run_bandit
from sqlalchemy.orm import Session

from app.database.models import ReviewRun
from app.services.ingestion import ingest_pull_request
from tests.github_fixtures import mock_github_client
from tests.test_review_agent import _snapshot


RUFF_JSON = """
[
  {
    "filename": "unused.py",
    "code": "F401",
    "message": "unused import",
    "location": {"row": 1, "column": 8}
  }
]
"""

PYRIGHT_JSON = """
{
  "generalDiagnostics": [
    {
      "file": "types.py",
      "message": "Undefined variable",
      "severity": "error",
      "rule": "reportUndefinedVariable",
      "range": {"start": {"line": 2, "character": 4}}
    }
  ]
}
"""

BANDIT_JSON = """
{
  "results": [
    {
      "filename": "sec.py",
      "line_number": 2,
      "test_id": "B301",
      "issue_text": "pickle used",
      "issue_severity": "HIGH"
    }
  ]
}
"""

SEMGREP_JSON = """
{
  "results": [
    {
      "check_id": "python.lang.security.audit.pickle-load",
      "path": "sec.py",
      "start": {"line": 2, "col": 1},
      "extra": {"message": "Unsafe deserialization via pickle.", "severity": "ERROR"}
    }
  ]
}
"""


def test_confined_path_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        confined_path(tmp_path, "../secret.py")
    with pytest.raises(UnsafePathError):
        confined_path(tmp_path, "/etc/passwd")
    with pytest.raises(UnsafePathError):
        confined_path(tmp_path, "pkg/../../outside.py")


def test_materialize_writes_nested_python(tmp_path: Path) -> None:
    written = materialize_files(tmp_path, {"pkg/mod.py": "x = 1\n", ".env": "SECRET=1\n"})
    assert written == ["pkg/mod.py"]
    assert (tmp_path / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not (tmp_path / ".env").exists()


def test_resolve_tool_refuses_non_allowlisted() -> None:
    with pytest.raises(ToolRefusedError):
        resolve_tool("python")
    with pytest.raises(ToolRefusedError):
        resolve_tool(r"C:\Windows\System32\cmd.exe")


def test_parse_tool_json(tmp_path: Path) -> None:
    ruff_issues = parse_ruff_json(RUFF_JSON, workspace=tmp_path)
    assert ruff_issues[0].tool == "ruff"
    assert ruff_issues[0].rule == "F401"
    assert ruff_issues[0].line == 1
    pyright_issues = parse_pyright_json(PYRIGHT_JSON, workspace=tmp_path)
    assert pyright_issues[0].line == 3
    assert pyright_issues[0].rule == "reportUndefinedVariable"
    bandit_issues = parse_bandit_json(BANDIT_JSON, workspace=tmp_path)
    assert bandit_issues[0].rule == "B301"
    semgrep_issues = parse_semgrep_json(SEMGREP_JSON, workspace=tmp_path)
    assert "pickle" in semgrep_issues[0].message.lower()


def test_python_analyzer_registry() -> None:
    names = [name for name, _ in analyzers_for_languages({"python"})]
    assert names == ["ruff", "pyright", "bandit", "semgrep"]
    assert analyzers_for_languages({"javascript"}) == []


def test_ruff_detects_unused_import(tmp_path: Path) -> None:
    (tmp_path / "unused.py").write_text("import os\n", encoding="utf-8")
    result = run_ruff(tmp_path, 20)
    if not result.available:
        pytest.skip("ruff is not installed")
    assert any(issue.rule == "F401" for issue in result.issues)


def test_bandit_detects_pickle(tmp_path: Path) -> None:
    (tmp_path / "sec.py").write_text("import pickle\npickle.loads(b'')\n", encoding="utf-8")
    result = run_bandit(tmp_path, 20)
    if not result.available:
        pytest.skip("bandit is not installed")
    assert any(issue.rule and issue.rule.startswith("B") for issue in result.issues)


def test_missing_tool_is_recorded_not_raised(tmp_path: Path, monkeypatch) -> None:
    from app.tools import lint as lint_mod
    from app.tools.process import ToolNotFoundError

    def boom(*args, **kwargs):
        raise ToolNotFoundError("pyright")

    monkeypatch.setattr(lint_mod, "run_allowlisted", boom)
    from app.tools.lint import run_pyright

    result = run_pyright(tmp_path, 5)
    assert result.available is False
    assert result.issues == []


def test_prompt_includes_static_analysis() -> None:
    report = StaticAnalysisReport(
        workspace_files=["backend/services/user_service.py"],
        runs=[
            ToolRun(
                tool="ruff",
                command=["ruff"],
                available=True,
                exit_code=1,
                issues=[
                    ToolIssue(
                        tool="ruff",
                        file="backend/services/user_service.py",
                        line=1,
                        rule="F401",
                        message="unused import",
                    )
                ],
            )
        ],
    )
    prompt = build_review_user_prompt(_snapshot(), None, static_analysis=report)
    assert "Static analysis findings" in prompt
    assert "F401" in prompt


def test_ingest_stores_static_analysis(db_session: Session) -> None:
    result = ingest_pull_request(
        db_session,
        mock_github_client(),
        owner="acme",
        repo="api",
        number=12,
        trigger="manual",
    )
    stored = db_session.get(ReviewRun, result.review_run_id)
    assert stored is not None
    assert stored.static_analysis_results is not None
    tools = [run["tool"] for run in stored.static_analysis_results["runs"]]
    assert "ruff" in tools
    assert "bandit" in tools
    assert stored.static_analysis_results["workspace_files"]
