"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FilterField } from "@/components/filter-field";
import { HeroSelect } from "@/components/hero-select";
import { LandLoader } from "@/components/land-loader";
import { PropertyCard } from "@/components/property-card";
import {
  landsignalApi,
  type RadarRow,
  type SearchFilters,
  type SearchMeta,
} from "@/lib/api";
import { describeHardFilters, enforceHardFilters } from "@/lib/hard-filters";

type FormState = {
  state: string;
  region: string;
  regionCustom: string;
  pricePreset: string;
  priceMin: string;
  priceMax: string;
  acrePreset: string;
  acreMin: string;
  acreMax: string;
  strategy: string;
  strategyCustom: string;
  holdYears: string;
  holdCustom: string;
  sort: string;
};

const DEFAULT_FORM: FormState = {
  state: "Any",
  region: "Any",
  regionCustom: "",
  pricePreset: "Any",
  priceMin: "",
  priceMax: "",
  acrePreset: "Any",
  acreMin: "",
  acreMax: "",
  strategy: "Any",
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

function parseMoney(v: string): number | undefined {
  const n = Number(String(v).replace(/[$,\s]/g, ""));
  return Number.isFinite(n) && n >= 0 ? n : undefined;
}

function normPresetLabel(s: string): string {
  return s
    .replace(/\u2264/g, "<=")
    .replace(/≤/g, "<=")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

/** Resolve min/max from catalog presets, with label parsing fallback so filters never silently drop. */
function resolvePresetBounds(
  label: string,
  presets: Array<{ label: string; min: number | null; max: number | null }> | undefined,
  kind: "price" | "acres",
): { min?: number; max?: number } {
  if (!label || label === "Any") return {};
  const hit =
    presets?.find((p) => p.label === label) ||
    presets?.find((p) => normPresetLabel(p.label) === normPresetLabel(label));
  if (hit) {
    return {
      min: hit.min == null ? undefined : hit.min,
      max: hit.max == null ? undefined : hit.max,
    };
  }
  if (kind === "price") {
    const upto = label.match(/(?:≤|<=)\s*\$?\s*([\d,.]+)\s*([kmb])?/i);
    if (upto) {
      let n = Number(String(upto[1]).replace(/,/g, ""));
      const u = (upto[2] || "").toLowerCase();
      if (u === "k") n *= 1_000;
      if (u === "m") n *= 1_000_000;
      if (u === "b") n *= 1_000_000_000;
      if (Number.isFinite(n)) return { max: n };
    }
    const plus = label.match(/\$?\s*([\d,.]+)\s*([kmb])?\s*\+/i);
    if (plus) {
      let n = Number(String(plus[1]).replace(/,/g, ""));
      const u = (plus[2] || "").toLowerCase();
      if (u === "k") n *= 1_000;
      if (u === "m") n *= 1_000_000;
      if (Number.isFinite(n)) return { min: n };
    }
  }
  if (kind === "acres") {
    const plus = label.match(/^([\d,.]+)\s*\+/i);
    if (plus) {
      const n = Number(String(plus[1]).replace(/,/g, ""));
      if (Number.isFinite(n)) return { min: n };
    }
  }
  return {};
}

export default function SearchPage() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [meta, setMeta] = useState<SearchMeta | null>(null);
  const [rows, setRows] = useState<RadarRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [appliedFilters, setAppliedFilters] = useState<SearchFilters | null>(null);

  const regionOptions = useMemo(() => {
    const code = stateCode(form.state);
    const byState = meta?.regions_by_state?.[code] || meta?.regions_by_state?.Any || ["Any"];
    // Canonical investor regions for the selected state (or national macros when Any).
    const merged = ["Any", ...byState.filter((r) => r && r !== "Any")];
    // When a state is picked, append live inventory counties as concrete region cues.
    if (code !== "Any") {
      const live = (meta?.regions || []).filter((r) => {
        if (!r || r === "Any") return false;
        // Prefer "County, ST" / region labels tied to the active state.
        return (
          r.endsWith(`, ${code}`) ||
          r.endsWith(` ${code}`) ||
          r.toUpperCase().includes(`, ${code}`)
        );
      });
      for (const r of live) {
        if (!merged.includes(r)) merged.push(r);
      }
    }
    if (!merged.includes("Type a region…")) merged.push("Type a region…");
    return merged;
  }, [form.state, meta]);

  const filtersFromForm = useCallback(
    (f: FormState): SearchFilters => {
      const customPrice = f.pricePreset.toLowerCase().includes("custom");
      const customAcres = f.acrePreset.toLowerCase().includes("custom");
      const priceBounds = customPrice
        ? { min: parseMoney(f.priceMin), max: parseMoney(f.priceMax) }
        : resolvePresetBounds(f.pricePreset, meta?.price_presets, "price");
      const acreBounds = customAcres
        ? { min: parseMoney(f.acreMin), max: parseMoney(f.acreMax) }
        : resolvePresetBounds(f.acrePreset, meta?.acre_presets, "acres");
      const region =
        f.regionCustom.trim() ||
        (f.region.startsWith("Type a") || f.region === "Any" ? undefined : f.region);

      let hold: number | undefined;
      if (f.holdYears === "__custom__") {
        const n = Number(f.holdCustom);
        if (Number.isFinite(n)) hold = Math.max(1, Math.min(100, n));
      } else if (f.holdYears !== "Any") {
        hold = Number(f.holdYears);
      }

      const strategy =
        f.strategy === "CUSTOM"
          ? f.strategyCustom.trim() || undefined
          : f.strategy === "Any"
            ? undefined
            : f.strategy;

      return {
        state: stateCode(f.state),
        region,
        min_price: priceBounds.min,
        max_price: priceBounds.max,
        min_acres: acreBounds.min,
        max_acres: acreBounds.max,
        strategy,
        hold_years: Number.isFinite(hold as number) ? hold : undefined,
        // Unpriced GIS can still match via assessed land value on the API.
        unpriced_mode: "include",
        include_unpriced: true,
        sort: f.sort,
        // Broaden may loosen region/channel only — never price, acres, state, or strategy.
        // Off whenever any hard option is set (every preset / custom band counts).
        broaden: !(
          priceBounds.min != null ||
          priceBounds.max != null ||
          acreBounds.min != null ||
          acreBounds.max != null ||
          !!region ||
          !!strategy ||
          (stateCode(f.state) !== "Any" && !!stateCode(f.state))
        ),
      };
    },
    [meta],
  );

  const runSearch = useCallback(
    async (override?: FormState) => {
      setLoading(true);
      setError(null);
      setHasSearched(true);
      // Smooth-scroll to results as soon as search starts
      requestAnimationFrame(() => {
        document.getElementById("search-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      try {
        const active = override ?? form;
        const filters = filtersFromForm(active);
        setAppliedFilters(filters);
        const data = await landsignalApi.radar(filters);
        // Client hard gate — results that violate the selected filters never render.
        const { kept, dropped } = enforceHardFilters(data, filters);
        setRows(kept);
        const metaNow = await landsignalApi.searchMeta().catch(() => null);
        if (metaNow) setMeta(metaNow);
        const total = metaNow?.inventory_count ?? kept.length;
        const filterLabel = describeHardFilters(filters);
        setStatus(
          kept.length
            ? `Strict filters: ${filterLabel} · showing ${kept.length.toLocaleString()} matches` +
                (dropped ? ` · ${dropped} out-of-band dropped` : "") +
                ` · ${total.toLocaleString()} live parcels indexed`
            : `No matches inside strict filters (${filterLabel}). Widen price/acres/state, then Show matches again.`,
        );
        // Re-align after results paint
        requestAnimationFrame(() => {
          document.getElementById("search-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    [filtersFromForm, form],
  );

  useEffect(() => {
    // Load filter catalogs only — do NOT auto-search
    landsignalApi
      .searchMeta()
      .then(setMeta)
      .catch(() => setMeta(null));
  }, []);

  async function scanFresh() {
    setScanning(true);
    setStatus("Inventory refresh started in the background. Click Show matches when you want results.");
    try {
      await landsignalApi.discover(10000, 0.1, false, undefined, true);
      const nextMeta = await landsignalApi.searchMeta();
      setMeta(nextMeta);
      setStatus(
        `Inventory refresh running · ${nextMeta.inventory_count?.toLocaleString() ?? 0} parcels indexed so far. Click Show matches to search.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  const sortedRows = useMemo(() => {
    // Re-enforce hard filters on every render so sort/UI never resurfaces violators.
    const list = appliedFilters ? enforceHardFilters(rows, appliedFilters).kept : [...rows];
    const key = form.sort;
    const num = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0);
    list.sort((a, b) => {
      switch (key) {
        case "score_desc":
          return num(b.opportunity) - num(a.opportunity);
        case "risk_asc":
          return num(a.risk) - num(b.risk);
        case "confidence_desc":
          return num(b.confidence) - num(a.confidence);
        case "price_asc":
          return (a.ask ?? Number.POSITIVE_INFINITY) - (b.ask ?? Number.POSITIVE_INFINITY);
        case "acres_desc":
          return num(b.acres) - num(a.acres);
        case "discount_asc":
          return num(a.discount_pct ?? 0) - num(b.discount_pct ?? 0);
        case "fit_desc":
        default:
          return num(b.fit_score ?? b.opportunity) - num(a.fit_score ?? a.opportunity);
      }
    });
    return list;
  }, [rows, form.sort, appliedFilters]);

  const inventoryStates = meta?.inventory_states || [];

  return (
    <div>
      <section className="hero-search">
        <div>
          <div className="hero-brand-row">
            <div className="hero-brand-mark">LandSignal</div>
            <div className="hero-live" title="Live public inventory index">
              <span className="hero-live-dot" aria-hidden />
              <span>Live</span>
            </div>
          </div>
          <h1>Scout the best land buys in the country</h1>
        </div>

        <div className="filter-grid filter-grid-12">
          <FilterField label="State">
            <HeroSelect
              ariaLabel="State"
              value={form.state}
              options={(meta?.states || ["Any"]).map((s) => ({ value: s, label: s }))}
              onChange={(v) => setForm((f) => ({ ...f, state: v, region: "Any", regionCustom: "" }))}
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
              options={(meta?.price_presets || [{ label: "Any" }]).map((p) => ({
                value: p.label,
                label: p.label,
              }))}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  pricePreset: v,
                  ...(v.toLowerCase().includes("custom") ? {} : { priceMin: "", priceMax: "" }),
                }))
              }
            />
            {form.pricePreset.toLowerCase().includes("custom") ? (
              <div className="filter-custom-pair mt-1.5">
                <input
                  value={form.priceMin}
                  placeholder="Min $"
                  inputMode="decimal"
                  onChange={(e) => setForm((f) => ({ ...f, priceMin: e.target.value }))}
                />
                <input
                  value={form.priceMax}
                  placeholder="Max $"
                  inputMode="decimal"
                  onChange={(e) => setForm((f) => ({ ...f, priceMax: e.target.value }))}
                />
              </div>
            ) : null}
          </FilterField>

          <FilterField label="Acreage">
            <HeroSelect
              ariaLabel="Acreage"
              value={form.acrePreset}
              options={(meta?.acre_presets || [{ label: "Any" }]).map((p) => ({
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
                  onChange={(e) => setForm((f) => ({ ...f, acreMin: e.target.value }))}
                />
                <input
                  value={form.acreMax}
                  placeholder="Max ac"
                  inputMode="decimal"
                  onChange={(e) => setForm((f) => ({ ...f, acreMax: e.target.value }))}
                />
              </div>
            ) : null}
          </FilterField>

          <FilterField
            label="Strategy"
            tip={{
              title: "What strategy does",
              body: "Prefers parcels that fit that use (farm, develop, timber…). Others stay in results — they just rank lower.",
            }}
          >
            <HeroSelect
              ariaLabel="Strategy"
              value={form.strategy}
              options={(meta?.strategies || ["Any"]).map((s) => ({
                value: s,
                label: s === "Any" ? "Any" : s === "CUSTOM" ? "Type my own…" : s.replaceAll("_", " "),
              }))}
              onChange={(v) =>
                setForm((f) => ({
                  ...f,
                  strategy: v,
                  strategyCustom: v === "CUSTOM" ? f.strategyCustom : "",
                }))
              }
            />
            {form.strategy === "CUSTOM" ? (
              <input
                className="mt-1.5"
                value={form.strategyCustom}
                placeholder="e.g. solar lease, hunting lease…"
                onChange={(e) => setForm((f) => ({ ...f, strategyCustom: e.target.value }))}
              />
            ) : null}
          </FilterField>

          <FilterField
            label="Hold period"
            tip={{
              title: "What hold period does",
              body: "Doesn’t remove results — only reorders them.",
            }}
          >
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
                placeholder="Years (1–100)"
                inputMode="numeric"
                onChange={(e) =>
                  setForm((f) => ({ ...f, holdCustom: e.target.value, holdYears: "__custom__" }))
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
                title="Ranks the strongest matches inside your current filters — never clears them"
                onClick={() => {
                  // Keep every filter the user selected; only boost opportunity sort.
                  const next = { ...form, sort: "score_desc" };
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
              <button
                type="button"
                className="btn btn-primary filter-action-reset"
                onClick={() => void runSearch()}
                disabled={loading}
              >
                {loading ? "Searching…" : "Show matches"}
              </button>
            </div>
          </div>
          {meta?.inventory_count != null && (
            <div className="filter-inventory-note">
              Live inventory: {meta.inventory_count} parcels
              {inventoryStates.length ? ` across ${inventoryStates.length} states (${inventoryStates.join(", ")})` : ""}
            </div>
          )}
          {appliedFilters ? (
            <div className="filter-inventory-note mt-2" title="Every option you pick is a hard constraint">
              Active hard filters: {describeHardFilters(appliedFilters)}
            </div>
          ) : (
            <div className="filter-inventory-note mt-2">
              Every State / Region / Price / Acreage / Strategy option is enforced strictly — not just 20+ ac or ≤ $1M.
            </div>
          )}
        </div>
      </section>

      <div id="search-results" className="results-head scroll-mt-24">
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
            Set your filters, then hit <strong>Show matches</strong>. Results only include parcels
            that pass every filter you selected. <strong>Top opportunities</strong> ranks the
            strongest matches inside those same filters — it never clears them.
          </p>
        </div>
      )}

      {!loading && hasSearched && !rows.length && (
        <div className="panel empty-state">
          <div className="display text-2xl text-[var(--ink)]">No matches for this search</div>
          <p className="mx-auto mt-2 max-w-lg">
            Try Reset to Any, widen price/acres, or pick another state — then click Show matches again.
          </p>
        </div>
      )}

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
