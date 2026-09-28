import { useEffect, useMemo, useState } from "react";
import { listReviews, getReview } from "../api";
import { Card } from "../components/common/Card";
import { SeverityBadge } from "../components/common/SeverityBadge";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { SEVERITY_ORDER, filterFindings, type VerificationFilter } from "../lib/findings";
import type { Finding, ReviewSummary } from "../types";

const CATEGORIES = ["all", "security", "bug", "performance", "style", "maintainability"] as const;
type CategoryFilter = (typeof CATEGORIES)[number];

function FindingRow({
  finding,
  active,
  onClick,
}: {
  finding: Finding;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <tr
      className={`finding-row${active ? " finding-row--active" : ""}`}
      onClick={onClick}
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
    >
      <td className="finding-cell finding-cell--severity">
        <SeverityBadge severity={finding.severity} />
      </td>
      <td className="finding-cell finding-cell--title">{finding.title}</td>
      <td className="finding-cell finding-cell--file">
        <span className="code-chip">
          {finding.file}
          {finding.line != null ? `:${finding.line}` : ""}
        </span>
      </td>
      <td className="finding-cell finding-cell--category">{finding.category}</td>
      <td className="finding-cell finding-cell--verified">
        {finding.verified === true ? (
          <span className="badge badge--green">Verified</span>
        ) : finding.verified === false ? (
          <span className="badge badge--red">Rejected</span>
        ) : (
          <span className="badge badge--muted">Unreviewed</span>
        )}
      </td>
    </tr>
  );
}

function DetailPanel({ finding, onClose }: { finding: Finding; onClose: () => void }) {
  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <div>
          <SeverityBadge severity={finding.severity} />
          <h3 className="detail-panel__title">{finding.title}</h3>
          <span className="code-chip detail-panel__loc">
            {finding.file}
            {finding.line != null ? `:${finding.line}` : ""}
          </span>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close detail panel">
          ✕
        </button>
      </div>

      <div className="detail-panel__body">
        <section className="detail-section">
          <h4 className="detail-section__label">Category</h4>
          <p className="detail-section__value">{finding.category}</p>
        </section>

        <section className="detail-section">
          <h4 className="detail-section__label">Description</h4>
          <p className="detail-section__value">{finding.description}</p>
        </section>

        {finding.evidence && (
          <section className="detail-section">
            <h4 className="detail-section__label">Evidence</h4>
            <pre className="code-block">{finding.evidence}</pre>
          </section>
        )}

        {finding.suggested_fix && (
          <section className="detail-section">
            <h4 className="detail-section__label">Suggested Fix</h4>
            <pre className="code-block code-block--fix">{finding.suggested_fix}</pre>
          </section>
        )}

        <section className="detail-section">
          <h4 className="detail-section__label">Confidence</h4>
          <div className="confidence-bar-wrap">
            <div
              className="confidence-bar"
              style={{ width: `${Math.round(finding.confidence * 100)}%` }}
            />
            <span className="confidence-label">{Math.round(finding.confidence * 100)}%</span>
          </div>
        </section>

        {finding.verification_reason && (
          <section className="detail-section">
            <h4 className="detail-section__label">Verification Reason</h4>
            <p className="detail-section__value">{finding.verification_reason}</p>
          </section>
        )}
      </div>
    </div>
  );
}

export default function IssuesPage() {
  const [reviews, setReviews] = useState<ReviewSummary[]>([]);
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const [allFindings, setAllFindings] = useState<Finding[]>([]);
  const [loadingReviews, setLoadingReviews] = useState(true);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // filters
  const [verification, setVerification] = useState<VerificationFilter>("all");
  const [severities, setSeverities] = useState<string[]>([]);
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [search, setSearch] = useState("");

  // detail panel
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    listReviews({ status: "completed" })
      .then((data) => {
        setReviews(data);
        if (data.length > 0) {
          setSelectedReviewId(data[0].id);
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingReviews(false));
  }, []);

  useEffect(() => {
    if (!selectedReviewId) return;
    setLoadingFindings(true);
    setAllFindings([]);
    setActiveId(null);
    getReview(selectedReviewId)
      .then((data) => setAllFindings(data.findings))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingFindings(false));
  }, [selectedReviewId]);

  const filtered = useMemo(() => {
    let items = filterFindings(allFindings, verification, severities);
    if (category !== "all") {
      items = items.filter((f) => f.category.toLowerCase().includes(category));
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter(
        (f) =>
          f.title.toLowerCase().includes(q) ||
          f.file.toLowerCase().includes(q) ||
          f.description.toLowerCase().includes(q),
      );
    }
    return items;
  }, [allFindings, verification, severities, category, search]);

  const activeFind = useMemo(
    () => filtered.find((f) => f.id === activeId) ?? null,
    [filtered, activeId],
  );

  function toggleSeverity(sev: string) {
    setSeverities((prev) =>
      prev.includes(sev) ? prev.filter((s) => s !== sev) : [...prev, sev],
    );
  }

  if (loadingReviews) return <LoadingState message="Loading reviews…" />;
  if (error) return <ErrorState message={error} />;

  const selectedReview = reviews.find((r) => r.id === selectedReviewId);

  return (
    <div className="issues-layout">
      {/* top toolbar */}
      <div className="page-toolbar">
        <div className="toolbar-left">
          <h1 className="page-title">Issues &amp; Bugs</h1>
          {selectedReview && (
            <span className="page-subtitle">
              {selectedReview.repository} — PR #{selectedReview.pull_request}
            </span>
          )}
        </div>
        <div className="toolbar-right">
          <select
            id="issues-review-select"
            className="select-input"
            value={selectedReviewId ?? ""}
            onChange={(e) => setSelectedReviewId(e.target.value)}
          >
            {reviews.map((r) => (
              <option key={r.id} value={r.id}>
                {r.repository} — PR #{r.pull_request} ({r.commit_sha.slice(0, 7)})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* filter bar */}
      <Card>
        <div className="filter-bar">
          <input
            id="issues-search"
            type="search"
            className="search-input"
            placeholder="Search title, file, description…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          <div className="filter-group">
            <span className="filter-label">Severity</span>
            {SEVERITY_ORDER.map((sev) => (
              <button
                key={sev}
                id={`issues-sev-${sev.toLowerCase()}`}
                className={`sev-pill sev-pill--${sev.toLowerCase()}${severities.includes(sev) ? " sev-pill--active" : ""}`}
                onClick={() => toggleSeverity(sev)}
              >
                {sev}
              </button>
            ))}
          </div>

          <div className="filter-group">
            <span className="filter-label">Status</span>
            {(["all", "verified", "rejected"] as VerificationFilter[]).map((v) => (
              <button
                key={v}
                id={`issues-vf-${v}`}
                className={`filter-btn${verification === v ? " filter-btn--active" : ""}`}
                onClick={() => setVerification(v)}
              >
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>

          <div className="filter-group">
            <span className="filter-label">Category</span>
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                id={`issues-cat-${cat}`}
                className={`filter-btn${category === cat ? " filter-btn--active" : ""}`}
                onClick={() => setCategory(cat)}
              >
                {cat.charAt(0).toUpperCase() + cat.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* main split view */}
      <div className={`issues-split${activeFind ? " issues-split--open" : ""}`}>
        <div className="issues-table-wrap">
          {loadingFindings ? (
            <LoadingState message="Loading findings…" />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon="🔍"
              title="No issues found"
              description="Adjust your filters or select a different review."
            />
          ) : (
            <table className="findings-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Issue</th>
                  <th>Location</th>
                  <th>Category</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((f) => (
                  <FindingRow
                    key={f.id}
                    finding={f}
                    active={f.id === activeId}
                    onClick={() => setActiveId(f.id === activeId ? null : f.id)}
                  />
                ))}
              </tbody>
            </table>
          )}
          <div className="table-footer">
            {filtered.length} issue{filtered.length !== 1 ? "s" : ""} shown
            {allFindings.length !== filtered.length && ` of ${allFindings.length} total`}
          </div>
        </div>

        {activeFind && (
          <DetailPanel finding={activeFind} onClose={() => setActiveId(null)} />
        )}
      </div>
    </div>
  );
}
