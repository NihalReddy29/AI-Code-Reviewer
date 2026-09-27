"""GitHub REST API client and GitHub App authentication."""

from __future__ import annotations

import time
from base64 import b64decode
from urllib.parse import quote

import httpx
import jwt

from app.core.config import Settings, get_settings
from app.core.logging import get_logger, log_event
from app.analyzers.diff import changed_file_from_github
from app.schemas.github import ChangedFile, PullRequestRef, PullRequestSnapshot

logger = get_logger(__name__)


class GitHubError(RuntimeError):
    """Raised when GitHub authentication or API access fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubAuthError(GitHubError):
    pass


class GitHubAPIError(GitHubError):
    pass


def normalize_private_key(raw: str) -> str:
    """Accept PEM text that was stored with escaped newlines in an env var."""

    key = raw.strip()
    if "\\n" in key and "\n" not in key:
        key = key.replace("\\n", "\n")
    return key


def create_app_jwt(app_id: str, private_key: str, *, now: int | None = None) -> str:
    issued_at = (now or int(time.time())) - 60
    payload = {"iat": issued_at, "exp": issued_at + 9 * 60, "iss": app_id}
    return jwt.encode(payload, normalize_private_key(private_key), algorithm="RS256")


class GitHubClient:
    """Synchronous GitHub REST client. Tokens are never written to logs."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://api.github.com",
        timeout_seconds: float = 30,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self.base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        return {
            "Accept": accept,
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-code-reviewer",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        accept: str | None = None,
        json_body: dict | None = None,
    ) -> httpx.Response:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        try:
            kwargs: dict[str, object] = {"headers": self._headers(accept or "application/vnd.github+json")}
            if json_body is not None:
                kwargs["json"] = json_body
            response = self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            logger.exception("github_http_error")
            raise GitHubAPIError(f"GitHub request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            log_event(
                logger,
                "github_api_error",
                status_code=response.status_code,
                path=path.split("?")[0],
            )
            raise GitHubAPIError(
                f"GitHub API returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        return response

    def get_pull_request(self, owner: str, repo: str, number: int) -> PullRequestRef:
        data = self._request("GET", f"/repos/{owner}/{repo}/pulls/{number}").json()
        head = data.get("head") or {}
        base = data.get("base") or {}
        user = data.get("user") or {}
        repository = data.get("base", {}).get("repo") or {}
        return PullRequestRef(
            owner=owner,
            repo=repo,
            number=int(data["number"]),
            title=str(data.get("title") or ""),
            author=user.get("login"),
            source_branch=head.get("ref"),
            target_branch=base.get("ref"),
            head_sha=str(head.get("sha") or ""),
            base_sha=base.get("sha"),
            html_url=data.get("html_url"),
            github_repo_id=repository.get("id"),
            default_branch=repository.get("default_branch"),
            body=data.get("body"),
        )

    def list_pull_request_files(self, owner: str, repo: str, number: int) -> list[ChangedFile]:
        files: list[ChangedFile] = []
        page = 1
        while True:
            response = self._request(
                "GET",
                f"/repos/{owner}/{repo}/pulls/{number}/files?per_page=100&page={page}",
            )
            batch = response.json()
            if not isinstance(batch, list) or not batch:
                break
            files.extend(changed_file_from_github(item) for item in batch)
            if len(batch) < 100:
                break
            page += 1
            if page > 50:
                raise GitHubAPIError("pull request file listing exceeded pagination limit")
        return files

    def get_pull_request_diff(self, owner: str, repo: str, number: int) -> str:
        response = self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{number}",
            accept="application/vnd.github.diff",
        )
        return response.text

    def fetch_pull_request_snapshot(self, owner: str, repo: str, number: int) -> PullRequestSnapshot:
        pull_request = self.get_pull_request(owner, repo, number)
        if not pull_request.head_sha:
            raise GitHubAPIError("pull request is missing head SHA")
        changed_files = self.list_pull_request_files(owner, repo, number)
        try:
            diff = self.get_pull_request_diff(owner, repo, number)
        except GitHubAPIError:
            logger.exception("github_diff_fetch_failed")
            diff = "\n".join(item.patch or "" for item in changed_files if item.patch)
        log_event(
            logger,
            "pull_request_fetched",
            repository=f"{owner}/{repo}",
            pull_request=number,
            commit_sha=pull_request.head_sha,
            changed_files=len(changed_files),
        )
        return PullRequestSnapshot(pull_request=pull_request, changed_files=changed_files, diff=diff)

    def get_git_tree(self, owner: str, repo: str, commit_sha: str, *, recursive: bool = True) -> tuple[list[str], bool]:
        """Return blob paths at a commit. Does not clone the repository."""

        suffix = "?recursive=1" if recursive else ""
        data = self._request("GET", f"/repos/{owner}/{repo}/git/trees/{commit_sha}{suffix}").json()
        truncated = bool(data.get("truncated"))
        paths: list[str] = []
        for entry in data.get("tree") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") != "blob":
                continue
            path = entry.get("path")
            if isinstance(path, str) and path:
                paths.append(path)
            if len(paths) >= 10_000:
                truncated = True
                break
        log_event(
            logger,
            "repository_tree_fetched",
            repository=f"{owner}/{repo}",
            commit_sha=commit_sha,
            file_count=len(paths),
            truncated=truncated,
        )
        return paths, truncated

    def get_text_file(self, owner: str, repo: str, path: str, *, ref: str, max_bytes: int = 262_144) -> str | None:
        """Fetch a small text file at `ref`. Returns None if missing or not decodable text."""

        try:
            data = self._request("GET", f"/repos/{owner}/{repo}/contents/{quote(path, safe='/')}?ref={ref}").json()
        except GitHubAPIError as exc:
            if exc.status_code in {404, 403}:
                return None
            raise
        if not isinstance(data, dict) or data.get("type") != "file":
            return None
        size = int(data.get("size") or 0)
        if size > max_bytes:
            log_event(logger, "manifest_skipped_too_large", path=path, size=size)
            return None
        encoding = data.get("encoding")
        content = data.get("content")
        if encoding != "base64" or not isinstance(content, str):
            if isinstance(data.get("download_url"), str):
                return None
            return None
        try:
            raw = b64decode(content)
        except ValueError:
            logger.exception("manifest_base64_decode_failed")
            return None
        return raw.decode("utf-8", errors="replace")

    def create_pull_request_review(
        self,
        owner: str,
        repo: str,
        number: int,
        *,
        commit_sha: str,
        body: str,
        comments: list[dict],
        event: str = "COMMENT",
    ) -> dict:
        """Create a PR review. `event` is COMMENT (does not approve or request changes)."""

        payload = {
            "commit_id": commit_sha,
            "body": body,
            "event": event,
            "comments": comments,
        }
        data = self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{number}/reviews",
            json_body=payload,
        ).json()
        review_id = data.get("id") if isinstance(data, dict) else None
        log_event(
            logger,
            "github_review_posted",
            repository=f"{owner}/{repo}",
            pull_request=number,
            github_review_id=review_id,
            comment_count=len(comments),
        )
        return data if isinstance(data, dict) else {}


def fetch_installation_token(
    settings: Settings,
    owner: str,
    repo: str,
    *,
    http_client: httpx.Client | None = None,
) -> str:
    if not settings.github_app_id or settings.github_private_key is None:
        raise GitHubAuthError("GitHub App credentials are not configured")
    private_key = settings.github_private_key.get_secret_value()
    app_jwt = create_app_jwt(settings.github_app_id, private_key)
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=settings.github_timeout_seconds)
    try:
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-code-reviewer",
        }
        installation = client.get(
            f"{settings.github_api_url.rstrip('/')}/repos/{owner}/{repo}/installation",
            headers=headers,
        )
        if installation.status_code >= 400:
            raise GitHubAuthError(
                f"Failed to resolve GitHub App installation (HTTP {installation.status_code})",
                status_code=installation.status_code,
            )
        installation_id = installation.json().get("id")
        if not installation_id:
            raise GitHubAuthError("GitHub installation response did not include an id")
        token_response = client.post(
            f"{settings.github_api_url.rstrip('/')}/app/installations/{installation_id}/access_tokens",
            headers=headers,
        )
        if token_response.status_code >= 400:
            raise GitHubAuthError(
                f"Failed to create GitHub installation token (HTTP {token_response.status_code})",
                status_code=token_response.status_code,
            )
        token = token_response.json().get("token")
        if not token:
            raise GitHubAuthError("GitHub installation token response was empty")
        return str(token)
    finally:
        if owns_client:
            client.close()


def build_github_client(
    owner: str,
    repo: str,
    *,
    settings: Settings | None = None,
    http_client: httpx.Client | None = None,
) -> GitHubClient:
    """Prefer a PAT when set; otherwise mint a GitHub App installation token."""

    settings = settings or get_settings()
    token = None
    if settings.github_token is not None:
        token = settings.github_token.get_secret_value().strip() or None
    if not token:
        token = fetch_installation_token(settings, owner, repo, http_client=http_client)
    return GitHubClient(
        token=token,
        base_url=settings.github_api_url,
        timeout_seconds=settings.github_timeout_seconds,
        http_client=http_client,
    )


def github_is_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    has_app = bool(
        settings.github_app_id
        and settings.github_private_key
        and settings.github_private_key.get_secret_value().strip()
    )
    has_token = bool(settings.github_token and settings.github_token.get_secret_value().strip())
    return has_app or has_token
