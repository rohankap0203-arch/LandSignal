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
};

type NearbyChip = {
  kind: NearbyKind;
  label: string;
  color: string;
  /** Overpass union body fragments (without around filter). */
  overpassParts: string[];
  radiiM: number[];
  maxMiles: number;
};

const NEARBY_CHIPS: NearbyChip[] = [
  {
    kind: "flood",
    label: "Flood",
    color: "#3b82f6",
    // Prefer explicit flood tags; waterways are a legitimate flood-adjacency proxy when flood polygons are unmapped.
    overpassParts: [
      'nwr["flood_prone"="yes"]',
      'nwr["hazard"="flood"]',
      'nwr["flood:zone"]',
      'way["waterway"~"^(river|stream|canal)$"]',
    ],
    radiiM: [800, 2500, 8000, 20000],
    maxMiles: 12.4,
  },
  {
    kind: "wetland",
    label: "Wetland",
    color: "#14b8a6",
    overpassParts: ['nwr["natural"="wetland"]', 'nwr["wetland"]'],
    radiiM: [600, 2000, 7000, 16000],
    maxMiles: 10,
  },
  {
    kind: "road",
    label: "Road",
    color: "#a16207",
    // Higher-class roads are paved; residential only when surface is explicitly paved.
    overpassParts: [
      'way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link)$"]',
      'way["highway"~"^(residential|unclassified)$"]["surface"~"^(paved|asphalt|concrete|chipseal|paving_stones)$"]',
    ],
    radiiM: [400, 1500, 5000, 12000],
    maxMiles: 7.5,
  },
  {
    kind: "power",
    label: "Power",
    color: "#ca8a04",
    overpassParts: [
      'way["power"~"^(line|minor_line|cable)$"]',
      'nwr["power"~"^(substation|transformer|tower|pole)$"]',
    ],
    radiiM: [600, 2500, 8000, 18000],
    maxMiles: 11,
  },
  {
    kind: "town",
    label: "Town",
    color: "#b45309",
    overpassParts: ['node["place"~"^(city|town|village)$"]'],
    radiiM: [2000, 8000, 20000, 40000],
    maxMiles: 25,
  },
  {
    kind: "school",
    label: "School",
    color: "#7c3aed",
    overpassParts: ['nwr["amenity"="school"]', 'nwr["amenity"="kindergarten"]'],
    radiiM: [800, 3000, 10000, 20000],
    maxMiles: 12.4,
  },
  {
    kind: "hospital",
    label: "Hospital",
    color: "#dc2626",
    overpassParts: ['nwr["amenity"="hospital"]', 'nwr["amenity"="clinic"]["emergency"="yes"]'],
    radiiM: [1500, 6000, 15000, 35000],
    maxMiles: 22,
  },
  {
    kind: "water",
    label: "Water",
    color: "#0ea5e9",
    overpassParts: [
      'nwr["natural"="water"]',
      'nwr["water"~"^(lake|pond|reservoir|basin)$"]',
      'nwr["landuse"="reservoir"]',
    ],
    radiiM: [600, 2500, 8000, 18000],
    maxMiles: 11,
  },
];

const NEARBY_CHIP_TITLES: Record<NearbyKind, string> = {
  flood: "Closest flood zone / flood-adjacent waterway",
  wetland: "Closest wetland",
  road: "Closest paved road",
  power: "Closest power line or substation",
  town: "Closest town / village",
  school: "Closest school",
  hospital: "Closest hospital",
  water: "Closest water body",
};

const OVERPASS_ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
];

const nearbyCache = new Map<string, NearbyHit | null>();

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
  const miles = meters / 1609.344;
  if (miles < 0.2) return `${Math.round(meters * 3.28084)} ft`;
  return `${miles.toFixed(miles < 10 ? 2 : 1)} mi`;
}

function ringAreaAcres(ring: [number, number][]) {
  if (ring.length < 3) return 0;
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

type OverpassElement = {
  type?: string;
  lat?: number;
  lon?: number;
  center?: { lat: number; lon: number };
  geometry?: Array<{ lat: number; lon: number }>;
  tags?: Record<string, string>;
};

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

async function overpassQuery(query: string): Promise<OverpassElement[]> {
  let lastErr: unknown;
  for (const endpoint of OVERPASS_ENDPOINTS) {
    try {
      const ctrl = new AbortController();
      const timer = window.setTimeout(() => ctrl.abort(), 14000);
      const res = await fetch(endpoint, {
        method: "POST",
        body: query,
        headers: { "Content-Type": "text/plain" },
        signal: ctrl.signal,
      });
      window.clearTimeout(timer);
      if (!res.ok) {
        lastErr = new Error(`Overpass ${res.status}`);
        continue;
      }
      const data = (await res.json()) as { elements?: OverpassElement[] };
      return data.elements || [];
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error("Overpass unavailable");
}

function pickBestHit(
  kind: NearbyKind,
  label: string,
  origin: [number, number],
  elements: OverpassElement[],
): NearbyHit | null {
  let best: NearbyHit | null = null;
  let bestFlood: NearbyHit | null = null;

  for (const el of elements) {
    const pt = closestOnElement(origin, el);
    if (!pt) continue;
    // Triple-check: recompute haversine from chosen point
    const meters = haversineMeters(origin, [pt.lat, pt.lon]);
    if (!Number.isFinite(meters) || meters < 0) continue;

    const name = elementName(el, label);
    const floodTagged = kind === "flood" && isFloodTagged(el);
    const detail =
      kind === "flood"
        ? floodTagged
          ? "OSM flood tag"
          : "Nearest mapped waterway (flood-adjacency)"
        : "OpenStreetMap";

    const hit: NearbyHit = {
      kind,
      label,
      name,
      lat: pt.lat,
      lon: pt.lon,
      meters,
      source: "live",
      detail,
    };

    if (kind === "flood" && floodTagged) {
      if (!bestFlood || meters < bestFlood.meters) bestFlood = hit;
    }
    if (!best || meters < best.meters) best = hit;
  }

  // Prefer explicit flood tags when present (accuracy > nearest arbitrary waterway).
  return bestFlood || best;
}

async function fetchNearby(kind: NearbyKind, lat: number, lon: number): Promise<NearbyHit | null> {
  const meta = NEARBY_CHIPS.find((c) => c.kind === kind);
  if (!meta) return null;

  const cacheKey = `${kind}:${lat.toFixed(4)}:${lon.toFixed(4)}`;
  if (nearbyCache.has(cacheKey)) return nearbyCache.get(cacheKey) ?? null;

  const origin: [number, number] = [lat, lon];
  let best: NearbyHit | null = null;

  // Progressive radii: small first → faster + prefers truly local features.
  for (const radius of meta.radiiM) {
    const union = meta.overpassParts.map((part) => `  ${part}(around:${radius},${lat},${lon});`).join("\n");
    const query = `
[out:json][timeout:12];
(
${union}
);
out geom;
`.trim();
    try {
      const elements = await overpassQuery(query);
      const hit = pickBestHit(kind, meta.label, origin, elements);
      if (hit) {
        // Accept immediately when found inside this radius (already the closest in-set).
        // Re-verify it is within the searched radius (+small tolerance for geom snap).
        if (hit.meters <= radius * 1.05) {
          best = hit;
          break;
        }
        if (!best || hit.meters < best.meters) best = hit;
      }
    } catch {
      // Try next radius / endpoint path; do not invent a fake location.
      continue;
    }
  }

  // Final legitimacy gate: never return a hit beyond chip max range.
  if (best && best.meters / 1609.344 > meta.maxMiles) {
    best = null;
  }

  // Second pass verification for accepted hit (distance consistency).
  if (best) {
    const again = haversineMeters(origin, [best.lat, best.lon]);
    if (Math.abs(again - best.meters) > 25) {
      best = { ...best, meters: again };
    }
  }

  nearbyCache.set(cacheKey, best);
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
  const [zoom, setZoom] = useState(14);
  const [measureInfo, setMeasureInfo] = useState("Click the map to drop measure points");
  const [copied, setCopied] = useState(false);
  const [elevationFt, setElevationFt] = useState<string | null>(null);
  const [parcelAcres, setParcelAcres] = useState<string | null>(null);
  const [nearbyActive, setNearbyActive] = useState<NearbyKind | null>(null);
  const [nearbyStatus, setNearbyStatus] = useState<string>("");
  const [nearbyLoading, setNearbyLoading] = useState(false);
  const [activeHit, setActiveHit] = useState<NearbyHit | null>(null);

  const hasGeo = latitude != null && longitude != null;
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
    setActiveHit(null);
    setElevationFt(null);
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

  useEffect(() => {
    if (!open || !hasGeo) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `https://api.open-meteo.com/v1/elevation?latitude=${latitude}&longitude=${longitude}`,
        );
        if (!res.ok) return;
        const data = (await res.json()) as { elevation?: number[] };
        const m = data.elevation?.[0];
        if (!cancelled && m != null && Number.isFinite(m)) {
          setElevationFt(`${Math.round(m * 3.28084)} ft elev`);
        }
      } catch {
        /* optional */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, hasGeo, latitude, longitude]);

  useEffect(() => {
    if (polygon?.[0]?.length) {
      const ring = polygon[0].map(([lon, lat]) => [lat, lon] as [number, number]);
      const acres = ringAreaAcres(ring);
      if (acres > 0) setParcelAcres(`${acres.toFixed(acres < 10 ? 2 : 1)} ac boundary`);
      else setParcelAcres(null);
    } else {
      setParcelAcres(null);
    }
  }, [polygon]);

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

  const showNearby = useCallback(
    async (kind: NearbyKind) => {
      if (!hasGeo || !mapRef.current) return;
      if (nearbyActive === kind) {
        layersRef.current.nearby?.clearLayers();
        setNearbyActive(null);
        setActiveHit(null);
        setNearbyStatus("");
        return;
      }
      const chip = NEARBY_CHIPS.find((c) => c.kind === kind);
      setNearbyLoading(true);
      setNearbyStatus(`Finding closest ${chip?.label ?? "feature"}…`);
      setNearbyActive(kind);
      setActiveHit(null);
      const group = layersRef.current.nearby;
      group?.clearLayers();

      let hit: NearbyHit | null = null;
      try {
        hit = await fetchNearby(kind, latitude!, longitude!);
      } catch {
        hit = null;
      }
      setNearbyLoading(false);

      const L = await import("leaflet");
      const map = mapRef.current;
      const layer = layersRef.current.nearby;
      if (!map || !layer) return;

      if (!hit) {
        setActiveHit(null);
        setNearbyStatus(
          `No mapped ${chip?.label?.toLowerCase() ?? "feature"} within ~${chip?.maxMiles ?? 10} mi (OpenStreetMap)`,
        );
        return;
      }

      setActiveHit(hit);
      const color = chip?.color || "#d6a243";
      L.polyline([center, [hit.lat, hit.lon]], {
        color,
        weight: 2.5,
        dashArray: "7 5",
      }).addTo(layer);
      L.circleMarker([hit.lat, hit.lon], {
        radius: 8,
        color: "#fff",
        weight: 2,
        fillColor: color,
        fillOpacity: 1,
      })
        .bindPopup(
          `<strong>${hit.label}</strong><br/>${hit.name}<br/>${formatDistance(hit.meters)} away` +
            (hit.detail ? `<br/><span style="opacity:.8">${hit.detail}</span>` : ""),
        )
        .addTo(layer)
        .openPopup();
      map.fitBounds(L.latLngBounds([center, [hit.lat, hit.lon]]), {
        padding: [60, 60],
        maxZoom: 14,
      });
      setNearbyStatus(
        `${hit.label}: ${formatDistance(hit.meters)} · ${hit.name}` +
          (hit.detail ? ` · ${hit.detail}` : ""),
      );
    },
    [center, hasGeo, latitude, longitude, nearbyActive],
  );

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
        attributionControl: true,
      }).setView(center, hasGeo ? 15 : 4);
      map.zoomControl.setPosition("topleft");
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

      map.on("mousemove", (e) => {
        setCoords(`${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`);
      });
      map.on("zoomend moveend", () => {
        setZoom(map!.getZoom());
        if (showGridRef.current) void drawGrid(true);
      });
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
              {[location, acresDisplay || parcelAcres, priceDisplay, elevationFt]
                .filter(Boolean)
                .join(" · ") || "Explore this parcel"}
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
              <button type="button" onClick={fitParcel} disabled={!hasGeo}>
                Fit land
              </button>
              <button type="button" onClick={copyCoords} disabled={!hasGeo}>
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
          <div className="land-viewer-nearby-head">
            <span className="land-viewer-nearby-label">Closest</span>
            {nearbyLoading ? (
              <span className="land-viewer-nearby-loading" role="status" aria-live="polite">
                <LiveMagnifier size={14} label="Finding closest landmark" />
                <span>Working</span>
              </span>
            ) : null}
          </div>
          <div className="land-viewer-nearby-grid">
            {NEARBY_CHIPS.map((chip) => (
              <button
                key={chip.kind}
                type="button"
                className={`land-viewer-chip${nearbyActive === chip.kind ? " is-on" : ""}`}
                style={{ ["--chip" as string]: chip.color }}
                title={NEARBY_CHIP_TITLES[chip.kind]}
                aria-label={NEARBY_CHIP_TITLES[chip.kind]}
                disabled={!hasGeo || nearbyLoading}
                onClick={() => void showNearby(chip.kind)}
              >
                {chip.label}
              </button>
            ))}
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
              <span>Zoom {zoom}</span>
              <span>Cursor {coords}</span>
              {hasGeo ? (
                <span>
                  Pin {latitude!.toFixed(4)}, {longitude!.toFixed(4)}
                </span>
              ) : null}
            </div>
            <div className="land-viewer-hud-row">
              {parcelAcres ? <span>{parcelAcres}</span> : null}
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
