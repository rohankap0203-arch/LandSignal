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
 * - State is always hard (supports multi-select "FL,TX").
 * - When broaden=true (default), acres/price/region trust the API's never-empty cascade
 *   (API may widen ~35% or fall back inside the state) so legitimate land still shows.
 * - When broaden=false, acres/price/region are strict client-side too.
 * - Strategy + hold never drop rows.
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
  if (filters.min_acres != null && filters.max_acres != null) {
    return `${filters.min_acres}–${filters.max_acres} ac`;
  }
  if (filters.min_acres != null) return `${filters.min_acres}+ ac`;
  return `≤ ${filters.max_acres} ac`;
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
  // Strategy / hold are ranking-only — omit from hard-filter summary.
  return bits.length ? bits.join(" · ") : "Any filters";
}

export type EmptySearchFactor = {
  /** Short chip label, e.g. "Acres" */
  label: string;
  /** Human value, e.g. "500–5,000 ac" */
  value: string;
  /** How this factor contributed to the empty set */
  role: "blocker" | "tight" | "context";
};

export type EmptySearchExplanation = {
  headline: string;
  summary: string;
  factors: EmptySearchFactor[];
  conflict?: string;
  suggestions: string[];
};

type EmptyExplainOpts = {
  filters: SearchFilters;
  /** Rows returned by the API before the client hard gate. */
  rawRows?: RadarRow[];
  keptCount: number;
  inventoryCount?: number | null;
  inventoryByState?: Record<string, number> | null;
};

/**
 * Build a plain-English diagnosis for an empty Scouted opportunities result.
 * Prefers measurable blockers (no inventory in state, hard-gate drops) over generic copy.
 */
export function explainEmptySearch(opts: EmptyExplainOpts): EmptySearchExplanation {
  const { filters, keptCount } = opts;
  const rawRows = opts.rawRows || [];
  const inventoryCount = opts.inventoryCount ?? null;
  const inventoryByState = opts.inventoryByState || {};
  const states = wantedStates(filters);
  const region = (filters.region || "").trim();
  const acres = acresLabel(filters);
  const price = priceLabel(filters);
  const strategies = (filters.strategy || "")
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s && s !== "Any");

  const factors: EmptySearchFactor[] = [];
  if (states.length) {
    factors.push({ label: "State", value: states.join(", "), role: "context" });
  }
  if (region && region !== "Any") {
    factors.push({ label: "Region", value: region, role: "context" });
  }
  if (acres) factors.push({ label: "Acres", value: acres, role: "context" });
  if (price) factors.push({ label: "Price", value: price, role: "context" });
  if (strategies.length) {
    factors.push({
      label: "Strategy",
      value: strategies.join(", "),
      role: "context",
    });
  }
  if (filters.hold_years != null) {
    factors.push({
      label: "Hold",
      value: `${filters.hold_years} yr`,
      role: "context",
    });
  }

  const suggestions: string[] = [];
  const mark = (label: string, role: EmptySearchFactor["role"]) => {
    const hit = factors.find((f) => f.label === label);
    if (hit) hit.role = role;
  };

  // 1) Empty live book
  if (inventoryCount === 0) {
    return {
      headline: "Live inventory is empty right now",
      summary:
        "There are no parcels loaded in this session yet, so every filter combination returns zero.",
      factors,
      conflict: "Inventory has not finished loading — filters never got a chance to match.",
      suggestions: [
        "Click Refresh live inventory and wait for the parcel count to climb",
        "Then tap Show matches again",
      ],
    };
  }

  // 2) Selected states missing from inventory
  if (states.length && inventoryCount != null && inventoryCount > 0) {
    const missing = states.filter((st) => !inventoryByState[st] || inventoryByState[st] <= 0);
    if (missing.length === states.length) {
      missing.forEach(() => mark("State", "blocker"));
      return {
        headline: "No live parcels for the state you picked",
        summary: `Live inventory does not currently include ${missing.join(", ")}. LandSignal never fills empty states with other states.`,
        factors,
        conflict: `${missing.join(", ")} × your other filters never ran — the state itself has no indexed parcels.`,
        suggestions: [
          "Reset State to Any, or pick a covered state from the list",
          "Refresh live inventory, then search again",
        ],
      };
    }
    if (missing.length) {
      mark("State", "tight");
      suggestions.push(
        `${missing.join(", ")} has no live parcels — drop it or refresh inventory`,
      );
    }
  }

  // 3) API returned candidates but client hard-gate wiped them
  if (rawRows.length > 0 && keptCount === 0) {
    // Client default broaden=true: only State is a hard drop. Region/acres/price
    // are informational "tight" signals unless broaden was turned off.
    const broaden = filters.broaden !== false;
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

    const blockers: Array<{ label: string; n: number; tip: string; hard: boolean }> = [];
    if (failState) {
      blockers.push({
        label: "State",
        n: failState,
        tip: "Results came back outside the state(s) you selected",
        hard: true,
      });
      mark("State", "blocker");
    }
    if (failRegion) {
      blockers.push({
        label: "Region",
        n: failRegion,
        tip: "Parcels did not match the region / county label",
        hard: !broaden,
      });
      mark("Region", broaden ? "tight" : "blocker");
    }
    if (failAcres) {
      blockers.push({
        label: "Acres",
        n: failAcres,
        tip: "Acreage fell outside your min/max band",
        hard: !broaden,
      });
      mark("Acres", broaden ? "tight" : "blocker");
    }
    if (failPrice) {
      blockers.push({
        label: "Price",
        n: failPrice,
        tip: "Asking price fell outside your min/max band",
        hard: !broaden,
      });
      mark("Price", broaden ? "tight" : "blocker");
    }

    const hardBlockers = blockers.filter((b) => b.hard).sort((a, b) => b.n - a.n);
    const ranked = (hardBlockers.length ? hardBlockers : blockers).sort((a, b) => b.n - a.n);
    const top = ranked.slice(0, 2);
    const conflict =
      top.length > 1
        ? `${top.map((b) => b.label).join(" + ")} together eliminated every candidate (${rawRows.length} came back from search).`
        : top.length === 1
          ? `${top[0].label} eliminated every candidate (${rawRows.length} came back from search).`
          : `${rawRows.length} parcels came back, but none survived your hard filters.`;

    if (failAcres) suggestions.push("Widen the acreage band (lower min or raise max)");
    if (failPrice) suggestions.push("Widen the price band (raise max price or clear min)");
    if (failRegion) suggestions.push("Set Region to Any, or pick a broader region label");
    if (failState) suggestions.push("Add another state, or set State to Any");
    if (strategies.length || filters.hold_years != null) {
      suggestions.push("Strategy and hold only re-rank — they do not hide parcels");
    }

    return {
      headline: "Filters conflicted with the parcels that came back",
      summary: top.map((b) => b.tip).join(". ") || "Hard filters removed every result.",
      factors,
      conflict,
      suggestions: suggestions.slice(0, 4),
    };
  }

  // 4) API itself returned nothing — diagnose from active filter combo
  const coveredInState =
    states.length > 0
      ? states
          .filter((st) => (inventoryByState[st] || 0) > 0)
          .map((st) => `${st} (${(inventoryByState[st] || 0).toLocaleString()})`)
      : [];
  const activeHard = factors.filter((f) =>
    ["State", "Region", "Acres", "Price"].includes(f.label),
  );
  if (activeHard.length >= 2) {
    activeHard.forEach((f) => {
      f.role = "tight";
    });
    const names = activeHard.map((f) => f.label);
    if (acres && price) {
      mark("Acres", "blocker");
      mark("Price", "blocker");
      suggestions.push("Raise max price, or lower minimum acres");
      suggestions.push("Search one band at a time (price OR acres) to see which unlocks results");
    }
    if (states.length && region && region !== "Any") {
      mark("Region", "blocker");
      suggestions.push("Try Region = Any inside the same state");
    }
    if (states.length && (acres || price)) {
      suggestions.push("Keep the state, clear price or acres, then narrow again");
    }
    const bookNote = coveredInState.length
      ? ` Live book still has ${coveredInState.join(", ")} — the combo above is the miss.`
      : "";
    return {
      headline: "This filter combination has no live matches",
      summary: `Nothing satisfied ${activeHard.map((f) => f.value).join(" · ")}.${bookNote}`,
      factors,
      conflict: `${names.join(" + ")} do not overlap in the current live book.`,
      suggestions: suggestions.length
        ? suggestions.slice(0, 4)
        : ["Reset the tightest filter to Any, then Show matches again"],
    };
  }

  if (activeHard.length === 1) {
    mark(activeHard[0].label, "blocker");
    return {
      headline: `No parcels match ${activeHard[0].label.toLowerCase()} = ${activeHard[0].value}`,
      summary: "That single hard filter wiped the result set against live inventory.",
      factors,
      conflict: `${activeHard[0].label} is the disconnect.`,
      suggestions: [
        `Clear or widen ${activeHard[0].label}`,
        "Or Reset to Any, then re-apply filters one at a time",
      ],
    };
  }

  return {
    headline: "No exact matches for these filters",
    summary:
      "Live inventory has parcels, but none lined up with the current search. LandSignal will not silently weaken your filters.",
    factors,
    suggestions: [
      "Expand acreage or raise max price",
      "Search a neighboring region or set Region to Any",
      "Reset to Any, then Show matches again",
    ],
  };
}
