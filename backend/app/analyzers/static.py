"""Language-aware static analysis orchestration."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from app.analyzers.workspace import materialize_files
from app.core.logging import get_logger, log_event
from app.schemas.static_analysis import StaticAnalysisReport, ToolRun
from app.tools.lint import run_pyright, run_ruff
from app.tools.security import run_bandit, run_semgrep

logger = get_logger(__name__)

Analyzer = Callable[[Path, int], ToolRun]

PYTHON_ANALYZERS: Sequence[tuple[str, Analyzer]] = (
    ("ruff", run_ruff),
    ("pyright", run_pyright),
    ("bandit", run_bandit),
    ("semgrep", run_semgrep),
)


def analyzers_for_languages(languages: set[str]) -> Sequence[tuple[str, Analyzer]]:
    """Return analyzers for detected languages. Additional languages plug in here."""

    selected: list[tuple[str, Analyzer]] = []
    if "python" in languages:
        selected.extend(PYTHON_ANALYZERS)
    return selected


def run_static_analyzers(
    workspace: Path,
    files: dict[str, str],
    *,
    languages: set[str],
    timeout_seconds: int,
    enabled_tools: set[str] | None = None,
) -> StaticAnalysisReport:
    written = materialize_files(workspace, files)
    runs: list[ToolRun] = []
    analyzers = analyzers_for_languages(languages)
    if not analyzers:
        log_event(logger, "static_analysis_skipped", reason="no_supported_language")
        return StaticAnalysisReport(workspace_files=written, runs=runs)
    for name, analyzer in analyzers:
        if enabled_tools is not None and name not in enabled_tools:
            runs.append(ToolRun(tool=name, command=[name], available=False, error="skipped_by_config"))
            log_event(logger, "static_analysis_tool_skipped", tool=name, reason="disabled_by_config")
            continue
        try:
            result = analyzer(workspace, timeout_seconds)
        except Exception:
            logger.exception("static_analysis_tool_failed")
            runs.append(ToolRun(tool=name, command=[name], available=False, error="tool execution failed"))
            continue
        runs.append(result)
        log_event(
            logger,
            "static_analysis_completed",
            tool=name,
            available=result.available,
            exit_code=result.exit_code,
            issue_count=len(result.issues),
        )
    return StaticAnalysisReport(workspace_files=written, runs=runs)
