"use client";

import { useEffect, useMemo, useState, useTransition, type ReactNode } from "react";
import { landsignalApi } from "@/lib/api";

type Impact = {
  p10?: number;
  p50?: number;
  p90?: number;
  display_low_pct?: number;
  display_high_pct?: number;
  central_pct?: number;
};

type Scenario = {
  id: string;
  event_key?: string;
  label: string;
  bucket?: string;
  data_integrity?: string;
  stage?: string;
  project_certainty_pct?: number;
  parcel_distance_mi?: number;
  estimated_completion_offset_years?: number;
  timing?: Record<string, number>;
  correlation_group?: string;
  chain?: Array<{ key?: string; label?: string }>;
  impact?: Impact;
  channels?: {
    immediate_repricing?: number;
    appreciation_rate_change?: number;
    hbu_transformation?: number;
  };
  compatibility_score?: number;
  confidence?: string;
  reasoning?: {
    headline?: string;
    because?: string[];
    counterfactors?: string[];
    confidence?: string;
  };
  historical_analogs?: { show_historical_analogs?: boolean; comparable_count?: number };
  raw_text?: string;
};

type PathPoint = {
  year?: number;
  offset?: number;
  baseline_value?: number;
  scenario_value?: number;
  delta_value?: number;
  delta_pct?: number;
  value_usd?: number;
};

type Engine = {
  title?: string;
  button_label?: string;
  subtitle?: string;
  opportunity?: { score?: number; label?: string; primary_reason?: string };
  scenarios?: Scenario[];
  stress_cases?: Record<string, { scenario_ids?: string[]; label?: string; description?: string }>;
  baseline_points?: PathPoint[];
};

function money(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function pctRange(impact?: Impact): string {
  if (!impact) return "—";
  const lo = Number(impact.display_low_pct);
  const hi = Number(impact.display_high_pct);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return "—";
  const fmt = (n: number) => {
    const rounded = Math.abs(n) >= 10 ? Math.round(n) : Math.round(n * 10) / 10;
    const body = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
    return `${rounded > 0 ? "+" : ""}${body}%`;
  };
  if (Math.abs(lo - hi) < 0.05) return fmt(lo);
  // Upside: +low to +high · Downside: more-negative to less-negative
  if (lo < 0 && hi <= 0) return `${fmt(Math.min(lo, hi))} to ${fmt(Math.max(lo, hi))}`;
  return `${fmt(Math.min(lo, hi))} to ${fmt(Math.max(lo, hi))}`;
}

function softCap(x: number, cap = 0.75): number {
  if (x === 0) return 0;
  const sign = x > 0 ? 1 : -1;
  const ax = Math.abs(x);
  if (ax <= cap) return x;
  return sign * (cap + (ax - cap) * 0.35);
}

function combineImpacts(selected: Scenario[]) {
  if (!selected.length) {
    return { immediate: 0, rate: 0, hbu: 0, notes: [] as string[] };
  }
  const groups = new Map<string, Scenario[]>();
  const independents: Scenario[] = [];
  for (const s of selected) {
    const g = s.correlation_group || `independent:${s.event_key || s.id}`;
    if (g.startsWith("independent:")) independents.push(s);
    else {
      const arr = groups.get(g) || [];
      arr.push(s);
      groups.set(g, arr);
    }
  }

  let imm = 0;
  let rate = 0;
  let hbu = 0;
  const notes: string[] = [];

  const add = (item: Scenario, weight = 1) => {
    const ch = item.channels || {};
    imm += Number(ch.immediate_repricing || 0) * weight;
    rate += Number(ch.appreciation_rate_change || 0) * weight;
    hbu += Number(ch.hbu_transformation || 0) * weight;
  };

  for (const s of independents) add(s, 1);
  for (const [, items] of groups) {
    if (items.length === 1) {
      add(items[0], 1);
      continue;
    }
    const sorted = [...items].sort(
      (a, b) => Math.abs(Number(b.impact?.p50 || 0)) - Math.abs(Number(a.impact?.p50 || 0)),
    );
    add(sorted[0], 1);
    sorted.slice(1).forEach((item, i) => {
      add(item, 0.45 / (i + 1));
      notes.push(`Overlap: ${item.label} shares effects with ${sorted[0].label}`);
    });
  }

  const keys = new Set(selected.map((s) => s.event_key));
  const util = ["sewer_extension", "municipal_water", "electrical_expansion"].some((k) => keys.has(k));
  const entitle = ["zoning_change", "density_entitlement", "annexation"].some((k) => keys.has(k));
  if (util && entitle) {
    hbu += 0.035;
    notes.push("Utilities + entitlement unlock extra highest-and-best-use upside together");
  }

  return {
    immediate: softCap(imm),
    rate: softCap(rate, 0.04),
    hbu: softCap(hbu),
    notes,
  };
}

function applyPath(
  baseline: PathPoint[],
  combo: ReturnType<typeof combineImpacts>,
  selected: Scenario[],
) {
  const forward = baseline.filter((p) => p.offset != null && Number(p.offset) >= 0);
  const series = forward.length ? forward : baseline;
  if (!series.length) return [] as PathPoint[];

  let start = 2;
  let full = 6;
  if (selected.length) {
    start = Math.min(...selected.map((s) => Number(s.timing?.value_recognition_start_offset ?? 2)));
    full = Math.max(...selected.map((s) => Number(s.timing?.value_recognition_full_offset ?? 6)));
  }

  const { immediate: imm, rate, hbu } = combo;
  return series.map((pt) => {
    const y =
      pt.offset != null ? Number(pt.offset) : Number(pt.year || 0) - Number(series[0].year || 0);
    const baseV = Number(pt.value_usd ?? pt.baseline_value ?? 0);
    let w = 0;
    if (full <= start) w = y >= full ? 1 : 0;
    else if (y <= start) w = 0;
    else if (y >= full) w = 1;
    else w = (y - start) / (full - start);
    w = w * w * (3 - 2 * w);

    const rateMult = y > start ? Math.pow(1 + rate, Math.max(0, y - start)) : 1;
    let scen = baseV * (1 + (imm + hbu) * w) * (w > 0 ? rateMult : 1);
    if (w < 1 && y > start) scen = baseV + (scen - baseV) * Math.max(w, 0.35);

    return {
      year: pt.year,
      offset: y,
      baseline_value: Math.round(baseV),
      scenario_value: Math.round(scen),
      delta_value: Math.round(scen - baseV),
      delta_pct: baseV ? Math.round((scen / baseV - 1) * 1000) / 10 : 0,
    };
  });
}

function pathSummary(path: PathPoint[]) {
  if (!path.length) return null;
  const today = path[0];
  const at5 = path.find((p) => Number(p.offset) >= 5) || path[Math.min(1, path.length - 1)];
  const at10 = path.find((p) => Number(p.offset) >= 10) || path[path.length - 1];
  return {
    today: today.baseline_value,
    y5b: at5.baseline_value,
    y5s: at5.scenario_value,
    y10b: at10.baseline_value,
    y10s: at10.scenario_value,
    add: at10.delta_value,
    addPct: at10.delta_pct,
  };
}

function Tip({ label, children }: { label: string; children: ReactNode }) {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!on) return;
    const close = () => setOn(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("click", close);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("click", close);
    };
  }, [on]);

  return (
    <span className={`help-tip tone-panel fse-tip ${on ? "is-open" : ""}`} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className={`help-tip-btn ${on ? "on" : ""}`}
        aria-label={label}
        aria-expanded={on}
        title={label}
        onClick={(e) => {
          e.stopPropagation();
          setOn((v) => !v);
        }}
      >
        ?
      </button>
      {on ? (
        <span className="help-tip-pop fse-tip-pop" role="tooltip">
          {children}
        </span>
      ) : null}
    </span>
  );
}

function PathChart({ path }: { path: PathPoint[] }) {
  if (path.length < 2) return null;
  const w = 560;
  const h = 140;
  const pad = { t: 12, r: 12, b: 22, l: 8 };
  const xs = path.map((p) => Number(p.offset || 0));
  const ys = path.flatMap((p) => [Number(p.baseline_value || 0), Number(p.scenario_value || 0)]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys) * 0.97;
  const maxY = Math.max(...ys) * 1.03 || 1;
  const sx = (x: number) =>
    pad.l + ((x - minX) / Math.max(0.001, maxX - minX)) * (w - pad.l - pad.r);
  const sy = (y: number) =>
    pad.t + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - pad.t - pad.b);
  const line = (key: "baseline_value" | "scenario_value") =>
    path
      .map(
        (p, i) =>
          `${i ? "L" : "M"}${sx(Number(p.offset || 0)).toFixed(1)},${sy(Number(p[key] || 0)).toFixed(1)}`,
      )
      .join(" ");

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="fse-chart" role="img" aria-label="Value path">
      <path d={line("baseline_value")} className="fse-chart-base" />
      <path d={line("scenario_value")} className="fse-chart-scen" />
      <text x={pad.l} y={h - 4} className="fse-chart-label">
        Today
      </text>
      <text x={w - pad.r} y={h - 4} textAnchor="end" className="fse-chart-label">
        +{Math.round(maxX)}y
      </text>
    </svg>
  );
}

function shortLabel(label: string): string {
  return label
    .replace(/^Municipal /i, "")
    .replace(/ reaches parcel$/i, "")
    .replace(/ is (added|built|widened)$/i, "")
    .replace(/ opens nearby$/i, "")
    .replace(/ \(higher intensity\)$/i, "")
    .replace(/ begins nearby$/i, "");
}

export function CatalystSimulator({
  parcelId,
  engine,
}: {
  parcelId: string;
  engine: Engine | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [stress, setStress] = useState("custom");
  const [customText, setCustomText] = useState("");
  const [customError, setCustomError] = useState<string | null>(null);
  const [customScenario, setCustomScenario] = useState<Scenario | null>(null);
  const [pending, startTransition] = useTransition();

  const scenarios = useMemo(() => {
    const base = [...(engine?.scenarios || [])];
    if (customScenario) base.push(customScenario);
    return base;
  }, [engine, customScenario]);

  const byBucket = useMemo(() => {
    const groups: Record<string, Scenario[]> = { likely: [], high_impact: [], downside: [] };
    for (const s of scenarios) {
      const b = s.bucket || "likely";
      if (b === "high_impact") groups.high_impact.push(s);
      else if (b === "downside") groups.downside.push(s);
      else groups.likely.push(s);
    }
    return groups;
  }, [scenarios]);

  const selectedScenarios = useMemo(
    () => scenarios.filter((s) => selected.has(s.id)),
    [scenarios, selected],
  );

  const combo = useMemo(() => combineImpacts(selectedScenarios), [selectedScenarios]);
  const path = useMemo(
    () => applyPath(engine?.baseline_points || [], combo, selectedScenarios),
    [engine?.baseline_points, combo, selectedScenarios],
  );
  const summary = useMemo(() => pathSummary(path), [path]);
  const chartPath = path.length
    ? path
    : applyPath(engine?.baseline_points || [], combineImpacts([]), []);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!engine) return null;

  const toggle = (id: string) => {
    setStress("custom");
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const applyStress = (key: string) => {
    setStress(key);
    setSelected(new Set(engine.stress_cases?.[key]?.scenario_ids || []));
  };

  const submitCustom = () => {
    const text = customText.trim();
    if (!text) {
      setCustomError("Ask a what-if first.");
      return;
    }
    setCustomError(null);
    startTransition(async () => {
      try {
        const res = (await landsignalApi.catalystSimulate(parcelId, {
          custom_text: text,
          scenario_ids: [...selected],
        })) as { custom?: { ok?: boolean; error?: string; scenario?: Scenario } };
        const custom = res.custom;
        if (!custom?.ok || !custom.scenario) {
          setCustomError(custom?.error || "Couldn’t map that yet.");
          return;
        }
        setCustomScenario(custom.scenario);
        setSelected((prev) => new Set([...prev, custom.scenario!.id]));
        setStress("custom");
        setCustomText("");
      } catch (e) {
        setCustomError(e instanceof Error ? e.message : "Request failed");
      }
    });
  };

  const opp = engine.opportunity;
  const hasSel = selectedScenarios.length > 0;

  return (
    <section id="sec-catalyst" className="fse-wrap scroll-mt-20">
      <button
        type="button"
        className="fse-launch"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <span className="fse-launch-label">{engine.button_label || "Future Scenario Engine"}</span>
        <span className="fse-launch-meta">
          {opp?.score != null ? (
            <>
              Opportunity <strong>{opp.score}</strong>
              <span className="fse-launch-dot">·</span>
              {opp.label}
            </>
          ) : (
            "What if the area around this land changes?"
          )}
        </span>
      </button>

      {open ? (
        <div
          className="fse-backdrop"
          role="presentation"
          onClick={() => setOpen(false)}
        >
          <div
            className="fse-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Future Scenario Engine"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="fse-modal-head">
              <div className="fse-modal-title-row">
                <h2 className="display fse-modal-title">Future Scenario Engine</h2>
                <Tip label="How this works">
                  <strong>What-if layer on the Value Path</strong>
                  <span>
                    Toggle nearby changes. Impacts are parcel-specific (distance, fit, timing,
                    certainty) — not flat national %. Hypothetical unless cited. Paths diverge when
                    the market would start pricing the event in.
                  </span>
                </Tip>
              </div>
              <button
                type="button"
                className="help-q on fse-close"
                aria-label="Close"
                onClick={() => setOpen(false)}
              >
                ×
              </button>
            </header>

            {opp ? (
              <div className="fse-opp-bar">
                <div className="fse-opp-num">
                  <strong>{opp.score}</strong>
                  <span>/100 {opp.label}</span>
                </div>
                <p>{opp.primary_reason}</p>
                <Tip label="Catalyst Opportunity">
                  <strong>Catalyst Opportunity</strong>
                  <span>
                    How well this parcel is positioned for plausible upside — weighted by fit,
                    timing, and downside pressure. Speculative rumours count less.
                  </span>
                </Tip>
              </div>
            ) : null}

            <div className="fse-stress" role="tablist" aria-label="Case">
              {(["baseline", "most_likely", "bull", "bear", "custom"] as const).map((key) => {
                const meta = engine.stress_cases?.[key];
                return (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={stress === key}
                    className={`fse-stress-btn ${stress === key ? "active" : ""}`}
                    title={meta?.description}
                    onClick={() => applyStress(key)}
                  >
                    {meta?.label || key}
                  </button>
                );
              })}
            </div>

            <div className="fse-body">
              <div className="fse-scenarios">
                {(
                  [
                    ["likely", "Likely"],
                    ["high_impact", "High impact"],
                    ["downside", "Downside"],
                  ] as const
                ).map(([key, label]) => {
                  const items = byBucket[key];
                  if (!items.length) return null;
                  return (
                    <div key={key} className="fse-bucket">
                      <h3>{label}</h3>
                      <ul>
                        {items.map((s) => {
                          const on = selected.has(s.id);
                          const because = (s.reasoning?.because || []).slice(0, 3);
                          const chain = (s.chain || []).slice(0, 3);
                          return (
                            <li key={s.id} className={`fse-row ${on ? "is-on" : ""} ${key}`}>
                              <label className="fse-toggle">
                                <input
                                  type="checkbox"
                                  checked={on}
                                  onChange={() => toggle(s.id)}
                                />
                                <span className="fse-toggle-body">
                                  <span className="fse-row-title">{shortLabel(s.label)}</span>
                                  <span className="fse-row-impact">{pctRange(s.impact)}</span>
                                </span>
                              </label>
                              <Tip label={`About ${s.label}`}>
                                <strong>{s.label}</strong>
                                <span>
                                  {s.stage} · {s.project_certainty_pct}% certainty · ~
                                  {s.parcel_distance_mi?.toFixed(1)} mi · fit{" "}
                                  {Math.round(s.compatibility_score || 0)}/100 · {s.confidence}{" "}
                                  confidence
                                  {s.data_integrity ? ` · ${s.data_integrity}` : ""}
                                </span>
                                {because.length ? (
                                  <span>{because.map((b) => `• ${b}`).join(" ")}</span>
                                ) : null}
                                {chain.length ? (
                                  <span>Then: {chain.map((c) => c.label).join(" → ")}</span>
                                ) : null}
                              </Tip>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  );
                })}

                <div className="fse-custom">
                  <div className="fse-custom-row">
                    <input
                      type="text"
                      value={customText}
                      onChange={(e) => setCustomText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") submitCustom();
                      }}
                      placeholder="What if sewer reaches the property?"
                      aria-label="Custom scenario"
                    />
                    <button
                      type="button"
                      className="btn fse-custom-run"
                      disabled={pending}
                      onClick={submitCustom}
                    >
                      {pending ? "…" : "Add"}
                    </button>
                  </div>
                  {customError ? <p className="fse-error">{customError}</p> : null}
                </div>
              </div>

              <div className="fse-path">
                <div className="fse-path-head">
                  <h3>Value path</h3>
                  <Tip label="Path timing">
                    <strong>When value moves</strong>
                    <span>
                      Scenario line stays on baseline until markets would begin pricing the event,
                      then ramps to full recognition — not a same-day jump.
                    </span>
                  </Tip>
                </div>

                {summary ? (
                  <div className="fse-path-stats">
                    <div>
                      <span>Today</span>
                      <strong>{money(summary.today)}</strong>
                    </div>
                    <div>
                      <span>5 yr</span>
                      <strong>{money(hasSel ? summary.y5s : summary.y5b)}</strong>
                      {hasSel ? <em>vs {money(summary.y5b)}</em> : null}
                    </div>
                    <div>
                      <span>10 yr</span>
                      <strong>{money(hasSel ? summary.y10s : summary.y10b)}</strong>
                      {hasSel ? <em>vs {money(summary.y10b)}</em> : null}
                    </div>
                  </div>
                ) : null}

                {hasSel && summary ? (
                  <p className="fse-delta">
                    Extra vs baseline @ 10 yr:{" "}
                    <strong>
                      {Number(summary.add) >= 0 ? "+" : ""}
                      {money(summary.add)} ({Number(summary.addPct) >= 0 ? "+" : ""}
                      {summary.addPct}%)
                    </strong>
                  </p>
                ) : (
                  <p className="fse-delta muted">Select catalysts to diverge from baseline.</p>
                )}

                <PathChart path={chartPath} />
                <div className="fse-legend">
                  <span className="base">Baseline</span>
                  <span className="scen">With selected</span>
                </div>
                {combo.notes[0] ? <p className="fse-note">{combo.notes[0]}</p> : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
