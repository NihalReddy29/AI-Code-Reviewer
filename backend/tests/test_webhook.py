"""Webhook HMAC verification tests. No live GitHub calls."""

import json

from fastapi.testclient import TestClient

from app.schemas.github import GitHubWebhookPayload
from app.tools.webhook import WebhookVerificationError, sign_payload, verify_github_signature
from tests.github_fixtures import WEBHOOK_SECRET, signed_headers, webhook_payload_bytes


def test_verify_signature_accepts_valid_hmac() -> None:
    payload = b'{"ok": true}'
    verify_github_signature(
        payload=payload,
        signature_header=sign_payload(payload, WEBHOOK_SECRET),
        secret=WEBHOOK_SECRET,
    )


def test_verify_signature_rejects_missing_header() -> None:
    try:
        verify_github_signature(payload=b"{}", signature_header=None, secret=WEBHOOK_SECRET)
    except WebhookVerificationError:
        return
    raise AssertionError("expected WebhookVerificationError")


def test_verify_signature_rejects_invalid_digest() -> None:
    try:
        verify_github_signature(payload=b"{}", signature_header="sha256=deadbeef", secret=WEBHOOK_SECRET)
    except WebhookVerificationError:
        return
    raise AssertionError("expected WebhookVerificationError")


def test_webhook_ping(client: TestClient) -> None:
    body = b'{"zen": "Keep it logically awesome."}'
    response = client.post("/webhooks/github", content=body, headers=signed_headers(body, event="ping"))
    assert response.status_code == 200
    assert response.json()["event"] == "ping"


def test_webhook_rejects_bad_signature(client: TestClient) -> None:
    body = webhook_payload_bytes()
    headers = signed_headers(body)
    headers["X-Hub-Signature-256"] = "sha256=" + ("00" * 32)
    response = client.post("/webhooks/github", content=body, headers=headers)
    assert response.status_code == 401


def test_webhook_ignores_non_review_actions(client: TestClient) -> None:
    body = webhook_payload_bytes({"action": "labeled"})
    response = client.post("/webhooks/github", content=body, headers=signed_headers(body))
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_rejects_malformed_json(client: TestClient) -> None:
    body = b"not-json"
    response = client.post(
        "/webhooks/github",
        content=body,
        headers=signed_headers(body, event="pull_request"),
    )
    assert response.status_code == 400


def test_webhook_discards_unknown_payload_fields() -> None:
    extra = json.loads(webhook_payload_bytes().decode())
    extra["organization"] = {"login": "acme"}
    extra["sender"] = {"login": "bot"}
    parsed = GitHubWebhookPayload.model_validate(extra)
    assert parsed.repository is not None
    assert parsed.repository.full_name == "acme/api"
    assert parsed.pull_request is not None
    assert parsed.pull_request.number == 12


def test_webhook_ingests_opened_pull_request(client: TestClient, monkeypatch) -> None:
    from app.api import github as github_api
    from tests.github_fixtures import mock_github_client

    monkeypatch.setattr(github_api, "build_github_client", lambda *args, **kwargs: mock_github_client())
    body = webhook_payload_bytes()
    response = client.post("/webhooks/github", content=body, headers=signed_headers(body, delivery="d-open-1"))
    assert response.status_code == 200
    data = response.json()
    assert data["duplicate"] is False
    assert data["pull_request"] == 12
    assert data["commit_sha"] == "abc123def456"
    assert data["changed_file_count"] == 1

    again = client.post("/webhooks/github", content=body, headers=signed_headers(body, delivery="d-open-1"))
    assert again.json()["duplicate"] is True
    assert again.json()["review_run_id"] == data["review_run_id"]
