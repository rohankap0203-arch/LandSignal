"use client";

/** Sparse map-pin loading state for search and parcel intelligence. */
const PINS: { left: string; top: string; delay: string; duration: string; scale: number }[] = [
  { left: "18%", top: "54%", delay: "0s", duration: "4.2s", scale: 1 },
  { left: "46%", top: "34%", delay: "1.4s", duration: "4.6s", scale: 0.9 },
  { left: "68%", top: "58%", delay: "2.6s", duration: "4.4s", scale: 1.05 },
  { left: "82%", top: "40%", delay: "0.8s", duration: "4.8s", scale: 0.85 },
];

function PinIcon() {
  return (
    <svg viewBox="0 0 24 32" width="18" height="24" aria-hidden>
      <path
        fill="currentColor"
        d="M12 0C6.5 0 2 4.4 2 9.8c0 7.4 9 20.7 9.4 21.3a.8.8 0 0 0 1.3 0C13 30.5 22 17.2 22 9.8 22 4.4 17.5 0 12 0zm0 14.2a4.4 4.4 0 1 1 0-8.8 4.4 4.4 0 0 1 0 8.8z"
      />
    </svg>
  );
}

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
              stroke="rgba(255,255,255,0.28)"
              strokeWidth="1.4"
            />
          ))}
        </svg>
        <div className="land-pin-field">
          {PINS.map((p, i) => (
            <span
              key={i}
              className="land-scout-pin"
              style={{
                left: p.left,
                top: p.top,
                animationDelay: p.delay,
                animationDuration: p.duration,
                ["--pin-scale" as string]: String(p.scale),
              }}
            >
              <PinIcon />
            </span>
          ))}
        </div>
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
