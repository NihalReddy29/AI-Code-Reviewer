import { useEffect, useMemo, useState } from "react";
import { listReviews, getReview } from "../api";
import { Card } from "../components/common/Card";
import { SeverityBadge } from "../components/common/SeverityBadge";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import type { Finding, ReviewSummary } from "../types";

/** Must-fix = CRITICAL or HIGH verified; Should-fix = MEDIUM or HIGH unreviewed */
function classify(findings: Finding[]): {
  mustFix: Finding[];
  shouldFix: Finding[];
  informational: Finding[];
} {
  const mustFix: Finding[] = [];
  const shouldFix: Finding[] = [];
  const informational: Finding[] = [];

  for (const f of findings) {
    if (f.severity === "CRITICAL" || (f.severity === "HIGH" && f.verified !== false)) {
      mustFix.push(f);
    } else if (f.severity === "MEDIUM" || f.severity === "HIGH") {
      shouldFix.push(f);
    } else {
      informational.push(f);
    }
  }
  return { mustFix, shouldFix, informational };
}

function CheckItem({
  finding,
  checked,
  onToggle,
}: {
  finding: Finding;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <li className={`check-item${checked ? " check-item--done" : ""}`}>
      <label className="check-item__label">
        <input
          type="checkbox"
          className="check-item__checkbox"
          checked={checked}
          onChange={onToggle}
        />
        <span className="check-item__content">
          <span className="check-item__header">
            <SeverityBadge severity={finding.severity} />
            <span className="check-item__title">{finding.title}</span>
          </span>
          <span className="check-item__meta">
            <span className="code-chip">
              {finding.file}
              {finding.line != null ? `:${finding.line}` : ""}
            </span>
            <span className="check-item__cat">{finding.category}</span>
          </span>
          {!checked && finding.suggested_fix && (
            <details className="check-item__fix">
              <summary className="check-item__fix-toggle">Suggested fix</summary>
              <pre className="code-block code-block--fix">{finding.suggested_fix}</pre>
            </details>
          )}
        </span>
      </label>
    </li>
  );
}

function Checklist({
  title,
  accent,
  icon,
  items,
  checked,
  onToggle,
}: {
  title: string;
  accent: string;
  icon: string;
  items: Finding[];
  checked: Set<string>;
  onToggle: (id: string) => void;
}) {
  const done = items.filter((f) => checked.has(f.id)).length;
  const pct = items.length > 0 ? Math.round((done / items.length) * 100) : 100;

  return (
    <div className="checklist-section">
      <div className="checklist-header" style={{ "--accent": accent } as React.CSSProperties}>
        <div className="checklist-header__left">
          <span className="checklist-icon">{icon}</span>
          <div>
            <h2 className="checklist-title">{title}</h2>
            <span className="checklist-meta">
              {done} / {items.length} resolved
            </span>
          </div>
        </div>
        <div className="checklist-progress-wrap">
          <div className="checklist-progress" style={{ "--pct": `${pct}%` } as React.CSSProperties}>
            <span className="checklist-pct">{pct}%</span>
          </div>
        </div>
      </div>

      {items.length === 0 ? (
        <EmptyState icon="✅" title="All clear!" description="No items in this group." />
      ) : (
        <ul className="check-list">
          {items.map((f) => (
            <CheckItem
              key={f.id}
              finding={f}
              checked={checked.has(f.id)}
              onToggle={() => onToggle(f.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ChangesPage() {
  const [reviews, setReviews] = useState<ReviewSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loadingReviews, setLoadingReviews] = useState(true);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());

  useEffect(() => {
    listReviews({ status: "completed" })
      .then((data) => {
        setReviews(data);
        if (data.length > 0) setSelectedId(data[0].id);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingReviews(false));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setLoadingFindings(true);
    setFindings([]);
    setChecked(new Set());
    getReview(selectedId)
      .then((data) => setFindings(data.findings))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingFindings(false));
  }, [selectedId]);

  const { mustFix, shouldFix, informational } = useMemo(() => classify(findings), [findings]);

  function toggle(id: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const totalDone = findings.filter((f) => checked.has(f.id)).length;
  const totalPct = findings.length > 0 ? Math.round((totalDone / findings.length) * 100) : 0;

  if (loadingReviews) return <LoadingState message="Loading reviews…" />;
  if (error) return <ErrorState message={error} />;

  const selectedReview = reviews.find((r) => r.id === selectedId);

  return (
    <div className="changes-layout">
      <div className="page-toolbar">
        <div className="toolbar-left">
          <h1 className="page-title">Changes Needed</h1>
          {selectedReview && (
            <span className="page-subtitle">
              {selectedReview.repository} — PR #{selectedReview.pull_request}
            </span>
          )}
        </div>
        <div className="toolbar-right">
          <select
            id="changes-review-select"
            className="select-input"
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {reviews.map((r) => (
              <option key={r.id} value={r.id}>
                {r.repository} — PR #{r.pull_request} ({r.commit_sha.slice(0, 7)})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* overall progress */}
      {!loadingFindings && findings.length > 0 && (
        <Card>
          <div className="overall-progress">
            <div className="overall-progress__text">
              <span className="overall-progress__label">Overall progress</span>
              <span className="overall-progress__count">
                {totalDone} of {findings.length} issues resolved
              </span>
            </div>
            <div className="overall-bar-track">
              <div className="overall-bar-fill" style={{ width: `${totalPct}%` }} />
            </div>
            <span className="overall-pct">{totalPct}%</span>
          </div>
        </Card>
      )}

      {loadingFindings ? (
        <LoadingState message="Loading findings…" />
      ) : findings.length === 0 ? (
        <EmptyState
          icon="✅"
          title="No changes needed"
          description="This review has no findings. Great work!"
        />
      ) : (
        <div className="checklists">
          <Checklist
            title="Must Fix"
            accent="var(--sev-critical)"
            icon="🚨"
            items={mustFix}
            checked={checked}
            onToggle={toggle}
          />
          <Checklist
            title="Should Fix"
            accent="var(--sev-medium)"
            icon="⚠️"
            items={shouldFix}
            checked={checked}
            onToggle={toggle}
          />
          <Checklist
            title="Informational"
            accent="var(--sev-low)"
            icon="💡"
            items={informational}
            checked={checked}
            onToggle={toggle}
          />
        </div>
      )}
    </div>
  );
}
