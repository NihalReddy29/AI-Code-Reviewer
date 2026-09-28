"""Unit tests for the heuristic scoring formula."""

from app.schemas.findings import FindingCategory, FindingSeverity, ReviewFinding
from app.services.scoring import (
    CRITICAL_WEIGHT,
    HIGH_WEIGHT,
    LOW_WEIGHT,
    MEDIUM_WEIGHT,
    calculate_review_score,
)


def _make_finding(severity: FindingSeverity, verified: bool | None = True) -> ReviewFinding:
    return ReviewFinding(
        file="app/main.py",
        line=10,
        category=FindingCategory.BUG,
        severity=severity,
        title="Test finding",
        description="A test issue",
        evidence="bad_code()",
        suggested_fix="good_code()",
        confidence=0.9,
        verified=verified,
    )


def test_perfect_score_when_no_findings():
    assert calculate_review_score([]) == 100


def test_unverified_findings_do_not_reduce_score():
    findings = [
        _make_finding(FindingSeverity.CRITICAL, verified=False),
        _make_finding(FindingSeverity.HIGH, verified=None),
    ]
    assert calculate_review_score(findings) == 100


def test_verified_findings_deduct_correct_weights():
    findings = [
        _make_finding(FindingSeverity.CRITICAL, verified=True),  # -15
        _make_finding(FindingSeverity.HIGH, verified=True),      # -8
        _make_finding(FindingSeverity.MEDIUM, verified=True),    # -3
        _make_finding(FindingSeverity.LOW, verified=True),       # -1
        _make_finding(FindingSeverity.INFO, verified=True),      # -0
    ]
    expected = 100 - (15 + 8 + 3 + 1)
    assert calculate_review_score(findings) == expected


def test_score_never_drops_below_zero():
    findings = [_make_finding(FindingSeverity.CRITICAL, verified=True) for _ in range(10)]
    assert calculate_review_score(findings) == 0


def test_works_with_dict_representations():
    raw_findings = [
        {"severity": "CRITICAL", "verified": True},
        {"severity": "HIGH", "verified": False},
        {"severity": "MEDIUM", "verified": True},
    ]
    expected = 100 - (CRITICAL_WEIGHT + MEDIUM_WEIGHT)
    assert calculate_review_score(raw_findings) == expected
