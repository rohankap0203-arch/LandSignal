/**
 * Session cache for Land Alerts so Search ↔ Alerts navigation paints instantly
 * while the network revalidates in the background.
 */
const PROFILE_KEY = "landsignal:land-alerts-profile:v1";
const MATCHES_KEY = "landsignal:land-alerts-matches:v1";

function read<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { savedAt?: number; data?: T };
    if (!parsed?.data) return null;
    if (Date.now() - Number(parsed.savedAt || 0) > 30 * 60 * 1000) return null;
    return parsed.data;
  } catch {
    return null;
  }
}

function write<T>(key: string, data: T): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), data }));
  } catch {
    /* ignore */
  }
}

export function readCachedLandAlertProfile<T = unknown>(): T | null {
  return read<T>(PROFILE_KEY);
}

export function writeCachedLandAlertProfile<T>(data: T): void {
  write(PROFILE_KEY, data);
}

export function readCachedLandAlertMatches<T = unknown>(): T | null {
  return read<T>(MATCHES_KEY);
}

export function writeCachedLandAlertMatches<T>(data: T): void {
  write(MATCHES_KEY, data);
}
