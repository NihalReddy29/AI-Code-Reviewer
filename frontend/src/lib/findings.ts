import type { Finding } from "../types";

export type VerificationFilter = "all" | "verified" | "rejected";

export const SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"] as const;

export function filterFindings(
  findings: Finding[],
  verification: VerificationFilter,
  severities: string[],
): Finding[] {
  const allowed = new Set(severities);
  return findings
    .filter((item) => {
      if (verification === "verified" && item.verified !== true) {
        return false;
      }
      if (verification === "rejected" && item.verified !== false) {
        return false;
      }
      if (allowed.size > 0 && !allowed.has(item.severity)) {
        return false;
      }
      return true;
    })
    .sort((left, right) => {
      const severityDelta =
        SEVERITY_ORDER.indexOf(left.severity as (typeof SEVERITY_ORDER)[number]) -
        SEVERITY_ORDER.indexOf(right.severity as (typeof SEVERITY_ORDER)[number]);
      if (severityDelta !== 0) {
        return severityDelta;
      }
      return left.file.localeCompare(right.file);
    });
}

export function shortSha(value: string): string {
  return value.slice(0, 7);
}

export function formatWhen(value: string | null): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}
