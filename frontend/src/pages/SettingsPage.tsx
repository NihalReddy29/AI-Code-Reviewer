import { useEffect, useMemo, useState } from "react";
import { listRepositories, listReviews, getReview } from "../api";
import { Card } from "../components/common/Card";
import { LoadingState } from "../components/common/LoadingState";
import { ErrorState } from "../components/common/ErrorState";
import { EmptyState } from "../components/common/EmptyState";
import type { ReviewSummary } from "../types";

function ConfigTree({ config }: { config: Record<string, unknown> }) {
  return (
    <pre className="config-tree">
      {JSON.stringify(config, null, 2)}
    </pre>
  );
}

function RepoCard({ repo, latestReview }: { repo: string; latestReview: ReviewSummary | null }) {
  const [expanded, setExpanded] = useState(false);
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [loadingCfg, setLoadingCfg] = useState(false);
  const [cfgError, setCfgError] = useState<string | null>(null);

  function loadConfig() {
    if (!latestReview) return;
    setExpanded((v) => {
      if (!v && !config) {
        setLoadingCfg(true);
        setCfgError(null);
        getReview(latestReview.id)
          .then((d) => {
            if (d.resolved_config) {
              setConfig(d.resolved_config as Record<string, unknown>);
            } else {
              setConfig({});
            }
          })
          .catch((err: Error) => setCfgError(err.message))
          .finally(() => setLoadingCfg(false));
      }
      return !v;
    });
  }

  const [owner, name] = repo.split("/");

  return (
    <div className="repo-card">
      <div className="repo-card__header" onClick={loadConfig} role="button" tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && loadConfig()}>
        <div className="repo-card__info">
          <span className="repo-card__icon">🗃️</span>
          <div>
            <span className="repo-card__owner">{owner}/</span>
            <span className="repo-card__name">{name}</span>
          </div>
        </div>
        <div className="repo-card__meta">
          {latestReview ? (
            <span className="badge badge--blue">
              {latestReview.finding_count} findings · PR #{latestReview.pull_request}
            </span>
          ) : (
            <span className="badge badge--muted">No reviews yet</span>
          )}
          <span className="repo-card__toggle">{expanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {expanded && (
        <div className="repo-card__body">
          {loadingCfg ? (
            <div className="muted">Loading config…</div>
          ) : cfgError ? (
            <div className="error-text">{cfgError}</div>
          ) : config && Object.keys(config).length > 0 ? (
            <>
              <h4 className="config-section__title">Resolved .codereviewer.yml</h4>
              <ConfigTree config={config} />
            </>
          ) : (
            <EmptyState
              icon="📄"
              title="Default config"
              description="No .codereviewer.yml found — using global defaults."
            />
          )}
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const [repos, setRepos] = useState<string[]>([]);
  const [reviews, setReviews] = useState<ReviewSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listRepositories(), listReviews()])
      .then(([r, rv]) => {
        setRepos(r);
        setReviews(rv);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const latestByRepo = useMemo<Record<string, ReviewSummary>>(() => {
    const map: Record<string, ReviewSummary> = {};
    for (const r of reviews) {
      if (!map[r.repository] || new Date(r.created_at ?? 0) > new Date(map[r.repository].created_at ?? 0)) {
        map[r.repository] = r;
      }
    }
    return map;
  }, [reviews]);

  if (loading) return <LoadingState message="Loading repositories…" />;
  if (error) return <ErrorState message={error} />;

  return (
    <div className="settings-layout">
      <div className="page-toolbar">
        <div className="toolbar-left">
          <h1 className="page-title">Repository Settings</h1>
          <span className="page-subtitle">Per-repo .codereviewer.yml configuration</span>
        </div>
      </div>

      <Card title="How it works" subtitle="Place a .codereviewer.yml in your repository root">
        <div className="settings-howto">
          <p className="settings-howto__text">
            Each repository can override review behaviour by committing a{" "}
            <code>.codereviewer.yml</code> file. Click a repository below to see its resolved
            configuration from the most recent review run.
          </p>
          <pre className="code-block">
{`# Example .codereviewer.yml
paths:
  ignore:
    - "migrations/**"
    - "*.generated.py"
tools:
  ruff: true
  bandit: true
  pyright: false
review:
  min_severity: MEDIUM
  max_comments: 20
  categories:
    - security
    - bug
  guidelines:
    - "Prefer explicit imports over wildcard imports."`}
          </pre>
        </div>
      </Card>

      {repos.length === 0 ? (
        <EmptyState
          icon="🏗️"
          title="No repositories yet"
          description="Trigger a review first to register a repository."
        />
      ) : (
        <div className="repo-list">
          {repos.map((repo) => (
            <RepoCard key={repo} repo={repo} latestReview={latestByRepo[repo] ?? null} />
          ))}
        </div>
      )}
    </div>
  );
}
