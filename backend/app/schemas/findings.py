"""Structured review findings. Severity and category are closed enums."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FindingCategory(StrEnum):
    BUG = "BUG"
    SECURITY = "SECURITY"
    PERFORMANCE = "PERFORMANCE"
    CODE_QUALITY = "CODE_QUALITY"
    MAINTAINABILITY = "MAINTAINABILITY"
    ERROR_HANDLING = "ERROR_HANDLING"
    TESTING = "TESTING"
    ARCHITECTURE = "ARCHITECTURE"
    PROJECT_CONVENTION = "PROJECT_CONVENTION"


class FindingSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class ReviewFinding(BaseModel):
    """Single LLM finding. Extra severity/category values are rejected."""

    file: str = Field(min_length=1)
    line: int | None = Field(default=None, ge=1)
    category: FindingCategory
    severity: FindingSeverity
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    suggested_fix: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    verified: bool | None = None
    verification_reason: str | None = None

    @field_validator("file")
    @classmethod
    def normalize_file(cls, value: str) -> str:
        return value.replace("\\", "/").lstrip("/")


class StructuredReview(BaseModel):
    summary: str = Field(min_length=1)
    findings: list[ReviewFinding] = Field(default_factory=list)


class FindingResponse(BaseModel):
    id: UUID
    file: str
    line: int | None
    category: FindingCategory
    severity: FindingSeverity
    title: str
    description: str
    evidence: str | None
    suggested_fix: str | None
    confidence: float
    verified: bool | None = None
    verification_reason: str | None = None


class FindingListResponse(BaseModel):
    review_run_id: UUID
    findings: list[FindingResponse]
