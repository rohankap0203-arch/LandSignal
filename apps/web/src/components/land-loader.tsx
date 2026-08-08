"use client";

/** Contour / terrain-style loading state for search and parcel intelligence. */
export function LandLoader({
  label = "Reading the land…",
  detail,
  compact = false,
}: {
  label?: string;
  detail?: string;
  compact?: boolean;
}) {
  return (
    <div className={`land-loader ${compact ? "compact" : ""}`} role="status" aria-live="polite">
      <div className="land-loader-stage" aria-hidden>
        <svg className="land-loader-svg" viewBox="0 0 360 160" preserveAspectRatio="none">
          <defs>
            <linearGradient id="landGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="rgba(31,107,79,0.55)" />
              <stop offset="55%" stopColor="rgba(15,61,46,0.35)" />
              <stop offset="100%" stopColor="rgba(196,92,38,0.35)" />
            </linearGradient>
          </defs>
          <rect width="360" height="160" fill="url(#landGrad)" />
          {[42, 58, 74, 90, 106, 122].map((y, i) => (
            <path
              key={y}
              className="land-contour"
              style={{ animationDelay: `${i * 0.18}s` }}
              d={`M0 ${y} C 60 ${y - 14}, 120 ${y + 12}, 180 ${y - 6} S 300 ${y + 10}, 360 ${y - 4}`}
              fill="none"
              stroke="rgba(255,255,255,0.35)"
              strokeWidth="1.4"
            />
          ))}
          <circle className="land-ping" cx="188" cy="78" r="6" />
          <circle className="land-ping delay" cx="188" cy="78" r="6" />
        </svg>
        <div className="land-scan" />
      </div>
      <div className="land-loader-copy">
        <div className="display text-xl font-semibold text-[var(--ink)]">{label}</div>
        {detail && <p className="mt-1 text-sm text-[var(--muted)]">{detail}</p>}
        <div className="land-loader-dots" aria-hidden>
          <span />
          <span />
          <span />
        </div>
      </div>
    </div>
  );
}
