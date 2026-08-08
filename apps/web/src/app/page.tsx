"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ProviderStrip } from "@/components/provider-strip";
import { SignalBadge } from "@/components/signal-badge";
import { landsignalApi, money, num, pct, type ProviderInfo, type RadarRow } from "@/lib/api";

export default function OpportunityRadarPage() {
  const [rows, setRows] = useState<RadarRow[]>([]);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState(0);
  const [showPersonalized, setShowPersonalized] = useState(false);

  useEffect(() => {
    Promise.all([landsignalApi.radar(), landsignalApi.providers()])
      .then(([r, p]) => {
        setRows(r);
        setProviders(p);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const filtered = useMemo(
    () => rows.filter((r) => r.opportunity >= minScore),
    [rows, minScore],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Opportunity Radar</h1>
          <p className="mt-1 max-w-3xl text-sm text-[var(--muted)]">
            Nationwide candidates ranked by risk-adjusted mispricing signal — not by novelty, acreage, or
            farm cosmetics. Global score and personalized score are never conflated.
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <label className="text-[var(--muted)]">
            Min score{" "}
            <input
              className="ml-2 w-16 border border-[var(--border)] bg-transparent px-2 py-1 mono"
              type="number"
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
            />
          </label>
          <label className="flex items-center gap-2 text-[var(--muted)]">
            <input
              type="checkbox"
              checked={showPersonalized}
              onChange={(e) => setShowPersonalized(e.target.checked)}
            />
            Show personalized
          </label>
        </div>
      </div>

      <ProviderStrip providers={providers} />

      {error && (
        <div className="panel border-[var(--danger)] p-3 text-sm text-[var(--danger)]">
          API unavailable: {error}. Start the API (`uvicorn landsignal.main:app --reload --port 8000`).
        </div>
      )}

      <div className="table-wrap">
        <table className="radar">
          <thead>
            <tr>
              <th>Signal</th>
              <th>Property</th>
              <th>Location</th>
              <th>Acres</th>
              <th>Ask</th>
              <th>$/Acre</th>
              <th>Est. Value</th>
              <th>Discount</th>
              <th>LandSignal</th>
              {showPersonalized && <th>Personalized</th>}
              <th>Asymmetry</th>
              <th>Risk</th>
              <th>Confidence</th>
              <th>Best Strategy</th>
              <th>Freshness</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.parcel_id}>
                <td>
                  <Link href={`/parcels/${r.parcel_id}`}>
                    <SignalBadge signal={r.signal} />
                  </Link>
                </td>
                <td>
                  <Link href={`/parcels/${r.parcel_id}`} className="hover:text-[var(--accent)]">
                    {r.property_name}
                    {r.is_demo && (
                      <span className="ml-2 ks" title="Demo fixture — not a live listing feed">
                        DEMO
                      </span>
                    )}
                  </Link>
                </td>
                <td>{r.location}</td>
                <td className="mono">{num(r.acres, 1)}</td>
                <td className="mono">{money(r.ask)}</td>
                <td className="mono">{money(r.price_per_acre)}</td>
                <td className="mono">{money(r.estimated_value)}</td>
                <td
                  className="mono"
                  style={{
                    color:
                      r.discount_pct != null && r.discount_pct < 0
                        ? "var(--positive)"
                        : "var(--muted)",
                  }}
                >
                  {pct(r.discount_pct)}
                </td>
                <td className="mono font-medium">{num(r.opportunity, 1)}</td>
                {showPersonalized && (
                  <td className="mono">{num(r.personalized_opportunity, 1)}</td>
                )}
                <td className="mono">{num(r.asymmetry, 1)}</td>
                <td className="mono">{num(r.risk, 1)}</td>
                <td className="mono">{num(r.confidence, 1)}</td>
                <td>{r.best_strategy || "—"}</td>
                <td className="mono">
                  {r.freshness_hours == null ? "—" : `${num(r.freshness_hours, 1)}h`}
                </td>
                <td>{r.status}</td>
              </tr>
            ))}
            {!filtered.length && !error && (
              <tr>
                <td colSpan={16} className="text-[var(--muted)]">
                  No scored parcels yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
