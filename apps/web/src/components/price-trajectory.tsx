"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

type Point = {
  year: number;
  value_usd: number;
  kind?: string;
  source?: string;
  note?: string;
  offset?: number;
};

type Trajectory = {
  identity?: string;
  headline?: string;
  regime?: string;
  regime_label?: string;
  knowledge_state?: string;
  knowledge_label?: string;
  confidence?: number;
  annual_rate_display?: string;
  cagr_5y_display?: string;
  cagr_10y_display?: string;
  cagr_forward_display?: string;
  now_usd?: number;
  peak?: { year: number; value_usd: number };
  trough?: { year: number; value_usd: number };
  points?: Point[];
  summary_bullets?: string[];
  method_notes?: string[];
  disclaimer?: string;
  interaction_hint?: string;
  windows?: number[];
  window_stats?: Record<
    string,
    {
      years?: number;
      start_year?: number;
      start_usd?: number;
      end_usd?: number;
      cagr_display?: string;
      change_pct?: number | null;
    }
  >;
  observed_marks?: Array<{ year: number; value_usd: number; label?: string }>;
};

const TIMEFRAMES = [1, 3, 5, 10, 15, 30, 50, 75, 100] as const;

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

/** Interactive value path — drag to scrub years; toggle 1y–100y windows. */
export function PriceTrajectory({
  trajectory,
  compact,
}: {
  trajectory: Trajectory | null | undefined;
  compact?: boolean;
}) {
  const allPoints = (trajectory?.points || []).filter((p) => Number.isFinite(Number(p.value_usd)));
  const windows = (trajectory?.windows?.length ? trajectory.windows : [...TIMEFRAMES]).filter((w) =>
    TIMEFRAMES.includes(w as (typeof TIMEFRAMES)[number]),
  );
  const [horizon, setHorizon] = useState(10);
  const [dragging, setDragging] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const points = useMemo(() => {
    if (!allPoints.length) return [];
    const fwd = Math.min(10, Math.max(1, Math.ceil(horizon / 5)));
    return allPoints.filter((p) => {
      const o = Number(p.offset ?? 0);
      return o >= -horizon && o <= fwd;
    });
  }, [allPoints, horizon]);

  const todayIdx = useMemo(() => {
    const i = points.findIndex((p) => p.offset === 0);
    return i >= 0 ? i : Math.max(0, points.length - 1);
  }, [points]);

  const [active, setActive] = useState(todayIdx);

  useEffect(() => {
    setActive(todayIdx);
  }, [todayIdx, horizon]);

  const layout = useMemo(() => {
    if (points.length < 2) return null;
    const ys = points.map((p) => Number(p.value_usd));
    const minY = Math.min(...ys) * 0.92;
    const maxY = Math.max(...ys) * 1.06;
    const padL = 52;
    const padR = 18;
    const padT = 22;
    const padB = 38;
    const w = compact ? 300 : 520;
    const h = compact ? 160 : 260;
    const xScale = (i: number) => padL + (i / Math.max(1, points.length - 1)) * (w - padL - padR);
    const yScale = (y: number) => padT + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - padT - padB);
    const mapped = points.map((p, i) => ({ ...p, cx: xScale(i), cy: yScale(Number(p.value_usd)) }));
    const hist = mapped.filter((p) => p.kind !== "outlook");
    const fut = mapped.filter((p) => p.kind === "outlook" || p.offset === 0);
    const histPath = hist.map((p, i) => `${i === 0 ? "M" : "L"} ${p.cx.toFixed(1)} ${p.cy.toFixed(1)}`).join(" ");
    const futPath = fut.map((p, i) => `${i === 0 ? "M" : "L"} ${p.cx.toFixed(1)} ${p.cy.toFixed(1)}`).join(" ");
    const areaPath =
      hist.length > 1
        ? `${histPath} L ${hist[hist.length - 1].cx.toFixed(1)} ${(h - padB).toFixed(1)} L ${hist[0].cx.toFixed(1)} ${(h - padB).toFixed(1)} Z`
        : "";
    return { w, h, padL, padT, padB, padR, mapped, histPath, futPath, areaPath, minY, maxY, yScale, xScale };
  }, [points, compact]);

  const indexFromClientX = useCallback(
    (clientX: number) => {
      if (!layout || !svgRef.current || points.length < 2) return 0;
      const rect = svgRef.current.getBoundingClientRect();
      const xSvg = ((clientX - rect.left) / Math.max(1, rect.width)) * layout.w;
      const t = (xSvg - layout.padL) / Math.max(1, layout.w - layout.padL - layout.padR);
      return Math.max(0, Math.min(points.length - 1, Math.round(t * (points.length - 1))));
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
    if (!dragging && e.pointerType !== "touch") {
      // hover scrub on desktop
      if (e.buttons === 1) setActive(indexFromClientX(e.clientX));
      else if (e.pointerType === "mouse") setActive(indexFromClientX(e.clientX));
      return;
    }
    if (dragging) setActive(indexFromClientX(e.clientX));
  };
  const onPointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    setDragging(false);
    try {
      (e.target as Element).releasePointerCapture?.(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  if (!trajectory || !layout) {
    return (
      <div className="price-trajectory">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Value over time</div>
        <p className="mt-1 text-sm text-[var(--muted)]">Building the dollar path for this listing…</p>
      </div>
    );
  }

  const selected = points[Math.min(Math.max(0, active), points.length - 1)];
  const win = trajectory.window_stats?.[String(horizon)];
  const knowledge = String(
    trajectory.knowledge_label || "Estimated from similar land nearby",
  ).replace(/_/g, " ");
  const sel = layout.mapped[Math.min(Math.max(0, active), layout.mapped.length - 1)];
  const vsToday =
    selected && trajectory.now_usd
      ? ((Number(selected.value_usd) - Number(trajectory.now_usd)) / Number(trajectory.now_usd)) * 100
      : null;

  return (
    <div className={`price-trajectory ${compact ? "compact" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Value over time</div>
          <h3 className="display text-lg font-semibold leading-snug">
            {trajectory.regime_label || "Dollar path for this listing"}
          </h3>
          <p className="mt-1 text-xs text-[var(--muted)] break-words">{knowledge}</p>
        </div>
        <div className="traj-stats">
          <div>
            <span>This window</span>
            <strong>{win?.cagr_display || trajectory.annual_rate_display || "—"}</strong>
          </div>
          <div>
            <span>Today</span>
            <strong>{money(trajectory.now_usd)}</strong>
          </div>
        </div>
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

      <p className="text-[11px] text-[var(--muted)]">
        {trajectory.interaction_hint ||
          "Drag your finger (or mouse) across the chart to see the dollar value in any year."}
      </p>

      <div className="traj-chart-wrap">
        <svg
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
          <title>Drag to see land value by year</title>
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
                <line x1={layout.padL} x2={layout.w - layout.padR} y1={gy} y2={gy} stroke="var(--line)" strokeWidth="1" />
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
          {/* sparse year ticks */}
          {layout.mapped.map((p, i) => {
            const show =
              i === 0 ||
              i === layout.mapped.length - 1 ||
              p.offset === 0 ||
              (layout.mapped.length <= 20 && i % 2 === 0) ||
              (layout.mapped.length > 20 && i % Math.ceil(layout.mapped.length / 6) === 0);
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
                fill={sel.kind === "outlook" ? "var(--accent, #2f6f4e)" : "var(--brand)"}
                stroke="#fff"
                strokeWidth="2"
              />
            </g>
          )}
          {/* invisible hit targets */}
          {layout.mapped.map((p, i) => (
            <circle
              key={`hit-${p.year}`}
              cx={p.cx}
              cy={p.cy}
              r={14}
              fill="transparent"
              onPointerDown={(e) => {
                e.stopPropagation();
                setActive(i);
                setDragging(true);
              }}
            />
          ))}
        </svg>
      </div>

      {selected && (
        <div className={`chart-readout traj-readout ${dragging ? "live" : ""}`}>
          <div>
            <strong>
              {selected.year}
              {selected.kind === "outlook" ? " · outlook" : ""}
              {selected.offset === 0 ? " · today" : ""}
            </strong>
            <span className="traj-readout-value">{money(selected.value_usd)}</span>
          </div>
          <span>
            {vsToday != null && selected.offset !== 0
              ? `${vsToday >= 0 ? "+" : ""}${vsToday.toFixed(0)}% vs today`
              : "Anchor year for this listing"}
            {win?.change_pct != null && selected.offset === 0
              ? ` · ${win.change_pct >= 0 ? "+" : ""}${win.change_pct.toFixed(0)}% across this ${horizon} yr window`
              : ""}
          </span>
          {!compact && selected.note ? <p>{selected.note}</p> : null}
        </div>
      )}

      {!compact && (
        <>
          <ul className="mt-1 space-y-1 text-sm text-[var(--muted)]">
            {(trajectory.method_notes || []).slice(0, 3).map((b) => (
              <li key={b}>• {b}</li>
            ))}
            {(trajectory.summary_bullets || []).slice(0, 2).map((b) => (
              <li key={b}>• {b}</li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-[var(--muted)] leading-relaxed">{trajectory.disclaimer}</p>
        </>
      )}
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
