"""Test discovery, JUnit parsing, and isolated pytest execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analyzers.tests import discover_pytest_files, select_test_workspace_paths
from app.agents.prompts import build_review_user_prompt
from app.schemas.tests import TestRunReport
from app.tools.testing import parse_junit_xml, run_pytest
from tests.test_review_agent import _snapshot


JUNIT = """
<testsuites>
  <testsuite name="pytest" errors="0" failures="1" skipped="0" tests="2">
    <testcase classname="test_mod" name="test_ok" time="0.01" file="test_mod.py"/>
    <testcase classname="test_mod" name="test_bad" time="0.02" file="test_mod.py">
      <failure message="assert 1 == 2">def test_bad():
E       assert 1 == 2</failure>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_discover_related_pytest_files() -> None:
    snapshot = _snapshot()
    snapshot.changed_files[0] = snapshot.changed_files[0].model_copy(
        update={"related_paths": ["backend/tests/test_user_service.py"]}
    )
    discovered = discover_pytest_files(snapshot)
    assert discovered == ["backend/tests/test_user_service.py"]
    workspace = select_test_workspace_paths(snapshot)
    assert "backend/services/user_service.py" in workspace
    assert "backend/tests/conftest.py" in workspace


def test_parse_junit_xml() -> None:
    cases = parse_junit_xml(JUNIT)
    assert [case.outcome for case in cases] == ["passed", "failed"]
    assert cases[1].message is not None
    assert "assert 1 == 2" in cases[1].message


def test_run_pytest_records_pass_and_fail(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text(
        "def test_ok():\n    assert True\n\ndef test_bad():\n    assert 1 == 2\n",
        encoding="utf-8",
    )
    report = run_pytest(tmp_path, ["test_sample.py"], 20)
    if not report.available:
        pytest.skip("pytest is not installed")
    assert report.passed >= 1
    assert report.failed >= 1
    assert any(case.outcome == "failed" for case in report.cases)


def test_prompt_includes_test_failures() -> None:
    report = TestRunReport(
        discovered=["backend/tests/test_user_service.py"],
        executed=["backend/tests/test_user_service.py"],
        passed=0,
        failed=1,
        cases=parse_junit_xml(JUNIT),
    )
    prompt = build_review_user_prompt(_snapshot(), None, test_results=report)
    assert "Test results" in prompt
    assert "test_bad" in prompt
