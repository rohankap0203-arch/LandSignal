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
  /** Overpass union body fragments (without bbox filter). */
  overpassParts: string[];
  /** Only used when primary parts return no validated hits (e.g. flood-adjacency). */
  overpassPartsFallback?: string[];
  radiiM: number[];
  maxMiles: number;
  /** center = fast POI lookup; geom = distance to line/area edge */
  outMode: "center" | "geom";
};

const NEARBY_CHIPS: NearbyChip[] = [
  {
    kind: "flood",
    label: "Flood zone",
    color: "#3b82f6",
    // Strict flood tags only; waterway adjacency is fallback when flood polygons are unmapped.
    overpassParts: [
      'nwr["flood_prone"="yes"]',
      'nwr["hazard"="flood"]',
      'nwr["flood:zone"]',
      'nwr["floodplain"="yes"]',
    ],
    overpassPartsFallback: ['way["waterway"~"^(river|stream|canal)$"]'],
    radiiM: [1500, 6000, 14000],
    maxMiles: 12.4,
    outMode: "geom",
  },
  {
    kind: "wetland",
    label: "Wetland",
    color: "#14b8a6",
    overpassParts: ['nwr["natural"="wetland"]', 'nwr["wetland"]'],
    radiiM: [1500, 6000, 14000],
    maxMiles: 10,
    outMode: "geom",
  },
  {
    kind: "water",
    label: "Water body",
    color: "#0ea5e9",
    // Standing water only — not rivers/streams (those are flood-adjacency / waterways).
    overpassParts: [
      'nwr["natural"="water"]["water"!~"^(river|stream|canal|drain|ditch|swimming_pool|reflecting_pool|fountain|moat)$"]',
      'nwr["water"~"^(lake|pond|reservoir|basin|lagoon)$"]',
      'nwr["landuse"="reservoir"]',
    ],
    radiiM: [1500, 6000, 14000],
    maxMiles: 11,
    outMode: "geom",
  },
  {
    kind: "road",
    label: "Paved road",
    color: "#a16207",
    // Classified roads are treated as paved; local roads require an explicit paved surface.
    overpassParts: [
      'way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link)$"]["surface"!~"^(unpaved|gravel|dirt|earth|grass|sand|mud|ground|fine_gravel|pebblestone|wood|metal)$"]',
      'way["highway"~"^(residential|unclassified)$"]["surface"~"^(paved|asphalt|concrete|chipseal|paving_stones|sett|cobblestone)$"]',
    ],
    radiiM: [800, 3000, 10000],
    maxMiles: 7.5,
    outMode: "geom",
  },
  {
    kind: "power",
    label: "Power line",
    color: "#ca8a04",
    // Actual transmission/distribution lines only — not poles, substations, or transformers.
    overpassParts: ['way["power"~"^(line|minor_line)$"]'],
    radiiM: [1500, 6000, 14000],
    maxMiles: 11,
    outMode: "geom",
  },
  {
    kind: "town",
    label: "Town / services",
    color: "#b45309",
    overpassParts: ['node["place"~"^(city|town|village)$"]'],
    radiiM: [12000, 28000],
    maxMiles: 25,
    outMode: "center",
  },
  {
    kind: "school",
    label: "School",
    color: "#7c3aed",
    overpassParts: ['nwr["amenity"="school"]'],
    radiiM: [4000, 12000, 18000],
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
    ],
    // Emergency-capable clinics only if no hospital is mapped nearby.
    overpassPartsFallback: ['nwr["amenity"="clinic"]["emergency"="yes"]'],
    radiiM: [10000, 28000],
    maxMiles: 22,
    outMode: "center",
  },
];

const OVERPASS_ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://lz4.overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
];

/** Hard ceiling for one Closest chip search — UI must never spin past this. */
const NEARBY_SEARCH_DEADLINE_MS = 12_000;
const NEARBY_MIRROR_TIMEOUT_MS = 5_500;
const NEARBY_NOMINATIM_TIMEOUT_MS = 4_000;

const nearbyCache = new Map<string, NearbyHit[]>();
/** In-flight Overpass aborts when the user switches Closest chips. */
let nearbyOverpassAbort: AbortController | null = null;

function beginNearbyOverpass() {
  nearbyOverpassAbort?.abort();
  nearbyOverpassAbort = new AbortController();
  return nearbyOverpassAbort;
}

function abortError(message = "Aborted") {
  return new DOMException(message, "AbortError");
}

/** Reject (and optionally abort) when a Closest lookup outlives its budget. */
function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  label: string,
  abort?: () => void,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      abort?.();
      reject(new Error(`${label} timed out`));
    }, ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        window.clearTimeout(timer);
        reject(err);
      },
    );
  });
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
  // Narrow both args via runtime checks; callers treat a true result as valid lat/lon numbers.
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

function titleCaseTag(v: string) {
  return v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function isFloodTagged(el: OverpassElement) {
  const t = el.tags || {};
  return Boolean(
    t.flood_prone === "yes" ||
      t.hazard === "flood" ||
      t["flood:zone"] ||
      t.floodplain === "yes",
  );
}

/** Keep only OSM elements that legitimately satisfy the selected Closest option. */
function matchesNearbyKind(kind: NearbyKind, el: OverpassElement): boolean {
  const t = el.tags || {};
  switch (kind) {
    case "flood":
      return (
        isFloodTagged(el) || /^(river|stream|canal)$/.test(String(t.waterway || ""))
      );
    case "wetland":
      return t.natural === "wetland" || Boolean(t.wetland && t.wetland !== "no");
    case "water": {
      if (
        /^(river|stream|canal|drain|ditch|swimming_pool|reflecting_pool|fountain|moat)$/.test(
          String(t.water || ""),
        ) ||
        t.leisure === "swimming_pool" ||
        (t.landuse === "basin" && t.basin === "detention")
      ) {
        return false;
      }
      return (
        t.natural === "water" ||
        /^(lake|pond|reservoir|basin|lagoon)$/.test(String(t.water || "")) ||
        t.landuse === "reservoir"
      );
    }
    case "road": {
      const hw = String(t.highway || "");
      const surface = String(t.surface || "");
      if (
        /^(unpaved|gravel|dirt|earth|grass|sand|mud|ground|fine_gravel|pebblestone|wood|metal)$/.test(
          surface,
        )
      ) {
        return false;
      }
      if (
        /^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link)$/.test(
          hw,
        )
      ) {
        return true;
      }
      return (
        /^(residential|unclassified)$/.test(hw) &&
        /^(paved|asphalt|concrete|chipseal|paving_stones|sett|cobblestone)$/.test(surface)
      );
    }
    case "power":
      return el.type === "way" && /^(line|minor_line)$/.test(String(t.power || ""));
    case "town":
      return /^(city|town|village)$/.test(String(t.place || ""));
    case "school":
      return t.amenity === "school";
    case "hospital":
      return (
        t.amenity === "hospital" ||
        t.healthcare === "hospital" ||
        (t.amenity === "clinic" && t.emergency === "yes")
      );
    default:
      return false;
  }
}

function elementName(el: OverpassElement, kind: NearbyKind, fallback: string) {
  const t = el.tags || {};
  const named = t.name || t["name:en"] || t.brand;
  if (named) return named;

  switch (kind) {
    case "flood":
      if (isFloodTagged(el)) {
        return t["flood:zone"] ? `Flood zone ${t["flood:zone"]}` : "Mapped flood hazard";
      }
      return t.waterway ? `${titleCaseTag(t.waterway)} (flood-adjacency)` : fallback;
    case "wetland":
      return t.wetland && t.wetland !== "yes" ? `${titleCaseTag(t.wetland)} wetland` : "Wetland";
    case "water":
      return t.water ? titleCaseTag(t.water) : t.landuse === "reservoir" ? "Reservoir" : "Water body";
    case "road":
      if (t.ref) return t.ref;
      if (t.highway) return `${titleCaseTag(t.highway)} road`;
      return "Paved road";
    case "power":
      return t.operator ? `${t.operator} power line` : "Power line";
    case "town":
      return t.place ? titleCaseTag(t.place) : "Town";
    case "school":
      return "School";
    case "hospital":
      if (t.amenity === "clinic") return "Emergency clinic";
      return "Hospital";
    default:
      return fallback;
  }
}

function elementDetail(kind: NearbyKind, el: OverpassElement): string | undefined {
  const t = el.tags || {};
  if (kind === "flood") {
    return isFloodTagged(el)
      ? "Mapped flood hazard tag"
      : "Nearest mapped waterway (flood-adjacency proxy)";
  }
  if (kind === "hospital" && t.amenity === "clinic") {
    return "Emergency clinic (no hospital mapped closer)";
  }
  if (kind === "town" && t.place) {
    return `OSM place=${t.place}`;
  }
  if (kind === "road" && t.surface) {
    return `Surface ${t.surface}`;
  }
  if (kind === "power" && t.voltage) {
    return `${t.voltage} V`;
  }
  return undefined;
}

function closestOnElement(
  origin: [number, number],
  el: OverpassElement,
): { lat: number; lon: number; meters: number } | null {
  const geom = el.geometry;
  if (geom && geom.length >= 2) {
    let best: { lat: number; lon: number; meters: number } | null = null;
    for (let i = 0; i < geom.length - 1; i++) {
      const aLat = geom[i]?.lat;
      const aLon = geom[i]?.lon;
      const bLat = geom[i + 1]?.lat;
      const bLon = geom[i + 1]?.lon;
      if (!isValidLatLon(aLat, aLon) || !isValidLatLon(bLat, bLon)) continue;
      const hit = closestPointOnSegment(origin, [aLat, aLon], [bLat, bLon]);
      if (!best || hit.meters < best.meters) best = hit;
    }
    if (best) return best;
  }
  if (geom && geom.length === 1 && isValidLatLon(geom[0]?.lat, geom[0]?.lon)) {
    const lat = geom[0].lat;
    const lon = geom[0].lon;
    return { lat, lon, meters: haversineMeters(origin, [lat, lon]) };
  }
  const lat = el.lat ?? el.center?.lat;
  const lon = el.lon ?? el.center?.lon;
  if (!isValidLatLon(lat, lon)) return null;
  return { lat: Number(lat), lon: Number(lon), meters: haversineMeters(origin, [Number(lat), Number(lon)]) };
}

/** Degrees bbox (south, west, north, east) covering a radius — faster than Overpass `around`. */
function radiusToBbox(lat: number, lon: number, radiusM: number): [number, number, number, number] {
  const latDelta = radiusM / 111_320;
  const cos = Math.max(0.2, Math.cos((lat * Math.PI) / 180));
  const lonDelta = radiusM / (111_320 * cos);
  return [lat - latDelta, lon - lonDelta, lat + latDelta, lon + lonDelta];
}

async function overpassQuery(
  query: string,
  timeoutMs = NEARBY_MIRROR_TIMEOUT_MS,
  externalSignal?: AbortSignal,
): Promise<OverpassElement[]> {
  // Race public Overpass mirrors — prefer a non-empty payload; never hang past budget.
  const budget = Math.max(1500, Math.min(timeoutMs, NEARBY_MIRROR_TIMEOUT_MS));
  const controllers = OVERPASS_ENDPOINTS.map(() => new AbortController());
  const abortAll = () => controllers.forEach((c) => c.abort());
  const onExternalAbort = () => abortAll();
  if (externalSignal) {
    if (externalSignal.aborted) throw abortError();
    externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }

  const mirrorFetch = async (endpoint: string, i: number): Promise<OverpassElement[]> => {
    const res = await fetch(endpoint, {
      method: "POST",
      body: query,
      headers: { "Content-Type": "text/plain" },
      signal: controllers[i].signal,
    });
    if (!res.ok) throw new Error(`Overpass ${res.status}`);
    const data = (await res.json()) as { elements?: OverpassElement[] };
    return data.elements || [];
  };

  try {
    const settled = await withTimeout(
      Promise.allSettled(OVERPASS_ENDPOINTS.map((endpoint, i) => mirrorFetch(endpoint, i))),
      budget,
      "Overpass",
      abortAll,
    );
    abortAll();
    const fulfilled = settled
      .filter((r): r is PromiseFulfilledResult<OverpassElement[]> => r.status === "fulfilled")
      .map((r) => r.value);
    if (!fulfilled.length) {
      if (externalSignal?.aborted) throw abortError();
      throw new Error("Overpass unavailable");
    }
    const withHits = fulfilled.find((els) => els.length > 0);
    return withHits ?? fulfilled[0];
  } catch (e) {
    abortAll();
    if (externalSignal?.aborted) throw abortError();
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw e instanceof Error ? e : new Error("Overpass unavailable");
  } finally {
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }
}

/** Nominatim settlement search — city/town/village only (rejects hamlets/suburbs). */
async function nominatimSettlements(
  lat: number,
  lon: number,
  radiusM: number,
  signal: AbortSignal,
): Promise<OverpassElement[]> {
  const [s, w, n, e] = radiusToBbox(lat, lon, radiusM);
  const viewbox = `${w},${n},${e},${s}`;
  const queries = ["city", "town", "village"];
  const local = new AbortController();
  const onParentAbort = () => local.abort();
  if (signal.aborted) throw abortError();
  signal.addEventListener("abort", onParentAbort, { once: true });

  try {
    const rows = (
      await withTimeout(
        Promise.all(
          queries.map(async (q) => {
            const params = new URLSearchParams({
              format: "jsonv2",
              limit: "6",
              dedupe: "1",
              bounded: "1",
              q,
              featuretype: "settlement",
              viewbox,
            });
            const res = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, {
              signal: local.signal,
              headers: { Accept: "application/json" },
            });
            if (!res.ok) return [];
            return (await res.json()) as Array<{
              lat?: string;
              lon?: string;
              name?: string;
              display_name?: string;
              type?: string;
              class?: string;
              osm_type?: string;
              osm_id?: number;
            }>;
          }),
        ),
        NEARBY_NOMINATIM_TIMEOUT_MS,
        "Nominatim",
        () => local.abort(),
      )
    ).flat();

    const out: OverpassElement[] = [];
    const seen = new Set<string>();
    for (const row of rows) {
      const place = String(row.type || "").toLowerCase();
      if (!/^(city|town|village)$/.test(place)) continue;
      if (row.class && row.class !== "place") continue;
      const rLat = Number(row.lat);
      const rLon = Number(row.lon);
      if (!Number.isFinite(rLat) || !Number.isFinite(rLon)) continue;
      // Keep inside the requested radius (Nominatim viewbox can still spill).
      if (haversineMeters([lat, lon], [rLat, rLon]) > radiusM * 1.05) continue;
      const key = `${row.osm_type || "node"}/${row.osm_id ?? `${rLat}:${rLon}`}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        type: row.osm_type === "way" || row.osm_type === "relation" ? row.osm_type : "node",
        id: row.osm_id,
        lat: rLat,
        lon: rLon,
        tags: {
          name: row.name || row.display_name?.split(",")[0] || titleCaseTag(place),
          place,
        },
      });
    }
    return out;
  } finally {
    signal.removeEventListener("abort", onParentAbort);
  }
}

function pickTopHits(
  kind: NearbyKind,
  label: string,
  origin: [number, number],
  elements: OverpassElement[],
  limit = NEARBY_RESULT_LIMIT,
): NearbyHit[] {
  const byKey = new Map<string, NearbyHit & { floodTagged: boolean; rankBoost: number }>();

  for (const el of elements) {
    if (!matchesNearbyKind(kind, el)) continue;
    const pt = closestOnElement(origin, el);
    if (!pt || !isValidLatLon(pt.lat, pt.lon)) continue;
    const meters = haversineMeters(origin, [pt.lat, pt.lon]);
    if (!Number.isFinite(meters) || meters < 0) continue;

    const floodTagged = kind === "flood" && isFloodTagged(el);
    const name = elementName(el, kind, label);
    const detail = elementDetail(kind, el);
    // Prefer true hospitals over emergency clinics; true flood tags over waterway proxies.
    const rankBoost =
      kind === "hospital" && el.tags?.amenity === "clinic"
        ? 1
        : kind === "flood" && !floodTagged
          ? 1
          : 0;

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
      rankBoost,
    };
    const prev = byKey.get(key);
    if (!prev || meters < prev.meters) byKey.set(key, hit);
  }

  const ranked = [...byKey.values()].sort((a, b) => {
    if (a.rankBoost !== b.rankBoost) return a.rankBoost - b.rankBoost;
    return a.meters - b.meters;
  });

  const out: NearbyHit[] = [];
  for (const raw of ranked) {
    const { floodTagged: _flood, rankBoost: _boost, ...hit } = raw;
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
 * Hard-deadline capped so Closest chips never spin forever.
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

  // v3: kind-validated hits only (bust older caches that mixed poles/pools/proxies).
  const cacheKey = `v3:${kind}:${lat.toFixed(4)}:${lon.toFixed(4)}`;
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
  const startedAt = Date.now();
  const timeLeft = () => NEARBY_SEARCH_DEADLINE_MS - (Date.now() - startedAt);
  const pastDeadline = () => timeLeft() <= 0;

  const emit = (hits: NearbyHit[]) => {
    if (!hits.length || !onPartial) return;
    const verified = verifyNearbyHits(origin, hits);
    const sig = verified.map((h) => `${h.osmKey ?? h.name}:${Math.round(h.meters)}`).join("|");
    if (sig === lastPartialSig) return;
    lastPartialSig = sig;
    onPartial(verified);
  };

  const outClause = meta.outMode === "center" ? "out center tags qt;" : "out geom qt;";

  const runParts = async (parts: string[], radius: number, timeoutMs: number) => {
    const [s, w, n, e] = radiusToBbox(lat, lon, radius);
    const bbox = `(${s.toFixed(5)},${w.toFixed(5)},${n.toFixed(5)},${e.toFixed(5)})`;
    const union = parts.map((part) => `  ${part}${bbox};`).join("\n");
    const query = `
[out:json][timeout:${Math.max(5, Math.round(timeoutMs / 1000))}];
(
${union}
);
${outClause}
`.trim();
    return overpassQuery(query, timeoutMs, overpassCtl.signal);
  };

  // Progressive radii: surface the first hit ASAP, then keep going for up to 3.
  // Use bbox (not `around`) — same client-side distance filter, much less Overpass CPU.
  for (let i = 0; i < meta.radiiM.length; i++) {
    const radius = meta.radiiM[i];
    if (isCancelled?.() || overpassCtl.signal.aborted || pastDeadline()) break;
    try {
      const remaining = timeLeft();
      if (remaining < 800) break;
      const timeoutMs = Math.min(
        remaining - 200,
        i === 0
          ? kind === "town"
            ? 4500
            : meta.outMode === "geom"
              ? 5500
              : 5000
          : meta.outMode === "geom"
            ? 5500
            : 5000,
      );
      const nonEmpty = async (p: Promise<OverpassElement[]>) => {
        const els = await p;
        if (!els.length) throw new Error("empty");
        return els;
      };
      let elements: OverpassElement[] = [];
      if (kind === "town" && i === 0) {
        // Race Nominatim vs Overpass — each path has its own timeout so a hung
        // Nominatim can never keep Closest spinning forever.
        elements = await Promise.any([
          nonEmpty(nominatimSettlements(lat, lon, radius, overpassCtl.signal)),
          nonEmpty(runParts(meta.overpassParts, radius, timeoutMs)),
        ]).catch(async () => {
          if (isCancelled?.() || overpassCtl.signal.aborted || pastDeadline()) return [];
          const retryBudget = Math.min(3500, timeLeft() - 200);
          if (retryBudget < 800) return [];
          try {
            return await runParts(meta.overpassParts, radius, retryBudget);
          } catch {
            return [];
          }
        });
      } else {
        elements = await runParts(meta.overpassParts, radius, timeoutMs);
      }

      let hits = pickTopHits(kind, meta.label, origin, elements, NEARBY_RESULT_LIMIT).filter(
        (h) => h.meters / 1609.344 <= meta.maxMiles && h.meters <= radius * 1.15,
      );

      // Fallback parts only when the strict query produced no validated hits.
      if (
        !hits.length &&
        meta.overpassPartsFallback?.length &&
        !isCancelled?.() &&
        !overpassCtl.signal.aborted &&
        !pastDeadline()
      ) {
        try {
          const fallbackBudget = Math.min(timeoutMs, timeLeft() - 200);
          if (fallbackBudget >= 800) {
            const fallbackEls = await runParts(meta.overpassPartsFallback, radius, fallbackBudget);
            hits = pickTopHits(kind, meta.label, origin, fallbackEls, NEARBY_RESULT_LIMIT).filter(
              (h) => h.meters / 1609.344 <= meta.maxMiles && h.meters <= radius * 1.15,
            );
          }
        } catch {
          // keep empty — try next radius
        }
      }

      if (isCancelled?.() || overpassCtl.signal.aborted) break;
      if (hits.length) {
        // Merge with prior radii so expanding search can add #2/#3 without dropping #1.
        const byKey = new Map<string, NearbyHit>();
        for (const h of [...best, ...hits]) {
          const key = h.osmKey || `${h.lat.toFixed(5)},${h.lon.toFixed(5)}`;
          const prev = byKey.get(key);
          if (!prev || h.meters < prev.meters) byKey.set(key, h);
        }
        best = [...byKey.values()].sort((a, b) => a.meters - b.meters).slice(0, NEARBY_RESULT_LIMIT);
        emit(best);
        // Cache partial success so a remount doesn't wait again.
        nearbyCache.set(cacheKey, verifyNearbyHits(origin, best));
        const farthestKept = best[best.length - 1];
        if (best.length >= NEARBY_RESULT_LIMIT && farthestKept.meters <= radius * 1.05) break;
      }
    } catch (e) {
      if (isCancelled?.() || overpassCtl.signal.aborted || pastDeadline()) break;
      if (e instanceof DOMException && e.name === "AbortError") break;
      // Try next radius / endpoint path; do not invent a fake location.
      continue;
    }
  }

  // Ensure in-flight mirror work stops when we leave — even on empty miss.
  if (!overpassCtl.signal.aborted) overpassCtl.abort();

  best = verifyNearbyHits(origin, best);
  // Never cache empty misses — allow a real retry on the next click.
  if (!isCancelled?.() && best.length) {
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
    nearbyOverpassAbort?.abort();
    setNearbyLoading(false);
    setElevationFt(null);
    setZoom(null);
    {
      const pair = asLatLon(latitude, longitude);
      setCoords(pair ? formatCoordPair(pair[0], pair[1], 5) : "—");
    }
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
      let hits: NearbyHit[] = [];
      let timedOut = false;
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

      // Absolute UI watchdog — Closest must never show "Working" forever.
      const watchdog = window.setTimeout(() => {
        if (gen !== nearbySearchGen.current) return;
        timedOut = true;
        nearbyOverpassAbort?.abort();
        setNearbyLoading(false);
        if (!paintedKey) {
          setNearbyStatus(
            `Couldn’t find ${chip?.label?.toLowerCase() ?? "that"} nearby — tap again to retry`,
          );
        }
      }, NEARBY_SEARCH_DEADLINE_MS + 500);

      try {
        hits = await fetchNearby(
          kind,
          latitude!,
          longitude!,
          applyPartial,
          () => gen !== nearbySearchGen.current || timedOut,
        );
      } catch {
        hits = [];
      } finally {
        window.clearTimeout(watchdog);
        if (gen === nearbySearchGen.current) {
          setNearbyLoading(false);
        }
      }

      if (gen !== nearbySearchGen.current) return;
      if (!mapRef.current || !layersRef.current.nearby) return;

      if (!hits.length) {
        setNearbyHits([]);
        setNearbyHitIndex(0);
        nearbyHitIndexRef.current = 0;
        if (!paintedKey) {
          setNearbyStatus(
            timedOut
              ? `Couldn’t find ${chip?.label?.toLowerCase() ?? "that"} nearby — tap again to retry`
              : `No mapped ${chip?.label?.toLowerCase() ?? "feature"} within ~${chip?.maxMiles ?? 10} mi`,
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
    const pair = asLatLon(latitude, longitude);
    if (!pair) return;
    const text = formatCoordPair(pair[0], pair[1], 6);
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
