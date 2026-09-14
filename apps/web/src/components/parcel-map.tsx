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

function ensureLeafletCss() {
  if (typeof document === "undefined") return;
  if (document.getElementById("leaflet-css")) return;
  const link = document.createElement("link");
  link.id = "leaflet-css";
  link.rel = "stylesheet";
  link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
  link.crossOrigin = "";
  document.head.appendChild(link);
}

function polygonSignature(polygon?: number[][][] | null): string {
  if (!polygon?.[0]?.length) return "";
  const ring = polygon[0];
  // Compact signature so identical geometry does not remount the map.
  const n = ring.length;
  const a = ring[0];
  const b = ring[Math.floor(n / 2)] || a;
  const c = ring[n - 1] || a;
  return `${n}:${a?.[0]?.toFixed?.(4)},${a?.[1]?.toFixed?.(4)}:${b?.[0]?.toFixed?.(4)},${b?.[1]?.toFixed?.(4)}:${c?.[0]?.toFixed?.(4)},${c?.[1]?.toFixed?.(4)}`;
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
};

type MapBundle = {
  map: import("leaflet").Map;
  polygonLayer?: import("leaflet").Polygon;
  marker?: import("leaflet").Marker;
  imagery?: import("leaflet").TileLayer;
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
}: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const bundleRef = useRef<MapBundle | null>(null);
  const titleRef = useRef(title);
  titleRef.current = title;

  const geoKey = `${latitude ?? ""}:${longitude ?? ""}:${polygonSignature(polygon)}:${compact ? 1 : 0}:${scrollWheelZoom ? 1 : 0}`;

  useEffect(() => {
    if (!ref.current) return;
    let cancelled = false;
    const el = ref.current;

    async function mount() {
      ensureLeafletCss();
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

      // Reuse an existing map instance when geometry is unchanged — avoids flicker.
      if (bundleRef.current?.map && ref.current.querySelector(".leaflet-container")) {
        return;
      }

      // Tear down prior instance cleanly if the container was reset.
      if (bundleRef.current?.map) {
        try {
          bundleRef.current.map.remove();
        } catch {
          /* ignore */
        }
        bundleRef.current = null;
      }
      ref.current.innerHTML = "";

      const pin = resolveLandPin(latitude, longitude, polygon);
      const center: [number, number] = pin || [39.5, -98.35];

      const map = L.map(ref.current, {
        scrollWheelZoom,
        dragging: true,
        doubleClickZoom: true,
        boxZoom: true,
        keyboard: true,
        zoomControl: true,
        attributionControl: false,
        fadeAnimation: false,
        zoomAnimation: false,
        markerZoomAnimation: false,
      }).setView(center, pin != null ? (compact ? 15 : 11) : 4);
      if (cancelled) {
        map.remove();
        return;
      }
      map.zoomControl.setPosition("topleft");

      // Streets first (stable paint). Imagery fades in after the base tiles settle
      // so the report map does not flash between two competing basemaps.
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "",
        maxZoom: 19,
      }).addTo(map);

      const imagery = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
          attribution: "",
          opacity: 0,
          maxZoom: 19,
        },
      );
      // Defer imagery so first paint is a single layer (no dual-tile flicker).
      window.setTimeout(() => {
        if (cancelled || !bundleRef.current || bundleRef.current.map !== map) return;
        imagery.addTo(map);
        imagery.setOpacity(0.85);
      }, 220);

      let polygonLayer: import("leaflet").Polygon | undefined;
      let marker: import("leaflet").Marker | undefined;

      if (polygon?.[0]?.length) {
        const latlngs = polygon[0].map(([lon, lat]) => [lat, lon] as [number, number]);
        polygonLayer = L.polygon(latlngs, {
          color: "#f2c14e",
          weight: 3.25,
          opacity: 1,
          fillColor: "#f2c14e",
          fillOpacity: 0.2,
        }).addTo(map);
        map.fitBounds(polygonLayer.getBounds(), {
          padding: compact ? [10, 10] : [24, 24],
          maxZoom: compact ? 17 : 18,
        });
        if (pin) {
          marker = L.marker(pin).addTo(map);
          if (titleRef.current) marker.bindPopup(titleRef.current);
        }
        if (titleRef.current) polygonLayer.bindPopup(titleRef.current);
      } else if (pin) {
        marker = L.marker(pin).addTo(map);
        if (titleRef.current) marker.bindPopup(titleRef.current);
      }

      bundleRef.current = { map, polygonLayer, marker, imagery };

      const bump = () => {
        try {
          map.invalidateSize({ animate: false });
        } catch {
          /* ignore */
        }
      };
      requestAnimationFrame(bump);
      window.setTimeout(bump, 160);
      el.addEventListener("pointerenter", bump);
      (map as unknown as { __onEnter?: () => void }).__onEnter = bump;
    }

    void mount();
    return () => {
      cancelled = true;
      const bundle = bundleRef.current;
      if (bundle?.map) {
        const bump = (bundle.map as unknown as { __onEnter?: () => void }).__onEnter;
        if (bump) el.removeEventListener("pointerenter", bump);
        try {
          bundle.map.remove();
        } catch {
          /* ignore */
        }
      }
      bundleRef.current = null;
    };
    // Remount only when geo / map options change — not on title churn.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geoKey]);

  // Update popups when title changes without remounting the map.
  useEffect(() => {
    const bundle = bundleRef.current;
    if (!bundle) return;
    if (title) {
      bundle.marker?.bindPopup(title);
      bundle.polygonLayer?.bindPopup(title);
    }
  }, [title]);

  useEffect(() => {
    const map = bundleRef.current?.map;
    if (!map) return;
    map.invalidateSize({ animate: false });
    const t = window.setTimeout(() => map.invalidateSize({ animate: false }), 80);
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
      <div
        ref={ref}
        style={{
          height,
          width: "100%",
          background: "color-mix(in srgb, var(--ink) 8%, var(--bg-elevated))",
        }}
      />
      {onExpand && !compact ? (
        <button
          type="button"
          className="parcel-map-expand"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onExpand();
          }}
          aria-label="Open full screen land view"
          title="Full screen land view"
        >
          <FullscreenIcon />
        </button>
      ) : null}
    </div>
  );
}
