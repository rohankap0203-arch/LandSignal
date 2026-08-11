"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { cpiFromMeta, deflate, realRate, type InflationMeta, type MoneyMode } from "@/lib/inflation";
import { MoneyModeControl, moneyModeShort } from "@/components/money-mode-control";
import { BuyingPowerLogic } from "@/components/buying-power-logic";

type Point = {
  year: number;
  value_usd: number;
  kind?: string;
  source?: string;
  note?: string;
  offset?: number;
};

type Hitch = {
  id: string;
  label?: string;
  short?: string;
  plain?: string;
  severity?: number;
  points?: Point[];
};

type HitchHelp = {
  title?: string;
  body?: string;
  items?: Array<{ id?: string; label?: string; plain?: string; math?: string }>;
};

type Trajectory = {
  identity?: string;
  headline?: string;
  regime?: string;
  regime_label?: string;
  knowledge_label?: string;
  annual_rate_display?: string;
  now_usd?: number;
  forward_usd_today?: number | null;
  cagr_forward_real?: number | null;
  cagr_forward_real_display?: string | null;
  inflation?: InflationMeta | null;
  points?: Point[];
  hitches?: Hitch[];
  hitch_help?: HitchHelp;
  summary_bullets?: string[];
  method_notes?: string[];
  disclaimer?: string;
  windows?: number[];
};

/** Value-over-time presets (not 5-year hold steps — those live on return hold). */
const TIMEFRAMES = [1, 3, 5, 10, 15, 25, 40, 60, 80, 100] as const;

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

function cagr(start: number, end: number, years: number): number | null {
  if (!(start > 0) || !(end > 0) || !(years > 0)) return null;
  return Math.pow(end / start, 1 / years) - 1;
}

/** Interactive value path — selected N-year window is exact lookback math. */
export function PriceTrajectory({
  trajectory,
  compact,
  moneyMode: moneyModeProp,
  onMoneyModeChange,
}: {
  trajectory: Trajectory | null | undefined;
  compact?: boolean;
  moneyMode?: MoneyMode;
  onMoneyModeChange?: (m: MoneyMode) => void;
}) {
  const hitches = trajectory?.hitches || [];
  const windows = (trajectory?.windows?.length ? trajectory.windows : [...TIMEFRAMES]).filter((w) =>
    TIMEFRAMES.includes(w as (typeof TIMEFRAMES)[number]),
  );
  const [horizon, setHorizon] = useState(10);
  const [hitchId, setHitchId] = useState<string>("base");
  const [hitchHelpOpen, setHitchHelpOpen] = useState(false);
  const [moneyModeLocal, setMoneyModeLocal] = useState<MoneyMode>("today");
  const moneyMode = moneyModeProp ?? moneyModeLocal;
  const setMoneyMode = onMoneyModeChange ?? setMoneyModeLocal;
  const [dragging, setDragging] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const cpi = cpiFromMeta(trajectory?.inflation);
  const cpiDisplay = trajectory?.inflation?.cpi_display || `${(cpi * 100).toFixed(1)}%/yr`;
  const showToday = moneyMode === "today";

  useEffect(() => {
    if (!hitchHelpOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setHitchHelpOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hitchHelpOpen]);

  const activeHitch = hitches.find((h) => h.id === hitchId) || null;
  const sourcePoints =
    hitchId !== "base" && activeHitch?.points?.length
      ? activeHitch.points
      : trajectory?.points || [];
  const allPoints = sourcePoints.filter((p) => Number.isFinite(Number(p.value_usd)));

  // Exact window: N years back AND N years forward (symmetric around today)
  const points = useMemo(() => {
    if (!allPoints.length) return [];
    const byOff = new Map(allPoints.map((p) => [Number(p.offset ?? 0), p]));
    const out: Point[] = [];
    for (let o = -horizon; o <= horizon; o++) {
      const hit = byOff.get(o);
      if (hit) out.push(hit);
    }
    return out;
  }, [allPoints, horizon]);

  const windowMath = useMemo(() => {
    const start = points.find((p) => Number(p.offset) === -horizon);
    const today = points.find((p) => Number(p.offset) === 0);
    const future = points.find((p) => Number(p.offset) === horizon);
    if (!start || !today || !future) return null;
    const pastRate = cagr(Number(start.value_usd), Number(today.value_usd), horizon);
    const fwdRate = cagr(Number(today.value_usd), Number(future.value_usd), horizon);
    const fwdReal = realRate(fwdRate, cpi);
    const futureToday = deflate(Number(future.value_usd), horizon, cpi);
    const pastChange =
      Number(start.value_usd) > 0
        ? ((Number(today.value_usd) - Number(start.value_usd)) / Number(start.value_usd)) * 100
        : null;
    const fwdChange =
      Number(today.value_usd) > 0
        ? ((Number(future.value_usd) - Number(today.value_usd)) / Number(today.value_usd)) * 100
        : null;
    return {
      startYear: start.year,
      todayYear: today.year,
      endYear: future.year,
      startUsd: Number(start.value_usd),
      todayUsd: Number(today.value_usd),
      endUsd: Number(today.value_usd),
      futureUsd: Number(future.value_usd),
      futureUsdToday: futureToday,
      years: horizon,
      pastRate,
      fwdRate,
      fwdReal,
      pastChange,
      fwdChange,
      cagrDisplay: pastRate != null ? `${pastRate >= 0 ? "+" : ""}${(pastRate * 100).toFixed(1)}%/yr` : "—",
      forwardCagrDisplay:
        fwdRate != null ? `${fwdRate >= 0 ? "+" : ""}${(fwdRate * 100).toFixed(1)}%/yr` : "—",
      forwardCagrRealDisplay:
        fwdReal != null
          ? `${fwdReal >= 0 ? "+" : ""}${(fwdReal * 100).toFixed(1)}%/yr in today’s dollars`
          : "—",
    };
  }, [points, horizon, cpi]);

  const todayIdx = useMemo(() => {
    const i = points.findIndex((p) => Number(p.offset) === 0);
    return i >= 0 ? i : Math.max(0, points.length - 1);
  }, [points]);

  const [active, setActive] = useState(todayIdx);
  useEffect(() => {
    setActive(todayIdx);
  }, [todayIdx, horizon]);

  const displayPoints = useMemo(() => {
    // After inflation: future marks in today’s purchasing power. Past/today stay as recorded.
    return points.map((p) => {
      const off = Number(p.offset ?? 0);
      const raw = Number(p.value_usd);
      if (!showToday || !(off > 0) || !Number.isFinite(raw)) {
        return { ...p, display_usd: raw };
      }
      return { ...p, display_usd: deflate(raw, off, cpi) ?? raw };
    });
  }, [points, showToday, cpi]);

  const layout = useMemo(() => {
    if (displayPoints.length < 2) return null;
    const years = displayPoints.map((p) => Number(p.year));
    const minYear = Math.min(...years);
    const maxYear = Math.max(...years);
    const ys = displayPoints.map((p) => Number(p.display_usd));
    const minY = Math.min(...ys) * 0.92;
    const maxY = Math.max(...ys) * 1.06;
    const padL = 52;
    const padR = 18;
    const padT = 22;
    const padB = 38;
    const w = compact ? 300 : 520;
    const h = compact ? 160 : 260;
    const span = Math.max(1, maxYear - minYear);
    const xScale = (year: number) => padL + ((year - minYear) / span) * (w - padL - padR);
    const yScale = (y: number) => padT + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - padT - padB);
    const mapped = displayPoints.map((p) => ({
      ...p,
      cx: xScale(Number(p.year)),
      cy: yScale(Number(p.display_usd)),
    }));
    const hist = mapped.filter((p) => Number(p.offset ?? 0) <= 0);
    const fut = mapped.filter((p) => Number(p.offset ?? 0) >= 0);
    const histPath = hist.map((p, i) => `${i === 0 ? "M" : "L"} ${p.cx.toFixed(1)} ${p.cy.toFixed(1)}`).join(" ");
    const futPath = fut.map((p, i) => `${i === 0 ? "M" : "L"} ${p.cx.toFixed(1)} ${p.cy.toFixed(1)}`).join(" ");
    const areaPath =
      hist.length > 1
        ? `${histPath} L ${hist[hist.length - 1].cx.toFixed(1)} ${(h - padB).toFixed(1)} L ${hist[0].cx.toFixed(1)} ${(h - padB).toFixed(1)} Z`
        : "";
    // Today x for a marker band
    const today = mapped.find((p) => Number(p.offset) === 0);
    return {
      w,
      h,
      padL,
      padT,
      padB,
      padR,
      mapped,
      histPath,
      futPath,
      areaPath,
      minY,
      maxY,
      minYear,
      maxYear,
      yScale,
      xScale,
      todayCx: today?.cx,
    };
  }, [displayPoints, compact]);

  const indexFromClientX = useCallback(
    (clientX: number) => {
      if (!layout || !svgRef.current || points.length < 2) return 0;
      const rect = svgRef.current.getBoundingClientRect();
      const xSvg = ((clientX - rect.left) / Math.max(1, rect.width)) * layout.w;
      // nearest point by x
      let best = 0;
      let bestDist = Infinity;
      layout.mapped.forEach((p, i) => {
        const d = Math.abs(p.cx - xSvg);
        if (d < bestDist) {
          bestDist = d;
          best = i;
        }
      });
      return best;
    },
    [layout, points.length],
  );

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (!layout) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    setDragging(true);
    setActive(indexFromClientX(e.clientX));
  };
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (dragging || e.pointerType === "mouse") setActive(indexFromClientX(e.clientX));
  };
  const onPointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    setDragging(false);
    try {
      (e.target as Element).releasePointerCapture?.(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  if (!trajectory || !layout || !windowMath) {
    return (
      <div className="price-trajectory">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Land value path</div>
        <p className="mt-1 text-sm text-[var(--muted)]">Building the dollar path…</p>
      </div>
    );
  }

  const selected = displayPoints[Math.min(Math.max(0, active), displayPoints.length - 1)];
  const sel = layout.mapped[Math.min(Math.max(0, active), layout.mapped.length - 1)];
  const selectedDisplay =
    selected && Number.isFinite(Number(selected.display_usd))
      ? Number(selected.display_usd)
      : Number(selected?.value_usd || 0);
  return (
    <div className={`price-trajectory ${compact ? "compact" : ""}`}>
      <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
        Land value path
      </div>

      <div className="traj-windows" role="tablist" aria-label="Chart time window">
        {(windows.length ? windows : TIMEFRAMES).map((y) => (
          <button
            key={y}
            type="button"
            role="tab"
            aria-selected={horizon === y}
            className={`traj-window-btn ${horizon === y ? "active" : ""}`}
            onClick={() => setHorizon(y)}
          >
            {y} yr
          </button>
        ))}
      </div>

      <div className="traj-head-row">
        <h3 className="display text-lg font-semibold leading-snug">
          {horizon} yr back · {horizon} yr ahead
        </h3>
        <div className="traj-stats">
          <div>
            <span>Past {horizon} yr</span>
            <strong className="tabular-nums">{windowMath.cagrDisplay}</strong>
          </div>
          <div>
            <span>Next {horizon} yr</span>
            <strong className="tabular-nums">
              {showToday ? windowMath.forwardCagrRealDisplay : windowMath.forwardCagrDisplay}
            </strong>
          </div>
          <div>
            <span>Now</span>
            <strong className="tabular-nums">{money(windowMath.todayUsd)}</strong>
          </div>
        </div>
      </div>

      <MoneyModeControl
        mode={moneyMode}
        onChange={setMoneyMode}
        cpiDisplay={cpiDisplay}
        compare={
          horizon >= 1 && windowMath.futureUsdToday != null
            ? {
                label: `Land value · ${horizon} yr ahead`,
                today: windowMath.futureUsdToday,
                before: windowMath.futureUsd,
                format: shortMoney,
              }
            : null
        }
      />

      <BuyingPowerLogic
        variant="land"
        years={horizon}
        cpi={cpi}
        cpiDisplay={cpiDisplay}
        markUsd={windowMath.todayUsd}
        futureNominal={windowMath.futureUsd}
        futureToday={windowMath.futureUsdToday}
      />

      <div className="traj-chart-row">
      <div className="traj-chart-wrap">
        <svg
          key={`traj-${horizon}-${hitchId}-${layout.minYear}-${layout.maxYear}`}
          ref={svgRef}
          className="traj-chart interactive"
          viewBox={`0 0 ${layout.w} ${layout.h}`}
          role="img"
          preserveAspectRatio="xMidYMid meet"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={() => setDragging(false)}
        >
          <title>{horizon} years back and {horizon} years forward</title>
          <defs>
            <linearGradient id="trajFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.22" />
              <stop offset="100%" stopColor="var(--brand)" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {[0, 0.5, 1].map((t) => {
            const y = layout.minY + t * (layout.maxY - layout.minY);
            const gy = layout.yScale(y);
            return (
              <g key={t}>
                <line
                  x1={layout.padL}
                  x2={layout.w - layout.padR}
                  y1={gy}
                  y2={gy}
                  stroke="var(--line)"
                  strokeWidth="1"
                />
                <text x={layout.padL - 6} y={gy + 3} textAnchor="end" className="chart-tick">
                  {shortMoney(y)}
                </text>
              </g>
            );
          })}
          {layout.areaPath ? <path d={layout.areaPath} fill="url(#trajFill)" /> : null}
          <path d={layout.histPath} fill="none" stroke="var(--brand)" strokeWidth="2.6" />
          <path
            d={layout.futPath}
            fill="none"
            stroke="var(--accent, #2f6f4e)"
            strokeWidth="2.2"
            strokeDasharray="5 4"
            opacity="0.9"
          />
          {layout.todayCx != null && (
            <line
              x1={layout.todayCx}
              x2={layout.todayCx}
              y1={layout.padT}
              y2={layout.h - layout.padB}
              stroke="var(--muted)"
              strokeWidth="1"
              strokeDasharray="2 3"
              opacity="0.5"
            />
          )}
          {/* Year ticks: start, today, end */}
          {layout.mapped.map((p, i) => {
            const o = Number(p.offset ?? 0);
            const show =
              o === -horizon ||
              o === 0 ||
              o === horizon ||
              i === 0 ||
              i === layout.mapped.length - 1;
            if (!show) return null;
            return (
              <text key={`tick-${p.year}-${i}`} x={p.cx} y={layout.h - 12} textAnchor="middle" className="chart-axis">
                {p.year}
              </text>
            );
          })}
          {sel && (
            <g className="traj-scrub">
              <line
                x1={sel.cx}
                x2={sel.cx}
                y1={layout.padT}
                y2={layout.h - layout.padB}
                stroke="var(--ink)"
                strokeWidth="1.2"
                strokeDasharray="3 3"
                opacity="0.45"
              />
              <circle
                cx={sel.cx}
                cy={sel.cy}
                r={dragging ? 7 : 5.5}
                fill={Number(sel.offset) > 0 ? "var(--accent, #2f6f4e)" : "var(--brand)"}
                stroke="#fff"
                strokeWidth="2"
              />
            </g>
          )}
        </svg>
      </div>

      {!compact && hitches.length > 0 ? (
        <div className="traj-hitch-col">
          <button
            type="button"
            className={`help-q hitch-help-q ${hitchHelpOpen ? "on" : ""}`}
            aria-label="What hitch buttons mean"
            aria-haspopup="dialog"
            aria-expanded={hitchHelpOpen}
            title="What these buttons mean"
            onClick={() => setHitchHelpOpen(true)}
          >
            ?
          </button>
          <div className="traj-hitch-rail" role="tablist" aria-label="Chart hitches">
            {hitches.slice(0, 3).map((h) => {
              const on = hitchId === h.id;
              return (
                <button
                  key={h.id}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  className={`traj-hitch-btn ${on ? "active" : ""}`}
                  onClick={() => setHitchId(on ? "base" : h.id)}
                  title={h.plain || h.label}
                >
                  <span className="traj-hitch-k">{h.short || h.label}</span>
                  <span className="traj-hitch-v">{on ? "On" : "Off"}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
      </div>

      {hitchHelpOpen && trajectory?.hitch_help ? (
        <div
          className="help-modal-backdrop"
          role="presentation"
          onClick={() => setHitchHelpOpen(false)}
        >
          <div
            className="help-modal help-modal--compact"
            role="dialog"
            aria-modal="true"
            aria-label="What hitch buttons mean"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h4 className="display text-base font-semibold">
                {trajectory.hitch_help.title || "What-if cases for the future"}
              </h4>
              <button
                type="button"
                className="help-q on"
                aria-label="Close"
                onClick={() => setHitchHelpOpen(false)}
              >
                ×
              </button>
            </div>
            <p className="mt-1.5 text-xs text-[var(--muted)] leading-snug">
              {trajectory.hitch_help.body}
            </p>
            <ul className="help-modal-list hitch-math-list">
              {(trajectory.hitch_help.items || []).map((item) => (
                <li key={item.id || item.label}>
                  <strong>{item.label}</strong>
                  {item.plain ? <span>{item.plain}</span> : null}
                  {item.math ? <code className="hitch-math">{item.math}</code> : null}
                </li>
              ))}
            </ul>
            <p className="mt-2.5 text-[11px] text-[var(--muted)] leading-snug">
              Tap a button to change only the future. Tap again to turn it off. Past years never
              change.
            </p>
          </div>
        </div>
      ) : null}

      {activeHitch && hitchId !== "base" ? (
        <p className="traj-hitch-note">{activeHitch.plain}</p>
      ) : !compact && hitches.length > 0 ? (
        <p className="traj-hitch-note">
          What-if: Higher rates · Stronger demand · Site problem · tap ? for math
        </p>
      ) : null}

      {selected && (
        <div className={`chart-readout traj-readout ${dragging ? "live" : ""}`}>
          <div>
            <strong>
              {selected.year}
              {Number(selected.offset) === 0
                ? " · today"
                : Number(selected.offset) < 0
                  ? ` · ${Math.abs(Number(selected.offset))} yr ago`
                  : ` · ${Number(selected.offset)} yr ahead`}
            </strong>
            <span className="traj-readout-value">
              {money(selectedDisplay)}
              {showToday && Number(selected.offset) > 0 ? (
                <em className="return-alt-line"> today’s dollars</em>
              ) : null}
            </span>
          </div>
        </div>
      )}

      <div className="traj-year-boxes">
        <div className="traj-year-box">
          <span>{horizon} yr back</span>
          <strong className="tabular-nums">{money(windowMath.startUsd)}</strong>
        </div>
        <div className="traj-year-box">
          <span>
            {horizon} yr ahead · {moneyModeShort(moneyMode)}
          </span>
          <strong className="tabular-nums">
            {money(showToday ? windowMath.futureUsdToday ?? windowMath.futureUsd : windowMath.futureUsd)}
          </strong>
        </div>
      </div>
    </div>
  );
}

/** Tiny sparkline for search cards. */
export function TrajectorySpark({
  values,
  label,
  cagr,
}: {
  values?: number[] | null;
  label?: string | null;
  cagr?: string | null;
}) {
  const vals = (values || []).filter((v) => Number.isFinite(v));
  if (vals.length < 2) return null;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const w = 120;
  const h = 28;
  const pts = vals
    .map((v, i) => {
      const x = (i / (vals.length - 1)) * w;
      const y = h - 2 - ((v - min) / Math.max(1, max - min)) * (h - 4);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const up = vals[vals.length - 1] >= vals[0];
  return (
    <div className="traj-spark">
      <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} aria-hidden>
        <polyline fill="none" stroke={up ? "var(--positive)" : "var(--danger)"} strokeWidth="2" points={pts} />
      </svg>
      <div className="traj-spark-meta">
        <span>{label || (up ? "Rising path" : "Soft path")}</span>
        {cagr ? <strong>{cagr}</strong> : null}
      </div>
    </div>
  );
}
