"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type LandViewerProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  location?: string | null;
  acresDisplay?: string | null;
  priceDisplay?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  polygon?: number[][][] | null;
  reportHref?: string | null;
};

type Basemap = "satellite" | "streets" | "hybrid";
type Tool = "pan" | "measure";

function haversineMeters(a: [number, number], b: [number, number]) {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b[0] - a[0]);
  const dLon = toRad(b[1] - a[1]);
  const lat1 = toRad(a[0]);
  const lat2 = toRad(b[0]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

function formatDistance(meters: number) {
  const miles = meters / 1609.344;
  if (miles < 0.2) return `${Math.round(meters * 3.28084)} ft`;
  return `${miles.toFixed(miles < 10 ? 2 : 1)} mi`;
}

function ringAreaAcres(ring: [number, number][]) {
  if (ring.length < 3) return 0;
  // Spherical excess approximation via equirectangular projection near centroid
  let lat0 = 0;
  let lon0 = 0;
  for (const [lat, lon] of ring) {
    lat0 += lat;
    lon0 += lon;
  }
  lat0 /= ring.length;
  lon0 /= ring.length;
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos((lat0 * Math.PI) / 180);
  let area = 0;
  for (let i = 0; i < ring.length; i++) {
    const [lat1, lon1] = ring[i];
    const [lat2, lon2] = ring[(i + 1) % ring.length];
    const x1 = (lon1 - lon0) * mPerDegLon;
    const y1 = (lat1 - lat0) * mPerDegLat;
    const x2 = (lon2 - lon0) * mPerDegLon;
    const y2 = (lat2 - lat0) * mPerDegLat;
    area += x1 * y2 - x2 * y1;
  }
  return Math.abs(area / 2) / 4046.8564224;
}

function ImageIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.75" />
      <circle cx="8.5" cy="10" r="1.6" fill="currentColor" />
      <path
        d="M4.5 16.5 9 12l3.2 3.2L16 11.5l3.5 5"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function LandViewerModal({
  open,
  onClose,
  title,
  location,
  acresDisplay,
  priceDisplay,
  latitude,
  longitude,
  polygon,
  reportHref,
}: LandViewerProps) {
  const titleId = useId();
  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const layersRef = useRef<{
    streets?: import("leaflet").TileLayer;
    satellite?: import("leaflet").TileLayer;
    parcel?: import("leaflet").Layer;
    measure?: import("leaflet").LayerGroup;
    marker?: import("leaflet").Marker;
  }>({});
  const measurePts = useRef<[number, number][]>([]);

  const [mounted, setMounted] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("hybrid");
  const [tool, setTool] = useState<Tool>("pan");
  const [showBoundary, setShowBoundary] = useState(true);
  const [coords, setCoords] = useState<string>("—");
  const [zoom, setZoom] = useState(14);
  const [measureInfo, setMeasureInfo] = useState("Click the map to drop measure points");
  const [copied, setCopied] = useState(false);

  const hasGeo = latitude != null && longitude != null;
  const center = useMemo<[number, number]>(
    () => (hasGeo ? [latitude!, longitude!] : [39.5, -98.35]),
    [hasGeo, latitude, longitude],
  );

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    setTool("pan");
    setBasemap("hybrid");
    setShowBoundary(true);
    setMeasureInfo("Click the map to drop measure points");
    setCopied(false);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  const applyBasemap = useCallback((mode: Basemap) => {
    const { streets, satellite } = layersRef.current;
    if (!streets || !satellite) return;
    if (mode === "streets") {
      streets.setOpacity(1);
      satellite.setOpacity(0);
    } else if (mode === "satellite") {
      streets.setOpacity(0);
      satellite.setOpacity(1);
    } else {
      streets.setOpacity(1);
      satellite.setOpacity(0.88);
    }
  }, []);

  const fitParcel = useCallback(() => {
    const map = mapRef.current;
    const parcel = layersRef.current.parcel;
    if (!map) return;
    if (parcel && "getBounds" in parcel) {
      map.fitBounds((parcel as import("leaflet").Polygon).getBounds(), {
        padding: [48, 48],
        maxZoom: 17,
      });
    } else if (hasGeo) {
      map.setView(center, 15);
    }
  }, [center, hasGeo]);

  const clearMeasure = useCallback(() => {
    measurePts.current = [];
    layersRef.current.measure?.clearLayers();
    setMeasureInfo("Click the map to drop measure points");
  }, []);

  const redrawMeasure = useCallback(async () => {
    const L = await import("leaflet");
    const group = layersRef.current.measure;
    const map = mapRef.current;
    if (!group || !map) return;
    group.clearLayers();
    const pts = measurePts.current;
    if (!pts.length) return;

    for (const p of pts) {
      L.circleMarker(p, {
        radius: 5,
        color: "#f2c14e",
        weight: 2,
        fillColor: "#fff",
        fillOpacity: 1,
      }).addTo(group);
    }
    if (pts.length > 1) {
      L.polyline(pts, { color: "#f2c14e", weight: 2.5, dashArray: "6 4" }).addTo(group);
      let total = 0;
      for (let i = 1; i < pts.length; i++) total += haversineMeters(pts[i - 1], pts[i]);
      const acres = pts.length >= 3 ? ringAreaAcres(pts) : 0;
      setMeasureInfo(
        acres > 0
          ? `Path ${formatDistance(total)} · Shape ~${acres.toFixed(2)} ac`
          : `Path ${formatDistance(total)} · click to continue`,
      );
    } else {
      setMeasureInfo("Point dropped — click again to measure");
    }
  }, []);

  // Mount / tear down map when modal opens
  useEffect(() => {
    if (!open || !mapEl.current) return;
    let cancelled = false;
    let map: import("leaflet").Map | null = null;

    async function boot() {
      const L = await import("leaflet");
      // @ts-expect-error leaflet image paths
      delete L.Icon.Default.prototype._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });
      if (cancelled || !mapEl.current) return;
      mapEl.current.innerHTML = "";

      map = L.map(mapEl.current, {
        scrollWheelZoom: true,
        dragging: true,
        doubleClickZoom: true,
        boxZoom: true,
        keyboard: true,
        zoomControl: false,
        attributionControl: true,
      }).setView(center, hasGeo ? 15 : 4);
      mapRef.current = map;

      const streets = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
      }).addTo(map);
      const satellite = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { attribution: "Esri imagery", maxZoom: 19, opacity: 0.88 },
      ).addTo(map);
      layersRef.current.streets = streets;
      layersRef.current.satellite = satellite;
      applyBasemap(basemap);

      const measure = L.layerGroup().addTo(map);
      layersRef.current.measure = measure;

      if (polygon?.[0]?.length) {
        const latlngs = polygon[0].map(([lon, lat]) => [lat, lon] as [number, number]);
        const layer = L.polygon(latlngs, {
          color: "#d6a243",
          weight: 2.5,
          fillColor: "#d6a243",
          fillOpacity: 0.22,
        }).addTo(map);
        layersRef.current.parcel = layer;
        map.fitBounds(layer.getBounds(), { padding: [48, 48], maxZoom: 17 });
      } else if (hasGeo) {
        layersRef.current.marker = L.marker(center).addTo(map).bindPopup(title || "Parcel");
      }

      map.on("mousemove", (e) => {
        setCoords(`${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`);
      });
      map.on("zoomend", () => setZoom(map!.getZoom()));
      setZoom(map.getZoom());

      map.on("click", (e) => {
        if (toolRef.current !== "measure") return;
        measurePts.current.push([e.latlng.lat, e.latlng.lng]);
        void redrawMeasure();
      });

      if (toolRef.current === "measure") {
        map.getContainer().style.cursor = "crosshair";
      }

      requestAnimationFrame(() => map?.invalidateSize());
      window.setTimeout(() => map?.invalidateSize(), 80);
      window.setTimeout(() => map?.invalidateSize(), 240);
    }

    boot();
    return () => {
      cancelled = true;
      measurePts.current = [];
      layersRef.current = {};
      map?.remove();
      mapRef.current = null;
    };
    // Intentionally remount when open toggles / geometry changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, latitude, longitude, polygon, title]);

  const toolRef = useRef(tool);
  useEffect(() => {
    toolRef.current = tool;
    const map = mapRef.current;
    if (!map) return;
    map.dragging.enable();
    map.getContainer().style.cursor = tool === "measure" ? "crosshair" : "";
    if (tool !== "measure") clearMeasure();
  }, [tool, clearMeasure]);

  useEffect(() => {
    applyBasemap(basemap);
  }, [basemap, applyBasemap]);

  useEffect(() => {
    const parcel = layersRef.current.parcel;
    if (!parcel || !mapRef.current) return;
    if (showBoundary) {
      if (!mapRef.current.hasLayer(parcel)) parcel.addTo(mapRef.current);
    } else {
      mapRef.current.removeLayer(parcel);
    }
  }, [showBoundary]);

  async function copyCoords() {
    if (!hasGeo) return;
    const text = `${latitude!.toFixed(6)}, ${longitude!.toFixed(6)}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }

  if (!mounted || !open) return null;

  return createPortal(
    <div
      className="land-viewer-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossOrigin=""
      />
      <div className="land-viewer">
        <header className="land-viewer-top">
          <div className="land-viewer-heading">
            <p className="land-viewer-kicker">Land view</p>
            <h2 id={titleId}>{title}</h2>
            <p className="land-viewer-sub">
              {[location, acresDisplay, priceDisplay].filter(Boolean).join(" · ") || "Explore this parcel"}
            </p>
          </div>
          <div className="land-viewer-top-actions">
            {reportHref ? (
              <a className="land-viewer-link" href={reportHref}>
                Full report
              </a>
            ) : null}
            <button type="button" className="land-viewer-close" onClick={onClose} aria-label="Close land view">
              ✕
            </button>
          </div>
        </header>

        <div className="land-viewer-tools" role="toolbar" aria-label="Map tools">
          <div className="land-viewer-tool-group" aria-label="Basemap">
            {(
              [
                ["hybrid", "Hybrid"],
                ["satellite", "Satellite"],
                ["streets", "Streets"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={basemap === id ? "is-on" : undefined}
                onClick={() => setBasemap(id)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="land-viewer-tool-group" aria-label="Interaction">
            <button
              type="button"
              className={tool === "pan" ? "is-on" : undefined}
              onClick={() => setTool("pan")}
            >
              Pan
            </button>
            <button
              type="button"
              className={tool === "measure" ? "is-on" : undefined}
              onClick={() => setTool("measure")}
            >
              Measure
            </button>
            <button
              type="button"
              className={showBoundary ? "is-on" : undefined}
              onClick={() => setShowBoundary((v) => !v)}
              disabled={!polygon?.[0]?.length}
            >
              Boundary
            </button>
          </div>

          <div className="land-viewer-tool-group" aria-label="View">
            <button type="button" onClick={() => mapRef.current?.zoomIn()}>
              +
            </button>
            <button type="button" onClick={() => mapRef.current?.zoomOut()}>
              −
            </button>
            <button type="button" onClick={fitParcel} disabled={!hasGeo}>
              Fit land
            </button>
            <button type="button" onClick={copyCoords} disabled={!hasGeo}>
              {copied ? "Copied" : "Copy pin"}
            </button>
            {tool === "measure" ? (
              <button type="button" onClick={clearMeasure}>
                Clear measure
              </button>
            ) : null}
          </div>
        </div>

        <div className="land-viewer-stage">
          {!hasGeo ? (
            <div className="land-viewer-empty">No coordinates available for this parcel yet.</div>
          ) : (
            <div ref={mapEl} className="land-viewer-map" />
          )}

          <div className="land-viewer-hud" aria-live="polite">
            <span>Zoom {zoom}</span>
            <span>Cursor {coords}</span>
            {hasGeo ? (
              <span>
                Pin {latitude!.toFixed(4)}, {longitude!.toFixed(4)}
              </span>
            ) : null}
            {tool === "measure" ? <span className="land-viewer-measure">{measureInfo}</span> : null}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function ViewLandButton({
  onClick,
  disabled,
}: {
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="land-alert-view-land"
      onClick={onClick}
      disabled={disabled}
    >
      <ImageIcon />
      <span>View land</span>
    </button>
  );
}
