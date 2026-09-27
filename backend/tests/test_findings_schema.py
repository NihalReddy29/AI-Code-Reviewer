"""Structured finding schema tests. No LLM calls."""

import pytest
from pydantic import ValidationError

from app.schemas.findings import FindingCategory, FindingSeverity, ReviewFinding, StructuredReview


def test_finding_rejects_invented_severity() -> None:
    with pytest.raises(ValidationError):
        ReviewFinding(
            file="app.py",
            line=1,
            category=FindingCategory.BUG,
            severity="URGENT",  # type: ignore[arg-type]
            title="x",
            description="x",
            evidence="x",
            suggested_fix="x",
            confidence=0.9,
        )


def test_finding_rejects_invented_category() -> None:
    with pytest.raises(ValidationError):
        ReviewFinding(
            file="app.py",
            line=1,
            category="STYLE",  # type: ignore[arg-type]
            severity=FindingSeverity.LOW,
            title="x",
            description="x",
            evidence="x",
            suggested_fix="x",
            confidence=0.5,
        )


def test_structured_review_round_trip() -> None:
    review = StructuredReview.model_validate(
        {
            "summary": "One security issue.",
            "findings": [
                {
                    "file": "backend/services/user_service.py",
                    "line": 11,
                    "category": "SECURITY",
                    "severity": "HIGH",
                    "title": "Unparameterized query",
                    "description": "User id is interpolated into SQL.",
                    "evidence": "query = 'SELECT * FROM users WHERE id = %s'",
                    "suggested_fix": "Pass bound parameters to execute.",
                    "confidence": 0.94,
                }
            ],
        }
    )
    assert review.findings[0].severity is FindingSeverity.HIGH
    assert review.findings[0].category is FindingCategory.SECURITY
