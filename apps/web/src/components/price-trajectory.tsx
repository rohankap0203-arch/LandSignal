"use client";

import { useMemo, useState } from "react";

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
  observed_marks?: Array<{ year: number; value_usd: number; label?: string }>;
};

function money(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

/** 10y history + forward outlook appreciation/depreciation path. */
export function PriceTrajectory({
  trajectory,
  compact,
}: {
  trajectory: Trajectory | null | undefined;
  compact?: boolean;
}) {
  const points = (trajectory?.points || []).filter((p) => Number.isFinite(Number(p.value_usd)));
  const [active, setActive] = useState(() => {
    const idx = points.findIndex((p) => p.offset === 0 || p.kind !== "outlook");
    return idx >= 0 ? points.findIndex((p) => p.offset === 0) : Math.max(0, points.length - 1);
  });

  const layout = useMemo(() => {
    if (points.length < 2) return null;
    const xs = points.map((_, i) => i);
    const ys = points.map((p) => Number(p.value_usd));
    const minY = Math.min(...ys) * 0.92;
    const maxY = Math.max(...ys) * 1.06;
    const padL = 48;
    const padR = 16;
    const padT = 20;
    const padB = 36;
    const w = compact ? 280 : 420;
    const h = compact ? 140 : 220;
    const xScale = (i: number) => padL + (i / Math.max(1, points.length - 1)) * (w - padL - padR);
    const yScale = (y: number) => padT + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - padT - padB);
    const mapped = points.map((p, i) => ({ ...p, cx: xScale(i), cy: yScale(Number(p.value_usd)) }));
    const hist = mapped.filter((p) => p.kind !== "outlook");
    const fut = mapped.filter((p) => p.kind === "outlook" || p.offset === 0);
    const histPath = hist.map((p, i) => `${i === 0 ? "M" : "L"} ${p.cx.toFixed(1)} ${p.cy.toFixed(1)}`).join(" ");
    const futPath = fut.map((p, i) => `${i === 0 ? "M" : "L"} ${p.cx.toFixed(1)} ${p.cy.toFixed(1)}`).join(" ");
    return { w, h, padL, padT, padB, mapped, histPath, futPath, minY, maxY, yScale };
  }, [points, compact]);

  if (!trajectory || !layout) {
    return (
      <div className="price-trajectory">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Value path</div>
        <p className="mt-1 text-sm text-[var(--muted)]">Building appreciation / depreciation path…</p>
      </div>
    );
  }

  const selected = points[Math.min(Math.max(0, active), points.length - 1)];
  const knowledge = String(trajectory.knowledge_state || "TREND_PROXY").replace(/_/g, " ");

  return (
    <div className={`price-trajectory ${compact ? "compact" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
            Appreciation / depreciation · {knowledge}
          </div>
          <h3 className="display text-lg font-semibold leading-snug">
            {trajectory.regime_label || "Market trajectory"}
          </h3>
          {!compact && (
            <p className="mt-1 text-xs text-[var(--muted)] break-words">{trajectory.headline}</p>
          )}
        </div>
        <div className="traj-stats">
          <div>
            <span>5y</span>
            <strong>{trajectory.cagr_5y_display || "—"}</strong>
          </div>
          <div>
            <span>10y</span>
            <strong>{trajectory.cagr_10y_display || "—"}</strong>
          </div>
          <div>
            <span>Fwd</span>
            <strong>{trajectory.cagr_forward_display || "—"}</strong>
          </div>
        </div>
      </div>

      <svg className="traj-chart" viewBox={`0 0 ${layout.w} ${layout.h}`} role="img" preserveAspectRatio="xMidYMid meet">
        <title>Land value trajectory</title>
        {[0, 0.5, 1].map((t) => {
          const y = layout.minY + t * (layout.maxY - layout.minY);
          const gy = layout.yScale(y);
          return (
            <g key={t}>
              <line x1={layout.padL} x2={layout.w - 16} y1={gy} y2={gy} stroke="var(--line)" strokeWidth="1" />
              <text x={layout.padL - 6} y={gy + 3} textAnchor="end" className="chart-tick">
                {y >= 1000 ? `${Math.round(y / 1000)}k` : money(y)}
              </text>
            </g>
          );
        })}
        <path d={layout.histPath} fill="none" stroke="var(--brand)" strokeWidth="2.4" />
        <path
          d={layout.futPath}
          fill="none"
          stroke="var(--accent, #2f6f4e)"
          strokeWidth="2"
          strokeDasharray="5 4"
          opacity="0.85"
        />
        {layout.mapped.map((p, i) => (
          <g key={p.year} onClick={() => setActive(i)} style={{ cursor: "pointer" }}>
            <circle
              cx={p.cx}
              cy={p.cy}
              r={active === i ? 5.5 : 3.5}
              fill={p.kind === "outlook" ? "var(--accent, #2f6f4e)" : "var(--brand)"}
              stroke="#fff"
              strokeWidth="1.2"
            />
            {(i === 0 || i === layout.mapped.length - 1 || p.offset === 0) && (
              <text x={p.cx} y={layout.h - 12} textAnchor="middle" className="chart-axis">
                {p.year}
              </text>
            )}
          </g>
        ))}
      </svg>

      {selected && (
        <div className="chart-readout">
          <strong>
            {selected.year}
            {selected.kind === "outlook" ? " outlook" : ""}
          </strong>
          <span>
            {money(selected.value_usd)}
            {selected.source === "blended_observed" ? " · blended with observed mark" : " · trend path"}
          </span>
          {!compact && <p>{selected.note}</p>}
        </div>
      )}

      {!compact && (
        <>
          <ul className="mt-2 space-y-1 text-sm text-[var(--muted)]">
            {(trajectory.summary_bullets || []).slice(0, 4).map((b) => (
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
        <span>{label || (up ? "Appreciating" : "Soft path")}</span>
        {cagr ? <strong>{cagr}</strong> : null}
      </div>
    </div>
  );
}
