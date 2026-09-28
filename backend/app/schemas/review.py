"""API schemas for review ingestion and stored review runs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.analysis import RepositoryContextResponse
from app.schemas.findings import FindingResponse
from app.schemas.github import ChangedFile
from app.schemas.rag import RetrievedChunk
from app.schemas.static_analysis import StaticAnalysisReport
from app.schemas.tests import TestRunReport


class ReviewIngestResponse(BaseModel):
    review_run_id: UUID
    status: str
    duplicate: bool = False
    repository: str
    pull_request: int
    commit_sha: str
    changed_file_count: int = 0
    trigger: str


class ReviewRunResponse(BaseModel):
    id: UUID
    status: str
    trigger: str
    commit_sha: str
    repository: str
    pull_request: int
    title: str
    author: str | None = None
    source_branch: str | None = None
    target_branch: str | None = None
    changed_files: list[ChangedFile] = Field(default_factory=list)
    repository_context: RepositoryContextResponse | None = None
    retrieved_context: list[RetrievedChunk] = Field(default_factory=list)
    static_analysis: StaticAnalysisReport | None = None
    test_results: TestRunReport | None = None
    agent_trace: list[dict] = Field(default_factory=list)
    summary: str | None = None
    posted_to_github: bool = False
    github_review_id: int | None = None
    findings: list[FindingResponse] = Field(default_factory=list)
    errors: list | dict | None = None
    resolved_config: dict | None = None
    config_sha: str | None = None
    score: int | None = None
    execution_time_ms: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ReviewRunSummary(BaseModel):
    id: UUID
    status: str
    trigger: str
    commit_sha: str
    repository: str
    pull_request: int
    title: str
    author: str | None = None
    source_branch: str | None = None
    target_branch: str | None = None
    finding_count: int = 0
    verified_count: int = 0
    score: int | None = None
    posted_to_github: bool = False
    github_review_id: int | None = None
    execution_time_ms: int | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class ReviewListResponse(BaseModel):
    reviews: list[ReviewRunSummary] = Field(default_factory=list)


class RepositorySummary(BaseModel):
    id: UUID
    full_name: str
    default_branch: str | None = None
    html_url: str | None = None


class RepositoryListResponse(BaseModel):
    repositories: list[RepositorySummary]
