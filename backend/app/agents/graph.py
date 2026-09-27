"""Compile and run the pull-request review LangGraph."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session
from langgraph.graph import END, START, StateGraph

from app.agents.nodes import ReviewGraphDeps, build_nodes, route_after_persist
from app.agents.state import ReviewGraphState
from app.core.logging import get_logger, log_event
from app.database.models import ReviewRunStatus
from app.services.ingestion import IngestResult
from app.tools.github import GitHubClient

logger = get_logger(__name__)


def build_review_graph(deps: ReviewGraphDeps):
    """Fetch → repo analysis → (RAG ∥ static ∥ tests) → persist → conditional LLM passes → merge → verify."""

    nodes = build_nodes(deps)
    builder = StateGraph(ReviewGraphState)
    for name, fn in nodes.items():
        builder.add_node(name, fn)

    builder.add_edge(START, "fetch_snapshot")
    builder.add_edge("fetch_snapshot", "analyze_repository")
    builder.add_edge("analyze_repository", "retrieve_context")
    builder.add_edge("analyze_repository", "run_static_analysis")
    builder.add_edge("analyze_repository", "run_tests")
    builder.add_edge("retrieve_context", "join_analysis")
    builder.add_edge("run_static_analysis", "join_analysis")
    builder.add_edge("run_tests", "join_analysis")
    builder.add_edge("join_analysis", "persist_run")
    builder.add_conditional_edges(
        "persist_run",
        route_after_persist,
        {"start_reviews": "start_reviews", "skip_review": "skip_review"},
    )
    builder.add_edge("skip_review", END)
    builder.add_edge("start_reviews", "review_security")
    builder.add_edge("start_reviews", "review_quality")
    builder.add_edge("review_security", "synthesize")
    builder.add_edge("review_quality", "synthesize")
    builder.add_edge("synthesize", "verify_findings")
    builder.add_edge("verify_findings", "persist_findings")
    builder.add_edge("persist_findings", "post_github_review")
    builder.add_edge("post_github_review", END)
    return builder.compile()


def run_review_graph(
    session: Session,
    client: GitHubClient,
    *,
    owner: str,
    repo: str,
    number: int,
    trigger: str,
    delivery_id: str | None = None,
    llm: object | None = None,
) -> IngestResult:
    deps = ReviewGraphDeps(session=session, client=client, llm=llm)
    graph = build_review_graph(deps)
    log_event(logger, "review_graph_started", repository=f"{owner}/{repo}", pull_request=number, trigger=trigger)
    final_state = graph.invoke(
        {
            "owner": owner,
            "repo": repo,
            "number": number,
            "trigger": trigger,
            "delivery_id": delivery_id,
            "errors": [],
            "events": [],
        }
    )
    review_run_id: UUID = final_state["review_run_id"]
    status = ReviewRunStatus(final_state.get("status") or ReviewRunStatus.PENDING.value)
    log_event(logger, "review_graph_finished", status=status.value, duplicate=bool(final_state.get("duplicate")))
    return IngestResult(
        review_run_id=review_run_id,
        duplicate=bool(final_state.get("duplicate")),
        snapshot=final_state["snapshot"],
        status=status,
    )
