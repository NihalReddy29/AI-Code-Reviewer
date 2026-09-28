"""Analytics endpoints providing summary metrics and trends."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database.models import PullRequest, Repository, ReviewRun
from app.database.session import get_db
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    AnalyticsTrendsResponse,
    DailyTrendPoint,
    FileFindingStat,
)
from app.services.scoring import calculate_review_score

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    repository: str | None = Query(default=None, description="Filter metrics by repository full_name (e.g. acme/api)"),
    db: Session = Depends(get_db),
) -> AnalyticsOverviewResponse:
    """Return aggregated review metrics, finding breakdowns, and top issue-heavy files.

    The overall score is a heuristic quality indicator from 0 to 100 based on verified findings.
    """
    stmt = (
        select(ReviewRun)
        .join(PullRequest)
        .join(Repository)
        .options(
            selectinload(ReviewRun.findings),
        )
    )
    if repository:
        stmt = stmt.where(Repository.full_name == repository)

    runs = db.scalars(stmt).unique().all()
    if not runs:
        return AnalyticsOverviewResponse()

    total_reviews = len(runs)
    scores = [calculate_review_score(r.findings) for r in runs]
    average_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    severity_counts = Counter({"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0})
    category_counts: Counter[str] = Counter()
    file_counts: Counter[str] = Counter()

    verified_count = 0
    rejected_count = 0
    unreviewed_count = 0
    total_findings = 0
    total_test_failures = 0

    for run in runs:
        if isinstance(run.test_results, dict):
            failed = run.test_results.get("failed") or 0
            errs = run.test_results.get("errors") or 0
            total_test_failures += (failed + errs)

        for finding in run.findings:
            total_findings += 1
            if finding.verified is True:
                verified_count += 1
            elif finding.verified is False:
                rejected_count += 1
            else:
                unreviewed_count += 1

            sev = getattr(finding.severity, "value", str(finding.severity)).upper()
            severity_counts[sev] += 1

            cat = getattr(finding.category, "value", str(finding.category))
            category_counts[cat] += 1

            if finding.file_path:
                file_counts[finding.file_path] += 1

    top_files = [
        FileFindingStat(file=file_path, count=count)
        for file_path, count in file_counts.most_common(10)
    ]

    return AnalyticsOverviewResponse(
        total_reviews=total_reviews,
        total_findings=total_findings,
        average_score=average_score,
        score_label="heuristic",
        verified_count=verified_count,
        rejected_count=rejected_count,
        unreviewed_count=unreviewed_count,
        total_test_failures=total_test_failures,
        findings_by_severity=dict(severity_counts),
        findings_by_category=dict(category_counts),
        top_files_by_findings=top_files,
    )


@router.get("/trends", response_model=AnalyticsTrendsResponse)
def get_analytics_trends(
    days: int = Query(default=30, ge=1, le=365, description="Number of past days to return"),
    repository: str | None = Query(default=None, description="Filter metrics by repository full_name"),
    db: Session = Depends(get_db),
) -> AnalyticsTrendsResponse:
    """Return chronological per-day review and finding volume trends."""
    now_utc = datetime.now(UTC)
    start_date = (now_utc - timedelta(days=days - 1)).date()

    # Pre-populate all days in range with zero counts
    daily_map: dict[str, dict] = {}
    for i in range(days):
        day_str = (start_date + timedelta(days=i)).isoformat()
        daily_map[day_str] = {"reviews": 0, "findings": 0, "scores": []}

    stmt = (
        select(ReviewRun)
        .join(PullRequest)
        .join(Repository)
        .options(
            selectinload(ReviewRun.findings),
        )
    )
    if repository:
        stmt = stmt.where(Repository.full_name == repository)

    runs = db.scalars(stmt).unique().all()

    for run in runs:
        if not run.created_at:
            continue
        created_dt = run.created_at
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=UTC)
        day_str = created_dt.astimezone(UTC).date().isoformat()

        if day_str in daily_map:
            daily_map[day_str]["reviews"] += 1
            daily_map[day_str]["findings"] += len(run.findings)
            daily_map[day_str]["scores"].append(calculate_review_score(run.findings))

    trend_points: list[DailyTrendPoint] = []
    for day_str in sorted(daily_map.keys()):
        data = daily_map[day_str]
        scores = data["scores"]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        trend_points.append(
            DailyTrendPoint(
                date=day_str,
                review_count=data["reviews"],
                finding_count=data["findings"],
                average_score=avg_score,
            )
        )

    return AnalyticsTrendsResponse(days=days, trends=trend_points)
