"""PR ingestion persistence tests using a mocked GitHub client."""

from sqlalchemy.orm import Session

from app.database.models import ReviewRun, ReviewRunStatus
from app.services.ingestion import ingest_pull_request
from tests.github_fixtures import mock_github_client


def test_ingest_creates_repository_pr_and_review_run(db_session: Session) -> None:
    result = ingest_pull_request(
        db_session,
        mock_github_client(),
        owner="acme",
        repo="api",
        number=12,
        trigger="manual",
    )
    assert result.duplicate is False
    assert result.status is ReviewRunStatus.PENDING
    stored = db_session.get(ReviewRun, result.review_run_id)
    assert stored is not None
    assert stored.commit_sha == "abc123def456"
    assert stored.changed_files is not None
    assert stored.changed_files[0]["path"].endswith("user_service.py")
    assert stored.changed_files[0]["language"] == "python"
    assert stored.repository_context["primary_language"] == "python"
    assert "pytest" in stored.repository_context["test_frameworks"]
    assert stored.retrieved_context is not None
    assert any(item["symbol"] == "get_user" for item in stored.retrieved_context)
    assert stored.static_analysis_results is not None
    assert stored.static_analysis_results["runs"]
    assert stored.test_results is not None
    assert "backend/tests/test_user_service.py" in stored.test_results["discovered"]
    assert stored.pull_request.repository.full_name == "acme/api"


def test_ingest_skips_duplicate_commit(db_session: Session) -> None:
    first = ingest_pull_request(
        db_session,
        mock_github_client(),
        owner="acme",
        repo="api",
        number=12,
        trigger="webhook:opened",
    )
    second = ingest_pull_request(
        db_session,
        mock_github_client(),
        owner="acme",
        repo="api",
        number=12,
        trigger="webhook:synchronize",
    )
    assert second.duplicate is True
    assert second.review_run_id == first.review_run_id
