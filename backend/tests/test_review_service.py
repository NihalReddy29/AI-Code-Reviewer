"""LLM review persistence tests with a fake model."""

from sqlalchemy.orm import Session

from app.database.models import Finding, ReviewRun, ReviewRunStatus
from app.schemas.findings import FindingCategory, FindingSeverity, ReviewFinding, StructuredReview
from app.services.ingestion import ingest_pull_request
from tests.github_fixtures import mock_github_client
from tests.test_review_agent import FakeLLM, _finding


def test_ingest_without_llm_key_stays_pending(db_session: Session) -> None:
    result = ingest_pull_request(
        db_session,
        mock_github_client(),
        owner="acme",
        repo="api",
        number=12,
        trigger="manual",
    )
    assert result.status is ReviewRunStatus.PENDING
    stored = db_session.get(ReviewRun, result.review_run_id)
    assert stored is not None
    assert stored.findings == []


def test_ingest_with_fake_llm_persists_findings(db_session: Session) -> None:
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
    assert result.status is ReviewRunStatus.COMPLETED
    stored = db_session.get(ReviewRun, result.review_run_id)
    assert stored is not None
    db_session.refresh(stored)
    findings = db_session.query(Finding).filter_by(review_run_id=stored.id).all()
    assert len(findings) == 1
    assert findings[0].category is FindingCategory.SECURITY
    assert findings[0].severity is FindingSeverity.HIGH
    assert findings[0].verified is True
    assert findings[0].verification_reason is not None
    assert stored.reviews[0].summary.startswith("SQL risk.")
    assert "Verification:" in stored.reviews[0].summary
    assert stored.reviews[0].posted_to_github is True
    assert stored.reviews[0].github_review_id == 555


def test_ingest_records_llm_failure(db_session: Session) -> None:
    llm = FakeLLM(RuntimeError("provider down"))
    result = ingest_pull_request(
        db_session,
        mock_github_client(),
        owner="acme",
        repo="api",
        number=12,
        trigger="manual",
        llm=llm,
    )
    assert result.status is ReviewRunStatus.FAILED
    stored = db_session.get(ReviewRun, result.review_run_id)
    assert stored is not None
    assert stored.errors is not None
    assert stored.errors[0]["component"] == "review_agent"
