"""LLM review agent with LangChain structured output."""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import SYSTEM_PROMPT, build_review_user_prompt
from app.core.llm import LLMConfigError, build_chat_model, llm_is_configured
from app.core.logging import get_logger, log_event
from app.schemas.analysis import RepositoryContextResponse
from app.schemas.findings import ReviewFinding, StructuredReview
from app.schemas.github import PullRequestSnapshot
from app.schemas.rag import RetrievedChunk
from app.schemas.static_analysis import StaticAnalysisReport
from app.schemas.tests import TestRunReport

logger = get_logger(__name__)


class SupportsStructuredReview(Protocol):
    def with_structured_output(self, schema: type[StructuredReview]) -> Any: ...


class ReviewAgentError(RuntimeError):
    pass


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def allowed_changed_paths(snapshot: PullRequestSnapshot) -> set[str]:
    paths: set[str] = set()
    for item in snapshot.changed_files:
        paths.add(_normalize_path(item.path))
        if item.previous_path:
            paths.add(_normalize_path(item.previous_path))
        for related in item.related_paths:
            paths.add(_normalize_path(related))
    return paths


def sanitize_review(review: StructuredReview, allowed_paths: set[str]) -> StructuredReview:
    """Drop findings that point at files the model was not given."""

    kept: list[ReviewFinding] = []
    for finding in review.findings:
        file_path = _normalize_path(finding.file)
        if file_path not in allowed_paths:
            log_event(logger, "review_finding_dropped_unknown_file", file=file_path)
            continue
        kept.append(finding.model_copy(update={"file": file_path}))
    summary = review.summary.strip()
    if not summary:
        summary = "No summary provided."
    return StructuredReview(summary=summary, findings=kept)


def generate_structured_review(
    snapshot: PullRequestSnapshot,
    repository_context: RepositoryContextResponse | None,
    *,
    llm: SupportsStructuredReview | None = None,
    retrieved_context: list[RetrievedChunk] | None = None,
    static_analysis: StaticAnalysisReport | None = None,
    test_results: TestRunReport | None = None,
    system_prompt: str | None = None,
    guidelines: str | None = None,
) -> StructuredReview:
    """Call the configured LLM and validate structured findings.

    Pass `llm` in tests. Production uses LangChain `with_structured_output`.
    """

    if llm is None:
        if not llm_is_configured():
            raise LLMConfigError("LLM_API_KEY is not configured")
        llm = build_chat_model()

    user_prompt = build_review_user_prompt(
        snapshot, repository_context, retrieved_context, static_analysis, test_results,
        guidelines=guidelines,
    )
    try:
        structured = llm.with_structured_output(StructuredReview)
        raw = structured.invoke(
            [SystemMessage(content=system_prompt or SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
        )
    except Exception as exc:
        logger.exception("llm_structured_output_failed")
        raise ReviewAgentError("LLM structured review failed") from exc

    if isinstance(raw, StructuredReview):
        review = raw
    else:
        review = StructuredReview.model_validate(raw)

    allowed = allowed_changed_paths(snapshot)
    sanitized = sanitize_review(review, allowed)
    log_event(logger, "review_generated", finding_count=len(sanitized.findings))
    return sanitized
