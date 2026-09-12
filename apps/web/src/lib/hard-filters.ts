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
  const words = needle
    .replace(/[\/\-]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 3 && !["metro", "edge", "fringe", "corridor", "region", "area", "county"].includes(w));
  return words.some((w) => hay.includes(w));
}

/**
 * Hard gate for search results — every active filter must match.
 * State, region, acres, and price are always enforced client-side.
 * Strategy / hold are enforced by the API; hold remains ranking-only.
 */
export function rowPassesHardFilters(row: RadarRow, filters: SearchFilters): boolean {
  const stateRaw = (filters.state || "").trim().toUpperCase();
  if (stateRaw && stateRaw !== "ANY" && stateRaw !== "ALL" && stateRaw !== "*") {
    const wanted = new Set(
      stateRaw
        .replace(/;/g, ",")
        .split(",")
        .map((s) => {
          let t = s.trim();
          if (!t || t === "ANY" || t === "ALL" || t === "*") return "";
          if (t.includes("—")) t = t.split("—", 1)[0].trim();
          if (t.includes("-") && t.length > 2) t = t.split("-", 1)[0].trim();
          return t.slice(0, 2);
        })
        .filter(Boolean),
    );
    if (wanted.size) {
      const rowState = (row.state || "").trim().toUpperCase().slice(0, 2);
      if (!rowState || !wanted.has(rowState)) return false;
    }
  }
  if (!regionPasses(row, filters.region)) return false;
  if (!inHardBand(row.acres, filters.min_acres, filters.max_acres)) return false;
  // Budget band uses the row's public/assessed ask the API already resolved.
  // Missing ask fails closed when a price bound is set.
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

const money = (n: number) =>
  n >= 1_000_000
    ? `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
    : n >= 1000
      ? `$${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}k`
      : `$${n.toLocaleString()}`;

function wantedStates(filters: SearchFilters): string[] {
  const stateRaw = (filters.state || "").trim().toUpperCase();
  if (!stateRaw || stateRaw === "ANY" || stateRaw === "ALL" || stateRaw === "*") return [];
  return stateRaw
    .replace(/;/g, ",")
    .split(",")
    .map((s) => {
      let t = s.trim();
      if (!t || t === "ANY" || t === "ALL" || t === "*") return "";
      if (t.includes("—")) t = t.split("—", 1)[0].trim();
      if (t.includes("-") && t.length > 2) t = t.split("-", 1)[0].trim();
      return t.slice(0, 2);
    })
    .filter(Boolean);
}

function acresLabel(filters: SearchFilters): string | null {
  if (filters.min_acres == null && filters.max_acres == null) return null;
  const fmt = (n: number) => n.toLocaleString();
  if (filters.min_acres != null && filters.max_acres != null) {
    return `${fmt(filters.min_acres)}–${fmt(filters.max_acres)} ac`;
  }
  if (filters.min_acres != null) return `${fmt(filters.min_acres)}+ ac`;
  return `≤ ${fmt(filters.max_acres!)} ac`;
}

function priceLabel(filters: SearchFilters): string | null {
  if (filters.min_price == null && filters.max_price == null) return null;
  if (filters.min_price != null && filters.max_price != null) {
    return `${money(filters.min_price)}–${money(filters.max_price)}`;
  }
  if (filters.max_price != null) return `≤ ${money(filters.max_price)}`;
  return `${money(filters.min_price!)}+`;
}

/** Human-readable summary of hard constraints currently applied. */
export function describeHardFilters(filters: SearchFilters): string {
  const bits: string[] = [];
  const states = wantedStates(filters);
  if (states.length) bits.push(states.join(", "));
  if (filters.region) bits.push(filters.region);
  const acres = acresLabel(filters);
  if (acres) bits.push(acres);
  const price = priceLabel(filters);
  if (price) bits.push(price);
  return bits.length ? bits.join(" · ") : "Any filters";
}

export type EmptySearchFactor = {
  label: string;
  value: string;
  role: "blocker" | "tight" | "context";
};

export type EmptySearchExplanation = {
  /** Clear reason in plain English */
  headline: string;
  /** One short supporting sentence */
  summary: string;
  factors: EmptySearchFactor[];
  /** Short clash label, e.g. "Acres + Price" */
  conflict?: string;
  /** At most one short tip */
  suggestions: string[];
};

type EmptyExplainOpts = {
  filters: SearchFilters;
  rawRows?: RadarRow[];
  keptCount: number;
  inventoryCount?: number | null;
  inventoryByState?: Record<string, number> | null;
};

function explain(
  headline: string,
  summary: string,
  conflict: string | undefined,
  factors: EmptySearchFactor[],
  tip?: string,
): EmptySearchExplanation {
  return {
    headline,
    summary,
    factors,
    conflict,
    suggestions: tip ? [tip] : [],
  };
}

/** Empty-result diagnosis with a clear reason, clash chips, and one tip. */
export function explainEmptySearch(opts: EmptyExplainOpts): EmptySearchExplanation {
  const { filters, keptCount } = opts;
  const rawRows = opts.rawRows || [];
  const inventoryCount = opts.inventoryCount ?? null;
  const inventoryByState = opts.inventoryByState || {};
  const states = wantedStates(filters);
  const region = (filters.region || "").trim();
  const acres = acresLabel(filters);
  const price = priceLabel(filters);

  const factors: EmptySearchFactor[] = [];
  if (states.length) factors.push({ label: "State", value: states.join(", "), role: "context" });
  if (region && region !== "Any") factors.push({ label: "Region", value: region, role: "context" });
  if (acres) factors.push({ label: "Acres", value: acres, role: "context" });
  if (price) factors.push({ label: "Price", value: price, role: "context" });

  const mark = (label: string, role: EmptySearchFactor["role"]) => {
    const hit = factors.find((f) => f.label === label);
    if (hit) hit.role = role;
  };
  const combo = factors.map((f) => f.value).join(" · ");

  if (inventoryCount === 0) {
    return explain(
      "No parcels are loaded yet",
      "Live inventory is empty, so every filter combo returns zero until refresh finishes.",
      "Inventory",
      factors,
      "Click Refresh live inventory, wait for the count to climb, then Show matches",
    );
  }

  if (states.length && inventoryCount != null && inventoryCount > 0) {
    const missing = states.filter((st) => !inventoryByState[st] || inventoryByState[st] <= 0);
    if (missing.length === states.length) {
      mark("State", "blocker");
      return explain(
        `No live parcels in ${missing.join(", ")}`,
        "That state is not in the current inventory book, so the other filters never got a chance to match.",
        "State",
        factors,
        "Pick a covered state, or Refresh live inventory",
      );
    }
  }

  if (rawRows.length > 0 && keptCount === 0) {
    let failState = 0;
    let failRegion = 0;
    let failAcres = 0;
    let failPrice = 0;
    for (const row of rawRows) {
      const stateOk = (() => {
        if (!states.length) return true;
        const rowState = (row.state || "").trim().toUpperCase().slice(0, 2);
        return Boolean(rowState && states.includes(rowState));
      })();
      if (!stateOk) {
        failState += 1;
        continue;
      }
      if (!regionPasses(row, filters.region)) failRegion += 1;
      if (!inHardBand(row.acres, filters.min_acres, filters.max_acres)) failAcres += 1;
      if (!inHardBand(row.ask, filters.min_price, filters.max_price)) failPrice += 1;
    }

    const hard: Array<{ label: string; n: number }> = [];
    if (failState) {
      hard.push({ label: "State", n: failState });
      mark("State", "blocker");
    }
    if (failRegion) {
      hard.push({ label: "Region", n: failRegion });
      mark("Region", "blocker");
    }
    if (failAcres) {
      hard.push({ label: "Acres", n: failAcres });
      mark("Acres", "blocker");
    }
    if (failPrice) {
      hard.push({ label: "Price", n: failPrice });
      mark("Price", "blocker");
    }
    const ranked = (
      hard.length ? hard : factors.filter((f) => f.role !== "context").map((f) => ({ label: f.label, n: 1 }))
    )
      .sort((a, b) => b.n - a.n)
      .slice(0, 2);
    const clash = ranked.map((b) => b.label).join(" + ") || "Filters";
    const tip = failPrice
      ? "Raise max price"
      : failAcres
        ? "Widen the acreage band"
        : failRegion
          ? "Set Region to Any"
          : failState
            ? "Add another state or set State to Any"
            : "Widen the tightest filter";
    return explain(
      `${clash} removed every result`,
      `${rawRows.length.toLocaleString()} parcels came back from search, but none survived ${clash.toLowerCase()}.`,
      clash,
      factors,
      tip,
    );
  }

  const coveredInState =
    states.length > 0 ? states.filter((st) => (inventoryByState[st] || 0) > 0) : [];
  const coveredNote = coveredInState.length
    ? coveredInState
        .map((st) => `${st} (${(inventoryByState[st] || 0).toLocaleString()})`)
        .join(", ")
    : "";
  const activeHard = factors.filter((f) =>
    ["State", "Region", "Acres", "Price"].includes(f.label),
  );

  if (activeHard.length >= 2) {
    activeHard.forEach((f) => {
      f.role = "tight";
    });
    if (acres && price) {
      mark("Acres", "blocker");
      mark("Price", "blocker");
    }
    if (states.length && region && region !== "Any") mark("Region", "blocker");
    const blockers = factors.filter((f) => f.role === "blocker");
    const clash = (blockers.length ? blockers : activeHard).map((f) => f.label).join(" + ");
    const tip =
      acres && price
        ? "Raise max price, or lower minimum acres"
        : region && region !== "Any"
          ? "Set Region to Any inside the same state"
          : "Clear the tightest filter, then Show matches again";
    return explain(
      `No parcels match ${clash}`,
      coveredNote
        ? `${combo} has no overlap in the live book (still has ${coveredNote}).`
        : `${combo} has no overlap in the live book.`,
      clash,
      factors,
      tip,
    );
  }

  if (activeHard.length === 1) {
    const only = activeHard[0];
    if (only.label === "State" && coveredInState.length) {
      return explain(
        `No matches inside ${states.join(", ")} for this search`,
        coveredNote
          ? `Inventory still has ${coveredNote}, but this exact query came back empty.`
          : "State inventory exists, but this exact query came back empty.",
        "Search miss",
        factors,
        "Loosen acres or price, then retry",
      );
    }
    mark(only.label, "blocker");
    return explain(
      `No parcels match ${only.label.toLowerCase()} = ${only.value}`,
      "That single hard filter wiped the result set against live inventory.",
      only.label,
      factors,
      `Widen or clear ${only.label}`,
    );
  }

  return explain(
    "No exact matches for these filters",
    "Live inventory has parcels, but none lined up with the current search.",
    undefined,
    factors,
    "Widen acres or raise max price",
  );
}
