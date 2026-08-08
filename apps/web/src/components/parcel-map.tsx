"use client";

import { useEffect, useRef } from "react";

type Props = {
  latitude?: number | null;
  longitude?: number | null;
  polygon?: number[][][] | null;
  title?: string;
  height?: number;
};

export function ParcelMap({ latitude, longitude, polygon, title, height = 360 }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    let cancelled = false;
    let map: import("leaflet").Map | null = null;

    async function mount() {
      const L = await import("leaflet");
      // Fix default marker icons in bundlers
      // @ts-expect-error leaflet image paths
      delete L.Icon.Default.prototype._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      if (cancelled || !ref.current) return;
      ref.current.innerHTML = "";
      const center: [number, number] =
        latitude != null && longitude != null ? [latitude, longitude] : [39.5, -98.35];
      map = L.map(ref.current, { scrollWheelZoom: false }).setView(center, latitude ? 11 : 4);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(map);
      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { attribution: "Esri imagery", opacity: 0.85, maxZoom: 19 },
      ).addTo(map);

      if (polygon?.[0]?.length) {
        const latlngs = polygon[0].map(([lon, lat]) => [lat, lon] as [number, number]);
        const layer = L.polygon(latlngs, {
          color: "#d6a243",
          weight: 2,
          fillColor: "#d6a243",
          fillOpacity: 0.25,
        }).addTo(map);
        map.fitBounds(layer.getBounds(), { padding: [24, 24] });
        if (title) layer.bindPopup(title);
      } else if (latitude != null && longitude != null) {
        L.marker([latitude, longitude]).addTo(map).bindPopup(title || "Parcel");
      }
    }

    mount();
    return () => {
      cancelled = true;
      if (map) map.remove();
    };
  }, [latitude, longitude, polygon, title]);

  if (latitude == null && longitude == null && !polygon) {
    return (
      <div className="panel p-4 text-sm text-[var(--muted)]" style={{ height }}>
        No geometry available for map.
      </div>
    );
  }

  return (
    <div className="overflow-hidden border border-[var(--border)]">
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossOrigin=""
      />
      <div ref={ref} style={{ height, width: "100%" }} />
      <div className="px-3 py-2 text-[11px] text-[var(--muted)]">
        OSM + Esri imagery · Toggle layers expand in Phase 2 (flood/wetlands overlays)
      </div>
    </div>
  );
}
