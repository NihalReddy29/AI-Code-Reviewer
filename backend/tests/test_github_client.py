"""GitHub client tests against a mocked HTTP transport."""

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import httpx

from app.core.config import Settings
from app.tools.github import GitHubAPIError, GitHubClient, create_app_jwt, fetch_installation_token
from tests.github_fixtures import POSTED_REVIEWS, mock_github_client


def test_fetch_pull_request_snapshot() -> None:
    client = mock_github_client()
    snapshot = client.fetch_pull_request_snapshot("acme", "api", 12)
    assert snapshot.pull_request.title == "Harden authentication"
    assert snapshot.pull_request.head_sha == "abc123def456"
    assert snapshot.pull_request.source_branch == "feature/auth"
    assert snapshot.pull_request.target_branch == "main"
    assert len(snapshot.changed_files) == 1
    assert "user_service.py" in snapshot.diff
    paths, truncated = client.get_git_tree("acme", "api", snapshot.pull_request.head_sha)
    assert truncated is False
    assert "pyproject.toml" in paths
    text = client.get_text_file("acme", "api", "pyproject.toml", ref=snapshot.pull_request.head_sha)
    assert text is not None and "fastapi" in text


def test_create_pull_request_review_posts_comment_event() -> None:
    client = mock_github_client()
    payload = client.create_pull_request_review(
        "acme",
        "api",
        12,
        commit_sha="abc123def456",
        body="summary",
        comments=[{"path": "backend/services/user_service.py", "line": 11, "side": "RIGHT", "body": "note"}],
        event="COMMENT",
    )
    assert payload["id"] == 555
    assert POSTED_REVIEWS[0]["event"] == "COMMENT"
    assert POSTED_REVIEWS[0]["commit_id"] == "abc123def456"


def test_github_client_raises_on_http_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, json={"message": "boom"}))
    client = GitHubClient(token="t", http_client=httpx.Client(transport=transport))
    try:
        client.get_pull_request("acme", "api", 12)
    except GitHubAPIError as exc:
        assert exc.status_code == 500
        return
    raise AssertionError("expected GitHubAPIError")


def test_create_app_jwt_is_rs256() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    token = create_app_jwt("12345", pem)
    public = key.public_key()
    claims = jwt.decode(token, public, algorithms=["RS256"], options={"verify_exp": False})
    assert claims["iss"] == "12345"


def test_fetch_installation_token() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Bearer ")
        if request.url.path == "/repos/acme/api/installation":
            return httpx.Response(200, json={"id": 77})
        if request.url.path == "/app/installations/77/access_tokens":
            return httpx.Response(201, json={"token": "ghs_install_token"})
        return httpx.Response(404)

    settings = Settings(
        github_app_id="12345",
        github_private_key=pem,
        github_token=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
    )
    token = fetch_installation_token(
        settings,
        "acme",
        "api",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert token == "ghs_install_token"
