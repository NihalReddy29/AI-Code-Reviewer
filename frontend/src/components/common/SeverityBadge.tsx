
interface SeverityBadgeProps {
  severity: string;
  size?: "sm" | "md";
}

export function SeverityBadge({ severity, size = "md" }: SeverityBadgeProps) {
  const norm = severity.toUpperCase();

  // Pick semantic symbol and class
  let symbol = "●";
  let label = norm;
  let variantClass = "severity-info";

  if (norm === "CRITICAL") {
    symbol = "▲";
    variantClass = "severity-critical";
  } else if (norm === "HIGH") {
    symbol = "■";
    variantClass = "severity-high";
  } else if (norm === "MEDIUM") {
    symbol = "◆";
    variantClass = "severity-medium";
  } else if (norm === "LOW") {
    symbol = "●";
    variantClass = "severity-low";
  } else if (norm === "INFO") {
    symbol = "ℹ";
    variantClass = "severity-info";
  }

  return (
    <span className={`severity-badge ${variantClass} size-${size}`} role="status" aria-label={`Severity: ${label}`}>
      <span className="severity-icon" aria-hidden="true">
        {symbol}
      </span>
      <span className="severity-label">{label}</span>
    </span>
  );
}
