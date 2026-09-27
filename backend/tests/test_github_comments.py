"""GitHub review comment builder tests. No live GitHub API."""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.core.config import clear_settings_cache
from app.database.models import ReviewRun, ReviewRunStatus
from app.schemas.findings import FindingSeverity, StructuredReview
from app.services.github_comments import (
    build_review_comments,
    comment_anchor,
    format_inline_comment,
    post_verified_review,
    should_post_finding,
)
from app.services.ingestion import ingest_pull_request
from app.tools.github import GitHubClient

from tests.github_fixtures import POSTED_REVIEWS, github_mock_handler, mock_github_client
from tests.test_review_agent import FakeLLM, _finding, _snapshot


def test_should_post_only_verified_medium_or_higher() -> None:
    assert should_post_finding(_finding(verified=True)) is True
    assert should_post_finding(_finding(verified=False, severity=FindingSeverity.CRITICAL)) is False
    assert should_post_finding(_finding(verified=True, severity=FindingSeverity.LOW)) is False
    assert should_post_finding(_finding(verified=None)) is False


def test_comment_anchor_maps_added_line_to_right() -> None:
    snapshot = _snapshot()
    changed = snapshot.changed_files[0]
    assert comment_anchor(changed, 11) == {"path": changed.path, "line": 11, "side": "RIGHT"}
    assert comment_anchor(changed, 999) is None


def test_build_review_comments_skips_unverified_and_redacts_secrets() -> None:
    snapshot = _snapshot()
    review = StructuredReview(
        summary="SQL risk.",
        findings=[
            _finding(verified=False),
            _finding(
                verified=True,
                title="Token leak",
                evidence="Authorization: Bearer ghs_live_token_value",
            ),
        ],
    )
    comments, posted, omitted = build_review_comments(review, snapshot)
    assert omitted == 0
    assert len(posted) == 1
    assert len(comments) == 1
    assert comments[0]["side"] == "RIGHT"
    assert comments[0]["path"] == "backend/services/user_service.py"
    assert "ghs_live_token_value" not in comments[0]["body"]
    assert "[REDACTED]" in comments[0]["body"]


def test_format_inline_comment_includes_severity() -> None:
    body = format_inline_comment(_finding(verified=True))
    assert "HIGH" in body
    assert "SQL built from user input" in body


def test_post_verified_review_returns_none_when_nothing_eligible() -> None:
    snapshot = _snapshot()
    review = StructuredReview(summary="clean", findings=[_finding(verified=False)])
    assert post_verified_review(mock_github_client(), snapshot, review) is None
    assert POSTED_REVIEWS == []


def test_post_verified_review_sends_comment_event() -> None:
    snapshot = _snapshot()
    review = StructuredReview(summary="SQL risk.", findings=[_finding(verified=True)])
    payload = post_verified_review(mock_github_client(), snapshot, review)
    assert payload is not None
    assert payload["id"] == 555
    assert len(POSTED_REVIEWS) == 1
    posted = POSTED_REVIEWS[0]
    assert posted["event"] == "COMMENT"
    assert posted["commit_id"] == "abc123def456"
    assert posted["comments"][0]["line"] == 11


def test_ingest_posts_github_review(db_session: Session) -> None:
    llm = FakeLLM(StructuredReview(summary="SQL risk.", findings=[_finding()]))
    ingest_pull_request(
        db_session,
        mock_github_client(),
        owner="acme",
        repo="api",
        number=12,
        trigger="manual",
        llm=llm,
    )
    assert len(POSTED_REVIEWS) == 1
    assert POSTED_REVIEWS[0]["event"] == "COMMENT"


def test_github_post_failure_keeps_run_completed(db_session: Session) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/reviews"):
            return httpx.Response(502, json={"message": "unavailable"})
        return github_mock_handler(request)

    client = GitHubClient(token="test-token", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    llm = FakeLLM(StructuredReview(summary="SQL risk.", findings=[_finding()]))
    result = ingest_pull_request(
        db_session,
        client,
        owner="acme",
        repo="api",
        number=12,
        trigger="manual",
        llm=llm,
    )
    stored = db_session.get(ReviewRun, result.review_run_id)
    assert stored is not None
    assert stored.status is ReviewRunStatus.COMPLETED
    assert stored.reviews[0].posted_to_github is False
    assert stored.errors is not None
    assert stored.errors[-1]["component"] == "github_comments"


def test_github_post_reviews_can_be_disabled(db_session: Session, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_POST_REVIEWS", "false")
    clear_settings_cache()
    try:
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
        assert stored.reviews[0].posted_to_github is False
        assert POSTED_REVIEWS == []
    finally:
        monkeypatch.delenv("GITHUB_POST_REVIEWS", raising=False)
        clear_settings_cache()
