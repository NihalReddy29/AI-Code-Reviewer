"""Manual review trigger and review lookup tests."""

from fastapi.testclient import TestClient

from tests.github_fixtures import mock_github_client


def test_manual_review_trigger_and_get(client: TestClient, monkeypatch) -> None:
    from app.api import reviews as reviews_api

    monkeypatch.setattr(reviews_api, "build_github_client", lambda *args, **kwargs: mock_github_client())
    created = client.post("/reviews/acme/api/12")
    assert created.status_code == 202
    body = created.json()
    review_id = body["review_run_id"]

    fetched = client.get(f"/reviews/{review_id}")
    assert fetched.status_code == 200
    detail = fetched.json()
    assert detail["title"] == "Harden authentication"
    assert detail["author"] == "dev"
    assert detail["changed_files"][0]["language"] == "python"
    assert detail["repository_context"]["primary_language"] == "python"
    assert detail["status"] == "pending"
    assert detail["posted_to_github"] is False
    assert detail["github_review_id"] is None
    assert detail["findings"] == []
    assert detail["score"] == 100
    assert detail["static_analysis"] is not None
    assert "ruff" in [run["tool"] for run in detail["static_analysis"]["runs"]]
    assert detail["test_results"] is not None
    assert "backend/tests/test_user_service.py" in detail["test_results"]["discovered"]

    findings = client.get(f"/reviews/{review_id}/findings")
    assert findings.status_code == 200
    assert findings.json()["findings"] == []

    listed = client.get("/reviews")
    assert listed.status_code == 200
    reviews = listed.json()["reviews"]
    assert reviews[0]["id"] == review_id
    assert reviews[0]["repository"] == "acme/api"
    assert reviews[0]["finding_count"] == 0
    assert reviews[0]["score"] == 100

    filtered = client.get("/reviews", params={"repository": "acme/api", "status": "pending"})
    assert filtered.status_code == 200
    assert len(filtered.json()["reviews"]) == 1

    empty = client.get("/reviews", params={"repository": "missing/repo"})
    assert empty.json()["reviews"] == []

    bad_status = client.get("/reviews", params={"status": "nope"})
    assert bad_status.status_code == 400

    repos = client.get("/repositories")
    assert repos.status_code == 200
    names = [item["full_name"] for item in repos.json()["repositories"]]
    assert "acme/api" in names


def test_manual_review_rejects_invalid_owner(client: TestClient) -> None:
    response = client.post("/reviews/bad owner/api/12")
    assert response.status_code == 400


def test_get_review_not_found(client: TestClient) -> None:
    response = client.get("/reviews/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404


def test_get_review_returns_resolved_config(client: TestClient, db_session) -> None:
    from app.database.models import PullRequest, Repository, ReviewRun, ReviewRunStatus

    repo = Repository(full_name="acme/tooling")
    db_session.add(repo)
    db_session.flush()

    pr = PullRequest(
        repository_id=repo.id,
        number=7,
        title="Config test PR",
        author="alice",
        source_branch="feat",
        target_branch="main",
        head_sha="111222333",
    )
    db_session.add(pr)
    db_session.flush()

    run = ReviewRun(
        pull_request_id=pr.id,
        commit_sha=pr.head_sha,
        status=ReviewRunStatus.COMPLETED,
        trigger="manual",
        resolved_config={"tools": {"pytest": False}, "review": {"min_severity": "HIGH"}},
        config_sha="abcdef1234567890",
    )
    db_session.add(run)
    db_session.commit()

    resp = client.get(f"/reviews/{run.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved_config"] == {"tools": {"pytest": False}, "review": {"min_severity": "HIGH"}}
    assert data["config_sha"] == "abcdef1234567890"
