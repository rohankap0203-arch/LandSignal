"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ProviderStrip } from "@/components/provider-strip";
import { SignalBadge } from "@/components/signal-badge";
import { landsignalApi, money, num, pct, type ProviderInfo, type RadarRow } from "@/lib/api";

export default function OpportunityRadarPage() {
  const [rows, setRows] = useState<RadarRow[]>([]);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState(0);
  const [showPersonalized, setShowPersonalized] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [discoverMsg, setDiscoverMsg] = useState<string | null>(null);
  const [hideDemo, setHideDemo] = useState(true);

  const refresh = useCallback(async () => {
    const [r, p] = await Promise.all([landsignalApi.radar(), landsignalApi.providers()]);
    setRows(r);
    setProviders(p);
  }, []);

  useEffect(() => {
    refresh()
      .catch((e: Error) => setError(e.message));
    const t = setInterval(() => {
      refresh().catch(() => undefined);
    }, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const filtered = useMemo(
    () =>
      rows
        .filter((r) => r.opportunity >= minScore)
        .filter((r) => (hideDemo ? !r.is_demo : true)),
    [rows, minScore, hideDemo],
  );

  async function runDiscover() {
    setDiscovering(true);
    setDiscoverMsg("Scanning BLM LPAD + configured feeds, enriching with USDA/FEMA/NWI/USGS…");
    try {
      const res = await landsignalApi.discover(24, 20);
      setDiscoverMsg(
        `Imported ${res.imported} · scored ${res.scored}. ${String(res.note || "")}`,
      );
      await refresh();
    } catch (e) {
      setDiscoverMsg(e instanceof Error ? e.message : "Discover failed");
    } finally {
      setDiscovering(false);
    }
  }

  const top = filtered[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Opportunity Radar</h1>
          <p className="mt-1 max-w-3xl text-sm text-[var(--muted)]">
            Ranked by risk-adjusted mispricing / optionality — not novelty or acreage cosmetics.
            Live public inventory via BLM LPAD; licensed MLS/Land.com require vendor keys.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <button
            type="button"
            className="panel px-3 py-2 text-[var(--accent)] disabled:opacity-50"
            disabled={discovering}
            onClick={runDiscover}
          >
            {discovering ? "Scanning…" : "Scan real opportunities"}
          </button>
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
            <input type="checkbox" checked={showPersonalized} onChange={(e) => setShowPersonalized(e.target.checked)} />
            Personalized
          </label>
          <label className="flex items-center gap-2 text-[var(--muted)]">
            <input type="checkbox" checked={hideDemo} onChange={(e) => setHideDemo(e.target.checked)} />
            Hide DEMO
          </label>
        </div>
      </div>

      <ProviderStrip providers={providers} />

      {discoverMsg && <div className="panel p-3 text-sm text-[var(--muted)]">{discoverMsg}</div>}

      {top && (
        <div className="panel p-4">
          <div className="text-[11px] uppercase tracking-wide text-[var(--muted)]">Top signal</div>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <SignalBadge signal={top.signal} />
            <Link href={`/parcels/${top.parcel_id}`} className="text-lg font-medium hover:text-[var(--accent)]">
              {top.property_name}
            </Link>
            <span className="mono text-[var(--muted)]">
              LS {num(top.opportunity, 1)} · Risk {num(top.risk, 1)} · Asym {num(top.asymmetry, 1)} ·{" "}
              {top.best_strategy}
            </span>
          </div>
        </div>
      )}

      {error && (
        <div className="panel border-[var(--danger)] p-3 text-sm text-[var(--danger)]">
          API unavailable: {error}
        </div>
      )}

      {!filtered.length && !error && (
        <div className="panel p-4 text-sm text-[var(--muted)]">
          No scored real parcels yet. Click <strong>Scan real opportunities</strong> to pull BLM disposal
          lands and run due diligence. Auto-scan also runs on API startup.
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
                    {r.is_demo && <span className="ml-2 ks">DEMO</span>}
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
                    color: r.discount_pct != null && r.discount_pct < 0 ? "var(--positive)" : "var(--muted)",
                  }}
                >
                  {pct(r.discount_pct)}
                </td>
                <td className="mono font-medium">{num(r.opportunity, 1)}</td>
                {showPersonalized && <td className="mono">{num(r.personalized_opportunity, 1)}</td>}
                <td className="mono">{num(r.asymmetry, 1)}</td>
                <td className="mono">{num(r.risk, 1)}</td>
                <td className="mono">{num(r.confidence, 1)}</td>
                <td>{r.best_strategy || "—"}</td>
                <td>{r.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
