"""Shared GitHub API fixtures used by Phase 2 tests."""

from __future__ import annotations

import base64
import json

import httpx

from app.tools.github import GitHubClient
from app.tools.webhook import sign_payload

WEBHOOK_SECRET = "test-webhook-secret"

PR_JSON = {
    "number": 12,
    "title": "Harden authentication",
    "html_url": "https://github.com/acme/api/pull/12",
    "body": "Use parameterized queries.",
    "user": {"login": "dev"},
    "head": {"ref": "feature/auth", "sha": "abc123def456"},
    "base": {
        "ref": "main",
        "sha": "base111",
        "repo": {"id": 99, "default_branch": "main", "html_url": "https://github.com/acme/api"},
    },
}

FILE_PATCH = "@@ -10,4 +10,5 @@ def get_user(user_id):\n     query = 'SELECT * FROM users WHERE id = %s'\n-    return db.execute(query)\n+    return db.execute(query, (user_id,))\n"

FILES_JSON = [
    {
        "filename": "backend/services/user_service.py",
        "status": "modified",
        "additions": 1,
        "deletions": 1,
        "sha": "fileSha1",
        "patch": FILE_PATCH,
    }
]

UNIFIED_DIFF = (
    "diff --git a/backend/services/user_service.py b/backend/services/user_service.py\n"
    "--- a/backend/services/user_service.py\n"
    "+++ b/backend/services/user_service.py\n"
    f"{FILE_PATCH}\n"
)

TREE_PATHS = [
    "README.md",
    "pyproject.toml",
    "backend/services/user_service.py",
    "backend/tests/test_user_service.py",
    "backend/tests/conftest.py",
    ".github/workflows/ci.yml",
]

PYPROJECT_TOML = """
[project]
name = "api"
dependencies = ["fastapi>=0.115", "sqlalchemy"]

[tool.pytest.ini_options]
testpaths = ["backend/tests"]
""".strip()

USER_SERVICE_PY = (
    '"""User lookup helpers."""\n'
    + ("\n" * 8)
    + "def get_user(user_id):\n"
    + "    query = 'SELECT * FROM users WHERE id = %s'\n"
    + "    return db.execute(query, (user_id,))\n"
)

README_MD = """# API

Use parameterized queries in `get_user`.
"""

TEST_USER_SERVICE_PY = '''def test_get_user():
    assert get_user(1) is not None
'''

FILE_CONTENTS = {
    "pyproject.toml": PYPROJECT_TOML,
    "backend/services/user_service.py": USER_SERVICE_PY,
    "backend/tests/test_user_service.py": TEST_USER_SERVICE_PY,
    "README.md": README_MD,
}

TREE_JSON = {
    "truncated": False,
    "tree": [{"path": path, "type": "blob", "size": 100} for path in TREE_PATHS],
}

WEBHOOK_BODY = {
    "action": "opened",
    "number": 12,
    "pull_request": {
        "number": 12,
        "title": "Harden authentication",
        "html_url": "https://github.com/acme/api/pull/12",
        "user": {"login": "dev"},
        "head": {"ref": "feature/auth", "sha": "abc123def456"},
        "base": {"ref": "main", "sha": "base111"},
    },
    "repository": {
        "id": 99,
        "full_name": "acme/api",
        "default_branch": "main",
        "html_url": "https://github.com/acme/api",
    },
}


POSTED_REVIEWS: list[dict] = []


def github_mock_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    accept = request.headers.get("accept", "")
    if request.method == "POST" and path == "/repos/acme/api/pulls/12/reviews":
        payload = json.loads(request.content.decode("utf-8") or "{}")
        POSTED_REVIEWS.append(payload)
        return httpx.Response(
            200,
            json={"id": 555, "html_url": "https://github.com/acme/api/pull/12#pullrequestreview-555"},
        )
    path = request.url.path
    accept = request.headers.get("accept", "")
    if path == "/repos/acme/api/pulls/12" and "diff" in accept:
        return httpx.Response(200, text=UNIFIED_DIFF)
    if path == "/repos/acme/api/pulls/12/files":
        return httpx.Response(200, json=FILES_JSON)
    if path == "/repos/acme/api/pulls/12":
        return httpx.Response(200, json=PR_JSON)
    if path == "/repos/acme/api/git/trees/abc123def456":
        return httpx.Response(200, json=TREE_JSON)
    if path.startswith("/repos/acme/api/contents/"):
        file_path = path.removeprefix("/repos/acme/api/contents/")
        if file_path in FILE_CONTENTS:
            text = FILE_CONTENTS[file_path]
            encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
            return httpx.Response(
                200,
                json={"type": "file", "encoding": "base64", "size": len(text), "content": encoded},
            )
    return httpx.Response(404, json={"message": "Not Found"})


def mock_github_client() -> GitHubClient:
    POSTED_REVIEWS.clear()
    transport = httpx.MockTransport(github_mock_handler)
    return GitHubClient(token="test-token", http_client=httpx.Client(transport=transport))


def signed_headers(body: bytes, *, event: str = "pull_request", delivery: str = "delivery-1") -> dict[str, str]:
    return {
        "X-Hub-Signature-256": sign_payload(body, WEBHOOK_SECRET),
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }


def webhook_payload_bytes(overrides: dict | None = None) -> bytes:
    payload = json.loads(json.dumps(WEBHOOK_BODY))
    if overrides:
        payload.update(overrides)
    return json.dumps(payload).encode("utf-8")
