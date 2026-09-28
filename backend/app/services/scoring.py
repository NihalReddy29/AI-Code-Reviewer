"""Heuristic scoring for code reviews.

Calculates a 0-100 quality score based on verified findings:
  score = max(0, 100 - (critical*15 + high*8 + medium*3 + low*1))
"""

from __future__ import annotations

from typing import Any, Iterable

# Named penalty weights for verified findings by severity
CRITICAL_WEIGHT: int = 15
HIGH_WEIGHT: int = 8
MEDIUM_WEIGHT: int = 3
LOW_WEIGHT: int = 1
INFO_WEIGHT: int = 0

BASE_SCORE: int = 100


def calculate_review_score(findings: Iterable[Any]) -> int:
    """Calculate a heuristic review score from 0 to 100.

    Only verified findings (verified is True) contribute penalties to the score.
    Returns 100 if there are no verified findings.
    """
    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0
    info_count = 0

    for item in findings:
        # Support both ORM/Pydantic models and plain dictionaries
        if isinstance(item, dict):
            verified = item.get("verified")
            severity = str(item.get("severity", "")).upper()
        else:
            verified = getattr(item, "verified", None)
            severity_attr = getattr(item, "severity", "")
            # severity may be a FindingSeverity enum or string
            severity = getattr(severity_attr, "value", str(severity_attr)).upper()

        if verified is not True:
            continue

        if severity == "CRITICAL":
            critical_count += 1
        elif severity == "HIGH":
            high_count += 1
        elif severity == "MEDIUM":
            medium_count += 1
        elif severity == "LOW":
            low_count += 1
        elif severity == "INFO":
            info_count += 1

    penalty = (
        critical_count * CRITICAL_WEIGHT
        + high_count * HIGH_WEIGHT
        + medium_count * MEDIUM_WEIGHT
        + low_count * LOW_WEIGHT
        + info_count * INFO_WEIGHT
    )

    return max(0, BASE_SCORE - penalty)
