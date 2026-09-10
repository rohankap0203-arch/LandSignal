import type { SearchMeta } from "@/lib/api";

/** Pull a 2-letter code from "FL", "FL — Florida", etc. */
export function stateCodeFromLabel(label: string | null | undefined): string | null {
  if (!label) return null;
  const raw = label.trim();
  if (!raw || raw.toUpperCase() === "ANY") return null;
  const left = raw.includes("—")
    ? raw.split("—", 1)[0].trim()
    : raw.includes("-")
      ? raw.split("-", 1)[0].trim()
      : raw;
  const code = left.slice(0, 2).toUpperCase();
  return /^[A-Z]{2}$/.test(code) ? code : null;
}

/** Friendly place name for copy — "Florida", not "FL — Florida". */
export function stateDisplayName(label: string | null | undefined): string | null {
  if (!label) return null;
  const raw = label.trim();
  if (!raw || raw.toUpperCase() === "ANY") return null;
  if (raw.includes("—")) {
    const name = raw.split("—")[1]?.trim();
    if (name) return name;
  }
  const code = stateCodeFromLabel(raw);
  if (code && STATE_NAMES[code]) return STATE_NAMES[code];
  return raw;
}

const STATE_NAMES: Record<string, string> = {
  AL: "Alabama",
  AK: "Alaska",
  AZ: "Arizona",
  AR: "Arkansas",
  CA: "California",
  CO: "Colorado",
  CT: "Connecticut",
  DE: "Delaware",
  FL: "Florida",
  GA: "Georgia",
  HI: "Hawaii",
  ID: "Idaho",
  IL: "Illinois",
  IN: "Indiana",
  IA: "Iowa",
  KS: "Kansas",
  KY: "Kentucky",
  LA: "Louisiana",
  ME: "Maine",
  MD: "Maryland",
  MA: "Massachusetts",
  MI: "Michigan",
  MN: "Minnesota",
  MS: "Mississippi",
  MO: "Missouri",
  MT: "Montana",
  NE: "Nebraska",
  NV: "Nevada",
  NH: "New Hampshire",
  NJ: "New Jersey",
  NM: "New Mexico",
  NY: "New York",
  NC: "North Carolina",
  ND: "North Dakota",
  OH: "Ohio",
  OK: "Oklahoma",
  OR: "Oregon",
  PA: "Pennsylvania",
  RI: "Rhode Island",
  SC: "South Carolina",
  SD: "South Dakota",
  TN: "Tennessee",
  TX: "Texas",
  UT: "Utah",
  VT: "Vermont",
  VA: "Virginia",
  WA: "Washington",
  WV: "West Virginia",
  WI: "Wisconsin",
  WY: "Wyoming",
  DC: "Washington, D.C.",
};

function formatList(names: string[]): string {
  if (names.length === 0) return "";
  if (names.length === 1) return names[0];
  if (names.length === 2) return `${names[0]} & ${names[1]}`;
  return `${names.slice(0, -1).join(", ")} & ${names[names.length - 1]}`;
}

function formatCount(n: number): string {
  return n.toLocaleString("en-US");
}

export type InventoryCaption = {
  /** Full line under Show matches */
  text: string;
  /** Numeric count currently reflected (for aria / animation keys) */
  count: number;
  /** Digits shown first, or null when still gathering */
  countLabel: string | null;
  /** Soft phrase after the number */
  detail: string;
};

/**
 * Natural marketplace copy for inventory under Show matches.
 * Avoids developer phrasing like "Live inventory" / "parcels indexed".
 */
export function inventoryCaption(
  meta: SearchMeta | null | undefined,
  selectedStateLabels: string[] | null | undefined,
): InventoryCaption | null {
  const total = meta?.inventory_count ?? 0;
  const byState = meta?.inventory_by_state || {};
  const selectedCodes = (selectedStateLabels || [])
    .map(stateCodeFromLabel)
    .filter((c): c is string => Boolean(c));

  if (selectedCodes.length > 0) {
    const count = selectedCodes.reduce((sum, code) => sum + Number(byState[code] || 0), 0);
    const names = selectedCodes.map((c) => STATE_NAMES[c] || c);
    const place = formatList(names);
    if (count <= 0) {
      const detail =
        selectedCodes.length === 1
          ? `Finding ${place} listings…`
          : `Finding listings in ${place}…`;
      return { count: 0, countLabel: null, detail, text: detail };
    }
    if (selectedCodes.length === 1) {
      const detail = `${place} listing${count === 1 ? "" : "s"} ready to scout`;
      return {
        count,
        countLabel: formatCount(count),
        detail,
        text: `${formatCount(count)} ${detail}`,
      };
    }
    const detail = `listings in ${place}`;
    return {
      count,
      countLabel: formatCount(count),
      detail,
      text: `${formatCount(count)} ${detail}`,
    };
  }

  if (total <= 0) {
    const detail = "Gathering listings across the country…";
    return { count: 0, countLabel: null, detail, text: detail };
  }

  const states = (meta?.inventory_states || []).filter(Boolean);
  const placeNames = states
    .map((s) => STATE_NAMES[s.toUpperCase()] || s)
    .slice(0, 4);
  const more = states.length > placeNames.length ? states.length - placeNames.length : 0;
  const place =
    placeNames.length === 0
      ? "the country"
      : more > 0
        ? `${formatList(placeNames)} +${more} more`
        : formatList(placeNames);

  const detail = `listings across ${place}`;
  return {
    count: total,
    countLabel: formatCount(total),
    detail,
    text: `${formatCount(total)} ${detail}`,
  };
}
