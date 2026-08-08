"use client";

import { useMemo, useState } from "react";

type AnyRec = Record<string, unknown>;

function money(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

/** X–Y bid clearing chart + compact source/contact under the map. */
export function SignalCockpit({ cockpit }: { cockpit: AnyRec }) {
  const chart = (cockpit.chart as AnyRec) || {};
  const points = ((chart.points as AnyRec[]) || []).filter(
    (p) => Number.isFinite(Number(p.x)) && Number.isFinite(Number(p.y)),
  );
  const source = (cockpit.source as AnyRec) || {};
  const [active, setActive] = useState(0);

  const layout = useMemo(() => {
    if (!points.length) return null;
    const xs = points.map((p) => Number(p.x));
    const ys = points.map((p) => Number(p.y));
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = 0;
    const maxY = Math.max(100, ...ys);
    const padL = 44;
    const padR = 12;
    const padT = 16;
    const padB = 36;
    const w = 320;
    const h = 200;
    const xScale = (x: number) => padL + ((x - minX) / Math.max(1, maxX - minX)) * (w - padL - padR);
    const yScale = (y: number) => padT + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - padT - padB);
    const mapped = points.map((p) => ({
      ...p,
      cx: xScale(Number(p.x)),
      cy: yScale(Number(p.y)),
    }));
    const path = mapped.map((p, i) => `${i === 0 ? "M" : "L"} ${p.cx.toFixed(1)} ${p.cy.toFixed(1)}`).join(" ");
    return { w, h, padL, padT, padB, minX, maxX, maxY, mapped, path, xScale, yScale };
  }, [points]);

  const selected = points[Math.min(active, Math.max(0, points.length - 1))];

  return (
    <div className="signal-cockpit">
      <div>
        <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--muted)]">
          Price (X) × buyers still in (Y)
        </div>
        <h3 className="display text-lg font-semibold">{String(cockpit.title || "Bid clearing chart")}</h3>
        <p className="mt-0.5 text-xs text-[var(--muted)]">{String(cockpit.subtitle || "")}</p>
      </div>

      {layout ? (
        <>
          <svg className="clearing-chart" viewBox={`0 0 ${layout.w} ${layout.h}`} role="img">
            <title>Bid clearing chart</title>
            {/* grid */}
            {[0, 25, 50, 75, 100].map((y) => {
              const gy = layout.yScale(y);
              return (
                <g key={y}>
                  <line x1={layout.padL} x2={layout.w - 12} y1={gy} y2={gy} stroke="var(--line)" strokeWidth="1" />
                  <text x={layout.padL - 6} y={gy + 3} textAnchor="end" className="chart-tick">
                    {y}
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
              x2={layout.w - 12}
              y2={layout.h - layout.padB}
              stroke="var(--ink)"
              strokeWidth="1.2"
            />
            <path d={layout.path} fill="none" stroke="var(--brand)" strokeWidth="2.2" />
            {layout.mapped.map((p, i) => (
              <g key={String(p.label)} className="chart-point" onClick={() => setActive(i)} style={{ cursor: "pointer" }}>
                <circle
                  cx={p.cx}
                  cy={p.cy}
                  r={active === i ? 6 : 4.5}
                  fill={active === i ? "var(--accent)" : "var(--brand)"}
                  stroke="#fff"
                  strokeWidth="1.5"
                />
                <text x={p.cx} y={p.cy - 10} textAnchor="middle" className="chart-label">
                  {String(p.label)}
                </text>
              </g>
            ))}
            <text x={(layout.padL + layout.w - 12) / 2} y={layout.h - 8} textAnchor="middle" className="chart-axis">
              {String(chart.x_label || "Price ($)")}
            </text>
            <text
              x={12}
              y={layout.h / 2}
              textAnchor="middle"
              className="chart-axis"
              transform={`rotate(-90 12 ${layout.h / 2})`}
            >
              {String(chart.y_label || "Buyers still competing (%)")}
            </text>
          </svg>
          {selected && (
            <div className="chart-readout">
              <strong>{String(selected.label)}</strong>
              <span>
                {money(selected.x)} · {Number(selected.y).toFixed(0)}% still competing
              </span>
              <p>{String(selected.note || "")}</p>
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-[var(--muted)]">Not enough price points to chart this parcel yet.</p>
      )}

      {/* Concrete source / contact — no filler */}
      <div className="source-card">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Retrieved from</div>
        <div className="font-semibold break-words">{String(source.source_name || cockpit.subtitle || "Public GIS")}</div>
        <div className="mt-1 text-sm text-[var(--muted)] break-words">{String(source.office || "")}</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {source.website ? (
            <a className="btn-posting" href={String(source.website)} target="_blank" rel="noreferrer">
              Open source site
            </a>
          ) : null}
          {source.phone ? (
            <a className="btn-call" href={`tel:${String(source.phone).replace(/-/g, "")}`}>
              {String(source.phone)}
            </a>
          ) : null}
        </div>
        {source.how_to_buy ? (
          <p className="mt-2 text-xs leading-relaxed text-[var(--muted)]">{String(source.how_to_buy)}</p>
        ) : null}
      </div>
    </div>
  );
}
