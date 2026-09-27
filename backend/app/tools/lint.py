"""Ruff and Pyright runners. Parse JSON into the common ToolIssue format."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.logging import redact
from app.schemas.static_analysis import ToolIssue, ToolRun
from app.tools.process import ToolNotFoundError, ToolRefusedError, run_allowlisted


def _relative_file(workspace: Path, filename: str) -> str:
    path = Path(filename)
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return path.as_posix().lstrip("/\\")


def parse_ruff_json(payload: str, *, workspace: Path) -> list[ToolIssue]:
    if not payload.strip():
        return []
    data = json.loads(payload)
    if not isinstance(data, list):
        return []
    issues: list[ToolIssue] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        location = item.get("location") or {}
        issues.append(
            ToolIssue(
                tool="ruff",
                file=_relative_file(workspace, str(item.get("filename") or "")),
                line=location.get("row"),
                column=location.get("column"),
                rule=item.get("code"),
                message=redact(str(item.get("message") or "")),
            )
        )
    return issues


def parse_pyright_json(payload: str, *, workspace: Path) -> list[ToolIssue]:
    if not payload.strip():
        return []
    data = json.loads(payload)
    diagnostics = data.get("generalDiagnostics") if isinstance(data, dict) else None
    if not isinstance(diagnostics, list):
        return []
    issues: list[ToolIssue] = []
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        start = ((item.get("range") or {}).get("start") or {})
        line = start.get("line")
        issues.append(
            ToolIssue(
                tool="pyright",
                file=_relative_file(workspace, str(item.get("file") or "")),
                line=(int(line) + 1) if isinstance(line, int) else None,
                column=(int(start["character"]) + 1) if isinstance(start.get("character"), int) else None,
                rule=item.get("rule"),
                message=redact(str(item.get("message") or "")),
                severity=str(item.get("severity") or "") or None,
            )
        )
    return issues


def run_ruff(workspace: Path, timeout_seconds: int) -> ToolRun:
    try:
        completed = run_allowlisted(
            "ruff",
            ["check", "--output-format", "json", "--no-cache", "."],
            cwd=workspace,
            timeout_seconds=timeout_seconds,
        )
    except ToolNotFoundError:
        return ToolRun(tool="ruff", command=["ruff"], available=False, error="ruff is not installed")
    except ToolRefusedError as exc:
        return ToolRun(tool="ruff", command=["ruff"], available=False, error=str(exc))
    issues: list[ToolIssue] = []
    error = None
    try:
        issues = parse_ruff_json(completed.stdout, workspace=workspace)
    except json.JSONDecodeError:
        error = "invalid json output"
    if completed.returncode == -1:
        error = "timeout"
    return ToolRun(
        tool="ruff",
        command=["ruff", "check", "--output-format", "json", "."],
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        issues=issues,
        error=error,
    )


def run_pyright(workspace: Path, timeout_seconds: int) -> ToolRun:
    try:
        completed = run_allowlisted(
            "pyright",
            ["--outputjson", "."],
            cwd=workspace,
            timeout_seconds=timeout_seconds,
        )
    except ToolNotFoundError:
        return ToolRun(tool="pyright", command=["pyright"], available=False, error="pyright is not installed")
    except ToolRefusedError as exc:
        return ToolRun(tool="pyright", command=["pyright"], available=False, error=str(exc))
    issues: list[ToolIssue] = []
    try:
        issues = parse_pyright_json(completed.stdout, workspace=workspace)
    except json.JSONDecodeError:
        pass
    return ToolRun(
        tool="pyright",
        command=["pyright", "--outputjson", "."],
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        issues=issues,
        error="timeout" if completed.returncode == -1 else None,
    )
