"use client";

import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

type PathPoint = {
  year_offset: number;
  land_usd?: number;
  exit_usd?: number;
  noi_usd?: number;
  cumulative_rent_usd?: number;
  cumulative_carry_usd?: number;
  total_back_usd?: number;
  gain_usd?: number;
};

type CaseEndpoint = {
  irr?: number | null;
  irr_display?: string;
  exit_usd?: number | null;
  land_mark_usd?: number | null;
  cumulative_rent_usd?: number | null;
  total_back_usd?: number | null;
  gain_usd?: number | null;
  path?: PathPoint[];
  starting_noi?: number | null;
  effective_annual_used?: number | null;
  case_label?: string;
  purchase_usd?: number | null;
  hold_years?: number;
};

type Factor = {
  key?: string;
  label?: string;
  bps?: number;
  pct_points?: number;
  direction?: string;
  kind?: string;
  plain?: string;
};

type ReturnIntel = {
  available?: boolean;
  reason?: string;
  purchase_usd?: number | null;
  mark_usd?: number | null;
  hold_years?: number;
  windows?: number[];
  model?: {
    effective_annual?: number;
    effective_annual_display?: string;
    uncertainty?: number;
    usable_frac?: number;
    factor_count?: number;
    place?: string;
    strategy?: string;
  };
  factors?: Factor[];
  all_factors?: Factor[];
  endpoints?: Record<string, Record<string, CaseEndpoint>>;
  paths_100?: Record<
    string,
    {
      path?: PathPoint[];
      case_label?: string;
      purchase_usd?: number;
      starting_noi?: number;
      effective_annual_used?: number;
    }
  >;
  summary?: string;
  method?: string;
};

/** Legacy scenario shape — only used if return_intelligence is missing. */
type LegacyCase = {
  case?: string;
  case_label?: string;
  case_type?: string;
  summary?: string;
  plain_english?: string;
  numbers?: Record<string, unknown>;
  irr?: number | string | null;
  noi?: number;
  annual_appreciation?: number;
  annual_appreciation_display?: string;
  purchase_price?: number;
  cash_rent_per_acre?: number;
};

const HOLD_YEARS = [1, 3, 5, 10, 15, 30, 50, 75, 100] as const;
const CASE_ORDER = ["BEAR", "BASE", "BULL"] as const;

function money(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function shortMoney(v: number): string {
  const a = Math.abs(v);
  if (a >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (a >= 10_000) return `$${Math.round(v / 1000)}k`;
  if (a >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  return money(v);
}

function caseLabel(key: string): string {
  if (key === "BEAR" || key === "DOWNSIDE" || key === "STRESS") return "Cautious";
  if (key === "BULL" || key === "UPSIDE") return "Optimistic";
  return "Typical";
}

function caseTone(key: string): string {
  if (key === "BEAR" || key === "DOWNSIDE" || key === "STRESS") return "bear";
  if (key === "BULL" || key === "UPSIDE") return "bull";
  return "base";
}

/** Interactive multi-factor return path — curved year-by-year, not a flat diagonal. */
export function ReturnVisual({
  intel,
  cases: legacyCases,
  entryUsd,
  markUsd,
  annualRate,
}: {
  intel?: ReturnIntel | null;
  cases?: LegacyCase[];
  identity?: string;
  entryLabel?: string;
  markLabel?: string;
  entryUsd?: number | null;
  markUsd?: number | null;
  annualRate?: number | null;
}) {
  const windows = (intel?.windows?.length ? intel.windows : [...HOLD_YEARS]).filter((w) =>
    HOLD_YEARS.includes(w as (typeof HOLD_YEARS)[number]),
  );
  const [holdYears, setHoldYears] = useState(intel?.hold_years && windows.includes(intel.hold_years) ? intel.hold_years : 10);
  const [activeCase, setActiveCase] = useState<(typeof CASE_ORDER)[number]>("BASE");
  const [scrubYear, setScrubYear] = useState(holdYears);
  const [dragging, setDragging] = useState(false);
  const [showAllFactors, setShowAllFactors] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const available = intel?.available !== false && Boolean(intel?.endpoints || intel?.paths_100);

  const endpoint = intel?.endpoints?.[String(holdYears)]?.[activeCase];
  const fullPath = intel?.paths_100?.[activeCase]?.path || endpoint?.path || [];
  const path = useMemo(() => {
    const pts = fullPath.filter((p) => Number(p.year_offset) >= 1 && Number(p.year_offset) <= holdYears);
    return pts.length ? pts : (endpoint?.path || []).slice(0, holdYears);
  }, [fullPath, holdYears, endpoint?.path]);

  // Keep scrub inside the selected hold window
  const scrubClamped = Math.max(1, Math.min(holdYears, scrubYear));
  const scrubPoint = path.find((p) => Number(p.year_offset) === scrubClamped) || path[path.length - 1];

  const bandPaths = useMemo(() => {
    const out: Record<string, PathPoint[]> = {};
    for (const c of CASE_ORDER) {
      const src = intel?.paths_100?.[c]?.path || intel?.endpoints?.[String(holdYears)]?.[c]?.path || [];
      out[c] = src.filter((p) => Number(p.year_offset) >= 1 && Number(p.year_offset) <= holdYears);
    }
    return out;
  }, [intel, holdYears]);

  const chart = useMemo(() => {
    const series = bandPaths.BASE.length ? bandPaths : { BASE: path, BEAR: path, BULL: path };
    const allVals = Object.values(series)
      .flat()
      .map((p) => Number(p.total_back_usd ?? p.exit_usd ?? p.land_usd ?? 0))
      .filter((v) => v > 0);
    const purchase = Number(intel?.purchase_usd || endpoint?.purchase_usd || entryUsd || markUsd || 0);
    if (purchase > 0) allVals.push(purchase);
    const minV = allVals.length ? Math.min(...allVals) * 0.92 : 0;
    const maxV = allVals.length ? Math.max(...allVals) * 1.06 : 1;
    const W = 640;
    const H = 220;
    const padL = 48;
    const padR = 16;
    const padT = 18;
    const padB = 28;
    const xOf = (y: number) => padL + ((y - 0) / Math.max(1, holdYears)) * (W - padL - padR);
    const yOf = (v: number) => {
      const t = (v - minV) / Math.max(1, maxV - minV);
      return padT + (1 - t) * (H - padT - padB);
    };
    const lineFor = (pts: PathPoint[]) => {
      if (!pts.length) return "";
      const start = `M ${xOf(0)} ${yOf(purchase)}`;
      const rest = pts
        .map((p) => {
          const v = Number(p.total_back_usd ?? p.exit_usd ?? p.land_usd ?? 0);
          return `L ${xOf(Number(p.year_offset))} ${yOf(v)}`;
        })
        .join(" ");
      return `${start} ${rest}`;
    };
    // Sample for smooth-looking polyline (every year for short holds; step for long)
    const step = holdYears > 40 ? 2 : 1;
    const sample = (pts: PathPoint[]) => pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
    return {
      W,
      H,
      padL,
      padR,
      padT,
      padB,
      xOf,
      yOf,
      purchase,
      minV,
      maxV,
      bearD: lineFor(sample(series.BEAR || [])),
      baseD: lineFor(sample(series.BASE || [])),
      bullD: lineFor(sample(series.BULL || [])),
    };
  }, [bandPaths, path, holdYears, intel?.purchase_usd, endpoint?.purchase_usd, entryUsd, markUsd]);

  const yearFromClientX = useCallback(
    (clientX: number) => {
      const svg = svgRef.current;
      if (!svg) return holdYears;
      const rect = svg.getBoundingClientRect();
      const rel = (clientX - rect.left) / Math.max(1, rect.width);
      const x = rel * chart.W;
      const t = (x - chart.padL) / Math.max(1, chart.W - chart.padL - chart.padR);
      return Math.max(1, Math.min(holdYears, Math.round(t * holdYears)));
    },
    [chart, holdYears],
  );

  const onPointerDown = (e: ReactPointerEvent) => {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setDragging(true);
    setScrubYear(yearFromClientX(e.clientX));
  };
  const onPointerMove = (e: ReactPointerEvent) => {
    if (!dragging && e.buttons === 0) return;
    setScrubYear(yearFromClientX(e.clientX));
  };
  const onPointerUp = () => setDragging(false);

  const factors = showAllFactors ? intel?.all_factors || intel?.factors || [] : intel?.factors || [];
  const factorCount = intel?.model?.factor_count ?? factors.length;
  const irrPct = endpoint?.irr != null ? Number(endpoint.irr) * 100 : null;
  const endpointsAtHold = intel?.endpoints?.[String(holdYears)] || {};

  // Fallback: legacy flat compound if intel missing
  if (!available) {
    return (
      <LegacyReturnVisual
        cases={legacyCases || []}
        entryUsd={entryUsd}
        markUsd={markUsd}
        annualRate={annualRate}
        reason={intel?.reason}
        factors={intel?.factors}
      />
    );
  }

  const scrubX = chart.xOf(scrubClamped);
  const scrubY = scrubPoint
    ? chart.yOf(Number(scrubPoint.total_back_usd ?? scrubPoint.exit_usd ?? 0))
    : chart.yOf(chart.purchase);

  return (
    <div className="return-visual">
      <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
        Multi-factor return path
      </div>
      <h3 className="display text-lg font-semibold">If you hold this property</h3>
      <p className="mt-1 text-sm text-[var(--muted)] leading-relaxed">
        {intel?.summary ||
          `${factorCount} screens bend this path — soil, flood, growth, channel, carry, and more — not a flat diagonal.`}
        {intel?.purchase_usd ? ` Buy near ${money(intel.purchase_usd)}.` : ""}
      </p>

      <div className="traj-windows mt-3" role="tablist" aria-label="Return case">
        {CASE_ORDER.map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={activeCase === k}
            className={`traj-window-btn ${activeCase === k ? "active" : ""}`}
            onClick={() => setActiveCase(k)}
          >
            {caseLabel(k)}
          </button>
        ))}
      </div>

      <div className="traj-windows" role="tablist" aria-label="Hold length">
        {windows.map((y) => (
          <button
            key={y}
            type="button"
            role="tab"
            aria-selected={holdYears === y}
            className={`traj-window-btn ${holdYears === y ? "active" : ""}`}
            onClick={() => {
              setHoldYears(y);
              setScrubYear(y);
            }}
          >
            {y} yr
          </button>
        ))}
      </div>

      <div className="return-chart-wrap mt-3">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${chart.W} ${chart.H}`}
          className="return-chart"
          role="img"
          aria-label={`Return path over ${holdYears} years`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
        >
          <defs>
            <linearGradient id="returnBand" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.18" />
              <stop offset="100%" stopColor="var(--brand)" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {/* Grid years */}
          {[0, Math.round(holdYears / 2), holdYears].map((y) => (
            <g key={y}>
              <line
                x1={chart.xOf(y)}
                x2={chart.xOf(y)}
                y1={chart.padT}
                y2={chart.H - chart.padB}
                stroke="var(--line)"
                strokeWidth="1"
              />
              <text
                x={chart.xOf(y)}
                y={chart.H - 8}
                textAnchor="middle"
                fontSize="10"
                fill="var(--muted)"
              >
                {y === 0 ? "buy" : `${y}y`}
              </text>
            </g>
          ))}
          <text x={8} y={chart.padT + 4} fontSize="10" fill="var(--muted)">
            {shortMoney(chart.maxV)}
          </text>
          <text x={8} y={chart.H - chart.padB} fontSize="10" fill="var(--muted)">
            {shortMoney(chart.minV)}
          </text>

          {chart.bearD ? (
            <path d={chart.bearD} fill="none" stroke="var(--danger)" strokeOpacity="0.35" strokeWidth="1.5" />
          ) : null}
          {chart.bullD ? (
            <path d={chart.bullD} fill="none" stroke="var(--positive)" strokeOpacity="0.4" strokeWidth="1.5" />
          ) : null}
          {chart.baseD ? (
            <path
              d={chart.baseD}
              fill="none"
              stroke="var(--brand)"
              strokeWidth={activeCase === "BASE" ? 2.75 : 2}
              className="return-path-line"
            />
          ) : null}
          {/* Active case emphasis */}
          {activeCase === "BEAR" && chart.bearD ? (
            <path d={chart.bearD} fill="none" stroke="var(--danger)" strokeWidth="2.75" />
          ) : null}
          {activeCase === "BULL" && chart.bullD ? (
            <path d={chart.bullD} fill="none" stroke="var(--positive)" strokeWidth="2.75" />
          ) : null}

          <line
            x1={scrubX}
            x2={scrubX}
            y1={chart.padT}
            y2={chart.H - chart.padB}
            stroke="var(--ink)"
            strokeOpacity="0.35"
            strokeDasharray="3 3"
          />
          <circle cx={scrubX} cy={scrubY} r="5" fill="var(--brand)" stroke="var(--bg)" strokeWidth="2" />
          <circle cx={chart.xOf(0)} cy={chart.yOf(chart.purchase)} r="3.5" fill="var(--ink)" />
        </svg>
        <div className="return-scrub-hint">
          Drag the chart · year {scrubClamped} of {holdYears} · total back{" "}
          <strong>{money(scrubPoint?.total_back_usd)}</strong>
        </div>
      </div>

      {endpoint && (
        <div className="return-future mt-3">
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
            After exactly {holdYears} years · {caseLabel(activeCase).toLowerCase()}
          </div>
          <div className="return-future-grid">
            <div>
              <span>Land at exit</span>
              <strong>{money(endpoint.exit_usd)}</strong>
            </div>
            <div>
              <span>Rent along the way</span>
              <strong>{money(endpoint.cumulative_rent_usd)}</strong>
            </div>
            <div>
              <span>Total back</span>
              <strong>{money(endpoint.total_back_usd)}</strong>
            </div>
            <div>
              <span>Vs buy · annualized</span>
              <strong
                className={
                  (endpoint.gain_usd ?? 0) >= 0 ? "text-[var(--positive)]" : "text-[var(--danger)]"
                }
              >
                {(endpoint.gain_usd ?? 0) >= 0 ? "+" : ""}
                {money(endpoint.gain_usd)}
                {irrPct != null ? ` · ${irrPct.toFixed(1)}%/yr` : ""}
              </strong>
            </div>
          </div>
          <p className="mt-2 text-[11px] text-[var(--muted)] leading-relaxed">
            Path bends year-by-year with cycles, carry, usable acres, and an exit haircut — not
            buy × (1 + r)^{holdYears}. Pace used ~{" "}
            {endpoint.effective_annual_used != null
              ? `${(Number(endpoint.effective_annual_used) * 100).toFixed(1)}%/yr`
              : intel?.model?.effective_annual_display || "—"}{" "}
            before case stress.
          </p>
        </div>
      )}

      <div className="mt-4 space-y-2">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
          All cases at {holdYears} years
        </div>
        {CASE_ORDER.map((k) => {
          const ep = endpointsAtHold[k];
          if (!ep) return null;
          const pct = ep.irr != null ? Number(ep.irr) * 100 : null;
          const maxAbs = Math.max(
            12,
            ...CASE_ORDER.map((x) => Math.abs(Number(endpointsAtHold[x]?.irr || 0) * 100)),
          );
          const w = pct != null ? Math.max(6, (Math.abs(pct) / maxAbs) * 100) : 6;
          return (
            <button
              key={k}
              type="button"
              className={`return-mini ${activeCase === k ? "active" : ""} tone-${caseTone(k)}`}
              onClick={() => setActiveCase(k)}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-semibold">{caseLabel(k)}</span>
                <span className="tabular-nums">
                  {pct != null ? `${pct.toFixed(1)}%/yr` : "n/a"} · land {money(ep.exit_usd)}
                </span>
              </div>
              <div className="return-track">
                <div
                  className={`return-fill ${pct != null && pct >= 0 ? "pos" : "neg"}`}
                  style={{ width: `${w}%` }}
                />
              </div>
            </button>
          );
        })}
      </div>

      {factors.length > 0 && (
        <div className="return-factors mt-4">
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
              What bends this path · {factorCount} screens
            </div>
            {(intel?.all_factors?.length || 0) > (intel?.factors?.length || 0) && (
              <button
                type="button"
                className="text-[11px] text-[var(--brand)] underline-offset-2 hover:underline"
                onClick={() => setShowAllFactors((v) => !v)}
              >
                {showAllFactors ? "Show top drivers" : "Show all"}
              </button>
            )}
          </div>
          <div className="return-factor-grid mt-2">
            {factors.map((f) => (
              <div key={f.key || f.label} className={`return-factor dir-${f.direction || "neutral"}`}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold">{f.label}</span>
                  <span className="tabular-nums text-[11px]">
                    {f.bps != null && f.bps !== 0
                      ? `${f.bps > 0 ? "+" : ""}${(Number(f.bps) / 100).toFixed(2)} pts`
                      : f.kind === "entry"
                        ? "entry"
                        : "—"}
                  </span>
                </div>
                <p>{f.plain}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {intel?.method ? (
        <p className="mt-3 text-[10px] text-[var(--muted)] leading-relaxed">{intel.method}</p>
      ) : null}
    </div>
  );
}

/** Flat compound fallback when multi-factor intel is unavailable. */
function LegacyReturnVisual({
  cases,
  entryUsd,
  markUsd,
  annualRate,
  reason,
  factors,
}: {
  cases: LegacyCase[];
  entryUsd?: number | null;
  markUsd?: number | null;
  annualRate?: number | null;
  reason?: string;
  factors?: Factor[];
}) {
  const purchase = Number(entryUsd || markUsd || 0);
  return (
    <div className="return-visual">
      <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
        Possible yearly return
      </div>
      <h3 className="display text-lg font-semibold">If you hold this property</h3>
      <p className="mt-1 text-sm text-[var(--muted)]">
        {reason ||
          "Need a buy price or value estimate before a multi-factor return path can be built."}
        {purchase > 0 ? ` Entry near ${money(purchase)}.` : ""}
      </p>
      {factors && factors.length > 0 ? (
        <div className="return-factor-grid mt-3">
          {factors.slice(0, 6).map((f) => (
            <div key={f.key || f.label} className={`return-factor dir-${f.direction || "neutral"}`}>
              <div className="font-semibold">{f.label}</div>
              <p>{f.plain}</p>
            </div>
          ))}
        </div>
      ) : cases.length ? (
        <p className="mt-2 text-[11px] text-[var(--muted)]">
          Legacy rent cases are on file, but the full path engine needs a usable entry price.
          {annualRate != null ? ` Area pace ~${(annualRate * 100).toFixed(1)}%/yr.` : ""}
        </p>
      ) : null}
    </div>
  );
}
