"""Bandit and Semgrep runners. Prefer these over the LLM for security detection."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.logging import redact
from app.schemas.static_analysis import ToolIssue, ToolRun
from app.tools.process import ToolNotFoundError, ToolRefusedError, run_allowlisted

SEMGREP_RULES = Path(__file__).resolve().parent / "rules" / "python.yml"


def _relative_file(workspace: Path, filename: str) -> str:
    path = Path(filename)
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return path.as_posix().lstrip("/\\")


def parse_bandit_json(payload: str, *, workspace: Path) -> list[ToolIssue]:
    if not payload.strip():
        return []
    data = json.loads(payload)
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []
    issues: list[ToolIssue] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        issues.append(
            ToolIssue(
                tool="bandit",
                file=_relative_file(workspace, str(item.get("filename") or "")),
                line=item.get("line_number"),
                rule=item.get("test_id"),
                message=redact(str(item.get("issue_text") or "")),
                severity=str(item.get("issue_severity") or "") or None,
            )
        )
    return issues


def parse_semgrep_json(payload: str, *, workspace: Path) -> list[ToolIssue]:
    if not payload.strip():
        return []
    data = json.loads(payload)
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []
    issues: list[ToolIssue] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        start = item.get("start") or {}
        extra = item.get("extra") or {}
        issues.append(
            ToolIssue(
                tool="semgrep",
                file=_relative_file(workspace, str(item.get("path") or "")),
                line=start.get("line"),
                column=start.get("col"),
                rule=item.get("check_id"),
                message=redact(str(extra.get("message") or item.get("check_id") or "")),
                severity=str(extra.get("severity") or "") or None,
            )
        )
    return issues


def run_bandit(workspace: Path, timeout_seconds: int) -> ToolRun:
    try:
        completed = run_allowlisted(
            "bandit",
            ["-r", ".", "-f", "json", "-q"],
            cwd=workspace,
            timeout_seconds=timeout_seconds,
        )
    except ToolNotFoundError:
        return ToolRun(tool="bandit", command=["bandit"], available=False, error="bandit is not installed")
    except ToolRefusedError as exc:
        return ToolRun(tool="bandit", command=["bandit"], available=False, error=str(exc))
    issues: list[ToolIssue] = []
    try:
        issues = parse_bandit_json(completed.stdout, workspace=workspace)
    except json.JSONDecodeError:
        pass
    return ToolRun(
        tool="bandit",
        command=["bandit", "-r", ".", "-f", "json", "-q"],
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        issues=issues,
        error="timeout" if completed.returncode == -1 else None,
    )


def run_semgrep(workspace: Path, timeout_seconds: int) -> ToolRun:
    if not SEMGREP_RULES.is_file():
        return ToolRun(tool="semgrep", command=["semgrep"], available=False, error="semgrep rules file is missing")
    try:
        completed = run_allowlisted(
            "semgrep",
            ["--json", "--quiet", "--metrics=off", "--config", str(SEMGREP_RULES), "."],
            cwd=workspace,
            timeout_seconds=timeout_seconds,
        )
    except ToolNotFoundError:
        return ToolRun(tool="semgrep", command=["semgrep"], available=False, error="semgrep is not installed")
    except ToolRefusedError as exc:
        return ToolRun(tool="semgrep", command=["semgrep"], available=False, error=str(exc))
    issues: list[ToolIssue] = []
    try:
        issues = parse_semgrep_json(completed.stdout, workspace=workspace)
    except json.JSONDecodeError:
        pass
    return ToolRun(
        tool="semgrep",
        command=["semgrep", "--json", "--config", str(SEMGREP_RULES), "."],
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        issues=issues,
        error="timeout" if completed.returncode == -1 else None,
    )
