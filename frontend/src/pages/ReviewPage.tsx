import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getReview } from "../api";
import { SEVERITY_ORDER, filterFindings, formatWhen, shortSha, type VerificationFilter } from "../lib/findings";
import type { ReviewDetail } from "../types";

const TABS = ["findings", "files", "static", "tests", "rag", "trace"] as const;

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [review, setReview] = useState<ReviewDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("findings");
  const [verification, setVerification] = useState<VerificationFilter>("all");
  const [severities, setSeverities] = useState<string[]>([]);

  useEffect(() => {
    if (!id) {
      return;
    }
    const reviewId = id;
    let cancelled = false;
    let timer: number | undefined;

    async function load() {
      try {
        const data = await getReview(reviewId);
        if (!cancelled) {
          setReview(data);
          setError(null);
          if (data.status === "pending" || data.status === "running") {
            timer = window.setTimeout(load, 2500);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load review");
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [id]);

  const findings = useMemo(
    () => (review ? filterFindings(review.findings, verification, severities) : []),
    [review, verification, severities],
  );

  function toggleSeverity(value: string) {
    setSeverities((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    );
  }

  if (error) {
    return (
      <section className="panel">
        <p className="error">{error}</p>
        <Link to="/">Back to reviews</Link>
      </section>
    );
  }
  if (!review) {
    return <p className="muted">Loading review…</p>;
  }

  return (
    <section>
      <p>
        <Link to="/">← Reviews</Link>
      </p>
      <div className="panel">
        <h1>
          {review.repository}#{review.pull_request}
        </h1>
        <p>{review.title}</p>
        <div className="badges">
          <span className={`badge ${review.status}`}>{review.status}</span>
          {review.posted_to_github ? <span className="badge verified">posted to GitHub</span> : null}
        </div>
        <div className="meta">
          <span>{review.author ?? "unknown author"}</span>
          <span>
            {review.source_branch} → {review.target_branch}
          </span>
          <span>{shortSha(review.commit_sha)}</span>
          <span>{formatWhen(review.finished_at ?? review.created_at)}</span>
          {review.execution_time_ms != null ? <span>{review.execution_time_ms} ms</span> : null}
        </div>
        {review.summary ? <p>{review.summary}</p> : <p className="muted">No LLM summary yet.</p>}
        {review.errors ? <pre>{JSON.stringify(review.errors, null, 2)}</pre> : null}
      </div>

      <div className="tabs">
        {TABS.map((item) => (
          <button key={item} className={tab === item ? "active" : ""} type="button" onClick={() => setTab(item)}>
            {item}
          </button>
        ))}
      </div>

      {tab === "findings" ? (
        <div className="panel">
          <div className="row">
            <label>
              Verification
              <select
                value={verification}
                onChange={(event) => setVerification(event.target.value as VerificationFilter)}
              >
                <option value="all">All</option>
                <option value="verified">Verified</option>
                <option value="rejected">Rejected</option>
              </select>
            </label>
            {SEVERITY_ORDER.map((severity) => (
              <label key={severity} style={{ flexDirection: "row", alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={severities.includes(severity)}
                  onChange={() => toggleSeverity(severity)}
                />
                {severity}
              </label>
            ))}
          </div>
          {findings.length === 0 ? <p className="muted">No findings match these filters.</p> : null}
          <div className="grid">
            {findings.map((item) => (
              <article key={item.id} className="finding">
                <div className="badges">
                  <span className={`badge ${item.severity}`}>{item.severity}</span>
                  <span className="badge">{item.category}</span>
                  <span className={`badge ${item.verified === true ? "verified" : "rejected"}`}>
                    {item.verified === true ? "verified" : item.verified === false ? "rejected" : "unchecked"}
                  </span>
                </div>
                <h3>{item.title}</h3>
                <p className="muted">
                  {item.file}
                  {item.line ? `:${item.line}` : ""} · confidence {Math.round(item.confidence * 100)}%
                </p>
                <p>{item.description}</p>
                {item.evidence ? <pre>{item.evidence}</pre> : null}
                {item.suggested_fix ? <p>Fix: {item.suggested_fix}</p> : null}
                {item.verification_reason ? <p className="muted">{item.verification_reason}</p> : null}
              </article>
            ))}
          </div>
        </div>
      ) : null}

      {tab === "files" ? (
        <div className="panel">
          {review.changed_files.map((file) => (
            <article key={file.path} className="finding">
              <strong>{file.path}</strong>
              <p className="muted">
                {file.status} · +{file.additions} −{file.deletions} · {file.language ?? "unknown"}
              </p>
              {file.patch ? <pre>{file.patch}</pre> : <p className="muted">No patch stored.</p>}
            </article>
          ))}
        </div>
      ) : null}

      {tab === "static" ? (
        <div className="panel">
          {(review.static_analysis?.runs ?? []).map((run) => (
            <article key={run.tool} className="finding">
              <strong>{run.tool}</strong>
              <p className="muted">
                {run.available ? `exit ${run.exit_code ?? "n/a"}` : "unavailable"} · {run.issues.length} issue(s)
              </p>
              {run.error ? <p className="error">{run.error}</p> : null}
              {run.issues.slice(0, 20).map((issue, index) => (
                <p key={`${issue.file}-${index}`}>
                  {issue.file}:{issue.line ?? "?"} {issue.rule} {issue.message}
                </p>
              ))}
            </article>
          ))}
        </div>
      ) : null}

      {tab === "tests" ? (
        <div className="panel">
          {review.test_results ? (
            <>
              <p>
                {review.test_results.passed} passed · {review.test_results.failed} failed · {review.test_results.errors}{" "}
                errors
              </p>
              {review.test_results.skip_reason ? <p className="muted">{review.test_results.skip_reason}</p> : null}
              {(review.test_results.cases ?? []).map((item) => (
                <p key={item.nodeid}>
                  {item.outcome} · {item.nodeid}
                </p>
              ))}
            </>
          ) : (
            <p className="muted">No test results on this run.</p>
          )}
        </div>
      ) : null}

      {tab === "rag" ? (
        <div className="panel">
          {(review.retrieved_context ?? []).map((chunk, index) => (
            <article key={`${chunk.file_path}-${index}`} className="finding">
              <strong>
                {chunk.file_path}
                {chunk.symbol ? ` · ${chunk.symbol}` : ""}
              </strong>
              <p className="muted">
                {chunk.start_line}-{chunk.end_line} · score {chunk.score.toFixed(3)}
              </p>
              <pre>{chunk.text}</pre>
            </article>
          ))}
          {review.retrieved_context.length === 0 ? <p className="muted">No retrieved chunks.</p> : null}
        </div>
      ) : null}

      {tab === "trace" ? (
        <div className="panel">
          <pre>{JSON.stringify(review.agent_trace, null, 2)}</pre>
        </div>
      ) : null}
    </section>
  );
}
