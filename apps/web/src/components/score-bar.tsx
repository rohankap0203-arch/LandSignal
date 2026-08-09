"use client";

/** Horizontal red→green meter — hint must be listing-specific (no generic band copy). */
export function ScoreBar({
  label,
  value,
  hint,
  invert = false,
}: {
  label: string;
  value: number;
  hint?: string;
  /** If true, high values are bad (risk) — bar still fills, color flips */
  invert?: boolean;
}) {
  const v = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  const hue = invert ? 120 - v * 1.2 : v * 1.2;
  const fill = `hsl(${Math.max(0, Math.min(120, hue))} 65% 42%)`;

  return (
    <div className="score-bar">
      <div className="flex items-baseline justify-between gap-3">
        <div className="font-semibold">{label}</div>
        <div className="text-sm font-semibold tabular-nums whitespace-nowrap">
          {Math.round(v)} <span className="text-[var(--muted)] font-medium">/ 100</span>
        </div>
      </div>
      <div className="score-bar-track" aria-hidden>
        <div className="score-bar-fill" style={{ width: `${v}%`, background: fill }} />
      </div>
      {hint ? <p className="mt-1.5 text-sm leading-relaxed text-[var(--muted)]">{hint}</p> : null}
    </div>
  );
}
