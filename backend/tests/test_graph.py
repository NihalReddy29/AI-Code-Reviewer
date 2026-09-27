"""LangGraph routing, merge, and orchestration tests. No live LLM provider."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.graph import build_review_graph
from app.agents.nodes import ReviewGraphDeps, merge_structured_reviews, route_after_persist
from app.database.models import ReviewRun, ReviewRunStatus
from app.schemas.findings import FindingCategory, FindingSeverity, StructuredReview
from app.services.ingestion import ingest_pull_request
from tests.github_fixtures import mock_github_client
from tests.test_review_agent import FakeLLM, _finding


def test_route_after_persist() -> None:
    assert route_after_persist({"duplicate": True, "llm_ready": True}) == "skip_review"
    assert route_after_persist({"duplicate": False, "llm_ready": False}) == "skip_review"
    assert route_after_persist({"duplicate": False, "llm_ready": True}) == "start_reviews"


def test_merge_drops_duplicate_findings() -> None:
    first = StructuredReview(summary="Security pass.", findings=[_finding()])
    second = StructuredReview(
        summary="Quality pass.",
        findings=[
            _finding(),
            _finding(
                title="Missing tests",
                category=FindingCategory.TESTING,
                severity=FindingSeverity.MEDIUM,
                evidence="No test file in the diff.",
                suggested_fix="Add a unit test for get_user.",
                confidence=0.7,
            ),
        ],
    )
    merged = merge_structured_reviews(first, second)
    assert len(merged.findings) == 2
    assert "Security pass." in merged.summary
    assert "Quality pass." in merged.summary


def test_graph_contains_parallel_and_conditional_nodes(db_session: Session) -> None:
    graph = build_review_graph(ReviewGraphDeps(session=db_session, client=mock_github_client()))
    names = set(graph.get_graph().nodes)
    assert "retrieve_context" in names
    assert "run_static_analysis" in names
    assert "run_tests" in names
    assert "review_security" in names
    assert "synthesize" in names
    assert "verify_findings" in names
    assert "post_github_review" in names
    assert "skip_review" in names


def test_ingest_records_graph_trace_without_llm(db_session: Session) -> None:
    result = ingest_pull_request(
        db_session,
        mock_github_client(),
        owner="acme",
        repo="api",
        number=12,
        trigger="manual",
    )
    stored = db_session.get(ReviewRun, result.review_run_id)
    assert stored is not None
    assert stored.status is ReviewRunStatus.PENDING
    nodes = [item["node"] for item in stored.agent_trace or []]
    assert "retrieve_context" in nodes
    assert "run_static_analysis" in nodes
    assert "run_tests" in nodes
    assert "skip_review" in nodes
    assert "review_security" not in nodes


def test_ingest_with_fake_llm_runs_both_review_passes(db_session: Session) -> None:
    llm = FakeLLM(StructuredReview(summary="SQL risk.", findings=[_finding()]))
    result = ingest_pull_request(
        db_session,
        mock_github_client(),
        owner="acme",
        repo="api",
        number=12,
        trigger="manual",
        llm=llm,
    )
    stored = db_session.get(ReviewRun, result.review_run_id)
    assert stored is not None
    assert stored.status is ReviewRunStatus.COMPLETED
    nodes = [item["node"] for item in stored.agent_trace or []]
    assert "review_security" in nodes
    assert "review_quality" in nodes
    assert "synthesize" in nodes
    assert "verify_findings" in nodes
    assert "post_github_review" in nodes
    assert stored.findings[0].verified is True
    assert stored.reviews[0].posted_to_github is True
