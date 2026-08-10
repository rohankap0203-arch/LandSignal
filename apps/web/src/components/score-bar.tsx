"use client";

import { useState } from "react";

export type OpportunityStandings = {
  score?: number;
  sample_n?: number;
  beats_pct?: number;
  percentile?: number;
  median?: number | null;
  p75?: number | null;
  p90?: number | null;
  p95?: number | null;
  max?: number | null;
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
  rank_plain?: string;
  ceiling_plain?: string;
  method_plain?: string;
};

/** Clickable red→green meter — opportunity expands into sitewide standings + factors. */
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
  standings?: OpportunityStandings | null;
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
            <OpportunityStandingsPanel score={v} standings={standings} verdict={verdict} />
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

function OpportunityStandingsPanel({
  score,
  standings,
  verdict,
}: {
  score: number;
  standings: OpportunityStandings;
  verdict?: string;
}) {
  const hist = standings.histogram || [];
  const n = standings.sample_n || 0;
  const markerBucket = hist.findIndex((b) => score >= b.lo && score < b.hi);
  const markerIdx =
    markerBucket >= 0 ? markerBucket : score >= 100 ? hist.length - 1 : 0;

  return (
    <div className="opp-standings">
      <p className="opp-standings-rank">{standings.rank_plain || verdict}</p>

      <div
        className="opp-hist"
        role="img"
        aria-label={`Opportunity score ${Math.round(score)} vs ${n.toLocaleString()} live files. Median ${
          standings.median != null ? Math.round(standings.median) : "n/a"
        }, site high ${standings.max != null ? Math.round(standings.max) : "n/a"}.`}
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
              <span className="opp-hist-tick">{b.lo}</span>
            </div>
          ))}
        </div>
        <div className="opp-hist-legend">
          <span>
            You · <strong>{Math.round(score)}</strong>
            {standings.beats_pct != null ? (
              <span className="opp-hist-beat"> · beats ~{Math.round(standings.beats_pct)}%</span>
            ) : null}
          </span>
          <span>
            Median · <strong>{standings.median != null ? Math.round(standings.median) : "—"}</strong>
          </span>
          <span>
            Site high · <strong>{standings.max != null ? Math.round(standings.max) : "—"}</strong>
          </span>
          <span className="opp-hist-n">{n.toLocaleString()} live files</span>
        </div>
      </div>

      {standings.ceiling_plain ? (
        <p className="opp-standings-ceiling">{standings.ceiling_plain}</p>
      ) : null}

      <div className="opp-why-block">
        <div className="opp-why-k">Why this number — not 90?</div>
        <ul>
          {(standings.why_not_higher || []).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>

      {standings.factors && standings.factors.length ? (
        <div className="opp-factors">
          <div className="opp-why-k">What builds the score</div>
          <div className="opp-factor-list">
            {standings.factors.slice(0, 6).map((f) => (
              <div key={f.key} className={`opp-factor-row tone-${f.direction}`}>
                <div className="opp-factor-top">
                  <span className="opp-factor-label">{f.label}</span>
                  <span className="opp-factor-score tabular-nums">
                    {Math.round(f.score)}
                    <span className="opp-factor-w"> · {f.weight_pct}%</span>
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

      {standings.method_plain ? (
        <p className="opp-standings-method">{standings.method_plain}</p>
      ) : null}
    </div>
  );
}
