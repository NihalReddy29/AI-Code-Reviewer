"""Run pytest in an isolated workspace. Does not use a shell or repo install scripts."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

from app.core.logging import redact
from app.schemas.tests import TestCaseResult, TestRunReport
from app.tools.process import ToolNotFoundError, ToolRefusedError, run_allowlisted

JUNIT_FILENAME = ".ai-code-reviewer-junit.xml"
_KEEP_ENV = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "SYSTEMDRIVE",
}


def isolated_env(workspace: Path) -> dict[str, str]:
    """PATH-like variables only. Secrets from the API process are not inherited."""

    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.upper() in _KEEP_ENV:
            env[key] = value
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONPATH"] = str(workspace.resolve())
    return env


def parse_junit_xml(payload: str) -> list[TestCaseResult]:
    if not payload.strip():
        return []
    root = ET.fromstring(payload)
    cases: list[TestCaseResult] = []
    for node in root.iter("testcase"):
        classname = node.attrib.get("classname") or ""
        name = node.attrib.get("name") or ""
        nodeid = f"{classname}::{name}".strip(":")
        file_path = node.attrib.get("file") or (classname.replace(".", "/") + ".py" if classname else None)
        duration = node.attrib.get("time")
        failure = node.find("failure")
        error = node.find("error")
        skipped = node.find("skipped")
        if failure is not None:
            outcome = "failed"
            message = failure.attrib.get("message") or (failure.text or "")
        elif error is not None:
            outcome = "error"
            message = error.attrib.get("message") or (error.text or "")
        elif skipped is not None:
            outcome = "skipped"
            message = skipped.attrib.get("message") or None
        else:
            outcome = "passed"
            message = None
        cases.append(
            TestCaseResult(
                nodeid=nodeid,
                file=file_path,
                outcome=outcome,
                message=redact(message) if message else None,
                duration_seconds=float(duration) if duration else None,
            )
        )
    return cases


def run_pytest(workspace: Path, test_files: list[str], timeout_seconds: int) -> TestRunReport:
    if not test_files:
        return TestRunReport(skipped=True, skip_reason="no related pytest files", available=True)
    try:
        completed = run_allowlisted(
            "pytest",
            [
                "-o",
                "addopts=",
                "--rootdir=.",
                "-q",
                "--tb=short",
                f"--junitxml={JUNIT_FILENAME}",
                "--",
                *test_files,
            ],
            cwd=workspace,
            timeout_seconds=timeout_seconds,
            env=isolated_env(workspace),
        )
    except ToolNotFoundError:
        return TestRunReport(available=False, discovered=test_files, error="pytest is not installed")
    except ToolRefusedError as exc:
        return TestRunReport(available=False, discovered=test_files, error=str(exc))

    junit_path = workspace / JUNIT_FILENAME
    cases: list[TestCaseResult] = []
    parse_error = None
    if junit_path.is_file():
        try:
            cases = parse_junit_xml(junit_path.read_text(encoding="utf-8", errors="replace"))
        except ET.ParseError:
            parse_error = "invalid junit xml"
    passed = sum(1 for case in cases if case.outcome == "passed")
    failed = sum(1 for case in cases if case.outcome == "failed")
    errors = sum(1 for case in cases if case.outcome == "error")
    skipped_cases = sum(1 for case in cases if case.outcome == "skipped")
    timeout = completed.returncode == -1
    return TestRunReport(
        discovered=test_files,
        executed=test_files,
        available=True,
        exit_code=completed.returncode,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped_cases=skipped_cases,
        cases=cases,
        stdout=completed.stdout,
        stderr=completed.stderr,
        error="timeout" if timeout else parse_error,
    )
