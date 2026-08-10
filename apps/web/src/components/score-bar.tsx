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
  lifts?: Array<{ key: string; label: string; score: number; contribution?: number; gap?: number }>;
  drags?: Array<{ key: string; label: string; score: number; gap?: number }>;
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

/** Clickable meter — opportunity uses sitewide standings; risk/completeness use lean lenses. */
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
  const kind = standings?.kind || (invert ? "risk" : undefined);
  const hasStandings = Boolean(standings?.histogram?.length || standings?.rank_plain);
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
          {kind === "risk" && standings ? (
            <RiskLens score={v} standings={standings} />
          ) : kind === "confidence" && standings ? (
            <CompletenessLens score={v} standings={standings} />
          ) : hasStandings && standings?.histogram?.length ? (
            <OpportunityStandingsPanel score={v} standings={standings} />
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

/** Risk — spectrum + two chips. Deliberately not a histogram clone. */
function RiskLens({ score, standings }: { score: number; standings: ScoreStandings }) {
  const safer = Math.round(standings.beats_pct || 0);
  const worries = (standings.lifts || []).slice(0, 1);
  const calms = (standings.drags || []).slice(0, 1);
  const why = (standings.why_not_higher || [])[0];
  const band = score <= 35 ? "Calm" : score <= 55 ? "Watch" : "Elevated";

  return (
    <div className="score-lens score-lens--risk">
      <div className="score-lens-top">
        <span className={`score-lens-pill tone-${band.toLowerCase()}`}>{band}</span>
        <span className="score-lens-stat">
          Safer than <strong>~{safer}%</strong> of live files
        </span>
      </div>
      <div className="risk-spectrum" aria-hidden>
        <div className="risk-spectrum-track">
          <div className="risk-spectrum-you" style={{ left: `${score}%` }} title={`Risk ${Math.round(score)}`} />
        </div>
        <div className="risk-spectrum-labels">
          <span>Calm</span>
          <span>Hot</span>
        </div>
      </div>
      <div className="score-lens-chips">
        {worries[0] ? (
          <span className="score-chip score-chip--warn">
            Main flag · {worries[0].label}
          </span>
        ) : (
          <span className="score-chip">No loud map flag</span>
        )}
        {calms[0] ? (
          <span className="score-chip score-chip--ok">
            Helping · {calms[0].label}
          </span>
        ) : null}
      </div>
      {why ? <p className="score-lens-why">{why}</p> : null}
    </div>
  );
}

/** Completeness — checklist, not a standings clone. */
function CompletenessLens({ score, standings }: { score: number; standings: ScoreStandings }) {
  const factors = (standings.factors || []).slice(0, 4);
  const have = factors.filter((f) => f.direction === "up").length;
  const total = Math.max(factors.length, 1);
  const band = score >= 65 ? "Full enough" : score >= 40 ? "Partly filled" : "Thin file";
  const why = (standings.why_not_higher || [])[0];

  return (
    <div className="score-lens score-lens--complete">
      <div className="score-lens-top">
        <span className={`score-lens-pill tone-${score >= 65 ? "calm" : score >= 40 ? "watch" : "elevated"}`}>
          {band}
        </span>
        <span className="score-lens-stat">
          <strong>
            {have}/{total}
          </strong>{" "}
          key screens on file
        </span>
      </div>
      <ul className="complete-checks">
        {factors.map((f) => {
          const ok = f.direction === "up";
          return (
            <li key={f.key} className={ok ? "is-on" : "is-off"}>
              <span aria-hidden>{ok ? "✓" : "·"}</span>
              {f.label}
            </li>
          );
        })}
      </ul>
      {why ? <p className="score-lens-why">{why}</p> : null}
    </div>
  );
}

function OpportunityStandingsPanel({
  score,
  standings,
}: {
  score: number;
  standings: ScoreStandings;
}) {
  const hist = standings.histogram || [];
  const n = standings.sample_n || 0;
  const markerBucket = hist.findIndex((b) => score >= b.lo && score < b.hi);
  const markerIdx =
    markerBucket >= 0 ? markerBucket : score >= 100 ? hist.length - 1 : 0;
  const topFactors = (standings.factors || []).slice(0, 3);
  const why = (standings.why_not_higher || [])[0];
  const whyLabel = standings.why_label || "Why not 90";
  const factorsLabel = standings.factors_label || `What’s in your ${Math.round(score)}`;

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
            Beats <strong>~{Math.round(standings.beats_pct || 0)}%</strong>
          </span>
          <span>
            Median <strong>{standings.median != null ? Math.round(standings.median) : "—"}</strong>
          </span>
          <span>
            Site high <strong>{standings.max != null ? Math.round(standings.max) : "—"}</strong>
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
