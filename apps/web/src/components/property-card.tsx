"use client";

import Link from "next/link";
import { useState } from "react";
import { AcquireRail } from "@/components/acquire-rail";
import { TrajectorySpark } from "@/components/price-trajectory";
import { SignalBadge } from "@/components/signal-badge";
import type { RadarRow } from "@/lib/api";

export function PropertyCard({ row, index }: { row: RadarRow; index: number }) {
  const [intelPending, setIntelPending] = useState(false);
  const posting =
    row.links.find((l) => l.kind === "primary" && l.available !== false) ||
    (row.contact_website
      ? { label: "Open posting", url: row.contact_website, kind: "primary", available: true }
      : null);
  const findParcel = row.links.find((l) => l.kind === "lookup" && l.available !== false) || null;
  const phone =
    row.contact_phone ||
    row.links.find((l) => l.kind === "contact" && String(l.url).startsWith("tel:"))?.label ||
    null;
  const conviction = row.conviction || "WATCH";

  return (
    <article className="panel property-card" style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}>
      <div className="card-media">
        <div>
          <SignalBadge signal={row.signal} />
          <div className="mt-3 text-xs uppercase tracking-[0.08em] text-white/75">{row.provider_label}</div>
          <div className="display mt-1 text-2xl font-semibold leading-snug break-words">{row.headline_metric}</div>
        </div>
        <div>
          <div className="text-sm text-white/80 break-words">{row.location}</div>
          <div className="mt-1 text-lg font-semibold break-words">{row.acres_display}</div>
        </div>
      </div>

      <div className="card-body">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h2 className="display text-xl font-semibold leading-snug break-words">
              <Link href={`/parcels/${row.parcel_id}`} className="hover:text-[var(--brand-soft)]">
                {row.property_name}
              </Link>
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-[var(--ink)] break-words">
              {row.return_thesis || row.summary}
            </p>
            {row.source_name && (
              <p className="mt-1 text-xs text-[var(--muted)] break-words">
                Source: {row.source_name}
                {row.contact_office ? ` · ${row.contact_office}` : ""}
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <div
              className={`conviction-pill ${conviction.toLowerCase()}`}
              title="Acquisition desk conviction from LandSignal screen"
            >
              {conviction}
            </div>
            <div className="rounded-full bg-[var(--bg-soft)] px-3 py-1 text-sm font-semibold text-[var(--brand)] whitespace-nowrap">
              Fit {Math.round(row.fit_score ?? row.opportunity)}
            </div>
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
          <div className="metric metric-span">
            <div className="k">LandSignal {Math.round(row.opportunity)} / 100</div>
            <div
              className="mini-bar"
              style={{
                background: `linear-gradient(90deg, hsl(${row.opportunity * 1.2} 65% 42%) ${row.opportunity}%, var(--bg-elevated) ${row.opportunity}%)`,
              }}
            />
          </div>
          <div className="metric metric-span">
            <div className="k">Risk {Math.round(row.risk)} / 100</div>
            <div
              className="mini-bar"
              style={{
                background: `linear-gradient(90deg, hsl(${120 - row.risk * 1.2} 65% 42%) ${row.risk}%, var(--bg-elevated) ${row.risk}%)`,
              }}
            />
          </div>
          <div className="metric">
            <div className="k">Confidence</div>
            <div className="v">{Math.round(row.confidence)} / 100</div>
          </div>
          <div className="metric">
            <div className="k">Strategy</div>
            <div className="v">{row.best_strategy_label}</div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="chip">{row.discount_display}</span>
          <span className="chip">{row.risk_label}</span>
          <span className="chip">{row.confidence_label}</span>
        </div>

        <TrajectorySpark
          values={row.trajectory_sparkline}
          label={row.trajectory_label}
          cagr={row.trajectory_cagr_5y}
        />

        <ul className="reasons">
          {row.match_reasons.slice(0, 3).map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>

        <AcquireRail
          className="mt-3"
          postingUrl={posting?.url}
          phone={phone}
          office={row.contact_office}
          findUrl={findParcel?.url}
          findLabel={findParcel?.label?.replace(/^Find parcel /, "APN ")}
        />

        <div className="card-actions mt-3">
          <Link
            href={`/parcels/${row.parcel_id}`}
            className={`btn-intel ${intelPending ? "pending" : ""}`}
            onClick={() => setIntelPending(true)}
          >
            {intelPending ? "Opening intelligence…" : "Full intelligence"}
          </Link>
        </div>
      </div>
    </article>
  );
}
