/** Client-side land pin helpers — keep markers on the parcel, not in the lake. */

function pointInRing(lon: number, lat: number, ring: number[][]): boolean {
  // Ray cast — ring is GeoJSON [lon, lat]
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    const intersect =
      yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi + 0.0) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

/**
 * Return [lat, lon] on the land for a GeoJSON polygon ring set.
 * Prefers a vertex-average when inside; otherwise nudges edge midpoints inward.
 */
export function landPinFromPolygon(rings: number[][][] | null | undefined): [number, number] | null {
  const ring = rings?.[0];
  if (!ring || ring.length < 3) return null;
  let sx = 0;
  let sy = 0;
  let n = 0;
  for (const p of ring) {
    if (!p || p.length < 2) continue;
    sx += Number(p[0]);
    sy += Number(p[1]);
    n += 1;
  }
  if (!n) return null;
  const avgLon = sx / n;
  const avgLat = sy / n;
  if (pointInRing(avgLon, avgLat, ring)) return [avgLat, avgLon];

  for (let i = 0; i < ring.length - 1; i++) {
    const a = ring[i];
    const b = ring[i + 1];
    if (!a || !b || a.length < 2 || b.length < 2) continue;
    const mx = (Number(a[0]) + Number(b[0])) / 2;
    const my = (Number(a[1]) + Number(b[1])) / 2;
    for (const t of [0.2, 0.35, 0.5]) {
      const nx = mx + (avgLon - mx) * t;
      const ny = my + (avgLat - my) * t;
      if (pointInRing(nx, ny, ring)) return [ny, nx];
    }
  }
  return [Number(ring[0][1]), Number(ring[0][0])];
}

/** Prefer an on-land polygon pin when the stored lat/lon falls outside the outline. */
export function resolveLandPin(
  latitude: number | null | undefined,
  longitude: number | null | undefined,
  polygon?: number[][][] | null,
): [number, number] | null {
  const fromPoly = landPinFromPolygon(polygon);
  if (
    latitude != null &&
    longitude != null &&
    Number.isFinite(latitude) &&
    Number.isFinite(longitude)
  ) {
    const ring = polygon?.[0];
    if (ring && ring.length >= 3 && !pointInRing(longitude, latitude, ring) && fromPoly) {
      return fromPoly;
    }
    return [latitude, longitude];
  }
  return fromPoly;
}
