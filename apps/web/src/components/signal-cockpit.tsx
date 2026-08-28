"use client";

import { useMemo, useState } from "react";

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
  const [helpOpen, setHelpOpen] = useState(false);

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
    // Slightly shorter canvas — large screens further constrain via CSS max-width.
    const h = 200;
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
  const first = points[0];
  const last = points[points.length - 1];
  const startLabel = first ? String(first.label || "Start") : "Start";
  const endLabel = last ? String(last.label || "Value") : "Value";
  const startPrice = first ? money(first.x) : null;
  const endPrice = last ? money(last.x) : null;
  const startShare =
    first != null && Number.isFinite(Number(first.y)) ? `${Number(first.y).toFixed(0)}%` : null;
  const endShare =
    last != null && Number.isFinite(Number(last.y)) ? `${Number(last.y).toFixed(0)}%` : null;

  return (
    <div className="signal-cockpit">
      <div>
        <div className="flex items-center gap-2">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--muted)]">
            Who’s still bidding at each price
          </div>
          <button
            type="button"
            className={`help-q signal-help-q ${helpOpen ? "on" : ""}`}
            aria-label="What this bidding chart means"
            aria-haspopup="dialog"
            aria-expanded={helpOpen}
            title="What this chart means"
            onClick={() => setHelpOpen(true)}
          >
            ?
          </button>
        </div>
        <h3 className="display text-lg font-semibold">
          {String(cockpit.subtitle || "Price up → fewer buyers left")}
        </h3>
        <p className="mt-0.5 text-xs text-[var(--muted)]">
          Tap a point or legend item to read that price level.
        </p>
      </div>

      {helpOpen ? (
        <div
          className="help-modal-backdrop"
          role="presentation"
          onClick={() => setHelpOpen(false)}
        >
          <div
            className="help-modal help-modal--compact"
            role="dialog"
            aria-modal="true"
            aria-label="What this bidding chart means"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h4 className="display text-base font-semibold">Bidding by price</h4>
              <button
                type="button"
                className="help-q on"
                aria-label="Close"
                onClick={() => setHelpOpen(false)}
              >
                ×
              </button>
            </div>
            <p className="mt-2 text-sm leading-snug text-[var(--ink-soft)]">
              Higher price → fewer buyers stay in. Each point is a price on this file and about how
              much of the crowd is still bidding.
            </p>
            <ul className="help-modal-list">
              <li>
                <strong>{startLabel}</strong>
                <span>
                  {startPrice && startShare
                    ? `${startPrice} · ~${startShare} still in`
                    : "Low ask — most of the crowd is still bidding."}
                </span>
              </li>
              <li>
                <strong>Climb</strong>
                <span>As price rises, competition thins. Tap a point to read that level.</span>
              </li>
              <li>
                <strong>{endLabel}</strong>
                <span>
                  {endPrice && endShare
                    ? `${endPrice} · ~${endShare} left — finish band, not a promise`
                    : "Near our value — fewer buyers, clearer finish band."}
                </span>
              </li>
            </ul>
            <p className="mt-3 text-xs leading-snug text-[var(--muted)]">
              Use it to see where the crowd thins — not a guaranteed sale price.
            </p>
          </div>
        </div>
      ) : null}

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

          <div className="chart-legend">
            {points.map((p, i) => (
              <button
                key={`${String(p.label)}-leg-${i}`}
                type="button"
                className={`chart-legend-item ${active === i ? "active" : ""}`}
                onClick={() => setActive(i)}
              >
                <strong>{String(p.label)}</strong>
                <span>{money(p.x)}</span>
              </button>
            ))}
          </div>

          {selected && (
            <div className="chart-readout">
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
