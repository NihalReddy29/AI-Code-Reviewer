"""Pydantic models for GitHub payloads, diffs, and pull-request snapshots."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DiffHunk(BaseModel):
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added_line_numbers: list[int] = Field(default_factory=list)
    removed_line_numbers: list[int] = Field(default_factory=list)
    header: str | None = None


class ChangedFile(BaseModel):
    path: str
    previous_path: str | None = None
    status: str
    additions: int = 0
    deletions: int = 0
    sha: str | None = None
    patch: str | None = None
    hunks: list[DiffHunk] = Field(default_factory=list)
    language: str | None = None
    kind: str | None = None
    is_test: bool = False
    related_paths: list[str] = Field(default_factory=list)
    hunk_count: int = 0
    sensitive_areas: list[str] = Field(default_factory=list)


class PullRequestRef(BaseModel):
    owner: str
    repo: str
    number: int
    title: str
    author: str | None = None
    source_branch: str | None = None
    target_branch: str | None = None
    head_sha: str
    base_sha: str | None = None
    html_url: str | None = None
    github_repo_id: int | None = None
    default_branch: str | None = None
    body: str | None = None


class PullRequestSnapshot(BaseModel):
    pull_request: PullRequestRef
    changed_files: list[ChangedFile]
    diff: str


class WebhookRepository(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    full_name: str
    default_branch: str | None = None
    html_url: str | None = None


class WebhookPullRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: int
    title: str = ""
    html_url: str | None = None
    user: dict | None = None
    head: dict
    base: dict

    @field_validator("number")
    @classmethod
    def number_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("pull request number must be positive")
        return value


class GitHubWebhookPayload(BaseModel):
    """Subset of a GitHub webhook body. Unknown fields are discarded."""

    model_config = ConfigDict(extra="ignore")

    action: str | None = None
    number: int | None = None
    pull_request: WebhookPullRequest | None = None
    repository: WebhookRepository | None = None
    zen: str | None = None


REVIEWABLE_PULL_REQUEST_ACTIONS = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})

WebhookEvent = Literal["ping", "pull_request", "ignored"]
