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

/** Clickable meter — each score kind gets its own lean lens. */
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
          <ScorePin />
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
          ) : kind === "opportunity" && standings ? (
            <OpportunityLens score={v} standings={standings} />
          ) : hasStandings && standings ? (
            <OpportunityLens score={v} standings={standings} />
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

function ScorePin() {
  return (
    <svg className="score-pin" viewBox="0 0 16 16" width="14" height="14" aria-hidden>
      <path
        fill="currentColor"
        d="M8 1.5c-2.4 0-4.4 1.9-4.4 4.3 0 3.2 4.4 8.2 4.4 8.2s4.4-5 4.4-8.2C12.4 3.4 10.4 1.5 8 1.5zm0 6.1a1.8 1.8 0 1 1 0-3.6 1.8 1.8 0 0 1 0 3.6z"
      />
    </svg>
  );
}

/** Opportunity — plain compare to what’s live on the site. */
function OpportunityLens({ score, standings }: { score: number; standings: ScoreStandings }) {
  const beats = Math.round(standings.beats_pct || 0);
  const top = standings.max != null && Number.isFinite(Number(standings.max)) ? Math.round(Number(standings.max)) : null;
  const median =
    standings.median != null && Number.isFinite(Number(standings.median))
      ? Math.round(Number(standings.median))
      : null;
  const compare = (standings.why_not_higher || [])[0] || standings.ceiling_plain;
  const band =
    score >= 78
      ? "Strong buy"
      : score >= 66
        ? "Good buy"
        : score >= 50
          ? "Fair"
          : "Weak";
  const tone = score >= 66 ? "calm" : score >= 50 ? "watch" : "elevated";

  return (
    <div className="score-lens score-lens--opp">
      <div className="score-lens-top">
        <span className={`score-lens-pill tone-${tone}`}>{band}</span>
        <span className="score-lens-stat">
          Better than <strong>~{beats}%</strong> of listings on the site
          {top != null ? (
            <>
              {" "}
              · top is <strong>{top}</strong>
              {median != null ? (
                <>
                  {" "}
                  · middle ~<strong>{median}</strong>
                </>
              ) : null}
            </>
          ) : null}
        </span>
      </div>
      <div className="opp-edge" aria-hidden>
        <div className="opp-edge-track">
          <div className="opp-edge-fill" style={{ width: `${score}%` }} />
          <div className="opp-edge-you" style={{ left: `${score}%` }} title={`Opportunity ${Math.round(score)}`} />
        </div>
        <div className="opp-edge-labels">
          <span>Weak</span>
          <span>Strong</span>
        </div>
      </div>
      {compare ? <p className="score-lens-why">{compare}</p> : null}
    </div>
  );
}

/** Risk — spectrum + two chips. */
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
          <span className="score-chip score-chip--warn">Main flag · {worries[0].label}</span>
        ) : (
          <span className="score-chip">No loud map flag</span>
        )}
        {calms[0] ? (
          <span className="score-chip score-chip--ok">Helping · {calms[0].label}</span>
        ) : null}
      </div>
      {why ? <p className="score-lens-why">{why}</p> : null}
    </div>
  );
}

/** Completeness — checklist. */
function CompletenessLens({ score, standings }: { score: number; standings: ScoreStandings }) {
  const factors = (standings.factors || []).slice(0, 4);
  const have = factors.filter((f) => f.direction === "up").length;
  const total = Math.max(factors.length, 1);
  const band = score >= 65 ? "Full enough" : score >= 40 ? "Partly filled" : "Thin file";
  const why = (standings.why_not_higher || [])[0];

  return (
    <div className="score-lens score-lens--complete">
      <div className="score-lens-top">
        <span
          className={`score-lens-pill tone-${score >= 65 ? "calm" : score >= 40 ? "watch" : "elevated"}`}
        >
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
