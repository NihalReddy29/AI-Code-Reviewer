import type { HealthStatus, ReviewDetail, ReviewSummary } from "./types";

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the API. Start uvicorn on port 8000, or start Docker Desktop and run docker compose.");
  }
  const raw = await response.text();
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = JSON.parse(raw) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      if (response.status >= 500) {
        detail = "API is not running on port 8000. Start it with uvicorn or docker compose.";
      }
    }
    throw new ApiError(response.status, detail);
  }
  return JSON.parse(raw) as T;
}

export function getHealth(): Promise<HealthStatus> {
  return request("/health");
}

export async function listReviews(params?: {
  repository?: string;
  status?: string;
}): Promise<ReviewSummary[]> {
  const query = new URLSearchParams();
  if (params?.repository) {
    query.set("repository", params.repository);
  }
  if (params?.status) {
    query.set("status", params.status);
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  const body = await request<{ reviews: ReviewSummary[] }>(`/reviews${suffix}`);
  return body.reviews;
}

export function getReview(id: string): Promise<ReviewDetail> {
  return request(`/reviews/${id}`);
}

export async function triggerReview(
  owner: string,
  repo: string,
  pullRequest: number,
): Promise<{ review_run_id: string; status: string; duplicate: boolean }> {
  return request(`/reviews/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/${pullRequest}`, {
    method: "POST",
  });
}

export async function listRepositories(): Promise<string[]> {
  const body = await request<{ repositories: Array<{ full_name: string }> }>("/repositories");
  return body.repositories.map((item) => item.full_name);
}

export function getAnalyticsOverview(params?: { repository?: string }): Promise<import("./types").AnalyticsOverview> {
  const query = new URLSearchParams();
  if (params?.repository) {
    query.set("repository", params.repository);
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return request(`/analytics/overview${suffix}`);
}

export function getAnalyticsTrends(params?: {
  days?: number;
  repository?: string;
}): Promise<import("./types").AnalyticsTrends> {
  const query = new URLSearchParams();
  if (params?.days) {
    query.set("days", params.days.toString());
  }
  if (params?.repository) {
    query.set("repository", params.repository);
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return request(`/analytics/trends${suffix}`);
}
