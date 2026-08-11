"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LiveMagnifier } from "@/components/live-magnifier";

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

type NearbyChip = {
  kind: NearbyKind;
  label: string;
  color: string;
  /** Overpass union body fragments (without around filter). */
  overpassParts: string[];
  radiiM: number[];
  maxMiles: number;
  /** center = fast area/POI lookup; geom = needed for accurate linear features */
  outMode: "center" | "geom";
};

const NEARBY_CHIPS: NearbyChip[] = [
  {
    kind: "flood",
    label: "Flood zone",
    color: "#3b82f6",
    // Prefer explicit flood tags; waterways are a legitimate flood-adjacency proxy when flood polygons are unmapped.
    overpassParts: [
      'nwr["flood_prone"="yes"]',
      'nwr["hazard"="flood"]',
      'nwr["flood:zone"]',
      'way["waterway"~"^(river|stream|canal)$"]',
    ],
    radiiM: [1200, 5000, 14000],
    maxMiles: 12.4,
    outMode: "geom",
  },
  {
    kind: "wetland",
    label: "Wetland",
    color: "#14b8a6",
    // Tight wetland tag only — broad ["wetland"] + full geom was stalling Overpass.
    overpassParts: ['nwr["natural"="wetland"]'],
    radiiM: [1500, 6000, 15000],
    maxMiles: 10,
    outMode: "center",
  },
  {
    kind: "road",
    label: "Paved road",
    color: "#a16207",
    overpassParts: [
      'way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link)$"]',
      'way["highway"~"^(residential|unclassified)$"]["surface"~"^(paved|asphalt|concrete|chipseal|paving_stones)$"]',
    ],
    radiiM: [800, 3000, 10000],
    maxMiles: 7.5,
    outMode: "geom",
  },
  {
    kind: "power",
    label: "Power line",
    color: "#ca8a04",
    overpassParts: [
      'way["power"~"^(line|minor_line|cable)$"]',
      'nwr["power"~"^(substation|transformer|tower|pole)$"]',
    ],
    radiiM: [1200, 5000, 14000],
    maxMiles: 11,
    outMode: "geom",
  },
  {
    kind: "town",
    label: "Town / services",
    color: "#b45309",
    overpassParts: ['node["place"~"^(city|town|village)$"]'],
    radiiM: [3000, 12000, 30000],
    maxMiles: 25,
    outMode: "center",
  },
  {
    kind: "school",
    label: "School",
    color: "#7c3aed",
    overpassParts: ['nwr["amenity"="school"]', 'nwr["amenity"="kindergarten"]'],
    radiiM: [1500, 6000, 16000],
    maxMiles: 12.4,
    outMode: "center",
  },
  {
    kind: "hospital",
    label: "Hospital",
    color: "#dc2626",
    overpassParts: [
      'nwr["amenity"="hospital"]',
      'nwr["healthcare"="hospital"]',
      'nwr["amenity"="clinic"]["emergency"="yes"]',
    ],
    radiiM: [3000, 12000, 32000],
    maxMiles: 22,
    outMode: "center",
  },
  {
    kind: "water",
    label: "Water body",
    color: "#0ea5e9",
    overpassParts: [
      'nwr["natural"="water"]',
      'nwr["water"~"^(lake|pond|reservoir|basin)$"]',
      'nwr["landuse"="reservoir"]',
    ],
    radiiM: [1500, 6000, 15000],
    maxMiles: 11,
    outMode: "center",
  },
];

const OVERPASS_ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
];

const nearbyCache = new Map<string, NearbyHit[]>();
/** In-flight Overpass aborts when the user switches Closest chips. */
let nearbyOverpassAbort: AbortController | null = null;

function beginNearbyOverpass() {
  nearbyOverpassAbort?.abort();
  nearbyOverpassAbort = new AbortController();
  return nearbyOverpassAbort;
}

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

/** Closest point on segment A→B to point P, in lat/lon degrees (local ENU approx). */
function closestPointOnSegment(
  p: [number, number],
  a: [number, number],
  b: [number, number],
): { lat: number; lon: number; meters: number } {
  const lat0 = p[0];
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.max(0.2, Math.cos((lat0 * Math.PI) / 180));
  const px = (p[1] - a[1]) * mPerDegLon;
  const py = (p[0] - a[0]) * mPerDegLat;
  const bx = (b[1] - a[1]) * mPerDegLon;
  const by = (b[0] - a[0]) * mPerDegLat;
  const denom = bx * bx + by * by;
  const t = denom <= 1e-9 ? 0 : Math.max(0, Math.min(1, (px * bx + py * by) / denom));
  const lon = a[1] + (t * bx) / mPerDegLon;
  const lat = a[0] + (t * by) / mPerDegLat;
  return { lat, lon, meters: haversineMeters(p, [lat, lon]) };
}

function formatDistance(meters: number) {
  if (!Number.isFinite(meters) || meters < 0) return "—";
  const miles = meters / 1609.344;
  if (miles < 0.2) return `${Math.round(meters * 3.28084)} ft`;
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

type OverpassElement = {
  type?: string;
  id?: number;
  lat?: number;
  lon?: number;
  center?: { lat: number; lon: number };
  geometry?: Array<{ lat: number; lon: number }>;
  tags?: Record<string, string>;
};

function elementKey(el: OverpassElement): string {
  if (el.type && el.id != null) return `${el.type}/${el.id}`;
  const lat = el.lat ?? el.center?.lat ?? el.geometry?.[0]?.lat;
  const lon = el.lon ?? el.center?.lon ?? el.geometry?.[0]?.lon;
  if (lat == null || lon == null) return `anon:${Math.random()}`;
  return `pt:${lat.toFixed(5)}:${lon.toFixed(5)}`;
}

function elementName(el: OverpassElement, fallback: string) {
  const t = el.tags || {};
  return (
    t.name ||
    t["name:en"] ||
    t.brand ||
    t.operator ||
    t.waterway ||
    t.water ||
    t.highway ||
    t.place ||
    t.amenity ||
    t.power ||
    t.natural ||
    t.wetland ||
    t["flood:zone"] ||
    fallback
  );
}

function isFloodTagged(el: OverpassElement) {
  const t = el.tags || {};
  return Boolean(t.flood_prone === "yes" || t.hazard === "flood" || t["flood:zone"]);
}

function closestOnElement(
  origin: [number, number],
  el: OverpassElement,
): { lat: number; lon: number; meters: number } | null {
  const geom = el.geometry;
  if (geom && geom.length >= 2) {
    let best: { lat: number; lon: number; meters: number } | null = null;
    for (let i = 0; i < geom.length - 1; i++) {
      const a: [number, number] = [geom[i].lat, geom[i].lon];
      const b: [number, number] = [geom[i + 1].lat, geom[i + 1].lon];
      const hit = closestPointOnSegment(origin, a, b);
      if (!best || hit.meters < best.meters) best = hit;
    }
    if (best) return best;
  }
  if (geom && geom.length === 1) {
    const lat = geom[0].lat;
    const lon = geom[0].lon;
    return { lat, lon, meters: haversineMeters(origin, [lat, lon]) };
  }
  const lat = el.lat ?? el.center?.lat;
  const lon = el.lon ?? el.center?.lon;
  if (lat == null || lon == null) return null;
  return { lat, lon, meters: haversineMeters(origin, [lat, lon]) };
}

async function overpassQuery(
  query: string,
  timeoutMs = 8000,
  externalSignal?: AbortSignal,
): Promise<OverpassElement[]> {
  // Race public Overpass mirrors — first valid payload wins (wetland geom used to stall for 14s+).
  const controllers = OVERPASS_ENDPOINTS.map(() => new AbortController());
  const abortAll = () => controllers.forEach((c) => c.abort());
  const timer = window.setTimeout(abortAll, timeoutMs);
  const onExternalAbort = () => abortAll();
  if (externalSignal) {
    if (externalSignal.aborted) {
      window.clearTimeout(timer);
      throw new DOMException("Aborted", "AbortError");
    }
    externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }
  try {
    const elements = await Promise.any(
      OVERPASS_ENDPOINTS.map(async (endpoint, i) => {
        const res = await fetch(endpoint, {
          method: "POST",
          body: query,
          headers: { "Content-Type": "text/plain" },
          signal: controllers[i].signal,
        });
        if (!res.ok) throw new Error(`Overpass ${res.status}`);
        const data = (await res.json()) as { elements?: OverpassElement[] };
        // Empty is a valid answer for this radius — still prefer a mirror that responded.
        return data.elements || [];
      }),
    );
    abortAll();
    return elements;
  } catch (e) {
    if (externalSignal?.aborted) throw new DOMException("Aborted", "AbortError");
    throw e instanceof Error ? e : new Error("Overpass unavailable");
  } finally {
    window.clearTimeout(timer);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }
}

function pickTopHits(
  kind: NearbyKind,
  label: string,
  origin: [number, number],
  elements: OverpassElement[],
  limit = NEARBY_RESULT_LIMIT,
): NearbyHit[] {
  const byKey = new Map<string, NearbyHit & { floodTagged: boolean }>();

  for (const el of elements) {
    const pt = closestOnElement(origin, el);
    if (!pt) continue;
    const meters = haversineMeters(origin, [pt.lat, pt.lon]);
    if (!Number.isFinite(meters) || meters < 0) continue;

    const name = elementName(el, label);
    const floodTagged = kind === "flood" && isFloodTagged(el);
    const detail =
      kind === "flood"
        ? floodTagged
          ? "Flood tag"
          : "Nearest mapped waterway (flood-adjacency)"
        : undefined;

    const key = elementKey(el);
    const hit = {
      kind,
      label,
      name,
      lat: pt.lat,
      lon: pt.lon,
      meters,
      source: "live" as const,
      detail,
      osmKey: key,
      floodTagged,
    };
    const prev = byKey.get(key);
    if (!prev || meters < prev.meters) byKey.set(key, hit);
  }

  const all = [...byKey.values()];
  const floodFirst = all.filter((h) => h.floodTagged).sort((a, b) => a.meters - b.meters);
  const rest = all.filter((h) => !h.floodTagged).sort((a, b) => a.meters - b.meters);
  // Prefer explicit flood tags when present (accuracy > nearest arbitrary waterway).
  const ranked = floodFirst.length ? [...floodFirst, ...rest] : rest;

  const out: NearbyHit[] = [];
  for (const raw of ranked) {
    const { floodTagged: _flood, ...hit } = raw;
    const nearDup = out.some(
      (o) =>
        haversineMeters([o.lat, o.lon], [hit.lat, hit.lon]) < 55 &&
        o.name.trim().toLowerCase() === hit.name.trim().toLowerCase(),
    );
    if (nearDup) continue;
    out.push(hit);
    if (out.length >= limit) break;
  }
  return out;
}

function ordinalClosest(index: number) {
  if (index <= 0) return "Closest";
  if (index === 1) return "2nd closest";
  if (index === 2) return "3rd closest";
  return `${index + 1}th closest`;
}

function verifyNearbyHits(origin: [number, number], hits: NearbyHit[]): NearbyHit[] {
  return hits.slice(0, NEARBY_RESULT_LIMIT).map((hit) => {
    const again = haversineMeters(origin, [hit.lat, hit.lon]);
    if (Math.abs(again - hit.meters) > 25) return { ...hit, meters: again };
    return hit;
  });
}

/**
 * Progressive Overpass search. Calls onPartial as soon as #1 is known so the UI
 * can paint immediately, then keeps expanding radii in the background for #2/#3.
 */
async function fetchNearby(
  kind: NearbyKind,
  lat: number,
  lon: number,
  onPartial?: (hits: NearbyHit[]) => void,
  isCancelled?: () => boolean,
): Promise<NearbyHit[]> {
  const meta = NEARBY_CHIPS.find((c) => c.kind === kind);
  if (!meta) return [];

  const cacheKey = `${kind}:${lat.toFixed(4)}:${lon.toFixed(4)}`;
  // Only reuse successful caches — never lock in an empty miss (Overpass blips used to
  // make Hospital "permanently" fail after Water until reload).
  if (nearbyCache.has(cacheKey)) {
    const cached = nearbyCache.get(cacheKey) ?? [];
    if (cached.length) {
      onPartial?.(cached);
      return cached;
    }
    nearbyCache.delete(cacheKey);
  }

  const origin: [number, number] = [lat, lon];
  let best: NearbyHit[] = [];
  let lastPartialSig = "";
  const overpassCtl = beginNearbyOverpass();

  const emit = (hits: NearbyHit[]) => {
    if (!hits.length || !onPartial) return;
    const verified = verifyNearbyHits(origin, hits);
    const sig = verified.map((h) => `${h.osmKey ?? h.name}:${Math.round(h.meters)}`).join("|");
    if (sig === lastPartialSig) return;
    lastPartialSig = sig;
    onPartial(verified);
  };

  const outClause = meta.outMode === "center" ? "out center;" : "out geom;";

  // Progressive radii: surface the first hit ASAP, then keep going for up to 3.
  for (let i = 0; i < meta.radiiM.length; i++) {
    const radius = meta.radiiM[i];
    if (isCancelled?.() || overpassCtl.signal.aborted) break;
    const union = meta.overpassParts.map((part) => `  ${part}(around:${radius},${lat},${lon});`).join("\n");
    const query = `
[out:json][timeout:8];
(
${union}
);
${outClause}
`.trim();
    try {
      // First radius: fail fast. Later radii get a bit more time.
      const elements = await overpassQuery(query, i === 0 ? 8000 : 10000, overpassCtl.signal);
      if (isCancelled?.() || overpassCtl.signal.aborted) break;
      const hits = pickTopHits(kind, meta.label, origin, elements, NEARBY_RESULT_LIMIT).filter(
        (h) => h.meters / 1609.344 <= meta.maxMiles,
      );
      if (hits.length) {
        best = hits;
        emit(best);
        // Cache partial success so a remount doesn't wait again.
        nearbyCache.set(cacheKey, verifyNearbyHits(origin, best));
        const farthestKept = hits[hits.length - 1];
        if (hits.length >= NEARBY_RESULT_LIMIT && farthestKept.meters <= radius * 1.05) break;
      }
    } catch (e) {
      if (isCancelled?.() || overpassCtl.signal.aborted) break;
      if (e instanceof DOMException && e.name === "AbortError") break;
      // Try next radius / endpoint path; do not invent a fake location.
      continue;
    }
  }

  best = verifyNearbyHits(origin, best);
  // Never cache empty misses — allow a real retry on the next click.
  if (!isCancelled?.() && !overpassCtl.signal.aborted && best.length) {
    nearbyCache.set(cacheKey, best);
  }
  return best;
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
  const [showGrid, setShowGrid] = useState(false);
  const [radiusMiles, setRadiusMiles] = useState<0 | 1 | 5>(0);
  const [coords, setCoords] = useState<string>("—");
  const [zoom, setZoom] = useState<number | null>(null);
  const [measureInfo, setMeasureInfo] = useState("Click the map to drop measure points");
  const [copied, setCopied] = useState(false);
  const [elevationFt, setElevationFt] = useState<string | null>(null);
  const [nearbyActive, setNearbyActive] = useState<NearbyKind | null>(null);
  const [nearbyStatus, setNearbyStatus] = useState<string>("");
  const [nearbyLoading, setNearbyLoading] = useState(false);
  const [nearbyHits, setNearbyHits] = useState<NearbyHit[]>([]);
  const [nearbyHitIndex, setNearbyHitIndex] = useState(0);
  const nearbySearchGen = useRef(0);
  const nearbyHitIndexRef = useRef(0);

  const hasGeo = isValidLatLon(latitude, longitude);
  const pinLabel = hasGeo ? formatCoordPair(latitude!, longitude!, 5) : null;
  const acresLabel = useMemo(() => legitimateAcresDisplay(acresDisplay), [acresDisplay]);
  const priceLabel = useMemo(() => legitimatePriceDisplay(priceDisplay), [priceDisplay]);
  const center = useMemo<[number, number]>(
    () => (hasGeo ? [latitude!, longitude!] : [39.5, -98.35]),
    [hasGeo, latitude, longitude],
  );

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    setTool("pan");
    toolRef.current = "pan";
    setBasemap("hybrid");
    setShowBoundary(true);
    setShowGrid(false);
    setRadiusMiles(0);
    radiusMilesRef.current = 1;
    setMeasureInfo("Click the map to drop measure points");
    setCopied(false);
    setNearbyActive(null);
    setNearbyStatus("");
    setNearbyHits([]);
    setNearbyHitIndex(0);
    nearbyHitIndexRef.current = 0;
    nearbySearchGen.current += 1;
    setElevationFt(null);
    setZoom(null);
    setCoords(isValidLatLon(latitude, longitude) ? formatCoordPair(latitude, longitude, 5) : "—");
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
          `https://api.open-meteo.com/v1/elevation?latitude=${latitude}&longitude=${longitude}`,
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
  }, [open, hasGeo, latitude, longitude]);

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
    if (!group) return;
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
      // Path length only — do not invent acreage from open click shapes.
      setMeasureInfo(
        Number.isFinite(total) && total > 0
          ? `Path ${formatDistance(total)} · click to continue`
          : "Click the map to drop measure points",
      );
    } else {
      setMeasureInfo("Point dropped — click again to measure");
    }
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
      color: "#d6a243",
      weight: 1.5,
      dashArray: "4 6",
      fillColor: "#d6a243",
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
      const color = chip?.color || "#d6a243";
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
        nearbyOverpassAbort?.abort();
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
      // Cancel any in-flight Water/#2/#3 Overpass work before starting Hospital/School/etc.
      nearbySearchGen.current += 1;
      const gen = nearbySearchGen.current;
      nearbyOverpassAbort?.abort();
      setNearbyLoading(true);
      setNearbyStatus(`Finding closest ${chip?.label ?? "feature"}…`);
      setNearbyActive(kind);
      setNearbyHits([]);
      setNearbyHitIndex(0);
      nearbyHitIndexRef.current = 0;
      const group = layersRef.current.nearby;
      group?.clearLayers();

      let paintedKey: string | null = null;
      const applyPartial = (partial: NearbyHit[]) => {
        if (gen !== nearbySearchGen.current || !partial.length) return;
        setNearbyLoading(false);
        setNearbyHits(partial);
        const first = partial[0];
        const key = first.osmKey ?? `${first.lat.toFixed(5)},${first.lon.toFixed(5)}`;
        // Paint #1 immediately; only re-paint if still viewing #1 and it improved.
        if (paintedKey === null || (nearbyHitIndexRef.current === 0 && paintedKey !== key)) {
          paintedKey = key;
          setNearbyHitIndex(0);
          nearbyHitIndexRef.current = 0;
          void paintNearbyHit(first, 0);
        }
      };

      let hits: NearbyHit[] = [];
      try {
        hits = await fetchNearby(
          kind,
          latitude!,
          longitude!,
          applyPartial,
          () => gen !== nearbySearchGen.current,
        );
        // One automatic retry on hard miss (Overpass often flakes right after another chip).
        if (!hits.length && gen === nearbySearchGen.current) {
          nearbyCache.delete(`${kind}:${latitude!.toFixed(4)}:${longitude!.toFixed(4)}`);
          hits = await fetchNearby(
            kind,
            latitude!,
            longitude!,
            applyPartial,
            () => gen !== nearbySearchGen.current,
          );
        }
      } catch {
        hits = [];
      }
      if (gen !== nearbySearchGen.current) return;
      setNearbyLoading(false);

      if (!mapRef.current || !layersRef.current.nearby) return;

      if (!hits.length) {
        setNearbyHits([]);
        setNearbyHitIndex(0);
        nearbyHitIndexRef.current = 0;
        setNearbyStatus(
          `No mapped ${chip?.label?.toLowerCase() ?? "feature"} within ~${chip?.maxMiles ?? 10} mi`,
        );
        return;
      }

      setNearbyHits(hits);
      if (paintedKey === null) {
        setNearbyHitIndex(0);
        nearbyHitIndexRef.current = 0;
        await paintNearbyHit(hits[0], 0);
      }
    },
    [hasGeo, latitude, longitude, nearbyActive, paintNearbyHit],
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

      if (hasGeo) setCoords(formatCoordPair(latitude!, longitude!, 5));
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
    }

    boot();
    return () => {
      cancelled = true;
      measurePts.current = [];
      layersRef.current = {};
      map?.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, latitude, longitude, polygon, title]);

  const showGridRef = useRef(showGrid);
  useEffect(() => {
    showGridRef.current = showGrid;
    void drawGrid(showGrid);
  }, [showGrid, drawGrid]);

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

  useEffect(() => {
    void drawRadius(radiusMiles);
  }, [radiusMiles, drawRadius]);

  async function copyCoords() {
    if (!isValidLatLon(latitude, longitude)) return;
    const text = formatCoordPair(latitude, longitude, 6);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }

  const mapsUrl = hasGeo
    ? `https://www.google.com/maps?q=${latitude},${longitude}`
    : null;
  const directionsUrl = hasGeo
    ? `https://www.google.com/maps/dir/?api=1&destination=${latitude},${longitude}`
    : null;
  const streetViewUrl = hasGeo
    ? `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${latitude},${longitude}`
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
              {tool === "measure" ? (
                <button type="button" onClick={clearMeasure} title="Clear measure points">
                  Clear
                </button>
              ) : null}
              <button
                type="button"
                className={showBoundary ? "is-on" : undefined}
                onClick={() => setShowBoundary((v) => !v)}
                disabled={!polygon?.[0]?.length}
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
            {NEARBY_CHIPS.map((chip) => (
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
              {tool === "measure" ? <span className="land-viewer-measure">{measureInfo}</span> : null}
              {nearbyStatus ? <span className="land-viewer-nearby-status">{nearbyStatus}</span> : null}
            </div>
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
      <MagnifierIcon />
      <span>View land</span>
    </button>
  );
}
