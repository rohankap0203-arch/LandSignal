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

/** True only when the row satisfies every hard constraint the user selected. */
export function rowPassesHardFilters(row: RadarRow, filters: SearchFilters): boolean {
  const state = (filters.state || "").trim().toUpperCase();
  if (state && state !== "ANY") {
    if ((row.state || "").toUpperCase() !== state) return false;
  }
  if (!inHardBand(row.acres, filters.min_acres, filters.max_acres)) return false;
  // Budget filter uses ask (market / assessed land) — never model estimated_value.
  if (!inHardBand(row.ask, filters.min_price, filters.max_price)) return false;
  const strategy = (filters.strategy || "").trim().toUpperCase().replace(/\s+/g, "_");
  if (strategy && strategy !== "ANY" && strategy !== "CUSTOM") {
    const blob = [
      row.best_strategy,
      row.best_strategy_label,
      row.secondary_strategy_label,
    ]
      .filter(Boolean)
      .join(" ")
      .toUpperCase()
      .replace(/\s+/g, "_");
    if (!blob.includes(strategy)) return false;
  }
  return true;
}

/** Drop every row that violates the active filter set. Never trust the API alone. */
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
  if (filters.strategy && filters.strategy !== "Any") bits.push(filters.strategy);
  if (filters.region) bits.push(filters.region);
  return bits.length ? bits.join(" · ") : "Any filters";
}
