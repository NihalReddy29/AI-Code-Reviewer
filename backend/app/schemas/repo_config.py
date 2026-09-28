from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.findings import FindingCategory, FindingSeverity


class PathsConfig(BaseModel):
    ignore: list[str] = Field(default_factory=list, max_length=50)


class ToolsConfig(BaseModel):
    ruff: bool = True
    pyright: bool = True
    bandit: bool = True
    semgrep: bool = True
    pytest: bool = True


class ReviewConfig(BaseModel):
    min_severity: FindingSeverity = FindingSeverity.MEDIUM
    max_comments: int = Field(20, ge=1, le=50)
    categories: list[FindingCategory] | None = None
    guidelines: str = Field("", max_length=2000)

    @field_validator("min_severity", mode="before")
    @classmethod
    def coerce_severity(cls, value: object) -> FindingSeverity:
        """Accept valid severity strings; fall back to MEDIUM for anything else."""
        if isinstance(value, FindingSeverity):
            return value
        try:
            return FindingSeverity(str(value).upper())
        except ValueError:
            return FindingSeverity.MEDIUM

    @field_validator("categories", mode="before")
    @classmethod
    def coerce_categories(cls, value: object) -> list[FindingCategory] | None:
        """Accept valid category strings; drop invalid ones silently."""
        if value is None:
            return None
        if not isinstance(value, list):
            return None
        result: list[FindingCategory] = []
        for item in value:
            try:
                result.append(FindingCategory(str(item).upper()))
            except ValueError:
                pass
        return result or None


class RepoConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    version: int = 1
    paths: PathsConfig = Field(default_factory=PathsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)