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

function FactorIcon({ name }: { name?: string }) {
  const k = (name || "").toLowerCase();
  const common = {
    className: "return-factor-icon",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };
  if (k.includes("flood") || k.includes("water")) {
    return (
      <svg {...common}>
        <path d="M12 3c-3 5-7 8-7 12a7 7 0 0 0 14 0c0-4-4-7-7-12z" />
      </svg>
    );
  }
  if (k.includes("soil") || k.includes("farm")) {
    return (
      <svg {...common}>
        <path d="M4 18c2-4 5-6 8-6s6 2 8 6" />
        <path d="M12 12V5" />
        <path d="M9 7c1 1 2 2 3 2s2-1 3-2" />
      </svg>
    );
  }
  if (k.includes("wet")) {
    return (
      <svg {...common}>
        <path d="M3 14c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2" />
        <path d="M3 18c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2" />
      </svg>
    );
  }
  if (k.includes("growth") || k.includes("area") || k.includes("pace")) {
    return (
      <svg {...common}>
        <path d="M4 18V10" />
        <path d="M10 18V6" />
        <path d="M16 18v-8" />
        <path d="M20 18V4" />
      </svg>
    );
  }
  if (k.includes("power") || k.includes("line") || k.includes("energy")) {
    return (
      <svg {...common}>
        <path d="M13 2 6 13h5l-1 9 8-12h-5l0-8z" />
      </svg>
    );
  }
  if (k.includes("access") || k.includes("road")) {
    return (
      <svg {...common}>
        <path d="M4 19 12 4l8 15" />
        <path d="M9 14h6" />
      </svg>
    );
  }
  if (k.includes("risk")) {
    return (
      <svg {...common}>
        <path d="M12 3 3 20h18L12 3z" />
        <path d="M12 9v5" />
        <path d="M12 17h.01" />
      </svg>
    );
  }
  if (k.includes("channel") || k.includes("sold") || k.includes("seller")) {
    return (
      <svg {...common}>
        <path d="M4 7h16" />
        <path d="M4 12h10" />
        <path d="M4 17h13" />
        <circle cx="18" cy="12" r="2" />
      </svg>
    );
  }
  if (k.includes("strateg") || k.includes("use") || k.includes("fit")) {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 8v4l3 2" />
      </svg>
    );
  }
  if (k.includes("liquid") || k.includes("scarce") || k.includes("rare") || k.includes("resale")) {
    return (
      <svg {...common}>
        <path d="M7 7h10v10H7z" />
        <path d="M3 12h4M17 12h4" />
      </svg>
    );
  }
  if (k.includes("complete") || k.includes("file")) {
    return (
      <svg {...common}>
        <path d="M7 3h7l4 4v14H7z" />
        <path d="M14 3v4h4" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="8" />
      <path d="M8 12h8" />
    </svg>
  );
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
  const [openFactor, setOpenFactor] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [casesHelpOpen, setCasesHelpOpen] = useState(false);
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
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
            Multi-factor return path
          </div>
          <h3 className="display text-lg font-semibold">If you hold this property</h3>
        </div>
        <button
          type="button"
          className={`help-q ${helpOpen ? "on" : ""}`}
          aria-label="How this return path works"
          aria-expanded={helpOpen}
          title="How this works"
          onClick={() => setHelpOpen((v) => !v)}
        >
          ?
        </button>
      </div>
      {helpOpen ? (
        <div className="help-panel mt-2">
          <p>
            This is not a straight “price goes up X% every year” line. LandSignal bends the path
            with this property’s own screens — soil, flood, wetlands, growth, how it’s sold, carry
            costs, and exit friction — then shows three cases:
          </p>
          <ul>
            <li>
              <strong>Cautious</strong> — slower rents, softer exit, higher carry
            </li>
            <li>
              <strong>Typical</strong> — base path for this file
            </li>
            <li>
              <strong>Optimistic</strong> — stronger rents and exit, still bounded
            </li>
          </ul>
          <p>
            Pick a hold length (1–100 yr). Drag the chart to read any year. Tap a factor card to see
            why it lifts or slows the path. First look only — not an appraisal.
          </p>
        </div>
      ) : null}
      <p className="mt-1 text-sm text-[var(--muted)] leading-snug">
        {factorCount} local screens shape the curve
        {intel?.purchase_usd ? ` · buy near ${money(intel.purchase_usd)}` : ""}.
        Pick a case and hold length.
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
            <div className="return-vs-cell">
              <span>Vs buy · annualized</span>
              <strong
                className={`return-vs-buy ${
                  (endpoint.gain_usd ?? 0) >= 0 ? "text-[var(--positive)]" : "text-[var(--danger)]"
                }`}
              >
                {(endpoint.gain_usd ?? 0) >= 0 ? "+" : ""}
                {shortMoney(Number(endpoint.gain_usd || 0))}
                {irrPct != null ? ` · ${irrPct.toFixed(1)}%/yr` : ""}
              </strong>
            </div>
          </div>
        </div>
      )}

      <div className="mt-4 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
            All cases at {holdYears} years
          </div>
          <button
            type="button"
            className={`help-q ${casesHelpOpen ? "on" : ""}`}
            aria-label="What these cases mean"
            aria-expanded={casesHelpOpen}
            title="What these cases mean"
            onClick={() => setCasesHelpOpen((v) => !v)}
          >
            ?
          </button>
        </div>
        {casesHelpOpen ? (
          <div className="help-panel">
            <p>Three ways the same hold can finish — tap a row to focus that path on the chart.</p>
            <ul>
              <li>
                <strong>Cautious</strong> — slower rents, softer sale price, more carry cost
              </li>
              <li>
                <strong>Typical</strong> — the base path for this property’s screens
              </li>
              <li>
                <strong>Optimistic</strong> — stronger rents and exit, still capped by the model
              </li>
            </ul>
            <p>
              The %/yr is the annualized return if you buy near the entry, collect rent, and sell at
              that case’s exit after exactly {holdYears} years. Not a promise — a screen.
            </p>
          </div>
        ) : null}
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
            {factors.map((f) => {
              const id = String(f.key || f.label);
              const open = openFactor === id;
              return (
                <button
                  key={id}
                  type="button"
                  className={`return-factor dir-${f.direction || "neutral"} text-left ${open ? "ring-1 ring-[var(--brand-soft)]" : ""}`}
                  onClick={() => setOpenFactor(open ? null : id)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="return-factor-head">
                      <FactorIcon name={f.key || f.label} />
                      <span className="font-semibold">{f.label}</span>
                    </span>
                    <span className="tabular-nums text-[11px]">
                      {f.bps != null && f.bps !== 0
                        ? `${f.bps > 0 ? "+" : ""}${(Number(f.bps) / 100).toFixed(2)} pts`
                        : f.kind === "entry"
                          ? "entry"
                          : "—"}
                    </span>
                  </div>
                  <p className={open ? "" : "line-clamp-3"}>{f.plain}</p>
                </button>
              );
            })}
          </div>
        </div>
      )}
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
