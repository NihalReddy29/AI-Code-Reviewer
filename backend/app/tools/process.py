"""Allowlisted subprocess runner for analysis tools. Never uses a shell."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from app.core.logging import get_logger, log_event

logger = get_logger(__name__)

ALLOWED_TOOLS = frozenset({"ruff", "bandit", "pyright", "semgrep", "pytest"})
MAX_CAPTURE_CHARS = 8_000


class ToolNotFoundError(RuntimeError):
    pass


class ToolRefusedError(RuntimeError):
    pass


def resolve_tool(name: str) -> Path:
    """Resolve an analysis binary. Unknown names are refused even if on PATH."""

    if "/" in name or "\\" in name:
        raise ToolRefusedError(f"tool is not allowlisted: {name}")
    stem = Path(name).stem.lower()
    if stem not in ALLOWED_TOOLS:
        raise ToolRefusedError(f"tool is not allowlisted: {name}")
    found = shutil.which(name)
    if found is None:
        scripts = Path(sys.executable).resolve().parent
        for filename in ((f"{name}.exe", name) if sys.platform == "win32" else (name,)):
            candidate = scripts / filename
            if candidate.is_file():
                found = str(candidate)
                break
    if found is None:
        raise ToolNotFoundError(name)
    resolved = Path(found)
    if resolved.stem.lower() not in ALLOWED_TOOLS:
        raise ToolRefusedError(f"resolved binary is not allowlisted: {resolved.name}")
    return resolved


def run_allowlisted(
    name: str,
    args: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `name` with explicit args. `cwd` must already exist. No `shell=True`."""

    executable = resolve_tool(name)
    command = [str(executable), *args]
    log_event(logger, "allowlisted_command", tool=name, cwd=str(cwd))
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "")[:MAX_CAPTURE_CHARS] if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "")[:MAX_CAPTURE_CHARS] if isinstance(exc.stderr, str) else ""
        return subprocess.CompletedProcess(command, -1, stdout, stderr or "timeout")
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        (completed.stdout or "")[:MAX_CAPTURE_CHARS],
        (completed.stderr or "")[:MAX_CAPTURE_CHARS],
    )
