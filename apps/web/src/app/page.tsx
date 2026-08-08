"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ComboFilter, FilterField } from "@/components/filter-field";
import { PropertyCard } from "@/components/property-card";
import {
  landsignalApi,
  type RadarRow,
  type SearchFilters,
  type SearchMeta,
} from "@/lib/api";

type FormState = {
  q: string;
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
  targetRoi: string;
  roiCustom: string;
  unpricedMode: string;
  sort: string;
};

const DEFAULT_FORM: FormState = {
  q: "",
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
  targetRoi: "Any",
  roiCustom: "",
  unpricedMode: "include",
  sort: "fit_desc",
};

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
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

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

      let roi: number | undefined;
      if (f.roiCustom.trim()) {
        const raw = f.roiCustom.trim().replace("%", "");
        const n = Number(raw);
        roi = n > 1 ? n / 100 : n;
      } else if (f.targetRoi !== "Any" && f.targetRoi !== "__custom__") roi = Number(f.targetRoi);

      const strategy =
        f.strategy === "CUSTOM"
          ? f.strategyCustom.trim() || undefined
          : f.strategy === "Any"
            ? undefined
            : f.strategy;

      return {
        q: f.q || undefined,
        state: stateCode(f.state),
        region,
        min_price: customPrice ? parseMoney(f.priceMin) : price?.min ?? undefined,
        max_price: customPrice ? parseMoney(f.priceMax) : price?.max ?? undefined,
        min_acres: customAcres ? parseMoney(f.acreMin) : acres?.min ?? undefined,
        max_acres: customAcres ? parseMoney(f.acreMax) : acres?.max ?? undefined,
        strategy,
        hold_years: Number.isFinite(hold as number) ? hold : undefined,
        target_roi: Number.isFinite(roi as number) ? roi : undefined,
        unpriced_mode: f.unpricedMode,
        include_unpriced: f.unpricedMode !== "priced",
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
            : "No matches yet — starting a nationwide live scan…",
        );
        // Auto-heal empty inventory without wiping filters
        if (!data.length) {
          landsignalApi.discover(10000, 0.1, false, undefined, true).catch(() => undefined);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    [filtersFromForm, form],
  );

  useEffect(() => {
    landsignalApi
      .searchMeta()
      .then(setMeta)
      .catch(() => setMeta(null));
  }, []);

  useEffect(() => {
    if (!meta) return;
    runSearch(DEFAULT_FORM);
  }, [meta]); // initial open = Any filters

  async function scanFresh() {
    setScanning(true);
    setStatus("Nationwide scan started — indexing thousands of public parcels…");
    try {
      // Never wipe on refresh — that was causing “no live matches”
      await landsignalApi.discover(10000, 0.1, false, undefined, true);
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const nextMeta = await landsignalApi.searchMeta();
        setMeta(nextMeta);
        await runSearch();
        if ((nextMeta.inventory_count || 0) >= 500) break;
      }
      setStatus("Live inventory updated — keep filtering; more parcels may still be indexing");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  const topFit = useMemo(() => rows[0], [rows]);
  const tips = meta?.tooltips || {};
  const inventoryStates = meta?.inventory_states || [];

  return (
    <div>
      <section className="hero-search">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.14em] text-white/70">LandSignal</div>
            <h1>Target the land that fits you</h1>
            <p>
              Set your range, hone the filters, and the engine ranks live public opportunities with
              plain-English scores — so you can see the best fit first.
            </p>
          </div>
        </div>

        <div className="filter-grid filter-grid-12">
          <FilterField label="Keywords">
            <input
              value={form.q}
              placeholder="County, APN, keywords"
              onChange={(e) => setForm((f) => ({ ...f, q: e.target.value }))}
            />
          </FilterField>

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
              {(meta?.hold_years || ["Any"]).map((s) => (
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
                placeholder="Years (e.g. 8)"
                onChange={(e) => setForm((f) => ({ ...f, holdCustom: e.target.value, holdYears: "__custom__" }))}
              />
            )}
          </FilterField>

          <FilterField label="Desired ROI / IRR">
            <select
              value={form.targetRoi}
              onChange={(e) => setForm((f) => ({ ...f, targetRoi: e.target.value }))}
            >
              {(meta?.target_roi || ["Any"]).map((s) => (
                <option key={String(s)} value={String(s)}>
                  {s === "Any" ? "Any" : `${Math.round(Number(s) * 100)}%+`}
                </option>
              ))}
              <option value="__custom__">Type my own…</option>
            </select>
            {(form.targetRoi === "__custom__" || form.roiCustom) && (
              <input
                className="mt-1.5"
                value={form.roiCustom}
                placeholder="e.g. 14 or 14%"
                onChange={(e) => setForm((f) => ({ ...f, roiCustom: e.target.value, targetRoi: "__custom__" }))}
              />
            )}
          </FilterField>

          <FilterField
            label="Unpriced federal / surplus"
            tip={
              tips.include_unpriced || {
                title: "Unpriced parcels",
                body: "Federal/surplus deals may have no retail ask. Include them for process opportunities.",
              }
            }
          >
            <select
              value={form.unpricedMode}
              onChange={(e) => setForm((f) => ({ ...f, unpricedMode: e.target.value }))}
            >
              {(
                meta?.unpriced_options || [
                  { value: "include", label: "Include unpriced federal / surplus" },
                  { value: "priced", label: "Priced / bids only" },
                  { value: "unpriced_only", label: "Unpriced process parcels only" },
                ]
              ).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </FilterField>
        </div>

        <div className="filter-actions">
          <button type="button" className="btn btn-primary" onClick={runSearch} disabled={loading}>
            {loading ? "Searching…" : "Show matches"}
          </button>
          <button type="button" className="btn btn-secondary" onClick={scanFresh} disabled={scanning}>
            {scanning ? "Scanning markets…" : "Refresh live inventory"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setForm(DEFAULT_FORM);
              // Pass DEFAULT explicitly — React state is async and was re-searching old filters
              void runSearch(DEFAULT_FORM);
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

      <div className="results-head">
        <div>
          <h2 className="display text-2xl font-semibold">Opportunity results</h2>
          <p className="mt-1 text-[var(--muted)]">
            {status ||
              "Set your criteria above. Fit score personalizes ranking without hiding the global LandSignal score."}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs uppercase tracking-wide text-[var(--muted)]">
            Sort results
            <select
              className="mt-1 block min-w-[220px] rounded-xl border border-[var(--line)] bg-[var(--bg-elevated)] px-3 py-2 text-sm normal-case text-[var(--ink)]"
              value={form.sort}
              onChange={(e) => {
                const next = { ...form, sort: e.target.value };
                setForm(next);
                void runSearch(next);
              }}
            >
              {(
                meta?.sort_options || [
                  { value: "fit_desc", label: "Best fit for my criteria" },
                  { value: "score_desc", label: "Highest LandSignal score" },
                  { value: "risk_asc", label: "Lowest screened risk" },
                  { value: "confidence_desc", label: "Highest confidence" },
                  { value: "price_asc", label: "Lowest price / bid" },
                  { value: "acres_desc", label: "Largest acreage" },
                  { value: "discount_asc", label: "Biggest discount vs model" },
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
              <div className="text-[var(--muted)]">Top fit right now</div>
              <div className="font-semibold">{topFit.property_name}</div>
              <div className="text-xs text-[var(--muted)]">
                Fit {Math.round(topFit.fit_score ?? 0)} · LandSignal {Math.round(topFit.opportunity)}
              </div>
            </div>
          )}
        </div>
      </div>

      {error && <div className="panel mb-4 p-4 text-[var(--danger)]">{error}</div>}

      {!loading && !rows.length && (
        <div className="panel empty-state">
          <div className="display text-2xl text-[var(--ink)]">No live matches yet</div>
          <p className="mx-auto mt-2 max-w-lg">
            Refresh public markets (BLM, tax sales, surplus). If you picked a state with thin coverage,
            leave region on Any or include unpriced federal parcels.
          </p>
          <button type="button" className="btn btn-dark mt-4" onClick={scanFresh}>
            Refresh live inventory
          </button>
        </div>
      )}

      <div className="results-grid">
        {rows.map((row, i) => (
          <PropertyCard key={row.parcel_id} row={row} index={i} />
        ))}
      </div>
    </div>
  );
}
