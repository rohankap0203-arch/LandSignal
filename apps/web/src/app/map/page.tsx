"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { landsignalApi, type RadarRow } from "@/lib/api";

export default function MapPage() {
  const [rows, setRows] = useState<RadarRow[]>([]);
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  useEffect(() => {
    landsignalApi.radar().then(setRows).catch(() => setRows([]));
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Map Mode</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          USA → state → county → parcel heat layers for opportunity, mispricing, and optionality.
        </p>
      </div>
      {!token ? (
        <div className="panel p-4 text-sm">
          Mapbox: <span className="text-[var(--warning)]">NOT_CONFIGURED</span>. Set{" "}
          <span className="mono">NEXT_PUBLIC_MAPBOX_TOKEN</span> to enable interactive tiles and overlays.
          Showing ranked parcel list fallback.
        </div>
      ) : (
        <div className="panel p-4 text-sm">Mapbox token present — GL map mount scheduled for Phase 1.5 overlays.</div>
      )}
      <div className="table-wrap">
        <table className="radar">
          <thead>
            <tr>
              <th>Property</th>
              <th>Location</th>
              <th>Score</th>
              <th>Strategy</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.parcel_id}>
                <td>
                  <Link href={`/parcels/${r.parcel_id}`}>{r.property_name}</Link>
                </td>
                <td>{r.location}</td>
                <td className="mono">{r.opportunity.toFixed(1)}</td>
                <td>{r.best_strategy}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
