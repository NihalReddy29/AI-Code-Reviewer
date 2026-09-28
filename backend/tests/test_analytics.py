"""Tests for analytics overview and trends endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.models import Finding, PullRequest, Repository, ReviewRun, ReviewRunStatus
from app.schemas.findings import FindingCategory, FindingSeverity


def _seed_sample_data(session: Session) -> tuple[Repository, ReviewRun, ReviewRun]:
    repo1 = Repository(full_name="acme/api")
    repo2 = Repository(full_name="acme/frontend")
    session.add_all([repo1, repo2])
    session.flush()

    pr1 = PullRequest(
        repository_id=repo1.id,
        number=1,
        title="Fix auth bug",
        head_sha="sha1",
    )
    pr2 = PullRequest(
        repository_id=repo2.id,
        number=2,
        title="Add styles",
        head_sha="sha2",
    )
    session.add_all([pr1, pr2])
    session.flush()

    run1 = ReviewRun(
        pull_request_id=pr1.id,
        commit_sha=pr1.head_sha,
        status=ReviewRunStatus.COMPLETED,
        trigger="webhook",
    )
    run2 = ReviewRun(
        pull_request_id=pr2.id,
        commit_sha=pr2.head_sha,
        status=ReviewRunStatus.COMPLETED,
        trigger="manual",
    )
    session.add_all([run1, run2])
    session.flush()

    # Findings on run1
    f1 = Finding(
        review_run_id=run1.id,
        file_path="src/auth.py",
        line=10,
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="SQL Injection",
        description="Dangerous SQL string",
        confidence=0.95,
        verified=True,  # -15
    )
    f2 = Finding(
        review_run_id=run1.id,
        file_path="src/auth.py",
        line=25,
        category=FindingCategory.BUG,
        severity=FindingSeverity.HIGH,
        title="Token leak",
        description="Token logged",
        confidence=0.85,
        verified=True,  # -8
    )
    f3 = Finding(
        review_run_id=run1.id,
        file_path="src/utils.py",
        line=5,
        category=FindingCategory.CODE_QUALITY,
        severity=FindingSeverity.LOW,
        title="Nit",
        description="Unused var",
        confidence=0.5,
        verified=False,  # rejected
    )

    # Finding on run2
    f4 = Finding(
        review_run_id=run2.id,
        file_path="src/index.css",
        line=1,
        category=FindingCategory.MAINTAINABILITY,
        severity=FindingSeverity.MEDIUM,
        title="CSS specificity",
        description="Deep nesting",
        confidence=0.7,
        verified=True,  # -3
    )

    session.add_all([f1, f2, f3, f4])
    session.commit()

    return repo1, run1, run2


def test_empty_analytics_overview(client: TestClient) -> None:
    response = client.get("/analytics/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviews"] == 0
    assert data["total_findings"] == 0
    assert data["average_score"] == 0.0
    assert data["score_label"] == "heuristic"
    assert data["verified_count"] == 0
    assert data["rejected_count"] == 0
    assert data["top_files_by_findings"] == []
    assert data["findings_by_severity"]["CRITICAL"] == 0


def test_analytics_overview_with_data(client: TestClient, db_session: Session) -> None:
    _seed_sample_data(db_session)

    response = client.get("/analytics/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviews"] == 2
    assert data["total_findings"] == 4
    # run1 score: 100 - (15 + 8) = 77
    # run2 score: 100 - 3 = 97
    # avg: (77 + 97) / 2 = 87.0
    assert data["average_score"] == 87.0
    assert data["verified_count"] == 3
    assert data["rejected_count"] == 1
    assert data["findings_by_severity"]["CRITICAL"] == 1
    assert data["findings_by_severity"]["HIGH"] == 1
    assert data["findings_by_severity"]["MEDIUM"] == 1
    assert data["findings_by_severity"]["LOW"] == 1
    assert data["findings_by_category"]["SECURITY"] == 1
    assert data["findings_by_category"]["BUG"] == 1

    top_files = data["top_files_by_findings"]
    assert len(top_files) >= 1
    assert top_files[0]["file"] == "src/auth.py"
    assert top_files[0]["count"] == 2


def test_analytics_overview_repository_filter(client: TestClient, db_session: Session) -> None:
    _seed_sample_data(db_session)

    response = client.get("/analytics/overview", params={"repository": "acme/api"})
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviews"] == 1
    assert data["total_findings"] == 3
    assert data["average_score"] == 77.0


def test_analytics_trends_default(client: TestClient, db_session: Session) -> None:
    _seed_sample_data(db_session)

    response = client.get("/analytics/trends")
    assert response.status_code == 200
    data = response.json()
    assert data["days"] == 30
    assert len(data["trends"]) == 30

    today_point = data["trends"][-1]
    assert today_point["review_count"] == 2
    assert today_point["finding_count"] == 4
    assert today_point["average_score"] == 87.0


def test_analytics_trends_custom_days_and_filter(client: TestClient, db_session: Session) -> None:
    _seed_sample_data(db_session)

    response = client.get("/analytics/trends", params={"days": 7, "repository": "acme/api"})
    assert response.status_code == 200
    data = response.json()
    assert data["days"] == 7
    assert len(data["trends"]) == 7

    today_point = data["trends"][-1]
    assert today_point["review_count"] == 1
    assert today_point["finding_count"] == 3
    assert today_point["average_score"] == 77.0
