/** Approximate a square parcel footprint (GeoJSON ring) from a pin + acres. */

const METERS_PER_ACRE = 4046.8564224;

export function approxAcreagePolygon(
  latitude: number,
  longitude: number,
  acres: number,
): number[][][] | null {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  if (!Number.isFinite(acres) || acres <= 0 || acres > 100_000) return null;

  const sideM = Math.sqrt(acres * METERS_PER_ACRE);
  const half = sideM / 2;
  const dLat = half / 111_320;
  const cosLat = Math.cos((latitude * Math.PI) / 180);
  const dLon = half / Math.max(111_320 * Math.max(0.2, Math.abs(cosLat)), 1e-6);

  const ring: number[][] = [
    [longitude - dLon, latitude - dLat],
    [longitude + dLon, latitude - dLat],
    [longitude + dLon, latitude + dLat],
    [longitude - dLon, latitude + dLat],
    [longitude - dLon, latitude - dLat],
  ];
  return [ring];
}

export function resolveMapPolygon(
  polygon: number[][][] | null | undefined,
  latitude?: number | null,
  longitude?: number | null,
  acres?: number | null,
): { polygon: number[][][] | null; approximate: boolean } {
  if (polygon?.[0]?.length && polygon[0].length >= 3) {
    return { polygon, approximate: false };
  }
  if (latitude != null && longitude != null && acres != null && acres > 0) {
    const approx = approxAcreagePolygon(Number(latitude), Number(longitude), Number(acres));
    if (approx) return { polygon: approx, approximate: true };
  }
  return { polygon: null, approximate: false };
}

/** Conventional LandSignal / county-map orange outline */
export const PARCEL_OUTLINE = {
  color: "#d6a243",
  weight: 2.5,
  fillColor: "#d6a243",
  fillOpacity: 0.22,
} as const;
