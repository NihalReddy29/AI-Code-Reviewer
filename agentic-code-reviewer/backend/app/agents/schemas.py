from __future__ import annotations

from pydantic import BaseModel, Field


class ReviewFinding(BaseModel):
    rule_id: str = Field(..., description='Identifier for the finding')
    message: str = Field(..., description='Human-readable reason for the finding')
    severity: str = Field(default='medium', description='Severity level')
    file: str | None = Field(default=None, description='Path to the relevant file')
