"use client";

import Link from "next/link";
import { SignalBadge } from "@/components/signal-badge";
import type { RadarRow } from "@/lib/api";

export function PropertyCard({ row, index }: { row: RadarRow; index: number }) {
  const primary = row.links.find((l) => l.kind === "primary") || row.links[0];
  const secondary = row.links.find((l) => l.kind === "map") || row.links[1];

  return (
    <article className="panel property-card" style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}>
      <div className="card-media">
        <div>
          <SignalBadge signal={row.signal} />
          <div className="mt-3 text-xs uppercase tracking-[0.08em] text-white/75">{row.provider_label}</div>
          <div className="display mt-1 text-2xl font-semibold leading-tight">{row.headline_metric}</div>
        </div>
        <div>
          <div className="text-sm text-white/80">{row.location}</div>
          <div className="mt-1 text-lg font-semibold">{row.acres_display}</div>
        </div>
      </div>

      <div className="card-body">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="display text-xl font-semibold leading-snug">
              <Link href={`/parcels/${row.parcel_id}`} className="hover:text-[var(--brand-soft)]">
                {row.property_name}
              </Link>
            </h2>
            <p className="mt-1 text-sm text-[var(--muted)]">{row.summary}</p>
          </div>
          <div className="rounded-full bg-[var(--bg-soft)] px-3 py-1 text-sm font-semibold text-[var(--brand)]">
            Fit {Math.round(row.fit_score ?? row.opportunity)}
          </div>
        </div>

        <div className="metric-row">
          <div className="metric">
            <div className="k">{row.price_label}</div>
            <div className="v">{row.price_display}</div>
          </div>
          <div className="metric">
            <div className="k">Model value</div>
            <div className="v">{row.estimated_value_display}</div>
          </div>
          <div className="metric">
            <div className="k">LandSignal</div>
            <div className="v">{row.opportunity.toFixed(0)}/100</div>
          </div>
          <div className="metric">
            <div className="k">Risk · Confidence</div>
            <div className="v">
              {row.risk.toFixed(0)} · {row.confidence.toFixed(0)}
            </div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full bg-[var(--bg-soft)] px-2.5 py-1">{row.best_strategy_label}</span>
          <span className="rounded-full bg-[var(--bg-soft)] px-2.5 py-1">{row.discount_display}</span>
          <span className="rounded-full bg-[var(--bg-soft)] px-2.5 py-1">{row.risk_label}</span>
          <span className="rounded-full bg-[var(--bg-soft)] px-2.5 py-1">{row.confidence_label}</span>
        </div>

        <ul className="reasons">
          {row.match_reasons.slice(0, 3).map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>

        <div className="card-actions">
          {primary && (
            <a className="primary" href={primary.url} target="_blank" rel="noreferrer">
              {primary.label}
            </a>
          )}
          {secondary && (
            <a href={secondary.url} target="_blank" rel="noreferrer">
              {secondary.label}
            </a>
          )}
          <Link href={`/parcels/${row.parcel_id}`}>Full intelligence</Link>
        </div>
      </div>
    </article>
  );
}
