"use client";

import { useEffect, useRef } from "react";

type Props = {
  latitude?: number | null;
  longitude?: number | null;
  polygon?: number[][][] | null;
  title?: string;
  height?: number;
  /** Hide caption; denser chrome for embed in cards */
  compact?: boolean;
  className?: string;
  /** Allow scroll-wheel zoom (default false — same as intelligence results) */
  scrollWheelZoom?: boolean;
  /** Bump to force Leaflet to remeasure after a parent layout/transform change */
  layoutKey?: string | number;
};

export function ParcelMap({
  latitude,
  longitude,
  polygon,
  title,
  height = 360,
  compact = false,
  className = "",
  scrollWheelZoom = false,
  layoutKey = 0,
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    let cancelled = false;
    let map: import("leaflet").Map | null = null;
    const el = ref.current;

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

      // Match intelligence-results map interaction options exactly
      map = L.map(ref.current, {
        scrollWheelZoom,
        dragging: true,
        doubleClickZoom: true,
        boxZoom: true,
        keyboard: true,
        zoomControl: true,
        attributionControl: !compact,
      }).setView(center, latitude != null ? (compact ? 15 : 11) : 4);
      if (cancelled) {
        map.remove();
        map = null;
        return;
      }
      mapRef.current = map;

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: compact ? undefined : "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(map);
      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
          attribution: compact ? undefined : "Esri imagery",
          opacity: 0.85,
          maxZoom: 19,
        },
      ).addTo(map);

      if (polygon?.[0]?.length) {
        const latlngs = polygon[0].map(([lon, lat]) => [lat, lon] as [number, number]);
        const layer = L.polygon(latlngs, {
          color: "#d6a243",
          weight: 2,
          fillColor: "#d6a243",
          fillOpacity: 0.25,
        }).addTo(map);
        map.fitBounds(layer.getBounds(), {
          padding: compact ? [10, 10] : [24, 24],
          maxZoom: compact ? 17 : 18,
        });
        if (title) layer.bindPopup(title);
      } else if (latitude != null && longitude != null) {
        L.marker([latitude, longitude]).addTo(map).bindPopup(title || "Parcel");
      }

      const bump = () => map?.invalidateSize({ animate: false });
      requestAnimationFrame(bump);
      window.setTimeout(bump, 100);
      window.setTimeout(bump, 300);
      el.addEventListener("pointerenter", bump);
      (map as unknown as { __onEnter?: () => void }).__onEnter = bump;
    }

    mount();
    return () => {
      cancelled = true;
      if (map) {
        const bump = (map as unknown as { __onEnter?: () => void }).__onEnter;
        if (bump) el.removeEventListener("pointerenter", bump);
        map.remove();
      }
      mapRef.current = null;
    };
  }, [latitude, longitude, polygon, title, compact, scrollWheelZoom]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.invalidateSize({ animate: false });
    const t = window.setTimeout(() => map.invalidateSize({ animate: false }), 50);
    return () => window.clearTimeout(t);
  }, [height, layoutKey]);

  if (latitude == null && longitude == null && !polygon) {
    return (
      <div
        className={`panel p-4 text-sm text-[var(--muted)] ${className}`.trim()}
        style={{ height }}
      >
        No geometry available for map.
      </div>
    );
  }

  return (
    <div
      className={`parcel-map-shell overflow-hidden border border-[var(--border)] ${compact ? "is-compact" : ""} ${className}`.trim()}
    >
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossOrigin=""
      />
      <div ref={ref} style={{ height, width: "100%" }} />
      {!compact ? (
        <div className="px-3 py-2 text-[11px] text-[var(--muted)]">
          OSM + Esri imagery · Toggle layers expand in Phase 2 (flood/wetlands overlays)
        </div>
      ) : null}
    </div>
  );
}
