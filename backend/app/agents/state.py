"""LangGraph state for a pull-request review run."""

from __future__ import annotations

from typing import Annotated, Any, NotRequired, TypedDict
from uuid import UUID


def merge_lists(left: list | None, right: list | None) -> list:
    """Reducer that concatenates node-emitted lists (errors, trace events)."""

    return list(left or []) + list(right or [])


class ReviewGraphState(TypedDict):
    owner: str
    repo: str
    number: int
    trigger: str
    delivery_id: NotRequired[str | None]
    snapshot: NotRequired[Any]
    repository_context: NotRequired[Any]
    retrieved_context: NotRequired[list]
    static_analysis: NotRequired[Any]
    test_results: NotRequired[Any]
    security_review: NotRequired[Any]
    quality_review: NotRequired[Any]
    review: NotRequired[Any]
    review_run_id: NotRequired[UUID | None]
    github_review_id: NotRequired[int | None]
    duplicate: NotRequired[bool]
    llm_ready: NotRequired[bool]
    status: NotRequired[str]
    repo_config: NotRequired[Any]
    config_warnings: NotRequired[list]
    resolved_config: NotRequired[dict | None]
    config_sha: NotRequired[str | None]
    errors: Annotated[list, merge_lists]
    events: Annotated[list, merge_lists]
