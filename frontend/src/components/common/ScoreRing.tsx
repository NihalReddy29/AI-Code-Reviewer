
export interface ScoreRingProps {
  score: number | null | undefined;
  size?: number;
  strokeWidth?: number;
  stroke?: number;
  label?: string;
  showLabel?: boolean;
  showScale?: boolean;
  compact?: boolean;
  className?: string;
}

export function ScoreRing({
  score,
  size = 140,
  strokeWidth,
  stroke,
  label = "Health Score",
  showLabel,
  showScale,
  compact,
  className = "",
}: ScoreRingProps) {
  const isCompact = compact ?? size < 80;
  const effectiveStrokeWidth =
    strokeWidth ?? stroke ?? (isCompact ? Math.max(3, Math.round(size * 0.09)) : 10);
  const shouldShowLabel = showLabel ?? !isCompact;
  const shouldShowScale = showScale ?? !isCompact;

  const displayScore = score != null ? Math.max(0, Math.min(100, Math.round(score))) : null;

  const radius = (size - effectiveStrokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset =
    displayScore != null ? circumference - (displayScore / 100) * circumference : circumference;

  let strokeColor = "#10B981"; // green (good)
  if (displayScore != null) {
    if (displayScore < 50) {
      strokeColor = "#EF4444"; // red (critical/poor)
    } else if (displayScore < 80) {
      strokeColor = "#F59E0B"; // orange (medium)
    }
  } else {
    strokeColor = "#4B5563";
  }

  const numberFontSize = isCompact ? `${Math.max(11, Math.round(size * 0.32))}px` : undefined;

  return (
    <div
      className={`score-ring-container ${isCompact ? "score-ring-container--compact" : ""} ${className}`.trim()}
      role="region"
      aria-label={`${label}: ${displayScore != null ? `${displayScore} out of 100` : "No score available"}`}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="score-ring-svg">
        {/* Background track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255, 255, 255, 0.08)"
          strokeWidth={effectiveStrokeWidth}
        />
        {/* Progress stroke */}
        {displayScore != null && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={strokeColor}
            strokeWidth={effectiveStrokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ transition: "stroke-dashoffset 0.8s ease-in-out" }}
          />
        )}
      </svg>
      <div className="score-ring-content" style={{ width: size, height: size }}>
        <span
          className="score-ring-number"
          style={numberFontSize ? { fontSize: numberFontSize } : undefined}
        >
          {displayScore != null ? displayScore : "—"}
        </span>
        {shouldShowScale && <span className="score-ring-scale">/ 100</span>}
        {shouldShowLabel && <span className="score-ring-label">{label}</span>}
      </div>
    </div>
  );
}
