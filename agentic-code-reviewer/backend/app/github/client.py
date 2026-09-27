from __future__ import annotations

from typing import Any

import httpx


class GitHubClient:
    """Thin wrapper around GitHub API calls used by the review pipeline."""

    def __init__(self, token: str | None = None, base_url: str = 'https://api.github.com') -> None:
        self.token = token
        self.base_url = base_url.rstrip('/')

    def headers(self) -> dict[str, str]:
        headers = {'Accept': 'application/vnd.github+json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        url = f'{self.base_url}/repos/{owner}/{repo}'
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers())
            response.raise_for_status()
            return response.json()
