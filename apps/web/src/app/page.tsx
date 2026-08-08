"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  pricePreset: string;
  acrePreset: string;
  strategy: string;
  holdYears: string;
  targetRoi: string;
  maxRisk: string;
  minConfidence: string;
  includeUnpriced: boolean;
};

const DEFAULT_FORM: FormState = {
  q: "",
  state: "Any",
  region: "Any",
  pricePreset: "Any",
  acrePreset: "Any",
  strategy: "Any",
  holdYears: "Any",
  targetRoi: "Any",
  maxRisk: "Any",
  minConfidence: "Any",
  includeUnpriced: true,
};

export default function SearchPage() {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [meta, setMeta] = useState<SearchMeta | null>(null);
  const [rows, setRows] = useState<RadarRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const buildFilters = useCallback((): SearchFilters => {
    const price = meta?.price_presets.find((p) => p.label === form.pricePreset);
    const acres = meta?.acre_presets.find((p) => p.label === form.acrePreset);
    return {
      q: form.q || undefined,
      state: form.state,
      region: form.region === "Any" ? undefined : form.region.split(",")[0]?.trim(),
      min_price: price?.min ?? undefined,
      max_price: price?.max ?? undefined,
      min_acres: acres?.min ?? undefined,
      max_acres: acres?.max ?? undefined,
      strategy: form.strategy,
      hold_years: form.holdYears === "Any" ? undefined : Number(form.holdYears),
      target_roi: form.targetRoi === "Any" ? undefined : Number(form.targetRoi),
      max_risk: form.maxRisk === "Any" ? undefined : Number(form.maxRisk),
      min_confidence: form.minConfidence === "Any" ? undefined : Number(form.minConfidence),
      include_unpriced: form.includeUnpriced,
    };
  }, [form, meta]);

  const runSearch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await landsignalApi.radar(buildFilters());
      setRows(data);
      setStatus(`${data.length} opportunities matched your criteria`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [buildFilters]);

  useEffect(() => {
    landsignalApi
      .searchMeta()
      .then(setMeta)
      .catch(() =>
        setMeta({
          states: ["Any"],
          regions: ["Any"],
          strategies: ["Any", "FARMLAND", "LAND_BANK", "ENERGY", "DEVELOPMENT", "RECREATIONAL", "TIMBER"],
          hold_years: ["Any", 5, 10, 15],
          target_roi: ["Any", 0.1, 0.12, 0.15],
          price_presets: [
            { label: "Any", min: null, max: null },
            { label: "Under $50k", min: null, max: 50000 },
            { label: "$50k–$250k", min: 50000, max: 250000 },
            { label: "$250k–$1M", min: 250000, max: 1000000 },
            { label: "$1M+", min: 1000000, max: null },
          ],
          acre_presets: [
            { label: "Any", min: null, max: null },
            { label: "1–20 ac", min: 1, max: 20 },
            { label: "20–100 ac", min: 20, max: 100 },
            { label: "100–500 ac", min: 100, max: 500 },
            { label: "500+ ac", min: 500, max: null },
          ],
        }),
      );
  }, []);

  useEffect(() => {
    if (!meta) return;
    runSearch();
  }, [meta]); // initial load

  async function scanFresh() {
    setScanning(true);
    setStatus("Scanning public land markets and running due diligence…");
    try {
      const res = await landsignalApi.discover(30, 1, true);
      setStatus(`Refreshed inventory: ${res.imported} imported, ${res.scored} scored`);
      await runSearch();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }

  const topFit = useMemo(() => rows[0], [rows]);

  return (
    <div>
      <section className="hero-search">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.14em] text-white/70">LandSignal</div>
            <h1>Find land the market may be mispricing</h1>
            <p>
              Not a generic listing site. Rank parcels by risk-adjusted optionality across farmland,
              energy, land banking, and development — with every score backed by evidence.
            </p>
          </div>
        </div>

        <div className="filter-grid">
          <Field label="Keywords">
            <input
              value={form.q}
              placeholder="County, APN, keywords"
              onChange={(e) => setForm((f) => ({ ...f, q: e.target.value }))}
            />
          </Field>
          <Field label="State">
            <select value={form.state} onChange={(e) => setForm((f) => ({ ...f, state: e.target.value }))}>
              {(meta?.states || ["Any"]).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="City / region">
            <select value={form.region} onChange={(e) => setForm((f) => ({ ...f, region: e.target.value }))}>
              {(meta?.regions || ["Any"]).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Price range">
            <select
              value={form.pricePreset}
              onChange={(e) => setForm((f) => ({ ...f, pricePreset: e.target.value }))}
            >
              {(meta?.price_presets || []).map((p) => (
                <option key={p.label} value={p.label}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Acreage">
            <select
              value={form.acrePreset}
              onChange={(e) => setForm((f) => ({ ...f, acrePreset: e.target.value }))}
            >
              {(meta?.acre_presets || []).map((p) => (
                <option key={p.label} value={p.label}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Strategy">
            <select
              value={form.strategy}
              onChange={(e) => setForm((f) => ({ ...f, strategy: e.target.value }))}
            >
              {(meta?.strategies || ["Any"]).map((s) => (
                <option key={s} value={s}>
                  {s === "Any" ? "Any" : s.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Hold period">
            <select
              value={form.holdYears}
              onChange={(e) => setForm((f) => ({ ...f, holdYears: e.target.value }))}
            >
              {(meta?.hold_years || ["Any"]).map((s) => (
                <option key={String(s)} value={String(s)}>
                  {s === "Any" ? "Any" : `${s} years`}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Desired ROI / IRR">
            <select
              value={form.targetRoi}
              onChange={(e) => setForm((f) => ({ ...f, targetRoi: e.target.value }))}
            >
              {(meta?.target_roi || ["Any"]).map((s) => (
                <option key={String(s)} value={String(s)}>
                  {s === "Any" ? "Any" : `${Math.round(Number(s) * 100)}%+`}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Max risk">
            <select
              value={form.maxRisk}
              onChange={(e) => setForm((f) => ({ ...f, maxRisk: e.target.value }))}
            >
              {["Any", "30", "45", "60"].map((s) => (
                <option key={s} value={s}>
                  {s === "Any" ? "Any" : `≤ ${s}/100`}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Min confidence">
            <select
              value={form.minConfidence}
              onChange={(e) => setForm((f) => ({ ...f, minConfidence: e.target.value }))}
            >
              {["Any", "40", "55", "70"].map((s) => (
                <option key={s} value={s}>
                  {s === "Any" ? "Any" : `≥ ${s}/100`}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Unpriced federal / surplus">
            <select
              value={form.includeUnpriced ? "include" : "priced"}
              onChange={(e) =>
                setForm((f) => ({ ...f, includeUnpriced: e.target.value === "include" }))
              }
            >
              <option value="include">Include (Any pricing type)</option>
              <option value="priced">Priced / bids only</option>
            </select>
          </Field>
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
              setTimeout(() => runSearch(), 0);
            }}
          >
            Reset to Any
          </button>
        </div>
      </section>

      <div className="results-head">
        <div>
          <h2 className="display text-2xl font-semibold">Opportunity results</h2>
          <p className="mt-1 text-[var(--muted)]">
            {status || "Set your criteria above. Fit score personalizes ranking without hiding the global LandSignal score."}
          </p>
        </div>
        {topFit && (
          <div className="panel px-4 py-3 text-sm">
            <div className="text-[var(--muted)]">Top fit right now</div>
            <div className="font-semibold">{topFit.property_name}</div>
          </div>
        )}
      </div>

      {error && <div className="panel mb-4 p-4 text-[var(--danger)]">{error}</div>}

      {!loading && !rows.length && (
        <div className="panel empty-state">
          <div className="display text-2xl text-[var(--ink)]">No matches for these filters</div>
          <p className="mx-auto mt-2 max-w-lg">
            Try setting more fields to Any, include unpriced federal/surplus land, or refresh live inventory.
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="filter-field">
      <label>{label}</label>
      {children}
    </div>
  );
}
