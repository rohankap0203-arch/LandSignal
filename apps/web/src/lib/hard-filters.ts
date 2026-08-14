import type { RadarRow, SearchFilters } from "@/lib/api";

/** Inclusive band check — unknown values fail when a bound is set. */
export function inHardBand(
  value: number | null | undefined,
  lo?: number | null,
  hi?: number | null,
): boolean {
  if (lo == null && hi == null) return true;
  if (value == null || !Number.isFinite(Number(value))) return false;
  const n = Number(value);
  if (lo != null && n < lo) return false;
  if (hi != null && n > hi) return false;
  return true;
}

function regionPasses(row: RadarRow, region?: string | null): boolean {
  if (!region || region === "Any") return true;
  const needle = region.toLowerCase().trim();
  if (!needle) return true;
  const hay = [row.county, row.state, row.location, row.region, row.property_name]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  if (hay.includes(needle)) return true;
  const token = needle.replace(/\s+county\b/g, "").trim();
  if (token && hay.includes(token)) return true;
  // Word overlap for macro labels ("Hill Country", "Phoenix metro…")
  const words = needle
    .replace(/[\/\-]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 3 && !["metro", "edge", "fringe", "corridor", "region", "area", "county"].includes(w));
  return words.some((w) => hay.includes(w));
}

/**
 * Hard gate for search results.
 * - State is always hard.
 * - When broaden=true (default), acres/price/region trust the API's never-empty cascade
 *   (API may widen ~35% or fall back inside the state) so legitimate land still shows.
 * - When broaden=false, acres/price/region are strict client-side too.
 * - Strategy + hold never drop rows.
 */
export function rowPassesHardFilters(row: RadarRow, filters: SearchFilters): boolean {
  const state = (filters.state || "").trim().toUpperCase();
  if (state && state !== "ANY") {
    if ((row.state || "").toUpperCase() !== state) return false;
  }
  const broaden = filters.broaden !== false;
  if (broaden) {
    // Trust API effective bands — only reject clear wrong-state rows.
    return true;
  }
  if (!regionPasses(row, filters.region)) return false;
  if (!inHardBand(row.acres, filters.min_acres, filters.max_acres)) return false;
  if (!inHardBand(row.ask, filters.min_price, filters.max_price)) return false;
  return true;
}

/** Drop every row that violates the active filter set. Never trust the API alone for state. */
export function enforceHardFilters(
  rows: RadarRow[],
  filters: SearchFilters,
): { kept: RadarRow[]; dropped: number } {
  const kept = rows.filter((r) => rowPassesHardFilters(r, filters));
  return { kept, dropped: rows.length - kept.length };
}

/** Human-readable summary of hard constraints currently applied. */
export function describeHardFilters(filters: SearchFilters): string {
  const bits: string[] = [];
  const state = (filters.state || "").trim().toUpperCase();
  if (state && state !== "ANY") bits.push(state);
  if (filters.region) bits.push(filters.region);
  if (filters.min_acres != null || filters.max_acres != null) {
    if (filters.min_acres != null && filters.max_acres != null) {
      bits.push(`${filters.min_acres}–${filters.max_acres} ac`);
    } else if (filters.min_acres != null) {
      bits.push(`${filters.min_acres}+ ac`);
    } else if (filters.max_acres != null) {
      bits.push(`≤ ${filters.max_acres} ac`);
    }
  }
  const money = (n: number) =>
    n >= 1_000_000
      ? `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
      : n >= 1000
        ? `$${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}k`
        : `$${n.toLocaleString()}`;
  if (filters.min_price != null || filters.max_price != null) {
    if (filters.min_price != null && filters.max_price != null) {
      bits.push(`${money(filters.min_price)}–${money(filters.max_price)}`);
    } else if (filters.max_price != null) {
      bits.push(`≤ ${money(filters.max_price)}`);
    } else if (filters.min_price != null) {
      bits.push(`${money(filters.min_price)}+`);
    }
  }
  // Strategy / hold are ranking-only — omit from hard-filter summary.
  return bits.length ? bits.join(" · ") : "Any filters";
}
