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
import { SEARCH_META_FALLBACK } from "@/lib/search-meta-fallback";

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
  const [meta, setMeta] = useState<SearchMeta>(SEARCH_META_FALLBACK);
  const [rows, setRows] = useState<RadarRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

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
        // Never auto-loosen filters — results must match what the user selected.
        broaden: false,
      };
    },
    [meta],
  );

  const runSearch = useCallback(
    async (override?: FormState) => {
      setLoading(true);
      setError(null);
      setHasSearched(true);
      setRows([]);
      // Smooth-scroll to results as soon as search starts
      requestAnimationFrame(() => {
        document.getElementById("search-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      try {
        const active = override ?? form;
        const data = await landsignalApi.radar(filtersFromForm(active));
        if (!Array.isArray(data)) {
          throw new Error("Search returned an unexpected response. Try Show matches again.");
        }
        setRows(data);
        const metaNow = await landsignalApi.searchMeta().catch(() => null);
        if (metaNow) {
          setMeta({
            ...SEARCH_META_FALLBACK,
            ...metaNow,
            states: metaNow.states?.length ? metaNow.states : SEARCH_META_FALLBACK.states,
          });
        }
        const total = metaNow?.inventory_count ?? data.length;
        setStatus(
          data.length
            ? `Showing ${data.length.toLocaleString()} matches for your filters · ${total.toLocaleString()} live parcels indexed`
            : "No parcels match these exact filters. Widen price/acres/strategy, or Reset to Any, then Show matches again.",
        );
        // Re-align after results paint
        requestAnimationFrame(() => {
          document.getElementById("search-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      } catch (e) {
        const raw = e instanceof Error ? e.message : "Search failed";
        const friendly = /not reachable|could not reach|Internal Server Error/i.test(raw)
          ? "LandSignal API is not reachable. Start it with `npm run dev:api`, then try Show matches again."
          : /Failed to fetch|NetworkError|Load failed|timeout|abort/i.test(raw)
            ? "Search failed to load results. Tap Show matches again — if it keeps failing, refresh the page."
            : raw.length > 280
              ? "Search failed. Tap Show matches again — if it keeps failing, try Reset to Any first."
              : raw;
        setError(friendly);
        setStatus(null);
      } finally {
        setLoading(false);
      }
    },
    [filtersFromForm, form],
  );

  useEffect(() => {
    // Load live catalogs (inventory counts, regions) — keep fallback if this fails
    let cancelled = false;
    landsignalApi
      .searchMeta()
      .then((live) => {
        if (cancelled || !live) return;
        setMeta({
          ...SEARCH_META_FALLBACK,
          ...live,
          states: live.states?.length ? live.states : SEARCH_META_FALLBACK.states,
          strategies: live.strategies?.length ? live.strategies : SEARCH_META_FALLBACK.strategies,
          price_presets: live.price_presets?.length
            ? live.price_presets
            : SEARCH_META_FALLBACK.price_presets,
          acre_presets: live.acre_presets?.length
            ? live.acre_presets
            : SEARCH_META_FALLBACK.acre_presets,
          hold_years: live.hold_years?.length ? live.hold_years : SEARCH_META_FALLBACK.hold_years,
        });
      })
      .catch(() => {
        /* keep SEARCH_META_FALLBACK — absolute localhost API bases fail on phones */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function scanFresh() {
    setScanning(true);
    setStatus("Inventory refresh started in the background. Click Show matches when you want results.");
    try {
      await landsignalApi.discover(10000, 0.1, false, undefined, true);
      const nextMeta = await landsignalApi.searchMeta();
      setMeta({
        ...SEARCH_META_FALLBACK,
        ...nextMeta,
        states: nextMeta.states?.length ? nextMeta.states : SEARCH_META_FALLBACK.states,
      });
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
    const pid = (r: RadarRow) => String(r.parcel_id || "");
    // Keep secondary keys aligned with the API — parcel_id last so ties stay stable.
    list.sort((a, b) => {
      let cmp = 0;
      switch (key) {
        case "score_desc":
          cmp = num(b.opportunity) - num(a.opportunity) || num(b.fit_score) - num(a.fit_score);
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
              body: "Boosts matching uses (farm, develop, timber…). Other results stay — they just rank lower.",
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
                label: s === "Any" ? "Any" : s === "CUSTOM" ? "Type my own…" : s.replaceAll("_", " "),
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
            Hit <strong>Top opportunities</strong> for the strongest engine-ranked files nationwide.
          </p>
        </div>
      )}

      {!loading && hasSearched && !rows.length && (
        <div className="panel empty-state">
          <div className="display text-2xl text-[var(--ink)]">No matches for this search</div>
          <p className="mx-auto mt-2 max-w-lg">
            {(() => {
              const picked = selectedStates(form.states);
              const live = new Set(inventoryStates || []);
              const missing = picked.filter((c) => live.size > 0 && !live.has(c));
              if (missing.length) {
                return (
                  <>
                    No live inventory indexed for{" "}
                    <strong>{missing.join(", ")}</strong> right now — results stay empty on purpose
                    (we don’t fill with other states). Reset to Any, pick a state that shows in
                    inventory, or run Inventory refresh, then Show matches again.
                  </>
                );
              }
              return (
                <>
                  Nothing in live inventory matches these exact filters. Widen price, acres, or
                  strategy — or Reset to Any — then click Show matches again.
                </>
              );
            })()}
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
