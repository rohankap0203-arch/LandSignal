"use client";

import { useEffect, useRef } from "react";
import { resolveLandPin } from "@/lib/land-pin";

function FullscreenIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M8 3H4v4M16 3h4v4M8 21H4v-4M16 21h4v-4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

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
  /** Opens the full-screen land viewer from the caption row */
  onExpand?: () => void;
  /** Opens the full-screen map tool (same viewer) from the map tile button */
  onViewMap?: () => void;
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
  onExpand,
  onViewMap,
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
      const pin = resolveLandPin(latitude, longitude, polygon);
      const center: [number, number] = pin || [39.5, -98.35];

      map = L.map(ref.current, {
        scrollWheelZoom,
        dragging: true,
        doubleClickZoom: true,
        boxZoom: true,
        keyboard: true,
        zoomControl: true,
        attributionControl: false,
      }).setView(center, pin != null ? (compact ? 15 : 11) : 4);
      if (cancelled) {
        map.remove();
        map = null;
        return;
      }
      mapRef.current = map;
      map.zoomControl.setPosition("topleft");

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "",
        maxZoom: 19,
      }).addTo(map);
      L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
          attribution: "",
          opacity: 0.85,
          maxZoom: 19,
        },
      ).addTo(map);

      if (polygon?.[0]?.length) {
        const latlngs = polygon[0].map(([lon, lat]) => [lat, lon] as [number, number]);
        const layer = L.polygon(latlngs, {
          color: "#f2c14e",
          weight: 3.25,
          opacity: 1,
          fillColor: "#f2c14e",
          fillOpacity: 0.2,
        }).addTo(map);
        map.fitBounds(layer.getBounds(), {
          padding: compact ? [10, 10] : [24, 24],
          maxZoom: compact ? 17 : 18,
        });
        // Always drop an on-land pin so lakeshore parcels don't look empty / off-parcel.
        if (pin) L.marker(pin).addTo(map).bindPopup(title || "Parcel");
        if (title) layer.bindPopup(title);
      } else if (pin) {
        L.marker(pin).addTo(map).bindPopup(title || "Parcel");
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
      {onExpand && !compact ? (
        <button
          type="button"
          className="parcel-map-expand"
          onClick={onExpand}
          aria-label="Open full screen land view"
          title="Full screen land view"
        >
          <FullscreenIcon />
        </button>
      ) : null}
      {onViewMap && !compact ? (
        <button
          type="button"
          className="parcel-map-view-images"
          onClick={onViewMap}
          aria-label="View map"
          title="Open full-screen map tools"
        >
          <span className="parcel-map-view-images-art" aria-hidden>
            <svg viewBox="0 0 120 72" preserveAspectRatio="xMidYMid slice">
              <defs>
                <linearGradient id="pmViSky" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#1a3d32" />
                  <stop offset="55%" stopColor="#245844" />
                  <stop offset="100%" stopColor="#2f6b52" />
                </linearGradient>
              </defs>
              <rect width="120" height="72" fill="url(#pmViSky)" />
              <circle className="metric-images-art-sun" cx="92" cy="20" r="10" />
              <path
                className="metric-images-art-land-far"
                d="M0 40 C22 34 36 46 54 40 C72 34 90 44 120 36 L120 72 L0 72 Z"
              />
              <path
                className="metric-images-art-land"
                d="M0 50 C20 44 38 56 58 50 C78 44 98 54 120 48 L120 72 L0 72 Z"
              />
            </svg>
          </span>
        </button>
      ) : null}
    </div>
  );
}
