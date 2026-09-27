"""Health endpoint tests. Uses an in-memory database, not a live GitHub or LLM service."""

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["service"] == "ai-code-reviewer-test"
    assert body["environment"] == "test"


def test_health_returns_503_when_database_is_down(client: TestClient) -> None:
    with patch(
        "app.api.health.check_database_connection",
        side_effect=RuntimeError("connection refused"),
    ):
        response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
    assert "database" in (body.get("detail") or "")


def test_list_reviews_database_error_is_503_not_500(client: TestClient) -> None:
    from sqlalchemy.exc import OperationalError

    with patch(
        "app.api.reviews.select",
        side_effect=OperationalError("select", {}, Exception("connection refused")),
    ):
        response = client.get("/reviews")
    assert response.status_code == 503
    assert "database" in response.json()["detail"].lower()


def test_cors_allows_dashboard_origin(client: TestClient) -> None:
    response = client.options(
        "/reviews",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
