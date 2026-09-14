"use client";

import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { FilterField } from "@/components/filter-field";
import { HeroSelect } from "@/components/hero-select";
import { UsedByStrip } from "@/components/used-by-strip";
import { LandLoader } from "@/components/land-loader";
import { PropertyCard } from "@/components/property-card";
import {
  landsignalApi,
  type RadarRow,
  type SearchFilters,
  type SearchMeta,
} from "@/lib/api";
import { describeHardFilters, enforceHardFilters, explainEmptySearch, type EmptySearchExplanation } from "@/lib/hard-filters";
import { formatListingsLabel } from "@/lib/listings-label";
import { readCachedSearchMeta, writeCachedSearchMeta } from "@/lib/search-meta-cache";
import { SEARCH_META_FALLBACK } from "@/lib/search-meta-fallback";
import { readSearchSession, writeSearchSession } from "@/lib/search-session";

type PriceUnit = "K" | "M";

type FormState = {
  states: string[];
  region: string;
  regionCustom: string;
  pricePreset: string;
  priceMin: string;
  priceMax: string;
  priceMinUnit: PriceUnit;
  priceMaxUnit: PriceUnit;
  acrePreset: string;
  acreMin: string;
  acreMax: string;
  strategies: string[];
  strategyCustom: string;
  holdYears: string;
  holdCustom: string;
  sort: string;
};

const DEFAULT_FORM: FormState = {
  states: ["Any"],
  region: "Any",
  regionCustom: "",
  pricePreset: "Any",
  priceMin: "",
  priceMax: "",
  priceMinUnit: "K",
  priceMaxUnit: "K",
  acrePreset: "Any",
  acreMin: "",
  acreMax: "",
  strategies: ["Any"],
  strategyCustom: "",
  holdYears: "Any",
  holdCustom: "",
  sort: "score_desc",
};

/** Hold-period presets — ranking hint only (plus custom). */
const HOLD_YEAR_OPTIONS: Array<string | number> = [
  "Any",
  1,
  3,
  5,
  10,
  15,
  25,
  40,
  60,
  80,
  100,
];

function stateCode(label: string): string {
  if (!label || label === "Any") return "Any";
  return label.split("—")[0]?.trim().toUpperCase() || label;
}

function selectedStates(labels: string[]): string[] {
  return labels.map(stateCode).filter((c) => c && c !== "Any");
}

type StateListingRow = { code: string; name: string; count: number };

function stateListingRows(meta: SearchMeta | null | undefined): StateListingRow[] {
  const byState = meta?.inventory_by_state || {};
  // Only list states that actually have inventory — never paint the full catalog as 0s.
  const liveCodes = Object.keys(byState).filter((code) => Number(byState[code]) > 0);
  if (!liveCodes.length) return [];

  const nameByCode = new Map<string, string>();
  for (const label of meta?.states || []) {
    if (!label || label === "Any") continue;
    const code = stateCode(label);
    const name = label.includes("—")
      ? label.split("—").slice(1).join("—").trim()
      : label;
    if (code && code !== "Any") nameByCode.set(code, name || code);
  }

  // Prefer catalog order when available, but only for states with live listings.
  const catalog = (meta?.state_codes || [])
    .map((c) => stateCode(String(c || "")))
    .filter((c) => c && c !== "Any");
  const ordered = catalog.length
    ? catalog.filter((c) => liveCodes.includes(c))
    : liveCodes.sort((a, b) => a.localeCompare(b));

  return ordered
    .map((code) => ({
      code,
      name: nameByCode.get(code) || code,
      count: Number(byState[code] || 0),
    }))
    .filter((row) => row.count > 0)
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Digits + optional single decimal only. */
function sanitizeDecimal(raw: string): string {
  let out = String(raw).replace(/[^\d.]/g, "");
  const firstDot = out.indexOf(".");
  if (firstDot !== -1) {
    out = out.slice(0, firstDot + 1) + out.slice(firstDot + 1).replace(/\./g, "");
  }
  return out;
}

/** Whole numbers only, capped. */
function sanitizeInt(raw: string, max: number): string {
  const digits = String(raw).replace(/\D/g, "");
  if (!digits) return "";
  const n = Number(digits);
  if (!Number.isFinite(n)) return "";
  return String(Math.min(max, n));
}

function parseUnitMoney(v: string, unit: PriceUnit): number | undefined {
  const n = Number(sanitizeDecimal(v));
  if (!Number.isFinite(n) || n < 0 || v.trim() === "") return undefined;
  return n * (unit === "M" ? 1_000_000 : 1_000);
}

function parseAcres(v: string): number | undefined {
  const n = Number(sanitizeDecimal(v));
  return Number.isFinite(n) && n >= 0 && v.trim() !== "" ? n : undefined;
}

function UnitToggle({
  value,
  onChange,
  ariaLabel,
}: {
  value: PriceUnit;
  onChange: (u: PriceUnit) => void;
  ariaLabel: string;
}) {
  return (
    <div className="filter-unit-toggle" role="group" aria-label={ariaLabel}>
      <button
        type="button"
        className={value === "K" ? "is-active" : undefined}
        aria-pressed={value === "K"}
        onClick={() => onChange("K")}
      >
        K
      </button>
      <button
        type="button"
        className={value === "M" ? "is-active" : undefined}
        aria-pressed={value === "M"}
        onClick={() => onChange("M")}
      >
        M
      </button>
    </div>
  );
}

export default function SearchPage() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  // Seed full catalogs immediately so phones never flash/stuck on only "Any".
  // Hydrate from session cache so Land Alerts → home never flashes "—" / empty counts.
  const [meta, setMeta] = useState<SearchMeta>(SEARCH_META_FALLBACK);
  const [rows, setRows] = useState<RadarRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [emptyExplanation, setEmptyExplanation] = useState<EmptySearchExplanation | null>(null);
  const [inventoryBreakdownOpen, setInventoryBreakdownOpen] = useState(false);
  const inventoryBreakdownRef = useRef<HTMLDivElement | null>(null);

  // Paint cached inventory before first paint after remount (Land Alerts → home).
  // useLayoutEffect avoids a "—" flash without SSR/sessionStorage mismatches.
  useLayoutEffect(() => {
    const cached = readCachedSearchMeta();
    if (cached) setMeta(cached);
  }, []);

  // Restore last Show matches results when returning from an intelligence report via the logo.
  const skipSearchScrollRef = useRef(false);
  useLayoutEffect(() => {
    const snap = readSearchSession();
    if (!snap) return;
    const formSnap = snap.form as FormState | null;
    if (!formSnap || typeof formSnap !== "object") return;
    skipSearchScrollRef.current = true;
    setForm({ ...DEFAULT_FORM, ...formSnap });
    setRows(snap.rows);
    setHasSearched(true);
    setStatus(snap.status);
    const y = Number(snap.scrollY);
    if (Number.isFinite(y) && y > 0) {
      requestAnimationFrame(() => {
        window.scrollTo({ top: y, behavior: "auto" });
      });
    }
  }, []);


  const inventoryStateRows = useMemo(() => stateListingRows(meta), [meta]);

  useEffect(() => {
    if (!inventoryBreakdownOpen) return;
    const onDocMouseDown = (event: MouseEvent) => {
      const root = inventoryBreakdownRef.current;
      const target = event.target;
      if (!(target instanceof Node) || !root) return;
      // Scrollbar / overlay hits can report targets outside the scrollport;
      // also accept closest() so inside interactions never dismiss the menu.
      if (root.contains(target)) return;
      if (target instanceof Element && target.closest(".filter-inventory-breakdown")) return;
      setInventoryBreakdownOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setInventoryBreakdownOpen(false);
    };
    // Bubble mousedown (not capture pointerup) so scrolling/dragging inside stays open.
    const timer = window.setTimeout(() => {
      document.addEventListener("mousedown", onDocMouseDown);
      document.addEventListener("keydown", onKey);
    }, 0);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [inventoryBreakdownOpen]);

  const regionOptions = useMemo(() => {
    const codes = selectedStates(form.states);
    const catalogs = meta?.regions_by_state || {};
    const merged = ["Any"];
    const pushUnique = (r: string) => {
      if (r && r !== "Any" && !merged.includes(r)) merged.push(r);
    };

    if (!codes.length) {
      for (const r of catalogs.Any || []) pushUnique(r);
    } else {
      for (const code of codes) {
        for (const r of catalogs[code] || []) pushUnique(r);
      }
      const live = (meta?.regions || []).filter((r) => {
        if (!r || r === "Any") return false;
        return codes.some(
          (code) =>
            r.endsWith(`, ${code}`) ||
            r.endsWith(` ${code}`) ||
            r.toUpperCase().includes(`, ${code}`),
        );
      });
      for (const r of live) pushUnique(r);
    }
    if (!merged.includes("Type a region…")) merged.push("Type a region…");
    return merged;
  }, [form.states, meta]);

  const filtersFromForm = useCallback(
    (f: FormState): SearchFilters => {
      const price = meta?.price_presets.find((p) => p.label === f.pricePreset);
      const acres = meta?.acre_presets.find((p) => p.label === f.acrePreset);
      const customPrice = f.pricePreset.toLowerCase().includes("custom");
      const customAcres = f.acrePreset.toLowerCase().includes("custom");
      const region =
        f.regionCustom.trim() ||
        (f.region.startsWith("Type a") || f.region === "Any" ? undefined : f.region);

      let hold: number | undefined;
      if (f.holdYears === "__custom__") {
        const n = Number(sanitizeInt(f.holdCustom, 500));
        if (Number.isFinite(n) && n >= 1) hold = Math.min(500, n);
      } else if (f.holdYears !== "Any") {
        hold = Number(f.holdYears);
      }

      const pickedStrategies = (f.strategies || []).filter((s) => s && s !== "Any");
      const strategyParts: string[] = [];
      for (const s of pickedStrategies) {
        if (s === "CUSTOM") {
          const custom = f.strategyCustom.trim();
          if (custom) strategyParts.push(custom);
        } else {
          strategyParts.push(s);
        }
      }
      const strategy = strategyParts.length ? strategyParts.join(",") : undefined;

      const stateCodes = selectedStates(f.states);
      const state = stateCodes.length ? stateCodes.join(",") : undefined;

      return {
        state,
        region,
        min_price: customPrice ? parseUnitMoney(f.priceMin, f.priceMinUnit) : price?.min ?? undefined,
        max_price: customPrice ? parseUnitMoney(f.priceMax, f.priceMaxUnit) : price?.max ?? undefined,
        min_acres: customAcres ? parseAcres(f.acreMin) : acres?.min ?? undefined,
        max_acres: customAcres ? parseAcres(f.acreMax) : acres?.max ?? undefined,
        strategy,
        hold_years: Number.isFinite(hold as number) ? hold : undefined,
        // Always include unpriced federal / surplus — no UI filter for this
        unpriced_mode: "include",
        include_unpriced: true,
        sort: f.sort,
        // Strict mode: every selected filter must match. Empty set stays empty.
        broaden: false,
      };
    },
    [meta],
  );

  const scrollToUsedByStrip = useCallback((behavior: ScrollBehavior = "smooth") => {
    const usedBy = document.querySelector(".used-by-strip") as HTMLElement | null;
    if (!usedBy) return;
    const header = document.querySelector(".shell-header") as HTMLElement | null;
    const headerH = header?.getBoundingClientRect().height ?? 0;
    // Bring "Used by buyers on" into view under the sticky header while matches load.
    const top = usedBy.getBoundingClientRect().top + window.scrollY - headerH - 8;
    const scroller = document.scrollingElement || document.documentElement;
    scroller.scrollTo({ top: Math.max(0, top), behavior });
  }, []);

  const scrollToScoutedOpportunities = useCallback((behavior: ScrollBehavior = "smooth") => {
    const heading = document.querySelector("#search-results h2") as HTMLElement | null;
    if (!heading) return;
    const header = document.querySelector(".shell-header") as HTMLElement | null;
    const headerH = header?.getBoundingClientRect().height ?? 0;
    // Sit just under the sticky header so "Scouted opportunities" is the first thing seen.
    const top = heading.getBoundingClientRect().top + window.scrollY - headerH - 4;
    const scroller = document.scrollingElement || document.documentElement;
    scroller.scrollTo({ top: Math.max(0, top), behavior });
  }, []);

  const runSearch = useCallback(
    async (override?: FormState) => {
      setLoading(true);
      setError(null);
      setHasSearched(true);
      setRows([]);
      setEmptyExplanation(null);
      // Step 1: on click, scroll so Used-by logos are on screen while Surveying matches loads.
      requestAnimationFrame(() => {
        scrollToUsedByStrip("smooth");
      });
      try {
        const active = override ?? form;
        const filters = filtersFromForm(active);
        const data = await landsignalApi.radar(filters);
        if (!Array.isArray(data)) {
          throw new Error("Search returned an unexpected response. Try Show matches again.");
        }
        // Client hard gate for state / region / acres / price — drop anything outside the band.
        const { kept, dropped } = enforceHardFilters(data, filters);
        setRows(kept);
        // Stop the Surveying spinner as soon as matches arrive — meta refresh is secondary.
        setLoading(false);
        const metaNow = await landsignalApi.searchMeta().catch(() => null);
        if (metaNow) {
          const mergedMeta = {
            ...SEARCH_META_FALLBACK,
            ...metaNow,
            states: metaNow.states?.length ? metaNow.states : SEARCH_META_FALLBACK.states,
          };
          writeCachedSearchMeta(mergedMeta);
          setMeta(mergedMeta);
        }
        const total = metaNow?.inventory_count ?? kept.length;
        const filterLabel = describeHardFilters(filters);
        if (kept.length) {
          setEmptyExplanation(null);
          setStatus(
            `Filters: ${filterLabel} · showing ${kept.length.toLocaleString()} matches` +
              (dropped ? ` · ${dropped} out-of-band dropped` : "") +
              ` · ${total.toLocaleString()} live parcels indexed`,
          );
        } else {
          const why = explainEmptySearch({
            filters,
            rawRows: data,
            keptCount: kept.length,
            inventoryCount: metaNow?.inventory_count ?? meta.inventory_count ?? null,
            inventoryByState: metaNow?.inventory_by_state ?? meta.inventory_by_state ?? null,
          });
          setEmptyExplanation(why);
          setStatus(
            why.conflict
              ? `${why.conflict}: ${why.headline}`
              : why.headline || `No match for ${filterLabel}`,
          );
        }
      } catch (e) {
        const raw = e instanceof Error ? e.message : "Search failed";
        const friendly = /busy|unreachable|catching up with live inventory|ECONNREFUSED|fetch failed|not reachable|not responding/i.test(
          raw,
        )
          ? "Search is catching up with live inventory. Tap Show matches again in a moment."
          : /Failed to fetch|NetworkError|Load failed/i.test(raw)
            ? "Search failed to load results (network). Tap Show matches again."
            : /Internal Server Error/i.test(raw)
              ? "Search hit a server error. Tap Show matches again — if it keeps failing, click Refresh live inventory first."
              : raw.length > 280
                ? "Search failed. Tap Show matches again — if it keeps failing, try Reset to Any first."
                : raw;
        setError(friendly);
        setStatus(null);
        setEmptyExplanation(null);
      } finally {
        setLoading(false);
      }
    },
    [filtersFromForm, form, scrollToUsedByStrip],
  );

  // Keep search results so the LandSignal logo can restore them after an intel report.
  useEffect(() => {
    if (!hasSearched || loading) return;
    writeSearchSession({
      form,
      rows,
      hasSearched: true,
      status,
    });
  }, [hasSearched, loading, form, rows, status]);

  // Step 2: once per finished search, bring "Scouted opportunities" under the sticky header.
  // Do not re-run on later rows.length noise — that fought users scrolling the filters/results.
  const searchScrollGen = useRef(0);
  useEffect(() => {
    if (!hasSearched || loading) return;
    if (skipSearchScrollRef.current) {
      skipSearchScrollRef.current = false;
      return;
    }
    const gen = ++searchScrollGen.current;
    const t1 = window.setTimeout(() => {
      if (searchScrollGen.current !== gen) return;
      scrollToScoutedOpportunities("smooth");
    }, 50);
    const t2 = window.setTimeout(() => {
      if (searchScrollGen.current !== gen) return;
      const heading = document.querySelector("#search-results h2") as HTMLElement | null;
      const header = document.querySelector(".shell-header") as HTMLElement | null;
      if (!heading) return;
      const headerH = header?.getBoundingClientRect().height ?? 0;
      const delta = heading.getBoundingClientRect().top - headerH - 4;
      if (Math.abs(delta) > 10) {
        const scroller = document.scrollingElement || document.documentElement;
        scroller.scrollTo({ top: Math.max(0, window.scrollY + delta), behavior: "auto" });
      }
    }, 420);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
    // Intentionally omit rows.length — only when a search finishes (loading → false).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasSearched, loading, scrollToScoutedOpportunities]);

  useEffect(() => {
    // Stay naturally connected: poll meta hard at first, auto-start discover if empty.
    let cancelled = false;
    let discoverKicked = false;
    let tick: number | null = null;

    const applyMeta = (live: SearchMeta) => {
      if (cancelled || !live) return;
      setMeta((prev) => {
        const nextCount = Number(live.inventory_count ?? (live as { inventory_total?: number }).inventory_total ?? prev.inventory_count ?? 0) || Number(prev.inventory_count || 0);
        const next: SearchMeta = {
          ...SEARCH_META_FALLBACK,
          ...prev,
          ...live,
          // Never flash the listing count back to 0 during a transient meta miss.
          inventory_count: nextCount,
          inventory_by_state:
            live.inventory_by_state && Object.keys(live.inventory_by_state).length
              ? live.inventory_by_state
              : prev.inventory_by_state,
          states: live.states?.length ? live.states : prev.states?.length ? prev.states : SEARCH_META_FALLBACK.states,
          strategies: live.strategies?.length
            ? live.strategies
            : prev.strategies?.length
              ? prev.strategies
              : SEARCH_META_FALLBACK.strategies,
          price_presets: live.price_presets?.length
            ? live.price_presets
            : prev.price_presets?.length
              ? prev.price_presets
              : SEARCH_META_FALLBACK.price_presets,
          acre_presets: live.acre_presets?.length
            ? live.acre_presets
            : prev.acre_presets?.length
              ? prev.acre_presets
              : SEARCH_META_FALLBACK.acre_presets,
          hold_years: live.hold_years?.length
            ? live.hold_years
            : prev.hold_years?.length
              ? prev.hold_years
              : SEARCH_META_FALLBACK.hold_years,
        };
        writeCachedSearchMeta(next);
        return next;
      });
      // Prefer live count, but fall back to cached inventory so remounting home
      // after Land Alerts does not look empty.
      const count = Number(live.inventory_count || 0);
      const cached = Number(readCachedSearchMeta()?.inventory_count || 0);
      const known = count > 0 ? count : cached;
      // Never auto-kick a nationwide discover from a zero/unknown count — that OOMs
      // the API mid-restore and leaves the listings caption stuck on a dash.
      // Only deepen when we *know* the book is thin but real.
      if (!discoverKicked && known > 0 && known < 50_000) {
        discoverKicked = true;
        void landsignalApi.discover(750000, 0.1, false, undefined, true).catch(() => {
          discoverKicked = false;
        });
      }
    };

    const refresh = () =>
      landsignalApi
        .searchMeta()
        .then(applyMeta)
        .catch(() => {
          // Keep the last good listing count visible.
        });

    void refresh();
    let n = 0;
    tick = window.setInterval(() => {
      if (cancelled) return;
      n += 1;
      // Fast for ~30s, then every 15s — avoid hammering meta during discover.
      if (n <= 10 || n % 5 === 0) void refresh();
    }, 3000);

    return () => {
      cancelled = true;
      if (tick != null) window.clearInterval(tick);
    };
  }, []);

  async function scanFresh() {
    setScanning(true);
    setStatus("Inventory refresh started in the background. Click Show matches when you want results.");
    try {
      await landsignalApi.discover(750000, 0.1, false, undefined, true);
      const nextMeta = await landsignalApi.searchMeta();
      const merged = {
        ...SEARCH_META_FALLBACK,
        ...nextMeta,
        states: nextMeta.states?.length ? nextMeta.states : SEARCH_META_FALLBACK.states,
      };
      writeCachedSearchMeta(merged);
      setMeta(merged);
      setStatus(
        `Refreshing listings · ${nextMeta.inventory_count?.toLocaleString() ?? 0}. Tap Show matches anytime.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  const sortedRows = useMemo(() => {
    const list = [...rows];
    const key = form.sort;
    const num = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0);
    const pid = (r: RadarRow) => String(r.parcel_id || "");
    // Keep secondary keys aligned with the API — parcel_id last so ties stay stable.
    list.sort((a, b) => {
      let cmp = 0;
      switch (key) {
        case "score_desc":
          // Align with API: opportunity → confidence → risk → discount → fit → id
          cmp =
            num(b.opportunity) - num(a.opportunity) ||
            num(b.confidence) - num(a.confidence) ||
            num(a.risk) - num(b.risk) ||
            num(a.discount_pct ?? 0) - num(b.discount_pct ?? 0) ||
            num(b.fit_score) - num(a.fit_score);
          break;
        case "risk_asc":
          cmp = num(a.risk) - num(b.risk) || num(b.fit_score) - num(a.fit_score);
          break;
        case "confidence_desc":
          cmp = num(b.confidence) - num(a.confidence) || num(b.opportunity) - num(a.opportunity);
          break;
        case "price_asc":
          cmp =
            (a.ask ?? Number.POSITIVE_INFINITY) - (b.ask ?? Number.POSITIVE_INFINITY);
          break;
        case "acres_desc":
          cmp = num(b.acres) - num(a.acres);
          break;
        case "discount_asc":
          cmp = num(a.discount_pct ?? 999) - num(b.discount_pct ?? 999);
          break;
        case "fit_desc":
        default:
          cmp =
            num(b.fit_score ?? b.opportunity) - num(a.fit_score ?? a.opportunity) ||
            num(b.opportunity) - num(a.opportunity);
          break;
      }
      return cmp || pid(a).localeCompare(pid(b));
    });
    return list;
  }, [rows, form.sort]);

  const inventoryStates = meta?.inventory_states || [];
  const strategyHasCustom = form.strategies.includes("CUSTOM");

  return (
    <div>
      <section className="hero-search">
        <div>
          <div className="hero-brand-row">
            <div className="hero-brand-mark">LandSignal</div>
            <div
              className="hero-live"
              title="Live public GIS / BLM inventory indexed in this session"
            >
              <span className="hero-live-dot" aria-hidden />
              <span>Live</span>
            </div>
          </div>
          <h1>Scout the best land buys in the country</h1>
        </div>

        <div className="filter-grid filter-grid-12">
          <FilterField label="State">
            <HeroSelect
              multi
              ariaLabel="State"
              values={form.states}
              options={(meta.states?.length ? meta.states : SEARCH_META_FALLBACK.states).map((s) => ({
                value: s,
                label: s,
              }))}
              onChange={(v) => setForm((f) => ({ ...f, states: v, region: "Any", regionCustom: "" }))}
            />
          </FilterField>

          <FilterField label="Region">
            <HeroSelect
              ariaLabel="Region"
              value={form.region}
              options={regionOptions.map((s) => ({ value: s, label: s }))}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  region: v,
                  regionCustom: v.startsWith("Type a") ? f.regionCustom : "",
                }))
              }
            />
            {form.region.startsWith("Type a") ? (
              <input
                className="mt-1.5"
                value={form.regionCustom}
                placeholder="e.g. Piedmont, Hill Country, Ozarks…"
                onChange={(e) => setForm((f) => ({ ...f, regionCustom: e.target.value }))}
              />
            ) : null}
          </FilterField>

          <FilterField label="Price range">
            <HeroSelect
              ariaLabel="Price range"
              value={form.pricePreset}
              options={(meta.price_presets?.length
                ? meta.price_presets
                : SEARCH_META_FALLBACK.price_presets
              ).map((p) => ({
                value: p.label,
                label: p.label,
              }))}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  pricePreset: v,
                  ...(v.toLowerCase().includes("custom")
                    ? {}
                    : { priceMin: "", priceMax: "", priceMinUnit: "K", priceMaxUnit: "K" }),
                }))
              }
            />
            {form.pricePreset.toLowerCase().includes("custom") ? (
              <div className="filter-custom-stack mt-1.5">
                <div className="filter-money-field">
                  <input
                    value={form.priceMin}
                    placeholder="Min"
                    inputMode="decimal"
                    onChange={(e) =>
                      setForm((f) => ({ ...f, priceMin: sanitizeDecimal(e.target.value) }))
                    }
                  />
                  <UnitToggle
                    value={form.priceMinUnit}
                    ariaLabel="Min price unit"
                    onChange={(u) => setForm((f) => ({ ...f, priceMinUnit: u }))}
                  />
                </div>
                <div className="filter-money-field">
                  <input
                    value={form.priceMax}
                    placeholder="Max"
                    inputMode="decimal"
                    onChange={(e) =>
                      setForm((f) => ({ ...f, priceMax: sanitizeDecimal(e.target.value) }))
                    }
                  />
                  <UnitToggle
                    value={form.priceMaxUnit}
                    ariaLabel="Max price unit"
                    onChange={(u) => setForm((f) => ({ ...f, priceMaxUnit: u }))}
                  />
                </div>
              </div>
            ) : null}
          </FilterField>

          <FilterField label="Acreage">
            <HeroSelect
              ariaLabel="Acreage"
              value={form.acrePreset}
              options={(meta.acre_presets?.length
                ? meta.acre_presets
                : SEARCH_META_FALLBACK.acre_presets
              ).map((p) => ({
                value: p.label,
                label: p.label,
              }))}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  acrePreset: v,
                  ...(v.toLowerCase().includes("custom") ? {} : { acreMin: "", acreMax: "" }),
                }))
              }
            />
            {form.acrePreset.toLowerCase().includes("custom") ? (
              <div className="filter-custom-pair mt-1.5">
                <input
                  value={form.acreMin}
                  placeholder="Min ac"
                  inputMode="decimal"
                  onChange={(e) =>
                    setForm((f) => ({ ...f, acreMin: sanitizeDecimal(e.target.value) }))
                  }
                />
                <input
                  value={form.acreMax}
                  placeholder="Max ac"
                  inputMode="decimal"
                  onChange={(e) =>
                    setForm((f) => ({ ...f, acreMax: sanitizeDecimal(e.target.value) }))
                  }
                />
              </div>
            ) : null}
          </FilterField>

          <FilterField
            label="Strategy"
            tip={{
              title: "Strategy",
              body: "Ranks matching land uses higher. Homes, cottages, and ranch houses are kept out of vacant-land results — pick Property on site to see those.",
            }}
          >
            <HeroSelect
              multi
              ariaLabel="Strategy"
              values={form.strategies}
              options={(meta.strategies?.length
                ? meta.strategies
                : SEARCH_META_FALLBACK.strategies
              ).map((s) => ({
                value: s,
                label:
                  s === "Any"
                    ? "Any"
                    : s === "CUSTOM"
                      ? "Type my own…"
                      : s === "IMPROVED_PROPERTY"
                        ? "Property on site"
                        : s.replaceAll("_", " "),
              }))}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  strategies: v,
                  strategyCustom: v.includes("CUSTOM") ? f.strategyCustom : "",
                }))
              }
            />
            {strategyHasCustom ? (
              <input
                className="mt-1.5"
                value={form.strategyCustom}
                placeholder="e.g. solar lease, hunting lease…"
                onChange={(e) => setForm((f) => ({ ...f, strategyCustom: e.target.value }))}
              />
            ) : null}
          </FilterField>

          <FilterField label="Hold period">
            <HeroSelect
              ariaLabel="Hold period"
              value={form.holdYears}
              options={[
                ...(meta?.hold_years?.length ? meta.hold_years : HOLD_YEAR_OPTIONS).map((s) => ({
                  value: String(s),
                  label: s === "Any" ? "Any" : `${s} years`,
                })),
                { value: "__custom__", label: "Type my own…" },
              ]}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  holdYears: v,
                  holdCustom: v === "__custom__" ? f.holdCustom : "",
                }))
              }
            />
            {form.holdYears === "__custom__" ? (
              <input
                className="mt-1.5"
                value={form.holdCustom}
                placeholder="Years"
                inputMode="numeric"
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    holdCustom: sanitizeInt(e.target.value, 500),
                    holdYears: "__custom__",
                  }))
                }
              />
            ) : null}
          </FilterField>
        </div>

        <div className="filter-actions">
          <div className="filter-actions-buttons">
            <div className="filter-actions-primary">
              <button
                type="button"
                className="btn btn-secondary btn-search-primary"
                onClick={() => {
                  setForm(DEFAULT_FORM);
                  setStatus("Filters reset to Any. Click Show matches when you want results.");
                }}
              >
                Reset to Any
              </button>
              <Link href="/alerts" className="btn btn-land-alerts btn-search-primary">
                Land Alerts
              </Link>
            </div>
            <div className="filter-actions-secondary">
              <button
                type="button"
                className="btn btn-secondary filter-action-top"
                disabled={loading}
                onClick={() => {
                  const next = { ...DEFAULT_FORM, sort: "score_desc" };
                  setForm(next);
                  void runSearch(next);
                }}
              >
                Top opportunities
              </button>
              <button
                type="button"
                className="btn btn-secondary filter-action-refresh"
                onClick={scanFresh}
                disabled={scanning}
              >
                {scanning ? "Refreshing" : "Refresh live inventory"}
              </button>
              <div className="filter-show-matches">
                <button
                  type="button"
                  className="btn btn-primary filter-action-reset"
                  onClick={() => void runSearch()}
                  disabled={loading}
                >
                  {loading ? "Searching…" : "Show matches"}
                </button>
                <div className="filter-inventory-breakdown" ref={inventoryBreakdownRef}>
                  <button
                    type="button"
                    data-testid="inventory-by-state-trigger"
                    className="filter-inventory-note filter-inventory-note-btn"
                    aria-live="polite"
                    aria-expanded={inventoryBreakdownOpen}
                    aria-controls="inventory-by-state-popup"
                    aria-haspopup="dialog"
                    title={
                      inventoryStateRows.length
                        ? "Listings by state"
                        : "Live inventory is still loading"
                    }
                    disabled={!inventoryStateRows.length && !(meta?.inventory_count)}
                    onClick={() => {
                      if (!inventoryStateRows.length) return;
                      setInventoryBreakdownOpen((open) => !open);
                    }}
                  >
                    {(() => {
                      const label = formatListingsLabel(meta?.inventory_count);
                      return label ? (
                        <>
                          <strong>{label}</strong> listings
                        </>
                      ) : (
                        <>
                          <strong aria-hidden>…</strong>
                          <span className="sr-only">Loading inventory count</span> listings
                        </>
                      );
                    })()}
                  </button>
                  {inventoryBreakdownOpen && inventoryStateRows.length > 0 ? (
                    <div
                      id="inventory-by-state-popup"
                      className="filter-inventory-popup"
                      role="dialog"
                      aria-label="Listings by state"
                      onMouseDown={(event) => event.stopPropagation()}
                      onPointerDown={(event) => event.stopPropagation()}
                    >
                      <ul className="filter-inventory-popup-list">
                        {inventoryStateRows.map((row) => (
                          <li key={row.code} className="filter-inventory-popup-row">
                            <span className="filter-inventory-popup-state">{row.name}</span>
                            <span className="filter-inventory-popup-count">
                              {row.count.toLocaleString("en-US")}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <UsedByStrip />

      <div id="search-results" className="results-head scroll-mt-0">
        <div>
          <h2 className="display text-2xl font-semibold">Scouted opportunities</h2>
          {status ? <p className="mt-1 text-[var(--muted)]">{status}</p> : null}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs uppercase tracking-wide text-[var(--muted)]">
            Sort results
            <select
              className="mt-1 block min-w-[220px] rounded-xl border border-[var(--line)] bg-[var(--bg-elevated)] px-3 py-2 text-sm normal-case text-[var(--ink)]"
              value={form.sort}
              onChange={(e) => setForm((f) => ({ ...f, sort: e.target.value }))}
              title="Re-orders the results you already loaded — does not hit the API again"
            >
              {(
                meta?.sort_options || [
                  { value: "fit_desc", label: "Best match for my filters" },
                  { value: "score_desc", label: "Highest opportunity score (0–100)" },
                  { value: "risk_asc", label: "Lowest risk score first" },
                  { value: "confidence_desc", label: "Most complete files first" },
                  { value: "price_asc", label: "Lowest price / starting bid" },
                  { value: "acres_desc", label: "Largest acreage first" },
                  { value: "discount_asc", label: "Biggest gap under our estimated value" },
                ]
              ).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error && <div className="panel mb-4 p-4 text-[var(--danger)]">{error}</div>}

      {loading && (
        <LandLoader
          label="Surveying matches…"
          detail="Ranking live public parcels against your filters — likely buy price, risk, and match score."
        />
      )}

      {!loading && !hasSearched && (
        <div className="panel empty-state">
          <div className="display text-2xl text-[var(--ink)]">Find buys others can’t see</div>
          <p className="mx-auto mt-2 max-w-lg">
            Hit <strong>Top opportunities</strong> for the strongest engine-ranked files nationwide.
          </p>
        </div>
      )}

      {!loading && hasSearched && !rows.length ? (
        <div className="panel empty-state" role="status" aria-live="polite">
          <div className="display text-2xl text-[var(--ink)]">No matches for these filters</div>
          <p className="mx-auto mt-2 max-w-lg">
            Adjust filters, then tap Show matches again.
          </p>
          {emptyExplanation ? (
            <div className="empty-filter-reason empty-filter-reason--in-alert">
              <h3 className="empty-filter-reason-headline">{emptyExplanation.headline}</h3>
              {emptyExplanation.summary ? (
                <p className="empty-filter-reason-summary">{emptyExplanation.summary}</p>
              ) : null}
              {emptyExplanation.conflict ? (
                <div className="empty-filter-reason-conflict">
                  <span className="empty-filter-reason-conflict-label">Disconnect</span>
                  <span className="empty-filter-reason-conflict-value">{emptyExplanation.conflict}</span>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {!loading && (
        <div className="results-grid">
          {sortedRows.map((row, i) => (
            <PropertyCard key={row.parcel_id} row={row} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
