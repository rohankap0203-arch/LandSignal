import type { SearchMeta } from "@/lib/api";
import { SEARCH_META_FALLBACK } from "@/lib/search-meta-fallback";

const META_KEY = "landsignal:search-meta:v2";
const COUNT_KEY = "landsignal:inventory-count:v1";

type CachedMeta = {
  savedAt: number;
  meta: SearchMeta;
};

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Normalize API / cache payloads — never lose a known positive count. */
export function normalizeInventoryCount(raw: unknown): number {
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : 0;
}

export function readCachedInventoryCount(): number {
  const s = storage();
  if (!s) return 0;
  try {
    return normalizeInventoryCount(s.getItem(COUNT_KEY));
  } catch {
    return 0;
  }
}

export function writeCachedInventoryCount(count: number): void {
  const n = normalizeInventoryCount(count);
  if (!n) return;
  const s = storage();
  if (!s) return;
  try {
    s.setItem(COUNT_KEY, String(n));
  } catch {
    /* private mode / quota */
  }
}

/** Keep last good inventory meta across reloads and Land Alerts ↔ home. */
export function readCachedSearchMeta(): SearchMeta | null {
  const s = storage();
  if (!s) return null;
  try {
    const raw = s.getItem(META_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedMeta;
    if (!parsed?.meta || typeof parsed.meta !== "object") return null;
    const count =
      normalizeInventoryCount(parsed.meta.inventory_count) || readCachedInventoryCount();
    if (!count) return null;
    if (Date.now() - Number(parsed.savedAt || 0) > 24 * 60 * 60 * 1000) {
      // Meta catalogs can go stale; keep the count alone.
      writeCachedInventoryCount(count);
      return {
        ...SEARCH_META_FALLBACK,
        inventory_count: count,
      };
    }
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
    const count = readCachedInventoryCount();
    return count ? { ...SEARCH_META_FALLBACK, inventory_count: count } : null;
  }
}

export function writeCachedSearchMeta(meta: SearchMeta | null | undefined): void {
  if (!meta) return;
  const count = normalizeInventoryCount(meta.inventory_count);
  if (!count) return;
  writeCachedInventoryCount(count);
  const s = storage();
  if (!s) return;
  try {
    const payload: CachedMeta = {
      savedAt: Date.now(),
      meta: { ...meta, inventory_count: count },
    };
    s.setItem(META_KEY, JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}
