"""Pydantic schemas for dashboard analytics and trend metrics."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileFindingStat(BaseModel):
    file: str
    count: int


class AnalyticsOverviewResponse(BaseModel):
    """Overview metrics for the dashboard.

    All scores are calculated using the heuristic scoring formula based on verified findings.
    """

    total_reviews: int = Field(0, description="Total number of review runs recorded")
    total_findings: int = Field(0, description="Total number of findings across all runs")
    average_score: float = Field(0.0, description="Average heuristic quality score (0-100)")
    score_label: str = Field("heuristic", description="Scoring methodology label")
    verified_count: int = Field(0, description="Count of findings confirmed by verification")
    rejected_count: int = Field(0, description="Count of findings rejected by verification")
    unreviewed_count: int = Field(0, description="Count of findings not yet verified")
    total_test_failures: int = Field(0, description="Total test failures across review runs")
    findings_by_severity: dict[str, int] = Field(
        default_factory=lambda: {
            "CRITICAL": 0,
            "HIGH": 0,
            "MEDIUM": 0,
            "LOW": 0,
            "INFO": 0,
        },
        description="Finding counts grouped by severity",
    )
    findings_by_category: dict[str, int] = Field(
        default_factory=dict,
        description="Finding counts grouped by category",
    )
    top_files_by_findings: list[FileFindingStat] = Field(
        default_factory=list,
        description="Top 10 files with the most findings",
    )


class DailyTrendPoint(BaseModel):
    date: str = Field(description="ISO date string YYYY-MM-DD")
    review_count: int = Field(0, description="Number of reviews initiated on this date")
    finding_count: int = Field(0, description="Total findings identified on this date")
    average_score: float = Field(0.0, description="Average heuristic score of reviews on this date")


class AnalyticsTrendsResponse(BaseModel):
    days: int = Field(30, description="Number of past days included in the trend")
    trends: list[DailyTrendPoint] = Field(
        default_factory=list,
        description="Chronological daily data points",
    )
