"""API schemas for repository and dependency analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RepositoryContextResponse(BaseModel):
    commit_sha: str
    truncated: bool = False
    primary_language: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    project_types: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    test_frameworks: list[str] = Field(default_factory=list)
    source_roots: list[str] = Field(default_factory=list)
    test_directories: list[str] = Field(default_factory=list)
    python_packages: list[str] = Field(default_factory=list)
    node_packages: list[str] = Field(default_factory=list)
    file_count: int = 0
