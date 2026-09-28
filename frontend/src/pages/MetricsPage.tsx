import { useEffect, useMemo, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { listReviews, getReview } from "../api";
import { Card } from "../components/common/Card";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";
import type { ReviewSummary, ReviewDetail } from "../types";

const SEV_COLORS: Record<string, string> = {
  CRITICAL: "var(--sev-critical)",
  HIGH: "var(--sev-high)",
  MEDIUM: "var(--sev-medium)",
  LOW: "var(--sev-low)",
  INFO: "var(--sev-info)",
};

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="stat-card">
      <span className="stat-card__label">{label}</span>
      <span className="stat-card__value">{value}</span>
      {sub && <span className="stat-card__sub">{sub}</span>}
    </div>
  );
}

export default function MetricsPage() {
  const [reviews, setReviews] = useState<ReviewSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [loadingReviews, setLoadingReviews] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setLoadingDetail(true);
    setDetail(null);
    getReview(selectedId)
      .then(setDetail)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoadingDetail(false));
  }, [selectedId]);

  const sevData = useMemo(() => {
    if (!detail) return [];
    const counts: Record<string, number> = {};
    for (const f of detail.findings) {
      counts[f.severity] = (counts[f.severity] ?? 0) + 1;
    }
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [detail]);

  const toolData = useMemo(() => {
    if (!detail?.static_analysis) return [];
    return detail.static_analysis.runs.map((run) => ({
      name: run.tool,
      issues: run.issues.length,
      available: run.available ? 1 : 0,
    }));
  }, [detail]);

  const catData = useMemo(() => {
    if (!detail) return [];
    const counts: Record<string, number> = {};
    for (const f of detail.findings) {
      counts[f.category] = (counts[f.category] ?? 0) + 1;
    }
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, value]) => ({ name, value }));
  }, [detail]);

  if (loadingReviews) return <LoadingState message="Loading reviews…" />;
  if (error) return <ErrorState message={error} />;

  const sel = reviews.find((r) => r.id === selectedId);
  const execSec = sel?.execution_time_ms != null ? (sel.execution_time_ms / 1000).toFixed(1) : "—";
  const testR = detail?.test_results;

  return (
    <div className="metrics-layout">
      <div className="page-toolbar">
        <div className="toolbar-left">
          <h1 className="page-title">Metrics &amp; Performance</h1>
          {sel && (
            <span className="page-subtitle">
              {sel.repository} — PR #{sel.pull_request}
            </span>
          )}
        </div>
        <div className="toolbar-right">
          <select
            id="metrics-review-select"
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

      {loadingDetail ? (
        <LoadingState message="Loading metrics…" />
      ) : !detail ? (
        <EmptyState icon="📊" title="No data" description="Select a completed review." />
      ) : (
        <>
          {/* summary stat cards */}
          <div className="stat-grid">
            <StatCard label="Quality Score" value={sel?.score != null ? sel.score : "—"} sub="out of 100" />
            <StatCard label="Total Findings" value={detail.findings.length} />
            <StatCard label="Verified" value={detail.verified_count} />
            <StatCard label="Files Changed" value={detail.changed_files.length} />
            <StatCard label="Execution Time" value={`${execSec}s`} />
            {testR && (
              <StatCard
                label="Tests"
                value={`${testR.passed}P / ${testR.failed}F`}
                sub={testR.available ? "pytest" : "unavailable"}
              />
            )}
          </div>

          <div className="metrics-charts">
            {/* severity donut */}
            <Card title="Findings by Severity">
              {sevData.length === 0 ? (
                <EmptyState icon="✅" title="No findings" description="Clean review!" />
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie
                      data={sevData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={90}
                      paddingAngle={3}
                    >
                      {sevData.map((entry) => (
                        <Cell key={entry.name} fill={SEV_COLORS[entry.name] ?? "#888"} />
                      ))}
                    </Pie>
                    <Legend />
                    <Tooltip
                      contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                      labelStyle={{ color: "var(--text-muted)" }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </Card>

            {/* category bar */}
            <Card title="Findings by Category">
              {catData.length === 0 ? (
                <EmptyState icon="✅" title="No findings" description="Clean review!" />
              ) : (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={catData} layout="vertical" margin={{ left: 16 }}>
                    <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={100}
                      tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
                    />
                    <Tooltip
                      contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                      cursor={{ fill: "rgba(99,179,237,0.07)" }}
                    />
                    <Bar dataKey="value" fill="var(--accent)" radius={[0, 4, 4, 0]} name="Issues" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Card>

            {/* static analysis tools */}
            {toolData.length > 0 && (
              <Card title="Static Analysis Tools">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={toolData}>
                    <XAxis dataKey="name" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} />
                    <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }}
                    />
                    <Bar dataKey="issues" fill="var(--sev-medium)" radius={[4, 4, 0, 0]} name="Issues" />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            )}

            {/* test results */}
            {testR && (
              <Card title="Test Results">
                <div className="test-results-grid">
                  <div className="test-stat test-stat--pass">
                    <span className="test-stat__num">{testR.passed}</span>
                    <span className="test-stat__lbl">Passed</span>
                  </div>
                  <div className="test-stat test-stat--fail">
                    <span className="test-stat__num">{testR.failed}</span>
                    <span className="test-stat__lbl">Failed</span>
                  </div>
                  <div className="test-stat test-stat--skip">
                    <span className="test-stat__num">{testR.skipped_cases}</span>
                    <span className="test-stat__lbl">Skipped</span>
                  </div>
                  <div className="test-stat test-stat--err">
                    <span className="test-stat__num">{testR.errors}</span>
                    <span className="test-stat__lbl">Errors</span>
                  </div>
                </div>
                {testR.failed > 0 && testR.cases.filter((c) => c.outcome === "failed").length > 0 && (
                  <div className="failed-tests">
                    <h4 className="failed-tests__title">Failed tests</h4>
                    <ul className="failed-tests__list">
                      {testR.cases
                        .filter((c) => c.outcome === "failed")
                        .map((c) => (
                          <li key={c.nodeid} className="failed-test">
                            <span className="code-chip">{c.nodeid}</span>
                            {c.message && <pre className="failed-test__msg">{c.message}</pre>}
                          </li>
                        ))}
                    </ul>
                  </div>
                )}
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  );
}
