"use client";

import { useEffect, useState } from "react";
import { landsignalApi } from "@/lib/api";

type Health = {
  data_mode?: string;
  inventory_label?: string;
  states_covered?: number;
  states_total?: number;
  counties_covered?: number;
  parcel_records?: number;
  active_land_listings?: number;
  cadastral_screens?: number;
  demo_records?: number;
  listings_added_24h?: number;
  listings_updated_24h?: number;
  stale_listings?: number;
  warnings?: string[];
  by_state?: Array<{
    state_code: string;
    state_name: string;
    parcel_count: number;
    active_listing_count: number;
    counties: number;
    healthy: boolean;
  }>;
  providers?: Array<{
    provider_id: string;
    label: string;
    status: string;
    notes?: string | null;
  }>;
};

export default function InventoryHealthPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    landsignalApi
      .inventoryHealth()
      .then((d) => setHealth(d as Health))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load inventory health"));
  }, []);

  if (error) {
    return <div className="panel m-6 p-4 text-[var(--danger)]">{error}</div>;
  }
  if (!health) {
    return <div className="panel m-6 p-4 text-[var(--muted)]">Loading inventory health…</div>;
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="display text-3xl font-semibold">Nationwide inventory health</h1>
      <p className="mt-2 text-[var(--muted)]">{health.inventory_label}</p>
      <p className="mt-1 text-sm text-[var(--muted)]">DATA_MODE={health.data_mode}</p>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[
          ["States covered", `${health.states_covered ?? 0} / ${health.states_total ?? 50}`],
          ["Counties covered", (health.counties_covered ?? 0).toLocaleString()],
          ["Parcel records", (health.parcel_records ?? 0).toLocaleString()],
          ["Active land listings", (health.active_land_listings ?? 0).toLocaleString()],
          ["Cadastral screens", (health.cadastral_screens ?? 0).toLocaleString()],
          ["Listings added 24h", (health.listings_added_24h ?? 0).toLocaleString()],
          ["Listings updated 24h", (health.listings_updated_24h ?? 0).toLocaleString()],
          ["Stale listings", (health.stale_listings ?? 0).toLocaleString()],
          ["Demo records", (health.demo_records ?? 0).toLocaleString()],
        ].map(([label, value]) => (
          <div key={label} className="panel p-4">
            <div className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</div>
            <div className="mt-1 text-2xl font-semibold text-[var(--ink)]">{value}</div>
          </div>
        ))}
      </div>

      {health.warnings?.length ? (
        <div className="panel mt-6 p-4">
          <h2 className="display text-xl font-semibold">Coverage alerts</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[var(--muted)]">
            {health.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="panel mt-6 p-4">
        <h2 className="display text-xl font-semibold">Provider sync status</h2>
        <div className="mt-3 space-y-2">
          {(health.providers || []).map((p) => (
            <div key={p.provider_id} className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--line)] py-2 text-sm">
              <div>
                <span className="font-medium text-[var(--ink)]">{p.label}</span>
                {p.notes ? <span className="ml-2 text-[var(--muted)]">{p.notes}</span> : null}
              </div>
              <span className="font-semibold tracking-wide">{p.status}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel mt-6 p-4">
        <h2 className="display text-xl font-semibold">Inventory per state</h2>
        <div className="mt-3 grid gap-1 sm:grid-cols-2">
          {(health.by_state || []).map((s) => (
            <div
              key={s.state_code}
              className="flex items-center justify-between border-b border-[var(--line)] py-1.5 text-sm"
            >
              <span>
                {s.state_name} ({s.state_code}) {s.healthy ? "✓" : "·"}
              </span>
              <span className="tabular-nums text-[var(--muted)]">
                {s.parcel_count.toLocaleString()} parcels
                {s.active_listing_count
                  ? ` · ${s.active_listing_count.toLocaleString()} active`
                  : ""}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
