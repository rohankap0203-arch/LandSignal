"use client";

/** Horizontal red→green meter for LandSignal / inverse for Risk */
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
  // LandSignal: low=red, high=green. Risk: low=green, high=red.
  const hue = invert ? 120 - v * 1.2 : v * 1.2;
  const fill = `hsl(${Math.max(0, Math.min(120, hue))} 65% 42%)`;
  const meaning = invert
    ? v < 35
      ? "Lower risk on the desktop screen"
      : v < 55
        ? "Moderate risk — dig into flood/wetlands/access"
        : "Elevated risk — budget more diligence"
    : v >= 70
      ? "Strong opportunity screen"
      : v >= 50
        ? "Moderate opportunity — compare a few peers"
        : "Weak screen so far — keep looking or loosen filters";

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
      <p className="mt-1.5 text-sm text-[var(--muted)]">{hint || meaning}</p>
    </div>
  );
}
