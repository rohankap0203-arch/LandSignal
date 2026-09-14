import type { RadarRow } from "@/lib/api";

const KEY = "landsignal:search-session:v1";

export type SearchSessionSnapshot = {
  savedAt: number;
  form: unknown;
  rows: RadarRow[];
  hasSearched: boolean;
  status: string | null;
  scrollY?: number;
};

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Persist last search so LandSignal logo / leaving an intel report restores results. */
export function writeSearchSession(snapshot: Omit<SearchSessionSnapshot, "savedAt">): void {
  const s = storage();
  if (!s) return;
  try {
    const payload: SearchSessionSnapshot = {
      ...snapshot,
      savedAt: Date.now(),
      scrollY: typeof window !== "undefined" ? window.scrollY : snapshot.scrollY,
    };
    s.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* quota */
  }
}

export function readSearchSession(): SearchSessionSnapshot | null {
  const s = storage();
  if (!s) return null;
  try {
    const raw = s.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SearchSessionSnapshot;
    if (!parsed || typeof parsed !== "object") return null;
    if (Date.now() - Number(parsed.savedAt || 0) > 6 * 60 * 60 * 1000) return null;
    if (!parsed.hasSearched || !Array.isArray(parsed.rows)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearSearchSession(): void {
  const s = storage();
  if (!s) return;
  try {
    s.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
