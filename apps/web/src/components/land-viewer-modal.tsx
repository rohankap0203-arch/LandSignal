"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LiveMagnifier } from "@/components/live-magnifier";
import { landsignalApi } from "@/lib/api";
import { resolveLandPin } from "@/lib/land-pin";

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
  /** When set, Closest uses the parcel's stored coordinates (preferred for every listing). */
  parcelId?: string | null;
};

/** Clear yellow land outline — same signal as the old inventory maps. */
const LAND_OUTLINE = {
  color: "#f2c14e",
  weight: 3.25,
  opacity: 1,
  fillColor: "#f2c14e",
  fillOpacity: 0.2,
} as const;

function ringsToLatLngs(polygon: number[][][] | null | undefined): [number, number][][] {
  if (!polygon?.length) return [];
  return polygon
    .map((ring) =>
      (ring || [])
        .map((pt) => {
          if (!pt || pt.length < 2) return null;
          const lon = Number(pt[0]);
          const lat = Number(pt[1]);
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
          if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
          return [lat, lon] as [number, number];
        })
        .filter((p): p is [number, number] => p != null),
    )
    .filter((ring) => ring.length >= 3);
}

type Basemap = "satellite" | "streets" | "hybrid";
type Tool = "pan" | "measure" | "radius";

type NearbyKind =
  | "flood"
  | "wetland"
  | "road"
  | "power"
  | "town"
  | "school"
  | "hospital"
  | "water";

type NearbyHit = {
  kind: NearbyKind;
  label: string;
  name: string;
  lat: number;
  lon: number;
  meters: number;
  source: "live";
  detail?: string;
  osmKey?: string;
};

const NEARBY_RESULT_LIMIT = 3;
/** UI watchdog — Closest must never spin past this even if the API is slow. */
const NEARBY_UI_DEADLINE_MS = 14_000;

type NearbyChip = {
  kind: NearbyKind;
  label: string;
  color: string;
  maxMiles: number;
};

const NEARBY_CHIPS: NearbyChip[] = [
  { kind: "flood", label: "Flood zone", color: "#3b82f6", maxMiles: 15 },
  { kind: "wetland", label: "Wetland", color: "#14b8a6", maxMiles: 18 },
  { kind: "water", label: "Water body", color: "#0ea5e9", maxMiles: 18 },
  { kind: "road", label: "Paved road", color: "#a16207", maxMiles: 12 },
  { kind: "power", label: "Power line", color: "#ca8a04", maxMiles: 18 },
  { kind: "town", label: "Town/services", color: "#b45309", maxMiles: 35 },
  { kind: "school", label: "School", color: "#7c3aed", maxMiles: 25 },
  { kind: "hospital", label: "Hospital", color: "#dc2626", maxMiles: 50 },
];

const NEARBY_ROW1 = NEARBY_CHIPS.filter((c) =>
  ["flood", "wetland", "water", "road", "power"].includes(c.kind),
);
const NEARBY_ROW2 = NEARBY_CHIPS.filter((c) =>
  ["town", "school", "hospital"].includes(c.kind),
);

const nearbyCache = new Map<string, { hits: NearbyHit[]; message?: string }>();
/** Cancel in-flight Closest API calls when the user switches chips. */
let nearbyAbort: AbortController | null = null;

function beginNearbySearch() {
  nearbyAbort?.abort();
  nearbyAbort = new AbortController();
  return nearbyAbort;
}

/** Great-circle distance between two [lat, lon] points (meters). */
function haversineMeters(a: [number, number], b: [number, number]): number {
  const R = 6371008.8;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const [lat1, lon1] = a;
  const [lat2, lon2] = b;
  const φ1 = toRad(lat1);
  const φ2 = toRad(lat2);
  const Δφ = toRad(lat2 - lat1);
  const Δλ = toRad(lon2 - lon1);
  const h =
    Math.sin(Δφ / 2) ** 2 + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

function formatDistance(meters: number) {
  if (!Number.isFinite(meters) || meters < 0) return "—";
  const miles = meters / 1609.344;
  const feet = meters * 3.28084;
  if (miles < 0.15) return `${Math.round(feet).toLocaleString()} ft`;
  if (miles < 1) {
    return `${miles.toFixed(2)} mi (${Math.round(feet).toLocaleString()} ft)`;
  }
  return `${miles.toFixed(miles < 10 ? 2 : 1)} mi`;
}

function formatDistanceShort(meters: number) {
  if (!Number.isFinite(meters) || meters < 0) return "—";
  const miles = meters / 1609.344;
  if (miles < 0.15) return `${Math.round(meters * 3.28084).toLocaleString()} ft`;
  return `${miles.toFixed(miles < 10 ? 2 : 1)} mi`;
}

function isValidLatLon(lat: unknown, lon: unknown): lat is number {
  return (
    typeof lat === "number" &&
    typeof lon === "number" &&
    Number.isFinite(lat) &&
    Number.isFinite(lon) &&
    Math.abs(lat) <= 90 &&
    Math.abs(lon) <= 180
  );
}

function asLatLon(lat: unknown, lon: unknown): [number, number] | null {
  return isValidLatLon(lat, lon) ? [lat, lon as number] : null;
}

/** High-precision display for live map coordinates (no padded fake zeros beyond source). */
function formatCoordPair(lat: number, lon: number, digits = 5): string {
  return `${lat.toFixed(digits)}, ${lon.toFixed(digits)}`;
}

/** Only accept published acreage strings — never invent from rough geometry. */
function legitimateAcresDisplay(acresDisplay?: string | null): string | null {
  const raw = String(acresDisplay || "").trim();
  if (!raw) return null;
  if (/n\/a|not published|unknown|null|undefined/i.test(raw)) return null;
  if (!/\d/.test(raw)) return null;
  return raw;
}

function legitimatePriceDisplay(priceDisplay?: string | null): string | null {
  const raw = String(priceDisplay || "").trim();
  if (!raw) return null;
  if (/n\/a|no public|unknown|null|undefined|—|-/i.test(raw)) return null;
  if (!/\d/.test(raw)) return null;
  return raw;
}

function ordinalClosest(index: number) {
  if (index <= 0) return "Closest";
  if (index === 1) return "2nd closest";
  if (index === 2) return "3rd closest";
  return `${index + 1}th closest`;
}

/**
 * Closest landmarks via LandSignal API for any listing pin nationwide.
 * Always queries by lat/lon (map pin coords). If a parcelId lookup is available
 * and lat/lon fails, falls back to the parcel endpoint — never depends on store
 * presence alone, so Closest stays functional after API restarts.
 */
async function requestNearbyPayload(
  kind: NearbyKind,
  lat: number,
  lon: number,
  parcelId: string | null | undefined,
  signal: AbortSignal,
) {
  const { landsignalApi } = await import("@/lib/api");
  try {
    return await landsignalApi.nearby(lat, lon, kind, { signal });
  } catch (err) {
    if (signal.aborted || (err instanceof DOMException && err.name === "AbortError")) {
      throw err;
    }
    if (!parcelId) throw err;
    return landsignalApi.nearbyForParcel(parcelId, kind, { signal });
  }
}

async function fetchNearby(
  kind: NearbyKind,
  lat: number,
  lon: number,
  onPartial?: (hits: NearbyHit[]) => void,
  isCancelled?: () => boolean,
  parcelId?: string | null,
): Promise<{ hits: NearbyHit[]; message: string | null }> {
  const meta = NEARBY_CHIPS.find((c) => c.kind === kind);
  if (!meta) return { hits: [], message: "Unknown landmark type" };

  const cacheKey = `api:v4:${kind}:${lat.toFixed(3)}:${lon.toFixed(3)}`;
  if (nearbyCache.has(cacheKey)) {
    const cached = nearbyCache.get(cacheKey)!;
    if (cached.hits.length) {
      onPartial?.(cached.hits);
      return { hits: cached.hits, message: null };
    }
  }

  const runOnce = async (): Promise<{ hits: NearbyHit[]; message: string | null; status?: string }> => {
    const ctl = beginNearbySearch();
    let timeoutId: number | undefined;
    try {
      const data = await new Promise<Awaited<ReturnType<typeof requestNearbyPayload>>>((resolve, reject) => {
        timeoutId = window.setTimeout(() => {
          ctl.abort();
          reject(new Error("Closest search timed out"));
        }, NEARBY_UI_DEADLINE_MS);
        const onAbort = () => {
          if (timeoutId) window.clearTimeout(timeoutId);
          reject(new DOMException("Aborted", "AbortError"));
        };
        ctl.signal.addEventListener("abort", onAbort, { once: true });
        requestNearbyPayload(kind, lat, lon, parcelId, ctl.signal)
          .then((value) => {
            if (timeoutId) window.clearTimeout(timeoutId);
            ctl.signal.removeEventListener("abort", onAbort);
            resolve(value);
          })
          .catch((err) => {
            if (timeoutId) window.clearTimeout(timeoutId);
            ctl.signal.removeEventListener("abort", onAbort);
            reject(err);
          });
      });

      if (isCancelled?.() || ctl.signal.aborted) {
        return { hits: [], message: null };
      }

      const hits: NearbyHit[] = (data.hits || [])
        .filter((h) => isValidLatLon(h.lat, h.lon) && Number.isFinite(h.meters))
        .slice(0, NEARBY_RESULT_LIMIT)
        .map((h) => ({
          kind,
          label: h.label || meta.label,
          name: h.name || meta.label,
          lat: Number(h.lat),
          lon: Number(h.lon),
          meters: Number(h.meters),
          source: "live" as const,
          detail: h.detail || undefined,
          osmKey: h.osm_key || undefined,
        }));

      if (hits.length) {
        onPartial?.(hits);
        nearbyCache.set(cacheKey, { hits });
        return { hits, message: null, status: "ok" };
      }

      const message =
        data.message ||
        (data.status === "unavailable"
          ? `Map data temporarily unavailable for ${meta.label.toLowerCase()} — tap again to retry`
          : `No mapped ${meta.label.toLowerCase()} within ~${meta.maxMiles} mi`);
      return { hits: [], message, status: data.status };
    } catch (e) {
      if (isCancelled?.() || (e instanceof DOMException && e.name === "AbortError")) {
        return { hits: [], message: null };
      }
      return {
        hits: [],
        message: `Couldn’t find ${meta.label.toLowerCase()} nearby — tap again to retry`,
        status: "unavailable",
      };
    }
  };

  let result = await runOnce();
  // One automatic retry on transient upstream failure — Closest must feel reliable.
  if (
    !result.hits.length &&
    !isCancelled?.() &&
    (result.status === "unavailable" || /unavailable|timed out|retry/i.test(result.message || ""))
  ) {
    await new Promise((r) => window.setTimeout(r, 450));
    if (!isCancelled?.()) {
      result = await runOnce();
    }
  }
  return { hits: result.hits, message: result.message };
}

function MagnifierIcon({ className = "" }: { className?: string }) {
  return (
    <svg
      className={`land-alert-view-land-icon ${className}`.trim()}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle cx="10.5" cy="10.5" r="6.25" stroke="currentColor" strokeWidth="2" />
      <line
        x1="15.2"
        y1="15.2"
        x2="20.5"
        y2="20.5"
        stroke="currentColor"
        strokeWidth="2.25"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function FullscreenIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
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
  parcelId,
}: LandViewerProps) {
  const titleId = useId();
  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import("leaflet").Map | null>(null);
  const layersRef = useRef<{
    streets?: import("leaflet").TileLayer;
    satellite?: import("leaflet").TileLayer;
    parcel?: import("leaflet").Layer;
    measure?: import("leaflet").LayerGroup;
    nearby?: import("leaflet").LayerGroup;
    radius?: import("leaflet").LayerGroup;
    grid?: import("leaflet").LayerGroup;
    marker?: import("leaflet").Marker;
  }>({});
  const measurePts = useRef<[number, number][]>([]);
  const toolRef = useRef<Tool>("pan");
  const radiusMilesRef = useRef(1);

  const [mounted, setMounted] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("hybrid");
  const [tool, setTool] = useState<Tool>("pan");
  const [showBoundary, setShowBoundary] = useState(true);
  const showBoundaryRef = useRef(true);
  const [showGrid, setShowGrid] = useState(false);
  const [radiusMiles, setRadiusMiles] = useState<0 | 1 | 5>(0);
  const [resolvedPolygon, setResolvedPolygon] = useState<number[][][] | null>(polygon ?? null);
  const [mapReady, setMapReady] = useState(false);
  const [coords, setCoords] = useState<string>("—");
  const [zoom, setZoom] = useState<number | null>(null);
  const [measureInfo, setMeasureInfo] = useState("Tap the map to drop the first point");
  const [measureTotalLabel, setMeasureTotalLabel] = useState<string | null>(null);
  const [measureSegmentLabel, setMeasureSegmentLabel] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [elevationFt, setElevationFt] = useState<string | null>(null);
  const [nearbyActive, setNearbyActive] = useState<NearbyKind | null>(null);
  const [nearbyStatus, setNearbyStatus] = useState<string>("");
  const [nearbyLoading, setNearbyLoading] = useState(false);
  const [nearbyHits, setNearbyHits] = useState<NearbyHit[]>([]);
  const [nearbyHitIndex, setNearbyHitIndex] = useState(0);
  const nearbySearchGen = useRef(0);
  const nearbyHitIndexRef = useRef(0);

  const hasGeo = isValidLatLon(latitude, longitude) || Boolean(resolvedPolygon?.[0]?.length);
  const landPin = useMemo(
    () => resolveLandPin(latitude, longitude, resolvedPolygon),
    [latitude, longitude, resolvedPolygon],
  );
  const pinLat = landPin?.[0] ?? null;
  const pinLon = landPin?.[1] ?? null;
  const pinLabel =
    pinLat != null && pinLon != null ? formatCoordPair(pinLat, pinLon, 5) : null;
  const acresLabel = useMemo(() => legitimateAcresDisplay(acresDisplay), [acresDisplay]);
  const priceLabel = useMemo(() => legitimatePriceDisplay(priceDisplay), [priceDisplay]);
  const center = useMemo<[number, number]>(
    () => (landPin ? landPin : [39.5, -98.35]),
    [landPin],
  );

  useEffect(() => setMounted(true), []);

  // Prefer prop polygon; otherwise fetch compact outline for every inventory open.
  useEffect(() => {
    if (!open) return;
    setResolvedPolygon(polygon ?? null);
  }, [open, polygon]);

  useEffect(() => {
    if (!open || !parcelId) return;
    // Always resolve from /geometry so inventory gets the real GIS outline
    // (never trust a leftover fake square on the card payload).
    let cancelled = false;
    void landsignalApi
      .parcelGeometry(parcelId)
      .then((g) => {
        if (cancelled) return;
        if (g.polygon?.[0]?.length) setResolvedPolygon(g.polygon);
        else if (!polygon?.[0]?.length) setResolvedPolygon(null);
      })
      .catch(() => null);
    return () => {
      cancelled = true;
    };
  }, [open, parcelId, polygon]);

  // Do not prefetch all Closest chips on open — parallel Overpass/Photon storms
  // make the chip the user actually taps time out on "Working". Fetch on demand.

  useEffect(() => {
    if (!open) return;
    setTool("pan");
    toolRef.current = "pan";
    setBasemap("hybrid");
    setShowBoundary(true);
    setShowGrid(false);
    setRadiusMiles(0);
    radiusMilesRef.current = 1;
    setMapReady(false);
    setMeasureInfo("Tap the map to drop the first point");
    setMeasureTotalLabel(null);
    setMeasureSegmentLabel(null);
    setCopied(false);
    setNearbyActive(null);
    setNearbyStatus("");
    setNearbyHits([]);
    setNearbyHitIndex(0);
    nearbyHitIndexRef.current = 0;
    nearbySearchGen.current += 1;
    nearbyAbort?.abort();
    setNearbyLoading(false);
    setElevationFt(null);
    setZoom(null);
    {
      const pair = asLatLon(latitude, longitude);
      setCoords(pair ? formatCoordPair(pair[0], pair[1], 5) : "—");
    }
    const prevBodyOverflow = document.body.style.overflow;
    const prevHtmlOverflow = document.documentElement.style.overflow;
    const prevBodyOverscroll = document.body.style.overscrollBehavior;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    document.body.style.overscrollBehavior = "none";
    document.documentElement.classList.add("land-viewer-open");
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevBodyOverflow;
      document.documentElement.style.overflow = prevHtmlOverflow;
      document.body.style.overscrollBehavior = prevBodyOverscroll;
      document.documentElement.classList.remove("land-viewer-open");
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose, latitude, longitude]);

  useEffect(() => {
    if (!open || !hasGeo) {
      setElevationFt(null);
      return;
    }
    let cancelled = false;
    setElevationFt(null);
    (async () => {
      try {
        const res = await fetch(
          `https://api.open-meteo.com/v1/elevation?latitude=${pinLat ?? latitude}&longitude=${pinLon ?? longitude}`,
        );
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as { elevation?: Array<number | null> };
        const m = data.elevation?.[0];
        // Only accept a real DEM sample in a physically plausible range — never invent.
        if (
          cancelled ||
          m == null ||
          !Number.isFinite(m) ||
          m < -420 ||
          m > 8850
        ) {
          return;
        }
        const ft = m * 3.280839895;
        if (!Number.isFinite(ft)) return;
        setElevationFt(`${Math.round(ft).toLocaleString()} ft elev`);
      } catch {
        if (!cancelled) setElevationFt(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, hasGeo, pinLat, pinLon, latitude, longitude]);

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

  const redrawMeasureRef = useRef<(() => Promise<void>) | null>(null);

  const clearMeasure = useCallback(() => {
    measurePts.current = [];
    layersRef.current.measure?.clearLayers();
    setMeasureInfo("Tap the map to drop the first point");
    setMeasureTotalLabel(null);
    setMeasureSegmentLabel(null);
  }, []);

  const redrawMeasure = useCallback(async () => {
    const L = await import("leaflet");
    const group = layersRef.current.measure;
    if (!group) return;
    group.clearLayers();
    const pts = measurePts.current;
    if (!pts.length) {
      setMeasureInfo("Tap the map to drop the first point");
      setMeasureTotalLabel(null);
      setMeasureSegmentLabel(null);
      return;
    }

    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      L.circleMarker(p, {
        radius: i === 0 ? 6 : 5,
        color: "#f2c14e",
        weight: 2,
        fillColor: i === 0 ? "#f2c14e" : "#fff",
        fillOpacity: 1,
      }).addTo(group);
    }

    if (pts.length === 1) {
      setMeasureTotalLabel(null);
      setMeasureSegmentLabel(null);
      setMeasureInfo("Point 1 set — tap again for distance");
      return;
    }

    L.polyline(pts, { color: "#f2c14e", weight: 3, dashArray: "7 5", opacity: 0.95 }).addTo(group);

    let total = 0;
    let lastSeg = 0;
    for (let i = 1; i < pts.length; i++) {
      const seg = haversineMeters(pts[i - 1], pts[i]);
      lastSeg = seg;
      total += seg;
      const mid: [number, number] = [
        (pts[i - 1][0] + pts[i][0]) / 2,
        (pts[i - 1][1] + pts[i][1]) / 2,
      ];
      const label = formatDistanceShort(seg);
      L.marker(mid, {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: "land-viewer-measure-label",
          html: `<span>${label}</span>`,
          iconSize: [0, 0],
          iconAnchor: [0, 0],
        }),
      }).addTo(group);
    }

    const totalText = formatDistance(total);
    const segText = formatDistance(lastSeg);
    setMeasureTotalLabel(totalText);
    setMeasureSegmentLabel(pts.length > 2 ? segText : null);
    setMeasureInfo(
      pts.length === 2
        ? `Distance ${totalText} · tap to add another point`
        : `Total ${totalText} · last segment ${segText} · tap to continue`,
    );
  }, []);

  redrawMeasureRef.current = redrawMeasure;

  const undoMeasurePoint = useCallback(() => {
    if (!measurePts.current.length) return;
    measurePts.current = measurePts.current.slice(0, -1);
    void redrawMeasureRef.current?.();
  }, []);

  const drawRadius = useCallback(async (miles: number) => {
    const L = await import("leaflet");
    const group = layersRef.current.radius;
    const map = mapRef.current;
    if (!group || !map || !hasGeo) return;
    group.clearLayers();
    if (miles <= 0) return;
    const meters = miles * 1609.344;
    L.circle(center, {
      radius: meters,
      color: "#f2c14e",
      weight: 1.5,
      dashArray: "4 6",
      fillColor: "#f2c14e",
      fillOpacity: 0.08,
    }).addTo(group);
    map.fitBounds(L.latLng(center[0], center[1]).toBounds(meters * 2.15), { maxZoom: 14 });
  }, [center, hasGeo]);

  const drawGrid = useCallback(async (on: boolean) => {
    const L = await import("leaflet");
    const group = layersRef.current.grid;
    const map = mapRef.current;
    if (!group || !map) return;
    group.clearLayers();
    if (!on) return;
    const b = map.getBounds().pad(0.15);
    const step = Math.max(0.005, (b.getNorth() - b.getSouth()) / 8);
    for (let lat = Math.floor(b.getSouth() / step) * step; lat <= b.getNorth(); lat += step) {
      L.polyline(
        [
          [lat, b.getWest()],
          [lat, b.getEast()],
        ],
        { color: "#ffffff", weight: 1.15, opacity: 0.55 },
      ).addTo(group);
    }
    for (let lon = Math.floor(b.getWest() / step) * step; lon <= b.getEast(); lon += step) {
      L.polyline(
        [
          [b.getSouth(), lon],
          [b.getNorth(), lon],
        ],
        { color: "#ffffff", weight: 1.15, opacity: 0.55 },
      ).addTo(group);
    }
  }, []);

  const paintNearbyHit = useCallback(
    async (hit: NearbyHit, index: number) => {
      const chip = NEARBY_CHIPS.find((c) => c.kind === hit.kind);
      const L = await import("leaflet");
      const map = mapRef.current;
      const layer = layersRef.current.nearby;
      if (!map || !layer) return;

      layer.clearLayers();
      const color = chip?.color || "#f2c14e";
      const rank = ordinalClosest(index);
      L.polyline([center, [hit.lat, hit.lon]], {
        color,
        weight: 2.5,
        dashArray: "7 5",
      }).addTo(layer);
      const detailHtml = hit.detail ? `<br/><em>${hit.detail}</em>` : "";
      L.circleMarker([hit.lat, hit.lon], {
        radius: 8,
        color: "#fff",
        weight: 2,
        fillColor: color,
        fillOpacity: 1,
      })
        .bindPopup(
          `<strong>${rank} ${hit.label}</strong><br/>${hit.name}<br/>${formatDistance(hit.meters)} away${detailHtml}`,
        )
        .addTo(layer)
        .openPopup();
      map.fitBounds(L.latLngBounds([center, [hit.lat, hit.lon]]), {
        padding: [60, 60],
        maxZoom: 14,
      });
      const detailSuffix = hit.detail ? ` · ${hit.detail}` : "";
      setNearbyStatus(
        `${rank} ${hit.label}: ${formatDistance(hit.meters)} · ${hit.name}${detailSuffix}`,
      );
    },
    [center],
  );

  const showNearby = useCallback(
    async (kind: NearbyKind) => {
      if (!hasGeo || !mapRef.current) return;
      if (nearbyActive === kind) {
        nearbySearchGen.current += 1;
        nearbyAbort?.abort();
        layersRef.current.nearby?.clearLayers();
        setNearbyActive(null);
        setNearbyHits([]);
        setNearbyHitIndex(0);
        nearbyHitIndexRef.current = 0;
        setNearbyLoading(false);
        setNearbyStatus("");
        return;
      }
      const chip = NEARBY_CHIPS.find((c) => c.kind === kind);
      nearbySearchGen.current += 1;
      const gen = nearbySearchGen.current;
      nearbyAbort?.abort();
      setNearbyLoading(true);
      setNearbyStatus(`Finding closest ${chip?.label ?? "feature"}…`);
      setNearbyActive(kind);
      setNearbyHits([]);
      setNearbyHitIndex(0);
      nearbyHitIndexRef.current = 0;
      layersRef.current.nearby?.clearLayers();

      let paintedKey: string | null = null;
      let hits: NearbyHit[] = [];
      let emptyMessage: string | null = null;
      const applyPartial = (partial: NearbyHit[]) => {
        if (gen !== nearbySearchGen.current || !partial.length) return;
        setNearbyLoading(false);
        setNearbyHits(partial);
        const first = partial[0];
        const key = first.osmKey ?? `${first.lat.toFixed(5)},${first.lon.toFixed(5)}`;
        if (paintedKey === null || (nearbyHitIndexRef.current === 0 && paintedKey !== key)) {
          paintedKey = key;
          setNearbyHitIndex(0);
          nearbyHitIndexRef.current = 0;
          void paintNearbyHit(first, 0);
        }
      };

      const watchdog = window.setTimeout(() => {
        if (gen !== nearbySearchGen.current) return;
        nearbyAbort?.abort();
        setNearbyLoading(false);
        if (!paintedKey) {
          setNearbyStatus(
            `Couldn’t find ${chip?.label?.toLowerCase() ?? "that"} nearby — tap again to retry`,
          );
        }
      }, NEARBY_UI_DEADLINE_MS + 400);

      try {
        const result = await fetchNearby(
          kind,
          pinLat ?? latitude!,
          pinLon ?? longitude!,
          applyPartial,
          () => gen !== nearbySearchGen.current,
          parcelId,
        );
        hits = result.hits;
        emptyMessage = result.message;
      } catch {
        hits = [];
        emptyMessage = `Couldn’t find ${chip?.label?.toLowerCase() ?? "that"} nearby — tap again to retry`;
      } finally {
        window.clearTimeout(watchdog);
        if (gen === nearbySearchGen.current) setNearbyLoading(false);
      }

      if (gen !== nearbySearchGen.current) return;
      if (!mapRef.current || !layersRef.current.nearby) return;

      if (!hits.length) {
        setNearbyHits([]);
        setNearbyHitIndex(0);
        nearbyHitIndexRef.current = 0;
        if (!paintedKey) {
          setNearbyStatus(
            emptyMessage ||
              `No mapped ${chip?.label?.toLowerCase() ?? "feature"} within ~${chip?.maxMiles ?? 10} mi`,
          );
        }
        return;
      }

      setNearbyHits(hits);
      if (paintedKey === null) {
        setNearbyHitIndex(0);
        nearbyHitIndexRef.current = 0;
        await paintNearbyHit(hits[0], 0);
      }
    },
    [hasGeo, pinLat, pinLon, latitude, longitude, nearbyActive, paintNearbyHit, parcelId],
  );

  const showPrevNearby = useCallback(() => {
    if (nearbyHitIndex <= 0) return;
    const prev = nearbyHitIndex - 1;
    const hit = nearbyHits[prev];
    if (!hit) return;
    setNearbyHitIndex(prev);
    nearbyHitIndexRef.current = prev;
    void paintNearbyHit(hit, prev);
  }, [nearbyHitIndex, nearbyHits, paintNearbyHit]);

  const showNextNearby = useCallback(() => {
    if (nearbyHitIndex >= nearbyHits.length - 1) return;
    if (nearbyHitIndex >= NEARBY_RESULT_LIMIT - 1) return;
    const next = nearbyHitIndex + 1;
    const hit = nearbyHits[next];
    if (!hit) return;
    setNearbyHitIndex(next);
    nearbyHitIndexRef.current = next;
    void paintNearbyHit(hit, next);
  }, [nearbyHitIndex, nearbyHits, paintNearbyHit]);

  const canPrevNearby = nearbyHits.length > 1 && nearbyHitIndex > 0;
  const canNextNearby =
    nearbyHits.length > 1 &&
    nearbyHitIndex < nearbyHits.length - 1 &&
    nearbyHitIndex < NEARBY_RESULT_LIMIT - 1;

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
        zoomControl: true,
        attributionControl: false,
      }).setView(center, hasGeo ? 15 : 4);
      map.zoomControl.setPosition("topleft");
      mapRef.current = map;

      const streets = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "",
        maxZoom: 19,
      }).addTo(map);
      const satellite = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { attribution: "", maxZoom: 19, opacity: 0.88 },
      ).addTo(map);
      layersRef.current.streets = streets;
      layersRef.current.satellite = satellite;
      applyBasemap("hybrid");

      layersRef.current.measure = L.layerGroup().addTo(map);
      layersRef.current.nearby = L.layerGroup().addTo(map);
      layersRef.current.radius = L.layerGroup().addTo(map);
      layersRef.current.grid = L.layerGroup().addTo(map);

      // Pin first; yellow land outline is painted by the outline effect
      // (geometry often arrives a tick after open on inventory cards).
      if (hasGeo && landPin) {
        layersRef.current.marker = L.marker(landPin).addTo(map).bindPopup(title || "Parcel");
      }

      if (landPin) setCoords(formatCoordPair(landPin[0], landPin[1], 5));
      map.on("mousemove", (e) => {
        const lat = e.latlng.lat;
        const lon = e.latlng.lng;
        if (!isValidLatLon(lat, lon)) return;
        setCoords(formatCoordPair(lat, lon, 5));
      });
      map.on("zoomend moveend", () => {
        const z = map!.getZoom();
        if (Number.isFinite(z)) setZoom(Math.round(z * 10) / 10);
        if (showGridRef.current) void drawGrid(true);
      });
      {
        const z = map.getZoom();
        if (Number.isFinite(z)) setZoom(Math.round(z * 10) / 10);
      }

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
      if (!cancelled) setMapReady(true);
    }

    boot();
    return () => {
      cancelled = true;
      setMapReady(false);
      measurePts.current = [];
      layersRef.current = {};
      map?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, latitude, longitude, title, hasGeo, landPin?.[0], landPin?.[1]]);

  // Yellow land outline — paint / refresh whenever geometry resolves (and map is ready).
  useEffect(() => {
    if (!open || !mapReady || !mapRef.current) return;
    const map = mapRef.current;
    const prev = layersRef.current.parcel;
    if (prev) {
      map.removeLayer(prev);
      layersRef.current.parcel = undefined;
    }
    const rings = ringsToLatLngs(resolvedPolygon);
    if (!rings.length) return;
    let cancelled = false;
    void import("leaflet").then((L) => {
      if (cancelled || !mapRef.current) return;
      const layer = L.polygon(rings, { ...LAND_OUTLINE });
      layersRef.current.parcel = layer;
      if (showBoundaryRef.current) layer.addTo(mapRef.current);
      try {
        mapRef.current.fitBounds(layer.getBounds(), { padding: [48, 48], maxZoom: 17 });
      } catch {
        /* ignore empty bounds */
      }
    });
    return () => {
      cancelled = true;
    };
    // showBoundary is read via ref so toggling Boundary does not re-fit the map.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mapReady, resolvedPolygon]);

  useEffect(() => {
    showBoundaryRef.current = showBoundary;
    const parcel = layersRef.current.parcel;
    if (!parcel || !mapRef.current) return;
    if (showBoundary) {
      if (!mapRef.current.hasLayer(parcel)) parcel.addTo(mapRef.current);
    } else {
      mapRef.current.removeLayer(parcel);
    }
  }, [showBoundary]);

  const showGridRef = useRef(showGrid);
  useEffect(() => {
    showGridRef.current = showGrid;
    void drawGrid(showGrid);
  }, [showGrid, drawGrid]);

  useEffect(() => {
    toolRef.current = tool;
    const map = mapRef.current;
    if (!map) return;
    if (tool === "measure") {
      map.getContainer().style.cursor = "crosshair";
      map.doubleClickZoom.disable();
    } else {
      map.getContainer().style.cursor = "";
      map.doubleClickZoom.enable();
      clearMeasure();
    }
  }, [tool, clearMeasure]);

  useEffect(() => {
    applyBasemap(basemap);
  }, [basemap, applyBasemap]);

  useEffect(() => {
    void drawRadius(radiusMiles);
  }, [radiusMiles, drawRadius]);

  async function copyCoords() {
    if (!landPin) return;
    const text = formatCoordPair(landPin[0], landPin[1], 6);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }

  const mapsUrl = landPin
    ? `https://www.google.com/maps?q=${landPin[0]},${landPin[1]}`
    : null;
  const directionsUrl = landPin
    ? `https://www.google.com/maps/dir/?api=1&destination=${landPin[0]},${landPin[1]}`
    : null;
  const streetViewUrl = landPin
    ? `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${landPin[0]},${landPin[1]}`
    : null;

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
              {[location, acresLabel, priceLabel, elevationFt].filter(Boolean).join(" · ") ||
                "Explore this parcel"}
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
          <div className="land-viewer-tools-row">
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
                onClick={() => {
                  toolRef.current = "pan";
                  setTool("pan");
                }}
              >
                Pan
              </button>
              <button
                type="button"
                className={tool === "measure" ? "is-on" : undefined}
                onClick={() => {
                  toolRef.current = "measure";
                  setTool("measure");
                }}
              >
                Measure
              </button>
              {tool === "measure" ? (
                <>
                  <button
                    type="button"
                    onClick={undoMeasurePoint}
                    title="Undo last measure point"
                  >
                    Undo
                  </button>
                  <button type="button" onClick={clearMeasure} title="Clear measure points">
                    Clear
                  </button>
                </>
              ) : null}
              <button
                type="button"
                className={showBoundary ? "is-on" : undefined}
                onClick={() => setShowBoundary((v) => !v)}
                disabled={!resolvedPolygon?.[0]?.length}
              >
                Boundary
              </button>
              <button
                type="button"
                className={showGrid ? "is-on" : undefined}
                onClick={() => setShowGrid((v) => !v)}
              >
                Grid
              </button>
            </div>
          </div>

          <div className="land-viewer-tools-row">
            <div className="land-viewer-tool-group" aria-label="Radius">
              <button
                type="button"
                className={radiusMiles === 1 ? "is-on" : undefined}
                onClick={() => setRadiusMiles((v) => (v === 1 ? 0 : 1))}
                disabled={!hasGeo}
              >
                1 mi
              </button>
              <button
                type="button"
                className={radiusMiles === 5 ? "is-on" : undefined}
                onClick={() => setRadiusMiles((v) => (v === 5 ? 0 : 5))}
                disabled={!hasGeo}
              >
                5 mi
              </button>
            </div>

            <div className="land-viewer-tool-group" aria-label="View">
              <button type="button" onClick={fitParcel} disabled={!hasGeo} title="Fit land">
                Fit land
              </button>
              <button type="button" onClick={copyCoords} disabled={!hasGeo} title="Copy pin coordinates">
                {copied ? "Copied" : "Copy pin"}
              </button>
            </div>

            <div className="land-viewer-tool-group" aria-label="Owner links">
              {mapsUrl ? (
                <a className="land-viewer-tool-link" href={mapsUrl} target="_blank" rel="noreferrer">
                  Maps
                </a>
              ) : null}
              {directionsUrl ? (
                <a className="land-viewer-tool-link" href={directionsUrl} target="_blank" rel="noreferrer">
                  Directions
                </a>
              ) : null}
              {streetViewUrl ? (
                <a className="land-viewer-tool-link" href={streetViewUrl} target="_blank" rel="noreferrer">
                  Street View
                </a>
              ) : null}
            </div>
          </div>
        </div>

        <div className="land-viewer-nearby" aria-label="Closest landmarks">
          <span className="land-viewer-nearby-label">Closest</span>
          <div className="land-viewer-nearby-chips">
            {NEARBY_ROW1.map((chip) => (
              <button
                key={chip.kind}
                type="button"
                className={`land-viewer-chip${nearbyActive === chip.kind ? " is-on" : ""}`}
                style={{ ["--chip" as string]: chip.color }}
                disabled={!hasGeo}
                onClick={() => void showNearby(chip.kind)}
                title={
                  nearbyLoading && nearbyActive === chip.kind
                    ? "Cancel search"
                    : nearbyLoading
                      ? `Switch to ${chip.label}`
                      : chip.label
                }
              >
                {chip.label}
              </button>
            ))}
            {NEARBY_ROW2.map((chip) => (
              <button
                key={chip.kind}
                type="button"
                className={`land-viewer-chip${chip.kind === "town" ? " land-viewer-chip--town" : ""}${nearbyActive === chip.kind ? " is-on" : ""}`}
                style={{ ["--chip" as string]: chip.color }}
                disabled={!hasGeo}
                onClick={() => void showNearby(chip.kind)}
                title={
                  nearbyLoading && nearbyActive === chip.kind
                    ? "Cancel search"
                    : nearbyLoading
                      ? `Switch to ${chip.label}`
                      : chip.label
                }
              >
                {chip.label}
              </button>
            ))}
            {nearbyLoading ? (
              <span className="land-viewer-nearby-loading" role="status" aria-live="polite">
                <LiveMagnifier size={14} label="Finding closest landmark" />
                <span>Working</span>
              </span>
            ) : nearbyHits.length > 1 ? (
              <div
                className="land-viewer-nearby-nav"
                role="group"
                aria-label={`Closest result ${nearbyHitIndex + 1} of ${nearbyHits.length}`}
              >
                <button
                  type="button"
                  className="land-viewer-nearby-nav-arrow is-back"
                  onClick={showPrevNearby}
                  disabled={!canPrevNearby}
                  aria-label="Previous closest"
                  title="Previous closest"
                >
                  <span className="land-viewer-nearby-next-arrow" aria-hidden>
                    ←
                  </span>
                </button>
                <span className="land-viewer-nearby-next-count">
                  {nearbyHitIndex + 1}/{nearbyHits.length}
                </span>
                <button
                  type="button"
                  className="land-viewer-nearby-nav-arrow is-forward"
                  onClick={showNextNearby}
                  disabled={!canNextNearby}
                  aria-label="Next closest"
                  title="Next closest"
                >
                  <span className="land-viewer-nearby-next-arrow" aria-hidden>
                    →
                  </span>
                </button>
              </div>
            ) : null}
          </div>
        </div>

        <div className="land-viewer-stage">
          {!hasGeo ? (
            <div className="land-viewer-empty">No coordinates available for this parcel yet.</div>
          ) : (
            <div ref={mapEl} className="land-viewer-map" />
          )}

          <div className="land-viewer-compass" aria-hidden>
            N
          </div>

          <div className="land-viewer-hud" aria-live="polite">
            <div className="land-viewer-hud-row">
              {zoom != null ? <span>Zoom {zoom}</span> : null}
              <span>Cursor {coords}</span>
              {pinLabel ? <span>Pin {pinLabel}</span> : null}
            </div>
            <div className="land-viewer-hud-row">
              {acresLabel ? <span>{acresLabel}</span> : null}
              {elevationFt ? <span>{elevationFt}</span> : null}
              {nearbyStatus ? <span className="land-viewer-nearby-status">{nearbyStatus}</span> : null}
            </div>
          </div>

          {tool === "measure" ? (
            <div className="land-viewer-measure-panel" role="status" aria-live="polite">
              <div className="land-viewer-measure-kicker">Measure distance</div>
              <div className="land-viewer-measure-value">
                {measureTotalLabel ?? "—"}
              </div>
              {measureSegmentLabel ? (
                <div className="land-viewer-measure-seg">Last segment · {measureSegmentLabel}</div>
              ) : null}
              <div className="land-viewer-measure-hint">{measureInfo}</div>
            </div>
          ) : null}
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
      <MagnifierIcon />
      <span>View land</span>
    </button>
  );
}
