"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ComboFilter, FilterField } from "@/components/filter-field";
import { LandLoader } from "@/components/land-loader";
import { PropertyCard } from "@/components/property-card";
import {
  landsignalApi,
  type RadarRow,
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

/** Hold-period filter steps — 5-year increments (plus custom). */
const HOLD_YEAR_OPTIONS: Array<string | number> = [
  "Any",
  5,
  10,
  15,
  20,
  25,
  30,
  35,
  40,
  45,
  50,
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
  const [status, setStatus] = useState<string | null>("Set any filters you want, then click Show matches. Nothing searches until you ask.");
  const [hasSearched, setHasSearched] = useState(false);

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
      if (f.holdCustom.trim()) hold = Number(f.holdCustom);
      else if (f.holdYears !== "Any" && f.holdYears !== "__custom__") hold = Number(f.holdYears);

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
        const total = metaNow?.inventory_count ?? data.length;
        setStatus(
          data.length
            ? `Showing top ${data.length.toLocaleString()} matches · ${total.toLocaleString()} live parcels indexed`
            : "No matches for these filters. Try Reset to Any, then Show matches again.",
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

  const topFit = useMemo(() => sortedRows[0], [sortedRows]);
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
            {(form.region.startsWith("Type a") || form.regionCustom) && (
              <input
                className="mt-1.5"
                value={form.regionCustom}
                placeholder="Type city, county, or corridor…"
                onChange={(e) => setForm((f) => ({ ...f, regionCustom: e.target.value }))}
              />
            )}
          </FilterField>

          <ComboFilter
            label="Price range"
            preset={form.pricePreset}
            presets={(meta?.price_presets || [{ label: "Any" }]).map((p) => p.label)}
            onPreset={(v) => setForm((f) => ({ ...f, pricePreset: v }))}
            custom={form.priceMin || form.priceMax ? `${form.priceMin}-${form.priceMax}` : ""}
            onCustom={() => undefined}
            showCustom={form.pricePreset.toLowerCase().includes("custom")}
            customPlaceholder="Use min/max below"
          />
          {form.pricePreset.toLowerCase().includes("custom") && (
            <FilterField label="Custom price min / max">
              <div className="flex gap-2">
                <input
                  value={form.priceMin}
                  placeholder="Min $"
                  onChange={(e) => setForm((f) => ({ ...f, priceMin: e.target.value }))}
                />
                <input
                  value={form.priceMax}
                  placeholder="Max $"
                  onChange={(e) => setForm((f) => ({ ...f, priceMax: e.target.value }))}
                />
              </div>
            </FilterField>
          )}

          <ComboFilter
            label="Acreage"
            preset={form.acrePreset}
            presets={(meta?.acre_presets || [{ label: "Any" }]).map((p) => p.label)}
            onPreset={(v) => setForm((f) => ({ ...f, acrePreset: v }))}
            custom=""
            onCustom={() => undefined}
            showCustom={form.acrePreset.toLowerCase().includes("custom")}
          />
          {form.acrePreset.toLowerCase().includes("custom") && (
            <FilterField label="Custom acres min / max">
              <div className="flex gap-2">
                <input
                  value={form.acreMin}
                  placeholder="Min ac"
                  onChange={(e) => setForm((f) => ({ ...f, acreMin: e.target.value }))}
                />
                <input
                  value={form.acreMax}
                  placeholder="Max ac"
                  onChange={(e) => setForm((f) => ({ ...f, acreMax: e.target.value }))}
                />
              </div>
            </FilterField>
          )}

          <FilterField label="Strategy">
            <select
              value={form.strategy}
              onChange={(e) => setForm((f) => ({ ...f, strategy: e.target.value }))}
            >
              {(meta?.strategies || ["Any"]).map((s) => (
                <option key={s} value={s}>
                  {s === "Any" ? "Any" : s === "CUSTOM" ? "Type my own…" : s.replaceAll("_", " ")}
                </option>
              ))}
            </select>
            {(form.strategy === "CUSTOM" || form.strategyCustom) && (
              <input
                className="mt-1.5"
                value={form.strategyCustom}
                placeholder="e.g. solar lease, hunting lease…"
                onChange={(e) => setForm((f) => ({ ...f, strategyCustom: e.target.value }))}
              />
            )}
          </FilterField>

          <FilterField label="Hold period">
            <select
              value={form.holdYears}
              onChange={(e) => setForm((f) => ({ ...f, holdYears: e.target.value }))}
            >
              {(meta?.hold_years?.length ? meta.hold_years : HOLD_YEAR_OPTIONS).map((s) => (
                <option key={String(s)} value={String(s)}>
                  {s === "Any" ? "Any" : `${s} years`}
                </option>
              ))}
              <option value="__custom__">Type my own…</option>
            </select>
            {(form.holdYears === "__custom__" || form.holdCustom) && (
              <input
                className="mt-1.5"
                value={form.holdCustom}
                placeholder="Years (e.g. 10)"
                onChange={(e) => setForm((f) => ({ ...f, holdCustom: e.target.value, holdYears: "__custom__" }))}
              />
            )}
          </FilterField>
        </div>

        <div className="filter-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void runSearch()}
            disabled={loading}
          >
            {loading ? "Searching…" : "Show matches"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={loading}
            onClick={() => {
              const next = { ...DEFAULT_FORM, sort: "score_desc" };
              setForm(next);
              void runSearch(next);
            }}
          >
            Top opportunities
          </button>
          <button type="button" className="btn btn-secondary" onClick={scanFresh} disabled={scanning}>
            {scanning ? "Starting refresh…" : "Refresh live inventory"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setForm(DEFAULT_FORM);
              setStatus("Filters reset to Any. Click Show matches when you want results.");
            }}
          >
            Reset to Any
          </button>
          {meta?.inventory_count != null && (
            <span className="self-center text-sm text-white/70">
              Live inventory: {meta.inventory_count} parcels
              {inventoryStates.length ? ` across ${inventoryStates.length} states (${inventoryStates.join(", ")})` : ""}
            </span>
          )}
        </div>
      </section>

      <div id="search-results" className="results-head scroll-mt-24">
        <div>
          <h2 className="display text-2xl font-semibold">Scouted opportunities</h2>
          <p className="mt-1 text-[var(--muted)]">
            {status ||
              "Ranked by opportunity by default — process / off-MLS inventory first, with risk and file completeness on every card."}
          </p>
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
          {topFit && (
            <div className="panel px-4 py-3 text-sm">
              <div className="text-[var(--muted)]">Strongest file in this set</div>
              <div className="font-semibold">{topFit.property_name}</div>
              <div className="text-xs text-[var(--muted)]">
                Opportunity {Math.round(topFit.opportunity)}/100 · Risk {Math.round(topFit.risk)}/100
                {topFit.signal ? ` · ${topFit.signal}` : ""}
              </div>
            </div>
          )}
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
            set filters and <strong>Show matches</strong>. Use <strong>Refresh live inventory</strong> to
            pull new tax-sale / surplus / BLM postings into the queue.
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
