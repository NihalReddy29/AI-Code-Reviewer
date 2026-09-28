import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Card } from "../components/common/Card";
import { SeverityBadge } from "../components/common/SeverityBadge";
import { ScoreRing } from "../components/common/ScoreRing";
import { EmptyState } from "../components/common/EmptyState";
import { ErrorState } from "../components/common/ErrorState";
import { LoadingState } from "../components/common/LoadingState";

describe("Card", () => {
  it("renders title, subtitle, and children", () => {
    render(
      <Card title="Overview" subtitle="Metrics summary">
        <p>Card body content</p>
      </Card>
    );
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Metrics summary")).toBeInTheDocument();
    expect(screen.getByText("Card body content")).toBeInTheDocument();
  });
});

describe("SeverityBadge", () => {
  it("renders critical severity with label and icon", () => {
    render(<SeverityBadge severity="CRITICAL" />);
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    const badge = screen.getByRole("status");
    expect(badge).toHaveClass("severity-critical");
  });

  it("renders medium severity with orange styling", () => {
    render(<SeverityBadge severity="MEDIUM" />);
    expect(screen.getByText("MEDIUM")).toBeInTheDocument();
    const badge = screen.getByRole("status");
    expect(badge).toHaveClass("severity-medium");
  });
});

describe("ScoreRing", () => {
  it("renders score number and label", () => {
    render(<ScoreRing score={85} label="Health Score" />);
    expect(screen.getByText("85")).toBeInTheDocument();
    expect(screen.getByText("Health Score")).toBeInTheDocument();
    expect(screen.getByRole("region")).toHaveAttribute("aria-label", "Health Score: 85 out of 100");
  });

  it("renders placeholder when score is null", () => {
    render(<ScoreRing score={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders compact mode with only score number and no overflowing labels", () => {
    render(<ScoreRing score={78} size={38} compact />);
    expect(screen.getByText("78")).toBeInTheDocument();
    expect(screen.queryByText("/ 100")).not.toBeInTheDocument();
    expect(screen.queryByText("Health Score")).not.toBeInTheDocument();
  });
});

describe("EmptyState, ErrorState, LoadingState", () => {
  it("renders empty state", () => {
    render(<EmptyState title="No items" message="Check back later" />);
    expect(screen.getByText("No items")).toBeInTheDocument();
    expect(screen.getByText("Check back later")).toBeInTheDocument();
  });

  it("renders error state", () => {
    render(<ErrorState title="Error Occurred" message="Network timeout" />);
    expect(screen.getByText("Error Occurred")).toBeInTheDocument();
    expect(screen.getByText("Network timeout")).toBeInTheDocument();
  });

  it("renders loading state", () => {
    render(<LoadingState message="Fetching reviews..." />);
    expect(screen.getByText("Fetching reviews...")).toBeInTheDocument();
  });
});
