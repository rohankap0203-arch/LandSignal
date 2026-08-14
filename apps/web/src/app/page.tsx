"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FilterField } from "@/components/filter-field";
import { LandLoader } from "@/components/land-loader";
import { PropertyCard } from "@/components/property-card";
import {
  landsignalApi,
  type RadarRow,
  type SearchEstimate,
  type SearchFilters,
  type SearchMeta,
} from "@/lib/api";

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

export default function SearchPage() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [meta, setMeta] = useState<SearchMeta | null>(null);
  const [rows, setRows] = useState<RadarRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [estimate, setEstimate] = useState<SearchEstimate | null>(null);

  const regionOptions = useMemo(() => {
    const code = stateCode(form.state);
    const byState = meta?.regions_by_state?.[code] || meta?.regions_by_state?.Any || ["Any"];
    const live = (meta?.regions || []).filter((r) => r !== "Any");
    const merged = ["Any", ...byState.filter((r) => r !== "Any")];
    for (const r of live) {
      if (code === "Any" || r.endsWith(`, ${code}`) || r.includes(` ${code}`)) {
        if (!merged.includes(r)) merged.push(r);
      }
    }
    if (!merged.includes("Type a city / county…")) merged.push("Type a city / county…");
    return merged;
  }, [form.state, meta]);

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
        min_price: customPrice ? parseMoney(f.priceMin) : price?.min ?? undefined,
        max_price: customPrice ? parseMoney(f.priceMax) : price?.max ?? undefined,
        min_acres: customAcres ? parseMoney(f.acreMin) : acres?.min ?? undefined,
        max_acres: customAcres ? parseMoney(f.acreMax) : acres?.max ?? undefined,
        strategy,
        hold_years: Number.isFinite(hold as number) ? hold : undefined,
        // Always include unpriced federal / surplus — no UI filter for this
        unpriced_mode: "include",
        include_unpriced: true,
        sort: f.sort,
        broaden: true,
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
        const data = await landsignalApi.radar(filtersFromForm(active));
        setRows(data);
        const metaNow = await landsignalApi.searchMeta().catch(() => null);
        if (metaNow) setMeta(metaNow);
        const exact = data.filter((r) => (r.match_tier || "exact") === "exact");
        const near = data.filter((r) => r.match_tier === "near");
        const label = metaNow?.inventory_label || "Development inventory";
        const parcels = metaNow?.inventory_count ?? 0;
        const statesN = metaNow?.states_covered ?? metaNow?.inventory_states?.length ?? 0;
        if (exact.length) {
          setStatus(
            `Exact matches: ${exact.length.toLocaleString()} shown · ${label}: ${parcels.toLocaleString()} parcels analyzed across ${statesN}/50 states`,
          );
        } else if (near.length) {
          setStatus(
            `No exact properties currently meet all hard filters · showing ${near.length} closest matches · ${label}`,
          );
        } else {
          setStatus("No active properties currently satisfy all selected hard filters.");
        }
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

  useEffect(() => {
    const filters = filtersFromForm(form);
    const handle = window.setTimeout(() => {
      landsignalApi
        .searchEstimate({
          state: filters.state,
          region: filters.region,
          min_price: filters.min_price,
          max_price: filters.max_price,
          min_acres: filters.min_acres,
          max_acres: filters.max_acres,
        })
        .then(setEstimate)
        .catch(() => setEstimate(null));
    }, 220);
    return () => window.clearTimeout(handle);
  }, [form, filtersFromForm]);

  async function scanFresh() {
    setScanning(true);
    setStatus("Inventory refresh started in the background. Click Show matches when you want results.");
    try {
      await landsignalApi.discover(10000, 0.1, false, undefined, true);
      const nextMeta = await landsignalApi.searchMeta();
      setMeta(nextMeta);
      setStatus(
        `Inventory refresh running · ${(nextMeta.inventory_label || "Development inventory")}: ${
          nextMeta.inventory_count?.toLocaleString() ?? 0
        } parcels analyzed · ${nextMeta.states_covered ?? 0}/50 states. Click Show matches to search.`,
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
  }, [rows, form.sort]);

  const exactRows = useMemo(
    () => sortedRows.filter((r) => (r.match_tier || "exact") === "exact"),
    [sortedRows],
  );
  const nearRows = useMemo(
    () => sortedRows.filter((r) => r.match_tier === "near"),
    [sortedRows],
  );

  const inventoryStates = meta?.inventory_states || [];
  const inventoryLabel = meta?.inventory_label || "Development inventory";

  return (
    <div>
      <section className="hero-search">
        <div>
          <div className="hero-brand-row">
            <div className="hero-brand-mark">LandSignal</div>
            <div className="hero-live" title={inventoryLabel}>
              <span className="hero-live-dot" aria-hidden />
              <span>{meta?.data_mode === "production" ? "Live" : "Dev inventory"}</span>
            </div>
          </div>
          <h1>Scout the best land buys in the country</h1>
        </div>

        <div className="filter-grid filter-grid-12">
          <FilterField label="State">
            <select
              value={form.state}
              onChange={(e) =>
                setForm((f) => ({ ...f, state: e.target.value, region: "Any", regionCustom: "" }))
              }
            >
              {(meta?.states || ["Any"]).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </FilterField>

          <FilterField label="City / region">
            <select
              value={form.region}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  region: e.target.value,
                  regionCustom: e.target.value.startsWith("Type a") ? f.regionCustom : "",
                }))
              }
            >
              {regionOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            {form.region.startsWith("Type a") ? (
              <input
                className="mt-1.5"
                value={form.regionCustom}
                placeholder="Type city, county, or corridor…"
                onChange={(e) => setForm((f) => ({ ...f, regionCustom: e.target.value }))}
              />
            ) : null}
          </FilterField>

          <FilterField label="Price range">
            <select
              value={form.pricePreset}
              onChange={(e) => {
                const v = e.target.value;
                setForm((f) => ({
                  ...f,
                  pricePreset: v,
                  ...(v.toLowerCase().includes("custom")
                    ? {}
                    : { priceMin: "", priceMax: "" }),
                }));
              }}
            >
              {(meta?.price_presets || [{ label: "Any" }]).map((p) => (
                <option key={p.label} value={p.label}>
                  {p.label}
                </option>
              ))}
            </select>
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
            <select
              value={form.acrePreset}
              onChange={(e) => {
                const v = e.target.value;
                setForm((f) => ({
                  ...f,
                  acrePreset: v,
                  ...(v.toLowerCase().includes("custom") ? {} : { acreMin: "", acreMax: "" }),
                }));
              }}
            >
              {(meta?.acre_presets || [{ label: "Any" }]).map((p) => (
                <option key={p.label} value={p.label}>
                  {p.label}
                </option>
              ))}
            </select>
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
            <select
              value={form.strategy}
              onChange={(e) => {
                const v = e.target.value;
                setForm((f) => ({
                  ...f,
                  strategy: v,
                  strategyCustom: v === "CUSTOM" ? f.strategyCustom : "",
                }));
              }}
            >
              {(meta?.strategies || ["Any"]).map((s) => (
                <option key={s} value={s}>
                  {s === "Any" ? "Any" : s === "CUSTOM" ? "Type my own…" : s.replaceAll("_", " ")}
                </option>
              ))}
            </select>
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
            <select
              value={form.holdYears}
              onChange={(e) => {
                const v = e.target.value;
                setForm((f) => ({
                  ...f,
                  holdYears: v,
                  holdCustom: v === "__custom__" ? f.holdCustom : "",
                }));
              }}
            >
              {(meta?.hold_years?.length ? meta.hold_years : HOLD_YEAR_OPTIONS).map((s) => (
                <option key={String(s)} value={String(s)}>
                  {s === "Any" ? "Any" : `${s} years`}
                </option>
              ))}
              <option value="__custom__">Type my own…</option>
            </select>
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
                {scanning ? "Starting refresh…" : "Refresh live inventory"}
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
              <div>
                {inventoryLabel}: {(meta.inventory_count || 0).toLocaleString()} parcels analyzed
                {" · "}
                {(meta.active_land_listings ?? 0).toLocaleString()} active land listings
                {" · "}
                {meta.states_covered ?? inventoryStates.length}/{meta.states_total ?? 50} states covered
                {meta.counties_covered != null ? ` · ${meta.counties_covered.toLocaleString()} counties` : ""}
              </div>
              {estimate ? (
                <div className="mt-1 font-medium text-[var(--ink)]">
                  {estimate.exact_match_count.toLocaleString()} matching properties for current hard filters
                </div>
              ) : null}
              {meta.inventory_warnings?.length ? (
                <div className="mt-1 text-[var(--muted)]">
                  {meta.inventory_warnings[0]}
                </div>
              ) : null}
            </div>
          )}
          {estimate?.facets?.regions?.length ? (
            <div className="filter-inventory-note mt-2">
              <span className="text-[var(--muted)]">Regions in view: </span>
              {estimate.facets.regions.slice(0, 6).map((r) => (
                <span key={r.label} className="mr-2">
                  {r.label} ({r.count.toLocaleString()})
                </span>
              ))}
            </div>
          ) : null}
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
            Hit <strong>Top opportunities</strong> for the strongest engine-ranked files nationwide, or
            set filters and <strong>Show matches</strong> for this page’s search.{" "}
            <strong>Land Alerts</strong> is separate — a saved watch profile that notifies you over time.
            Use <strong>Refresh live inventory</strong> to pull new tax-sale / surplus / BLM postings into
            the queue.
          </p>
        </div>
      )}

      {!loading && hasSearched && !rows.length && (
        <div className="panel empty-state">
          <div className="display text-2xl text-[var(--ink)]">No exact matches for this search</div>
          <p className="mx-auto mt-2 max-w-lg">
            No active properties currently satisfy all selected hard filters (state, region, price,
            acreage). Try widening price or acres — strategy and hold period do not exclude inventory.
          </p>
        </div>
      )}

      {!loading && exactRows.length > 0 && (
        <>
          <div className="results-head mt-2">
            <h3 className="display text-xl font-semibold">Exact matches</h3>
            <p className="text-sm text-[var(--muted)]">
              Satisfy 100% of hard filters (state, region, price, acreage).
            </p>
          </div>
          <div className="results-grid">
            {exactRows.map((row, i) => (
              <PropertyCard key={row.parcel_id} row={row} index={i} />
            ))}
          </div>
        </>
      )}

      {!loading && nearRows.length > 0 && (
        <>
          <div className="results-head mt-8">
            <h3 className="display text-xl font-semibold">Closest matches</h3>
            <p className="text-sm text-[var(--muted)]">
              No exact properties currently meet all hard filters — these are ranked by minimum
              filter deviation and are never mixed into Exact matches.
            </p>
          </div>
          <div className="results-grid">
            {nearRows.map((row, i) => (
              <div key={row.parcel_id}>
                {row.near_match_reason ? (
                  <div className="mb-2 text-xs text-[var(--muted)]">
                    {row.near_match_reason}
                  </div>
                ) : null}
                <PropertyCard row={row} index={i} />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
