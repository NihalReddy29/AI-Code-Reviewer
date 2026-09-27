import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, getHealth, listReviews, triggerReview } from "../api";
import { formatWhen, shortSha } from "../lib/findings";
import type { HealthStatus, ReviewSummary } from "../types";

export default function DashboardPage() {
  const navigate = useNavigate();
  const [reviews, setReviews] = useState<ReviewSummary[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [prNumber, setPrNumber] = useState("");

  async function load(status?: string) {
    setLoading(true);
    setError(null);
    try {
      const [items, healthStatus] = await Promise.all([
        listReviews(status ? { status } : undefined),
        getHealth().catch(() => null),
      ]);
      setReviews(items);
      setHealth(healthStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load reviews");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(statusFilter);
  }, [statusFilter]);

  async function onTrigger(event: FormEvent) {
    event.preventDefault();
    const number = Number(prNumber);
    if (!owner.trim() || !repo.trim() || !Number.isInteger(number) || number <= 0) {
      setError("Owner, repository, and a positive pull request number are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await triggerReview(owner.trim(), repo.trim(), number);
      navigate(`/reviews/${created.review_run_id}`);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not start review";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <div className="panel">
        <h1>Review runs</h1>
        <p className="muted">
          API {health ? `${health.status} · ${health.database}` : "unreachable from this browser"}
        </p>
        <form className="row" onSubmit={onTrigger}>
          <label>
            Owner
            <input value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="acme" />
          </label>
          <label>
            Repository
            <input value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="api" />
          </label>
          <label>
            Pull request
            <input
              value={prNumber}
              onChange={(event) => setPrNumber(event.target.value)}
              placeholder="12"
              inputMode="numeric"
            />
          </label>
          <button type="submit" disabled={submitting}>
            {submitting ? "Starting…" : "Run review"}
          </button>
        </form>
      </div>

      <div className="panel">
        <div className="row">
          <label>
            Status
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
            </select>
          </label>
          <button type="button" className="secondary" onClick={() => void load(statusFilter)}>
            Refresh
          </button>
        </div>
        {error ? <p className="error">{error}</p> : null}
        {loading ? <p className="muted">Loading reviews…</p> : null}
        {!loading && reviews.length === 0 ? (
          <p className="muted">No review runs yet. Trigger one above or wait for a GitHub webhook.</p>
        ) : null}
        <div className="grid">
          {reviews.map((item) => (
            <Link key={item.id} className="review-link" to={`/reviews/${item.id}`}>
              <strong>
                {item.repository}#{item.pull_request} · {item.title}
              </strong>
              <div className="badges">
                <span className={`badge ${item.status}`}>{item.status}</span>
                {item.posted_to_github ? <span className="badge verified">posted</span> : null}
              </div>
              <div className="meta">
                <span>{item.verified_count}/{item.finding_count} verified</span>
                <span>{shortSha(item.commit_sha)}</span>
                <span>{formatWhen(item.created_at)}</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
