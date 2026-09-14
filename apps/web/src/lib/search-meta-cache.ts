import type { SearchMeta } from "@/lib/api";
import { SEARCH_META_FALLBACK } from "@/lib/search-meta-fallback";

const KEY = "landsignal:search-meta:v1";

type CachedMeta = {
  savedAt: number;
  meta: SearchMeta;
};

/** Keep last good inventory meta across client navigations (Land Alerts → home). */
export function readCachedSearchMeta(): SearchMeta | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedMeta;
    if (!parsed?.meta || typeof parsed.meta !== "object") return null;
    const count = Number(parsed.meta.inventory_count || 0);
    // Ignore empty snapshots so we never paint "—" over a live book.
    if (!Number.isFinite(count) || count <= 0) return null;
    // 6h is plenty for a session; count is revalidated on mount anyway.
    if (Date.now() - Number(parsed.savedAt || 0) > 6 * 60 * 60 * 1000) return null;
    return {
      ...SEARCH_META_FALLBACK,
      ...parsed.meta,
      inventory_count: count,
      inventory_by_state:
        parsed.meta.inventory_by_state && Object.keys(parsed.meta.inventory_by_state).length
          ? parsed.meta.inventory_by_state
          : SEARCH_META_FALLBACK.inventory_by_state,
    };
  } catch {
    return null;
  }
}

export function writeCachedSearchMeta(meta: SearchMeta | null | undefined): void {
  if (typeof window === "undefined" || !meta) return;
  const count = Number(meta.inventory_count || 0);
  if (!Number.isFinite(count) || count <= 0) return;
  try {
    const payload: CachedMeta = {
      savedAt: Date.now(),
      meta: {
        ...meta,
        inventory_count: count,
      },
    };
    sessionStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* quota / private mode — ignore */
  }
}

/** Initial React state: cached live meta when present, else static fallback. */
export function initialSearchMeta(): SearchMeta {
  return readCachedSearchMeta() || SEARCH_META_FALLBACK;
}
