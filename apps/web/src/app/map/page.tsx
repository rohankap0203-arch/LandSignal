"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { landsignalApi, num, type RadarRow } from "@/lib/api";

const NationwideMap = dynamic(() => import("@/components/nationwide-map").then((m) => m.NationwideMap), {
  ssr: false,
});

export default function MapPage() {
  const [rows, setRows] = useState<RadarRow[]>([]);
  const [details, setDetails] = useState<Record<string, { lat: number; lon: number }>>({});

  useEffect(() => {
    landsignalApi.radar().then(async (r) => {
      setRows(r.filter((x) => !x.is_demo));
      const pairs: Record<string, { lat: number; lon: number }> = {};
      await Promise.all(
        r.slice(0, 40).map(async (row) => {
          try {
            const d = await landsignalApi.parcel(row.parcel_id);
            const p = d.parcel as { latitude?: number; longitude?: number };
            if (p.latitude != null && p.longitude != null) {
              pairs[row.parcel_id] = { lat: p.latitude, lon: p.longitude };
            }
          } catch {
            /* ignore */
          }
        }),
      );
      setDetails(pairs);
    });
  }, []);

  const points = useMemo(
    () =>
      rows
        .filter((r) => details[r.parcel_id])
        .map((r) => ({
          id: r.parcel_id,
          lat: details[r.parcel_id].lat,
          lon: details[r.parcel_id].lon,
          score: r.opportunity,
          title: r.property_name,
          signal: r.signal,
        })),
    [rows, details],
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Map Mode</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Nationwide opportunity heat from scored inventory. OSM basemap — Mapbox optional.
        </p>
      </div>
      <NationwideMap points={points} />
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
                <td className="mono">{num(r.opportunity, 1)}</td>
                <td>{r.best_strategy}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
