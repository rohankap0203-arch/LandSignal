"use client";

import { useEffect, useRef } from "react";

type Point = {
  id: string;
  lat: number;
  lon: number;
  score: number;
  title: string;
  signal: string;
};

export function NationwideMap({ points }: { points: Point[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    let map: import("leaflet").Map | null = null;
    let cancelled = false;

    (async () => {
      const L = await import("leaflet");
      if (cancelled || !ref.current) return;
      ref.current.innerHTML = "";
      map = L.map(ref.current).setView([39.5, -98.35], 4);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
      }).addTo(map);
      for (const p of points) {
        const color =
          p.score >= 85 ? "#d6a243" : p.score >= 70 ? "#3dba86" : p.score >= 50 ? "#5b8def" : "#8b9bb0";
        const marker = L.circleMarker([p.lat, p.lon], {
          radius: 7,
          color,
          fillColor: color,
          fillOpacity: 0.85,
          weight: 1,
        }).addTo(map);
        marker.bindPopup(
          `<strong>${p.title}</strong><br/>Score ${p.score.toFixed(1)} · ${p.signal}<br/><a href="/parcels/${p.id}">Open intelligence</a>`,
        );
      }
      if (points.length > 1) {
        map.fitBounds(
          L.latLngBounds(points.map((p) => [p.lat, p.lon] as [number, number])),
          { padding: [30, 30] },
        );
      }
    })();

    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [points]);

  return (
    <div className="overflow-hidden border border-[var(--border)]">
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossOrigin="" />
      <div ref={ref} style={{ height: 480, width: "100%" }} />
    </div>
  );
}
