"use client";

import { useMemo, useState } from "react";
import { HelpTip } from "@/components/filter-field";

type AnyRec = Record<string, unknown>;

function money(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

/** X–Y bid clearing chart from opener through our value. */
export function SignalCockpit({ cockpit }: { cockpit: AnyRec }) {
  const chart = (cockpit.chart as AnyRec) || {};
  const points = ((chart.points as AnyRec[]) || []).filter(
    (p) => Number.isFinite(Number(p.x)) && Number.isFinite(Number(p.y)),
  );
  const [active, setActive] = useState(0);

  const layout = useMemo(() => {
    if (!points.length) return null;
    const xs = points.map((p) => Number(p.x));
    const ys = points.map((p) => Number(p.y));
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = 0;
    const maxY = Math.max(100, ...ys);
    // Extra padding so point labels + axis titles never clip
    const padL = 52;
    const padR = 28;
    const padT = 28;
    const padB = 44;
    const w = 360;
    const h = 240;
    const xScale = (x: number) => padL + ((x - minX) / Math.max(1, maxX - minX)) * (w - padL - padR);
    const yScale = (y: number) => padT + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - padT - padB);
    const mapped = points.map((p) => ({
      ...p,
      cx: xScale(Number(p.x)),
      cy: yScale(Number(p.y)),
    }));
    const path = mapped.map((p, i) => `${i === 0 ? "M" : "L"} ${p.cx.toFixed(1)} ${p.cy.toFixed(1)}`).join(" ");
    return { w, h, padL, padT, padB, padR, minX, maxX, maxY, mapped, path, xScale, yScale };
  }, [points]);

  const selected = points[Math.min(active, Math.max(0, points.length - 1))];

  return (
    <div className="signal-cockpit">
      <div>
        <div className="flex items-center gap-2">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--muted)]">
            Who’s still bidding at each price
          </div>
          <HelpTip
            tone="panel"
            title="What this chart shows"
            body="As the price climbs, fewer buyers stay in. Each point is a price level on this file — from the start bid toward our value — and roughly how much competition is still there. Use it to see where the crowd thins and what a realistic finish looks like, not as a promise of the sale price."
          />
        </div>
        <h3 className="display text-lg font-semibold">
          {String(cockpit.subtitle || "Price up → fewer buyers left")}
        </h3>
        <p className="mt-0.5 text-xs text-[var(--muted)]">
          Tap a point or legend item to read that price level.
        </p>
      </div>

      {layout ? (
        <>
          <svg
            className="clearing-chart"
            viewBox={`0 0 ${layout.w} ${layout.h}`}
            role="img"
            preserveAspectRatio="xMidYMid meet"
          >
            <title>Buyers left at each price</title>
            {[0, 25, 50, 75, 100].map((y) => {
              const gy = layout.yScale(y);
              return (
                <g key={y}>
                  <line
                    x1={layout.padL}
                    x2={layout.w - layout.padR}
                    y1={gy}
                    y2={gy}
                    stroke="var(--line)"
                    strokeWidth="1"
                  />
                  <text x={layout.padL - 8} y={gy + 3} textAnchor="end" className="chart-tick">
                    {y}%
                  </text>
                </g>
              );
            })}
            <line
              x1={layout.padL}
              y1={layout.padT}
              x2={layout.padL}
              y2={layout.h - layout.padB}
              stroke="var(--ink)"
              strokeWidth="1.2"
            />
            <line
              x1={layout.padL}
              y1={layout.h - layout.padB}
              x2={layout.w - layout.padR}
              y2={layout.h - layout.padB}
              stroke="var(--ink)"
              strokeWidth="1.2"
            />
            <path d={layout.path} fill="none" stroke="var(--brand)" strokeWidth="2.2" />
            {layout.mapped.map((p, i) => {
              const nearTop = Number(p.y) >= 85;
              const labelY = nearTop ? p.cy + 16 : p.cy - 12;
              return (
                <g
                  key={`${String(p.label)}-${i}`}
                  className="chart-point"
                  onClick={() => setActive(i)}
                  style={{ cursor: "pointer" }}
                >
                  <circle
                    cx={p.cx}
                    cy={p.cy}
                    r={active === i ? 6 : 4.5}
                    fill={active === i ? "var(--accent)" : "var(--brand)"}
                    stroke="#fff"
                    strokeWidth="1.5"
                  />
                  <text x={p.cx} y={labelY} textAnchor="middle" className="chart-label">
                    {String(p.label)}
                  </text>
                </g>
              );
            })}
            <text
              x={(layout.padL + layout.w - layout.padR) / 2}
              y={layout.h - 12}
              textAnchor="middle"
              className="chart-axis"
            >
              Price
            </text>
            <text
              x={14}
              y={layout.h / 2}
              textAnchor="middle"
              className="chart-axis"
              transform={`rotate(-90 14 ${layout.h / 2})`}
            >
              % buyers left
            </text>
          </svg>

          <div className="bid-tag-rail" role="list">
            {points.map((p, i) => (
              <button
                key={`${String(p.label)}-leg-${i}`}
                type="button"
                role="listitem"
                className={`bid-tag ${active === i ? "is-live" : ""}`}
                onClick={() => setActive(i)}
                aria-pressed={active === i}
              >
                <strong>{String(p.label)}</strong>
                <span className="bid-tag-price">{money(p.x)}</span>
              </button>
            ))}
          </div>

          {selected && (
            <div className="bid-slip">
              <strong>{String(selected.label)}</strong>
              <span>
                {money(selected.x)} · about {Number(selected.y).toFixed(0)}% of buyers still bidding
              </span>
              <p>{String(selected.note || "")}</p>
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-[var(--muted)]">Not enough price points to chart this parcel yet.</p>
      )}
    </div>
  );
}
