"""Prompt construction for structured PR review. Secrets are redacted."""

from __future__ import annotations

from app.core.logging import redact
from app.schemas.analysis import RepositoryContextResponse
from app.schemas.findings import FindingCategory, FindingSeverity
from app.schemas.github import ChangedFile, PullRequestSnapshot
from app.schemas.rag import RetrievedChunk
from app.schemas.static_analysis import StaticAnalysisReport, ToolIssue
from app.schemas.tests import TestRunReport

SYSTEM_PROMPT = """You are a senior code reviewer for GitHub pull requests.
Report only issues that are supported by the provided diff, repository context, and static analysis.
Do not invent files, line numbers, or APIs that are not in the input.
Do not reproduce secrets; refer to them as redacted if they appear in the diff.
Use only these categories: {categories}.
Use only these severities: {severities}.
Prefer fewer, high-value findings over style nits.
Each finding must include concrete evidence quoted from the diff, a cited static-analysis issue, or a test failure.
Static analysis (Ruff, Pyright, Bandit, Semgrep) and pytest are independent of you. Treat confirmed tool and test results as evidence; do not dismiss them without justification. Do not replace those tools.
""".format(
    categories=", ".join(item.value for item in FindingCategory),
    severities=", ".join(item.value for item in FindingSeverity),
)

SECURITY_SYSTEM_PROMPT = (
    SYSTEM_PROMPT
    + "\nThis pass focuses on SECURITY and BUG findings (injection, auth, secrets, crashes). "
    "Omit pure style or naming nits."
)
QUALITY_SYSTEM_PROMPT = (
    SYSTEM_PROMPT
    + "\nThis pass focuses on CODE_QUALITY, MAINTAINABILITY, PERFORMANCE, TESTING, ERROR_HANDLING, "
    "ARCHITECTURE, and PROJECT_CONVENTION. Do not repeat a security issue unless you have new evidence."
)

_SKIP_PROMPT_FILES = {".env", ".env.local", ".pem", ".key"}
MAX_PATCH_CHARS = 8_000
MAX_PROMPT_CHARS = 60_000
MAX_RETRIEVED_CHARS = 12_000
MAX_STATIC_ISSUES = 30


def _should_skip_file(path: str) -> bool:
    lowered = path.lower()
    name = lowered.rsplit("/", 1)[-1]
    if name in _SKIP_PROMPT_FILES or name.endswith(".pem") or name.endswith(".key"):
        return True
    if name.startswith(".env"):
        return True
    return False


def _file_block(item: ChangedFile) -> str:
    patch = redact(item.patch or "")
    if len(patch) > MAX_PATCH_CHARS:
        patch = patch[:MAX_PATCH_CHARS] + "\n... [patch truncated]"
    related = ", ".join(item.related_paths[:8]) if item.related_paths else "none"
    sensitive = ", ".join(item.sensitive_areas[:8]) if item.sensitive_areas else "none"
    return (
        f"### {item.path}\n"
        f"status: {item.status}\n"
        f"language: {item.language or 'unknown'}\n"
        f"kind: {item.kind or 'unknown'}\n"
        f"related_paths: {related}\n"
        f"sensitive_areas: {sensitive}\n"
        f"patch:\n{patch}\n"
    )


def _retrieved_block(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return ""
    parts = ["\nRetrieved repository context (use as evidence, do not invent paths):\n"]
    used = 0
    for chunk in chunks:
        block = (
            f"### {chunk.file_path} lines {chunk.start_line}-{chunk.end_line}"
            f" symbol={chunk.symbol or 'unknown'}\n{chunk.text}\n"
        )
        if used + len(block) > MAX_RETRIEVED_CHARS:
            break
        parts.append(block)
        used += len(block)
    return "".join(parts)


def _static_issue_line(issue: ToolIssue) -> str:
    location = issue.file
    if issue.line is not None:
        location = f"{location}:{issue.line}"
    rule = issue.rule or "unknown"
    return f"- [{issue.tool}] {rule} {location} {issue.message}"


def _static_analysis_block(report: StaticAnalysisReport | None) -> str:
    if report is None:
        return ""
    lines = ["\nStatic analysis findings (deterministic tools; use as evidence, do not invent replacements):\n"]
    for run in report.runs:
        status = "available" if run.available else "unavailable"
        extra = f" error={run.error}" if run.error else ""
        lines.append(f"- tool={run.tool} {status} exit={run.exit_code} issues={len(run.issues)}{extra}")
    issues = report.issues[:MAX_STATIC_ISSUES]
    if not issues:
        lines.append("No static-analysis issues were reported.")
        return "".join(line + "\n" for line in lines)
    lines.append("Issues:")
    lines.extend(_static_issue_line(issue) for issue in issues)
    return "\n".join(lines) + "\n"


def _coerce_test_results(report: TestRunReport | dict | None) -> TestRunReport | None:
    if report is None:
        return None
    if isinstance(report, TestRunReport):
        return report
    return TestRunReport.model_validate(report)


def _test_results_block(report: TestRunReport | dict | None) -> str:
    report = _coerce_test_results(report)
    if report is None:
        return ""
    lines = ["\nTest results (pytest on related files; use as evidence, do not invent test names):\n"]
    if report.skipped:
        lines.append(f"skipped: {report.skip_reason or 'no tests run'}")
        return "\n".join(lines) + "\n"
    if not report.available:
        lines.append(f"pytest unavailable: {report.error or 'not installed'}")
        return "\n".join(lines) + "\n"
    lines.append(
        f"discovered={len(report.discovered)} passed={report.passed} failed={report.failed} "
        f"errors={report.errors} skipped={report.skipped_cases} exit={report.exit_code}"
    )
    if report.discovered:
        lines.append("files: " + ", ".join(report.discovered[:12]))
    for case in report.failed_cases[:15]:
        message = (case.message or "").strip().replace("\n", " ")[:240]
        lines.append(f"- {case.outcome} {case.nodeid} {message}".rstrip())
    if report.failed == 0 and report.errors == 0 and not report.skipped:
        lines.append("All executed related tests passed.")
    return "\n".join(lines) + "\n"


def build_review_user_prompt(
    snapshot: PullRequestSnapshot,
    repository_context: RepositoryContextResponse | None,
    retrieved_context: list[RetrievedChunk] | None = None,
    static_analysis: StaticAnalysisReport | None = None,
    test_results: TestRunReport | dict | None = None,
) -> str:
    ref = snapshot.pull_request
    context_lines = []
    if repository_context is not None:
        context_lines.extend(
            [
                f"primary_language: {repository_context.primary_language}",
                f"project_types: {', '.join(repository_context.project_types) or 'unknown'}",
                f"package_managers: {', '.join(repository_context.package_managers) or 'unknown'}",
                f"test_frameworks: {', '.join(repository_context.test_frameworks) or 'unknown'}",
                f"source_roots: {', '.join(repository_context.source_roots) or 'unknown'}",
            ]
        )
    files = [item for item in snapshot.changed_files if not _should_skip_file(item.path)]
    blocks = [_file_block(item) for item in files]
    prompt = (
        f"Repository: {ref.owner}/{ref.repo}\n"
        f"Pull request #{ref.number}: {ref.title}\n"
        f"Author: {ref.author or 'unknown'}\n"
        f"Branches: {ref.source_branch} -> {ref.target_branch}\n"
        f"Head SHA: {ref.head_sha}\n"
        + "\n".join(context_lines)
        + "\n\nChanged files:\n"
        + "\n".join(blocks)
        + _retrieved_block(retrieved_context or [])
        + _static_analysis_block(static_analysis)
        + _test_results_block(test_results)
    )
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[:MAX_PROMPT_CHARS] + "\n... [prompt truncated]"
    return prompt
