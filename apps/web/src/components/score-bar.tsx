"use client";

import { useState } from "react";

/** Clickable red→green meter with tailored bullets for this listing. */
export function ScoreBar({
  label,
  value,
  hint,
  bullets,
  verdict,
  invert = false,
}: {
  label: string;
  value: number;
  hint?: string;
  bullets?: string[];
  verdict?: string;
  /** If true, high values are bad (risk) — bar still fills, color flips */
  invert?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const v = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  const hue = invert ? 120 - v * 1.2 : v * 1.2;
  const fill = `hsl(${Math.max(0, Math.min(120, hue))} 65% 42%)`;
  const hasDetail = Boolean((bullets && bullets.length) || verdict || hint);

  return (
    <button
      type="button"
      className={`score-bar score-bar-click ${open ? "open" : ""}`}
      onClick={() => hasDetail && setOpen((o) => !o)}
      aria-expanded={open}
      disabled={!hasDetail}
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="font-semibold flex items-center gap-1.5">
          {label}
          {hasDetail ? (
            <span className="score-bar-chevron" aria-hidden>
              {open ? "▾" : "▸"}
            </span>
          ) : null}
        </div>
        <div className="text-sm font-semibold tabular-nums whitespace-nowrap">
          {Math.round(v)} <span className="text-[var(--muted)] font-medium">/ 100</span>
        </div>
      </div>
      <div className="score-bar-track" aria-hidden>
        <div className="score-bar-fill" style={{ width: `${v}%`, background: fill }} />
      </div>
      {!open && hint ? (
        <p className="mt-1.5 text-sm leading-snug text-[var(--muted)] line-clamp-2 text-left">
          {hint}
          <span className="ml-1 text-[var(--brand)]">Why ▸</span>
        </p>
      ) : null}
      {open ? (
        <div className="score-bar-detail mt-2 text-left">
          {verdict ? <p className="text-sm font-medium leading-snug">{verdict}</p> : null}
          {bullets && bullets.length ? (
            <ul className="mt-1.5 space-y-1.5">
              {bullets.slice(0, 4).map((b) => (
                <li key={b} className="text-sm leading-snug text-[var(--muted)]">
                  • {b}
                </li>
              ))}
            </ul>
          ) : hint ? (
            <p className="mt-1 text-sm leading-snug text-[var(--muted)]">{hint}</p>
          ) : null}
        </div>
      ) : null}
    </button>
  );
}
