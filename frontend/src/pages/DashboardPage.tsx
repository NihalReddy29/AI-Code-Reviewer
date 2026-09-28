import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ApiError,
  getAnalyticsOverview,
  getAnalyticsTrends,
  listRepositories,
  listReviews,
  triggerReview,
} from "../api";
import { Card } from "../components/common/Card";
import { EmptyState } from "../components/common/EmptyState";
import { ErrorState } from "../components/common/ErrorState";
import { LoadingState } from "../components/common/LoadingState";
import { ScoreRing } from "../components/common/ScoreRing";
import { formatWhen, shortSha } from "../lib/findings";
import type {
  AnalyticsOverview,
  DailyTrendPoint,
  ReviewSummary,
} from "../types";

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "#EF4444",
  HIGH: "#F87171",
  MEDIUM: "#F59E0B",
  LOW: "#10B981",
  INFO: "#60A5FA",
};

export default function DashboardPage() {
  const navigate = useNavigate();

  // State
  const [repositories, setRepositories] = useState<string[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [trends, setTrends] = useState<DailyTrendPoint[]>([]);
  const [recentReviews, setRecentReviews] = useState<ReviewSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Trigger form state
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [prNumber, setPrNumber] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  async function loadData(repoFilter: string) {
    setLoading(true);
    setError(null);
    try {
      const [reposData, overviewData, trendsData, reviewsData] = await Promise.all([
        listRepositories().catch(() => []),
        getAnalyticsOverview(repoFilter ? { repository: repoFilter } : undefined),
        getAnalyticsTrends(repoFilter ? { days: 14, repository: repoFilter } : { days: 14 }),
        listReviews(repoFilter ? { repository: repoFilter } : undefined),
      ]);
      setRepositories(reposData);
      setOverview(overviewData);
      setTrends(trendsData.trends);
      setRecentReviews(reviewsData.slice(0, 5));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData(selectedRepo);
  }, [selectedRepo]);

  async function onTrigger(event: FormEvent) {
    event.preventDefault();
    const number = Number(prNumber);
    if (!owner.trim() || !repo.trim() || !Number.isInteger(number) || number <= 0) {
      setTriggerError("Owner, repository, and a positive pull request number are required.");
      return;
    }
    setSubmitting(true);
    setTriggerError(null);
    try {
      const created = await triggerReview(owner.trim(), repo.trim(), number);
      navigate(`/review/${created.review_run_id}`);
    } catch (err) {
      setTriggerError(err instanceof ApiError ? err.message : "Could not start review");
    } finally {
      setSubmitting(false);
    }
  }

  // Format severity data for BarChart
  const severityChartData = overview
    ? [
        { name: "Critical", key: "CRITICAL", count: overview.findings_by_severity["CRITICAL"] || 0 },
        { name: "High", key: "HIGH", count: overview.findings_by_severity["HIGH"] || 0 },
        { name: "Medium", key: "MEDIUM", count: overview.findings_by_severity["MEDIUM"] || 0 },
        { name: "Low", key: "LOW", count: overview.findings_by_severity["LOW"] || 0 },
        { name: "Info", key: "INFO", count: overview.findings_by_severity["INFO"] || 0 },
      ]
    : [];

  const bugCount = overview?.findings_by_category["BUG"] ?? 0;
  const securityCount = overview?.findings_by_category["SECURITY"] ?? 0;
  const verifiedCount = overview?.verified_count ?? 0;
  const testFailures = overview?.total_test_failures ?? 0;

  return (
    <div className="dashboard-page-container">
      {/* Top Banner / Filter Bar */}
      <div className="dashboard-top-banner">
        <div className="dashboard-title-area">
          <h1>Analytics Dashboard</h1>
          <p>Real-time review quality metrics, trends, and security posture</p>
        </div>

        <div className="dashboard-controls">
          <label htmlFor="repo-filter" style={{ display: "none" }}>
            Repository Filter
          </label>
          <select
            id="repo-filter"
            className="repo-selector"
            value={selectedRepo}
            onChange={(e) => setSelectedRepo(e.target.value)}
            aria-label="Filter by repository"
          >
            <option value="">All Repositories</option>
            {repositories.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => void loadData(selectedRepo)}
            aria-label="Refresh dashboard data"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && <ErrorState message={error} onRetry={() => void loadData(selectedRepo)} />}

      {loading && !overview ? (
        <LoadingState message="Aggregating code review analytics..." />
      ) : overview ? (
        <>
          {/* Health Score Hero Card */}
          <Card className="score-hero-card">
            <div className="score-hero-container">
              <ScoreRing score={overview.average_score} size={150} strokeWidth={12} label="Average Score" />
              <div className="score-hero-text">
                <h2 className="score-hero-title">
                  {overview.average_score >= 80
                    ? "Healthy Code Quality"
                    : overview.average_score >= 50
                    ? "Attention Needed"
                    : "Action Required"}
                </h2>
                <p className="score-hero-desc">
                  Based on verified findings across {overview.total_reviews} pull request review run(s). Deductions
                  prioritize critical security vulnerabilities and functional bugs.
                </p>
                <div className="score-hero-stats">
                  <div className="score-stat-item">
                    <span className="score-stat-value">{overview.total_reviews}</span>
                    <span className="score-stat-label">Total Reviews</span>
                  </div>
                  <div className="score-stat-item">
                    <span className="score-stat-value">{overview.total_findings}</span>
                    <span className="score-stat-label">Findings Identified</span>
                  </div>
                  <div className="score-stat-item">
                    <span className="score-stat-value">
                      {overview.total_findings > 0
                        ? `${Math.round((overview.verified_count / overview.total_findings) * 100)}%`
                        : "0%"}
                    </span>
                    <span className="score-stat-label">Verification Rate</span>
                  </div>
                </div>
              </div>
            </div>
          </Card>

          {/* 4 Summary Metric Cards */}
          <div className="summary-cards-grid">
            <div className="metric-card">
              <div className="metric-icon-wrap bug" aria-hidden="true">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="8" y="6" width="8" height="12" rx="4" />
                  <path d="M19 12h-3M8 12H5M18 6l-2.5 2M8.5 8L6 6M18 18l-2.5-2M8.5 16L6 18" />
                </svg>
              </div>
              <div className="metric-info">
                <span className="metric-val">{bugCount}</span>
                <span className="metric-lbl">Bugs Detected</span>
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-icon-wrap security" aria-hidden="true">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
              </div>
              <div className="metric-info">
                <span className="metric-val">{securityCount}</span>
                <span className="metric-lbl">Security Flaws</span>
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-icon-wrap verified" aria-hidden="true">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </div>
              <div className="metric-info">
                <span className="metric-val">{verifiedCount}</span>
                <span className="metric-lbl">Verified Findings</span>
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-icon-wrap tests" aria-hidden="true">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M10 2v7.31M14 9.3V1.99M8.5 2h7M14 9.3a6.5 6.5 0 11-4 0" />
                </svg>
              </div>
              <div className="metric-info">
                <span className="metric-val">{testFailures}</span>
                <span className="metric-lbl">Test Failures</span>
              </div>
            </div>
          </div>

          {/* Charts Row */}
          <div className="charts-grid">
            <Card
              title="Findings & Reviews Over Time"
              subtitle="14-day chronological activity"
              className="chart-card-wrap"
            >
              <div style={{ width: "100%", height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trends} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1F2C44" />
                    <XAxis
                      dataKey="date"
                      stroke="#64748B"
                      fontSize={11}
                      tickFormatter={(val: string) => val.slice(5)}
                    />
                    <YAxis stroke="#64748B" fontSize={11} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#111A2E",
                        borderColor: "#243556",
                        borderRadius: "8px",
                        color: "#F8FAFC",
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }} />
                    <Line
                      type="monotone"
                      dataKey="finding_count"
                      name="Findings"
                      stroke="#3B82F6"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="review_count"
                      name="Reviews"
                      stroke="#10B981"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card
              title="Severity Distribution"
              subtitle="Findings categorized by severity impact"
              className="chart-card-wrap"
            >
              <div style={{ width: "100%", height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={severityChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1F2C44" />
                    <XAxis dataKey="name" stroke="#64748B" fontSize={11} />
                    <YAxis stroke="#64748B" fontSize={11} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#111A2E",
                        borderColor: "#243556",
                        borderRadius: "8px",
                        color: "#F8FAFC",
                      }}
                    />
                    <Bar dataKey="count" name="Count" radius={[4, 4, 0, 0]}>
                      {severityChartData.map((entry) => (
                        <Cell key={`cell-${entry.key}`} fill={SEVERITY_COLORS[entry.key] || "#3B82F6"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          {/* Categories & Top Files Row */}
          <div className="charts-grid">
            <Card title="Category Breakdown" subtitle="Distribution across architectural areas">
              {Object.keys(overview.findings_by_category).length === 0 ? (
                <EmptyState title="No categories yet" message="Run a review to see categorized issues." />
              ) : (
                <div className="category-breakdown-grid">
                  {Object.entries(overview.findings_by_category).map(([cat, count]) => (
                    <div key={cat} className="category-chip">
                      <span className="category-name">{cat.toLowerCase().replace(/_/g, " ")}</span>
                      <span className="category-count">{count}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Top Hotspot Files" subtitle="Files with highest count of issues">
              {overview.top_files_by_findings.length === 0 ? (
                <EmptyState title="No file issues" message="No findings recorded for files yet." />
              ) : (
                <div className="top-files-list">
                  {overview.top_files_by_findings.map((item, idx) => (
                    <div key={item.file} className="top-file-row">
                      <span className="top-file-path" title={item.file}>
                        {idx + 1}. {item.file}
                      </span>
                      <span className="top-file-badge">{item.count} issue(s)</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          {/* Quick Review Trigger Form & Recent Runs */}
          <Card title="Run Code Review" subtitle="Trigger an on-demand review for any GitHub pull request">
            <form className="row" onSubmit={onTrigger} style={{ marginBottom: "1.25rem" }}>
              <label>
                Owner
                <input
                  value={owner}
                  onChange={(e) => setOwner(e.target.value)}
                  placeholder="e.g. acme"
                  required
                />
              </label>
              <label>
                Repository
                <input
                  value={repo}
                  onChange={(e) => setRepo(e.target.value)}
                  placeholder="e.g. api"
                  required
                />
              </label>
              <label>
                Pull Request #
                <input
                  value={prNumber}
                  onChange={(e) => setPrNumber(e.target.value)}
                  placeholder="e.g. 12"
                  inputMode="numeric"
                  required
                />
              </label>
              <button type="submit" disabled={submitting}>
                {submitting ? "Starting Review…" : "Trigger Review"}
              </button>
            </form>
            {triggerError && <p className="error">{triggerError}</p>}

            {recentReviews.length > 0 && (
              <div>
                <h4 style={{ margin: "1rem 0 0.5rem 0", fontSize: "0.95rem" }}>Recent Review Runs</h4>
                <div className="grid">
                  {recentReviews.map((item) => (
                    <Link key={item.id} className="review-link" to={`/review/${item.id}`}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <strong>
                          {item.repository}#{item.pull_request} · {item.title}
                        </strong>
                        {item.score != null && (
                          <span
                            style={{
                              fontSize: "0.8rem",
                              fontWeight: 700,
                              color: item.score >= 80 ? "#10B981" : item.score >= 50 ? "#F59E0B" : "#EF4444",
                            }}
                          >
                            Score: {item.score}
                          </span>
                        )}
                      </div>
                      <div className="badges">
                        <span className={`badge ${item.status}`}>{item.status}</span>
                        {item.posted_to_github ? <span className="badge verified">posted</span> : null}
                      </div>
                      <div className="meta">
                        <span>
                          {item.verified_count}/{item.finding_count} verified
                        </span>
                        <span>{shortSha(item.commit_sha)}</span>
                        <span>{formatWhen(item.created_at)}</span>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </>
      ) : (
        <EmptyState title="No analytics data" message="Trigger a review to populate the dashboard." />
      )}
    </div>
  );
}
