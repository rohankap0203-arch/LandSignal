/** Pure geospatial helpers (no PostGIS). Units: meters / degrees as noted. */

const EARTH_RADIUS_M = 6371008.8;

export function toRadians(deg: number): number {
  return (deg * Math.PI) / 180;
}

export function haversineMeters(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const φ1 = toRadians(lat1);
  const φ2 = toRadians(lat2);
  const Δφ = toRadians(lat2 - lat1);
  const Δλ = toRadians(lon2 - lon1);
  const a =
    Math.sin(Δφ / 2) ** 2 +
    Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Shoelace area for ring in lon/lat degrees → approximate m² via equirectangular. */
export function ringAreaSquareMeters(ring: [number, number][]): number {
  if (ring.length < 4) return 0;
  let lat0 = 0;
  for (const [, lat] of ring) lat0 += lat;
  lat0 /= ring.length;
  const cosLat = Math.cos(toRadians(lat0));
  const mPerDegLat = (Math.PI / 180) * EARTH_RADIUS_M;
  const mPerDegLon = mPerDegLat * cosLat;
  let sum = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[i + 1];
    const X1 = x1 * mPerDegLon;
    const Y1 = y1 * mPerDegLat;
    const X2 = x2 * mPerDegLon;
    const Y2 = y2 * mPerDegLat;
    sum += X1 * Y2 - X2 * Y1;
  }
  return Math.abs(sum) / 2;
}

export function acresFromSquareMeters(m2: number): number {
  return m2 / 4046.8564224;
}

/** Polsby-Popper compactness proxy: 4πA / P² (1 = circle). */
export function compactnessScore(
  areaM2: number,
  perimeterM: number,
): number | null {
  if (areaM2 <= 0 || perimeterM <= 0) return null;
  return (4 * Math.PI * areaM2) / (perimeterM * perimeterM);
}

export function ringPerimeterMeters(ring: [number, number][]): number {
  let p = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    const [lon1, lat1] = ring[i];
    const [lon2, lat2] = ring[i + 1];
    p += haversineMeters(lat1, lon1, lat2, lon2);
  }
  return p;
}

export function buildableAcreageEstimate(input: {
  acreage: number;
  wetlandPct: number | null;
  floodPct: number | null;
  extremeSlopePctOfParcel: number | null;
}): number | null {
  if (input.acreage <= 0) return null;
  const wetland = input.wetlandPct ?? null;
  const flood = input.floodPct ?? null;
  const slope = input.extremeSlopePctOfParcel ?? null;
  // If critical inputs missing, do not invent buildable acres
  if (wetland == null || flood == null) return null;
  const constrained = Math.min(100, wetland + flood * 0.5 + (slope ?? 0));
  return input.acreage * (1 - constrained / 100);
}

export function usableAgAcreageEstimate(input: {
  acreage: number;
  wetlandPct: number | null;
  primeFarmlandPct: number | null;
  maxSlopePct: number | null;
}): number | null {
  if (input.acreage <= 0) return null;
  if (input.wetlandPct == null) return null;
  let usableFrac = 1 - input.wetlandPct / 100;
  if (input.maxSlopePct != null && input.maxSlopePct > 15) {
    usableFrac *= 0.7;
  }
  if (input.primeFarmlandPct != null) {
    usableFrac = Math.min(usableFrac, 0.2 + (input.primeFarmlandPct / 100) * 0.8);
  }
  return Math.max(0, input.acreage * usableFrac);
}
