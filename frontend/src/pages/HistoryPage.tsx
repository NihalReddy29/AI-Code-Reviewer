import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listReviews } from "../api";
import { Card } from "../components/common/Card";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { ScoreRing } from "../components/common/ScoreRing";
import { formatWhen, shortSha } from "../lib/findings";
import type { ReviewSummary } from "../types";

const STATUS_STYLE: Record<string, string> = {
  completed: "badge badge--green",
  running: "badge badge--blue",
  failed: "badge badge--red",
  pending: "badge badge--muted",
};

function getScoreInfo(score: number | null | undefined): {
  grade: string;
  gradeClass: string;
} {
  if (score == null) {
    return { grade: "Unrated", gradeClass: "history-score-grade--unrated" };
  }
  if (score >= 80) {
    return { grade: "Healthy", gradeClass: "history-score-grade--healthy" };
  }
  if (score >= 50) {
    return { grade: "Moderate", gradeClass: "history-score-grade--moderate" };
  }
  return { grade: "Critical", gradeClass: "history-score-grade--critical" };
}

function HistoryRow({ review }: { review: ReviewSummary }) {
  const cls = STATUS_STYLE[review.status] ?? "badge badge--muted";
  const scoreInfo = getScoreInfo(review.score);

  return (
    <tr className="history-row">
      <td className="history-cell">
        <Link to={`/review/${review.id}`} className="history-link">
          {review.repository}
        </Link>
        <span className="history-meta">PR #{review.pull_request}</span>
      </td>
      <td className="history-cell">
        <span className="code-chip">{shortSha(review.commit_sha)}</span>
      </td>
      <td className="history-cell history-cell--title">{review.title || "—"}</td>
      <td className="history-cell">
        <span className={cls}>{review.status}</span>
      </td>
      <td className="history-cell history-cell--score">
        <div className="history-score-cell">
          <ScoreRing
            score={review.score}
            size={38}
            strokeWidth={3.5}
            compact
          />
          <div className="history-score-text">
            <span className={`history-score-grade ${scoreInfo.gradeClass}`}>
              {scoreInfo.grade}
            </span>
            <span className="history-score-sub">
              {review.score != null ? `${Math.round(review.score)}/100` : "—"}
            </span>
          </div>
        </div>
      </td>
      <td className="history-cell">
        <span className="severity-summary">
          {review.finding_count > 0 ? (
            <>
              <span className="sev-dot sev-dot--critical" />
              {review.finding_count} findings
            </>
          ) : (
            <span className="badge badge--green">Clean</span>
          )}
        </span>
      </td>
      <td className="history-cell history-cell--date">{formatWhen(review.created_at)}</td>
      <td className="history-cell">
        {review.execution_time_ms != null
          ? `${(review.execution_time_ms / 1000).toFixed(1)}s`
          : "—"}
      </td>
    </tr>
  );
}

export default function HistoryPage() {
  const [reviews, setReviews] = useState<ReviewSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [repoFilter, setRepoFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    listReviews()
      .then(setReviews)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const repos = ["all", ...Array.from(new Set(reviews.map((r) => r.repository))).sort()];
  const statuses = ["all", ...Array.from(new Set(reviews.map((r) => r.status))).sort()];

  const filtered = reviews.filter((r) => {
    if (repoFilter !== "all" && r.repository !== repoFilter) return false;
    if (statusFilter !== "all" && r.status !== statusFilter) return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      if (
        !r.repository.toLowerCase().includes(q) &&
        !r.commit_sha.toLowerCase().includes(q) &&
        !(r.title ?? "").toLowerCase().includes(q) &&
        !(r.author ?? "").toLowerCase().includes(q)
      )
        return false;
    }
    return true;
  });

  if (loading) return <LoadingState message="Loading history…" />;
  if (error) return <ErrorState message={error} />;

  return (
    <div className="history-layout">
      <div className="page-toolbar">
        <div className="toolbar-left">
          <h1 className="page-title">Review History</h1>
          <span className="page-subtitle">{filtered.length} review runs</span>
        </div>
      </div>

      <Card>
        <div className="filter-bar">
          <input
            id="history-search"
            type="search"
            className="search-input"
            placeholder="Search repo, SHA, title, author…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="filter-group">
            <span className="filter-label">Repository</span>
            <select
              id="history-repo-filter"
              className="select-input select-input--sm"
              value={repoFilter}
              onChange={(e) => setRepoFilter(e.target.value)}
            >
              {repos.map((r) => (
                <option key={r} value={r}>
                  {r === "all" ? "All repositories" : r}
                </option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <span className="filter-label">Status</span>
            {statuses.map((s) => (
              <button
                key={s}
                id={`history-status-${s}`}
                className={`filter-btn${statusFilter === s ? " filter-btn--active" : ""}`}
                onClick={() => setStatusFilter(s)}
              >
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {filtered.length === 0 ? (
        <EmptyState
          icon="📜"
          title="No reviews found"
          description="Trigger a review from the Code Review page, or adjust your filters."
        />
      ) : (
        <div className="table-card">
          <table className="history-table">
            <thead>
              <tr>
                <th>Repository</th>
                <th>Commit</th>
                <th>Title</th>
                <th>Status</th>
                <th>Score</th>
                <th>Findings</th>
                <th>Started</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <HistoryRow key={r.id} review={r} />
              ))}
            </tbody>
          </table>
          <div className="table-footer">
            Showing {filtered.length} of {reviews.length} reviews
          </div>
        </div>
      )}
    </div>
  );
}
