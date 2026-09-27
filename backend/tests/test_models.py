"""ORM relationship tests against the in-memory test database."""

from sqlalchemy.orm import Session

from app.database.models import (
    Finding,
    FindingCategory,
    FindingSeverity,
    PullRequest,
    Repository,
    Review,
    ReviewRun,
    ReviewRunStatus,
)


def test_repository_pr_run_finding_relationships(db_session: Session) -> None:
    repository = Repository(full_name="acme/api", default_branch="main")
    pull_request = PullRequest(
        repository=repository,
        number=12,
        title="Harden auth",
        author="dev",
        source_branch="feature/auth",
        target_branch="main",
        head_sha="abc123",
    )
    review_run = ReviewRun(
        pull_request=pull_request,
        commit_sha="abc123",
        status=ReviewRunStatus.COMPLETED,
        trigger="manual",
    )
    finding = Finding(
        review_run=review_run,
        file_path="app/auth.py",
        line=42,
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.HIGH,
        title="Possible injection",
        description="User input reaches a query without parameterization.",
        evidence="query constructed with string format",
        suggested_fix="Use bound parameters.",
        confidence=0.94,
        verified=True,
        verification_reason="Static analysis and surrounding code agree.",
    )
    review = Review(review_run=review_run, summary="One high-severity finding.", posted_to_github=False)

    db_session.add_all([repository, pull_request, review_run, finding, review])
    db_session.flush()

    stored_repo = db_session.query(Repository).filter_by(full_name="acme/api").one()
    assert len(stored_repo.pull_requests) == 1
    stored_pr = stored_repo.pull_requests[0]
    assert stored_pr.number == 12
    assert stored_pr.review_runs[0].findings[0].severity is FindingSeverity.HIGH
    assert stored_pr.review_runs[0].reviews[0].summary is not None
    assert stored_pr.review_runs[0].id == finding.review_run_id
