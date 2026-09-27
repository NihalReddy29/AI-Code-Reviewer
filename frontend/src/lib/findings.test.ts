import { describe, expect, it } from "vitest";

import { filterFindings } from "./findings";
import type { Finding } from "../types";

function finding(overrides: Partial<Finding>): Finding {
  return {
    id: "1",
    file: "app.py",
    line: 1,
    category: "SECURITY",
    severity: "HIGH",
    title: "Issue",
    description: "desc",
    evidence: "code",
    suggested_fix: "fix",
    confidence: 0.9,
    verified: true,
    verification_reason: "ok",
    ...overrides,
  };
}

describe("filterFindings", () => {
  const items = [
    finding({ id: "a", verified: true, severity: "HIGH", file: "b.py" }),
    finding({ id: "b", verified: false, severity: "LOW", file: "a.py", title: "noise" }),
    finding({ id: "c", verified: true, severity: "CRITICAL", file: "c.py" }),
  ];

  it("keeps verified findings and sorts by severity", () => {
    const result = filterFindings(items, "verified", []);
    expect(result.map((item) => item.id)).toEqual(["c", "a"]);
  });

  it("filters rejected findings and severity", () => {
    const result = filterFindings(items, "rejected", ["LOW"]);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("b");
  });
});
