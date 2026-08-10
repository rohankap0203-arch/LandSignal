"use client";

import { useState } from "react";

export type ScoreStandings = {
  kind?: "opportunity" | "risk" | "confidence" | string;
  polarity?: "higher_better" | "lower_better" | string;
  score?: number;
  sample_n?: number;
  beats_pct?: number;
  percentile?: number;
  median?: number | null;
  p75?: number | null;
  p90?: number | null;
  p95?: number | null;
  max?: number | null;
  min?: number | null;
  histogram?: Array<{
    lo: number;
    hi: number;
    label: string;
    count: number;
    share: number;
    bar: number;
  }>;
  factors?: Array<{
    key: string;
    label: string;
    simple?: string;
    score: number;
    weight_pct: number;
    contribution: number;
    gap: number;
    direction: string;
  }>;
  lifts?: Array<{ key: string; label: string; score: number; contribution: number }>;
  drags?: Array<{ key: string; label: string; score: number; gap: number }>;
  why_not_higher?: string[];
  why_label?: string;
  factors_label?: string;
  meta_best_label?: string;
  meta_best_value?: number | null;
  rank_plain?: string;
  ceiling_plain?: string;
  method_plain?: string | null;
};

/** @deprecated alias — same shape as ScoreStandings */
export type OpportunityStandings = ScoreStandings;

/** Clickable red→green meter — expands into compact sitewide standings. */
export function ScoreBar({
  label,
  value,
  hint,
  bullets,
  verdict,
  standings,
  invert = false,
}: {
  label: string;
  value: number;
  hint?: string;
  bullets?: string[];
  verdict?: string;
  standings?: ScoreStandings | null;
  /** If true, high values are bad (risk) — bar still fills, color flips */
  invert?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const v = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  const hue = invert ? 120 - v * 1.2 : v * 1.2;
  const fill = `hsl(${Math.max(0, Math.min(120, hue))} 65% 42%)`;
  const hasStandings = Boolean(standings?.histogram?.length);
  const hasDetail = Boolean(hasStandings || (bullets && bullets.length) || verdict || hint);
  const closedHint = standings?.rank_plain || hint;

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
      {!open && closedHint ? (
        <p className="mt-1.5 text-sm leading-snug text-[var(--muted)] line-clamp-2 text-left">
          {closedHint}
          <span className="ml-1 text-[var(--brand)]">Why ▸</span>
        </p>
      ) : null}
      {open ? (
        <div className="score-bar-detail mt-2 text-left" onClick={(e) => e.stopPropagation()}>
          {hasStandings && standings ? (
            <ScoreStandingsPanel score={v} standings={standings} invert={invert} />
          ) : (
            <>
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
            </>
          )}
        </div>
      ) : null}
    </button>
  );
}

function ScoreStandingsPanel({
  score,
  standings,
  invert = false,
}: {
  score: number;
  standings: ScoreStandings;
  invert?: boolean;
}) {
  const hist = standings.histogram || [];
  const n = standings.sample_n || 0;
  const markerBucket = hist.findIndex((b) => score >= b.lo && score < b.hi);
  const markerIdx =
    markerBucket >= 0 ? markerBucket : score >= 100 ? hist.length - 1 : 0;
  const topFactors = (standings.factors || []).slice(0, 3);
  const why = (standings.why_not_higher || [])[0];
  const whyLabel = standings.why_label || (invert ? "Why not lower" : "Why not 90");
  const factorsLabel = standings.factors_label || `What’s in your ${Math.round(score)}`;
  const beatsLabel = invert ? "Safer than" : "Beats";
  const bestLabel = standings.meta_best_label || (invert ? "Site low" : "Site high");
  const bestValue =
    standings.meta_best_value != null
      ? standings.meta_best_value
      : invert
        ? standings.min
        : standings.max;

  return (
    <div className="opp-standings opp-standings--compact">
      <p className="opp-standings-rank">{standings.rank_plain}</p>
      {standings.ceiling_plain ? (
        <p className="opp-standings-meaning">{standings.ceiling_plain}</p>
      ) : null}

      <div
        className="opp-hist"
        role="img"
        aria-label={`Your ${Math.round(score)} vs ${n.toLocaleString()} live files`}
      >
        <div className="opp-hist-bars">
          {hist.map((b, i) => (
            <div
              key={b.label}
              className={`opp-hist-col ${i === markerIdx ? "is-you" : ""}`}
              title={`${b.label}: ${b.count.toLocaleString()} files`}
            >
              <div
                className="opp-hist-bar"
                style={{ height: `${Math.max(8, Math.round(b.bar * 100))}%` }}
              />
            </div>
          ))}
        </div>
        <div className="opp-hist-scale" aria-hidden>
          <span>0</span>
          <span>you {Math.round(score)}</span>
          <span>100</span>
        </div>
        <div className="opp-standings-meta">
          <span>
            {beatsLabel} <strong>~{Math.round(standings.beats_pct || 0)}%</strong>
          </span>
          <span>
            Median <strong>{standings.median != null ? Math.round(standings.median) : "—"}</strong>
          </span>
          <span>
            {bestLabel}{" "}
            <strong>{bestValue != null ? Math.round(bestValue) : "—"}</strong>
          </span>
        </div>
      </div>

      {why ? (
        <p className="opp-why-one">
          <span className="opp-why-k">{whyLabel} · </span>
          {why}
        </p>
      ) : null}

      {topFactors.length ? (
        <div className="opp-factors">
          <div className="opp-why-k">{factorsLabel}</div>
          <div className="opp-factor-list">
            {topFactors.map((f) => (
              <div key={f.key} className={`opp-factor-row tone-${f.direction}`}>
                <div className="opp-factor-top">
                  <span className="opp-factor-label">{f.label}</span>
                  <span className="opp-factor-score tabular-nums">
                    {Math.round(f.score)}
                    <span className="opp-factor-w"> · {f.weight_pct}% wt</span>
                  </span>
                </div>
                <div className="opp-factor-track" aria-hidden>
                  <div
                    className="opp-factor-fill"
                    style={{ width: `${Math.max(4, Math.min(100, f.score))}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
