"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
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
  data_integrity_note?: string;
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
    confidence_why?: string[];
  };
  historical_analogs?: {
    show_historical_analogs?: boolean;
    comparable_count?: number;
    analogs?: unknown[];
  };
  raw_text?: string;
};

type PathPoint = {
  year?: number;
  offset?: number;
  baseline_value?: number;
  scenario_value?: number;
  delta_value?: number;
  delta_pct?: number;
  recognition_weight?: number;
  value_usd?: number;
};

type Engine = {
  title?: string;
  button_label?: string;
  subtitle?: string;
  methodology_note?: string;
  opportunity?: {
    score?: number;
    label?: string;
    primary_reason?: string;
  };
  scenarios?: Scenario[];
  stress_cases?: Record<
    string,
    { scenario_ids?: string[]; label?: string; description?: string }
  >;
  baseline_points?: PathPoint[];
  detection?: {
    enabled?: boolean;
    count?: number;
    message?: string;
  };
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
  const fmt = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(0)}%`;
  if (lo === hi) return fmt(lo);
  // Keep sign-aware ordering for downside
  if (lo < 0 && hi < 0) return `${fmt(hi)} to ${fmt(lo)}`.replace("+", "");
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
    return {
      immediate: 0,
      rate: 0,
      hbu: 0,
      combined_p10: 0,
      combined_p50: 0,
      combined_p90: 0,
      interaction_notes: [] as string[],
    };
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
  let p10 = 0;
  let p50 = 0;
  let p90 = 0;
  const notes: string[] = [];

  const add = (item: Scenario, weight = 1) => {
    const ch = item.channels || {};
    const imp = item.impact || {};
    imm += Number(ch.immediate_repricing || 0) * weight;
    rate += Number(ch.appreciation_rate_change || 0) * weight;
    hbu += Number(ch.hbu_transformation || 0) * weight;
    p10 += Number(imp.p10 || 0) * weight;
    p50 += Number(imp.p50 || 0) * weight;
    p90 += Number(imp.p90 || 0) * weight;
  };

  for (const s of independents) add(s, 1);
  for (const [g, items] of groups) {
    if (items.length === 1) {
      add(items[0], 1);
      continue;
    }
    const sorted = [...items].sort(
      (a, b) => Math.abs(Number(b.impact?.p50 || 0)) - Math.abs(Number(a.impact?.p50 || 0)),
    );
    add(sorted[0], 1);
    sorted.slice(1).forEach((item, i) => {
      const w = 0.45 / (i + 1);
      add(item, w);
      notes.push(
        `Overlapping “${g.replace(/_/g, " ")}” catalysts: ${item.label} partially overlaps ${sorted[0].label}`,
      );
    });
  }

  const keys = new Set(selected.map((s) => s.event_key));
  const util = ["sewer_extension", "municipal_water", "electrical_expansion"].some((k) =>
    keys.has(k),
  );
  const entitle = ["zoning_change", "density_entitlement", "annexation"].some((k) => keys.has(k));
  if (util && entitle) {
    hbu += 0.035;
    p50 += 0.035;
    p10 += 0.021;
    p90 += 0.0455;
    notes.push(
      "Complementary interaction: utilities + entitlement unlock additional highest-and-best-use potential beyond either alone",
    );
  }

  return {
    immediate: softCap(imm),
    rate: softCap(rate, 0.04),
    hbu: softCap(hbu),
    combined_p10: softCap(p10),
    combined_p50: softCap(p50),
    combined_p90: softCap(p90),
    interaction_notes: notes,
  };
}

function applyPath(baseline: PathPoint[], combo: ReturnType<typeof combineImpacts>, selected: Scenario[]) {
  const forward = baseline.filter((p) => p.offset != null && Number(p.offset) >= 0);
  const series = forward.length ? forward : baseline;
  if (!series.length) return [] as PathPoint[];

  let start = 2;
  let full = 6;
  if (selected.length) {
    start = Math.min(
      ...selected.map((s) => Number(s.timing?.value_recognition_start_offset ?? 2)),
    );
    full = Math.max(
      ...selected.map((s) => Number(s.timing?.value_recognition_full_offset ?? 6)),
    );
  }

  const imm = combo.immediate;
  const rate = combo.rate;
  const hbu = combo.hbu;

  return series.map((pt) => {
    const y =
      pt.offset != null
        ? Number(pt.offset)
        : Number(pt.year || 0) - Number(series[0].year || 0);
    const baseV = Number(pt.value_usd ?? pt.baseline_value ?? 0);
    let w = 0;
    if (full <= start) w = y >= full ? 1 : 0;
    else if (y <= start) w = 0;
    else if (y >= full) w = 1;
    else w = (y - start) / (full - start);
    w = w * w * (3 - 2 * w);

    const rateMult = y > start ? Math.pow(1 + rate, Math.max(0, y - start)) : 1;
    const levelMult = 1 + (imm + hbu) * w;
    let scen = baseV * levelMult * (w > 0 ? rateMult : 1);
    if (w < 1 && y > start) scen = baseV + (scen - baseV) * Math.max(w, 0.35);

    return {
      year: pt.year,
      offset: y,
      baseline_value: Math.round(baseV),
      scenario_value: Math.round(scen),
      delta_value: Math.round(scen - baseV),
      delta_pct: baseV ? Math.round(((scen / baseV - 1) * 1000)) / 10 : 0,
      recognition_weight: Math.round(w * 1000) / 1000,
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

function PathChart({ path }: { path: PathPoint[] }) {
  if (path.length < 2) return null;
  const w = 640;
  const h = 180;
  const pad = { t: 16, r: 16, b: 28, l: 48 };
  const xs = path.map((p) => Number(p.offset || 0));
  const ys = path.flatMap((p) => [Number(p.baseline_value || 0), Number(p.scenario_value || 0)]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys) * 0.96;
  const maxY = Math.max(...ys) * 1.04;
  const sx = (x: number) =>
    pad.l + ((x - minX) / Math.max(0.001, maxX - minX)) * (w - pad.l - pad.r);
  const sy = (y: number) =>
    pad.t + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - pad.t - pad.b);

  const line = (key: "baseline_value" | "scenario_value") =>
    path
      .map((p, i) => `${i ? "L" : "M"}${sx(Number(p.offset || 0)).toFixed(1)},${sy(Number(p[key] || 0)).toFixed(1)}`)
      .join(" ");

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="fse-chart" role="img" aria-label="Baseline vs scenario value path">
      <path d={line("baseline_value")} className="fse-chart-base" />
      <path d={line("scenario_value")} className="fse-chart-scen" />
      <text x={pad.l} y={h - 8} className="fse-chart-label">
        Today
      </text>
      <text x={w - pad.r} y={h - 8} textAnchor="end" className="fse-chart-label">
        +{Math.round(maxX)} yrs
      </text>
    </svg>
  );
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
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [customOpen, setCustomOpen] = useState(false);
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
    const groups: Record<string, Scenario[]> = {
      likely: [],
      high_impact: [],
      downside: [],
    };
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

  useEffect(() => {
    if (!open) return;
    // Soft enter animation class handled via CSS; no work needed.
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
    const ids = engine.stress_cases?.[key]?.scenario_ids || [];
    setSelected(new Set(ids));
  };

  const submitCustom = () => {
    const text = customText.trim();
    if (!text) {
      setCustomError("Enter a scenario question first.");
      return;
    }
    setCustomError(null);
    startTransition(async () => {
      try {
        const res = (await landsignalApi.catalystSimulate(parcelId, {
          custom_text: text,
          scenario_ids: [...selected],
        })) as {
          custom?: { ok?: boolean; error?: string; scenario?: Scenario };
        };
        const custom = res.custom;
        if (!custom?.ok || !custom.scenario) {
          setCustomError(custom?.error || "Could not map that scenario.");
          return;
        }
        setCustomScenario(custom.scenario);
        setSelected((prev) => new Set([...prev, custom.scenario!.id]));
        setStress("custom");
        setExpandedId(custom.scenario.id);
        setCustomOpen(false);
        setCustomText("");
      } catch (e) {
        setCustomError(e instanceof Error ? e.message : "Request failed");
      }
    });
  };

  const opp = engine.opportunity;

  return (
    <section id="sec-catalyst" className="fse-wrap scroll-mt-20">
      <button
        type="button"
        className={`fse-launch ${open ? "is-open" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="fse-launch-label">{engine.button_label || "Future Scenario Engine"}</span>
        <span className="fse-launch-meta">
          {opp?.score != null ? (
            <>
              Catalyst Opportunity <strong>{opp.score}</strong>/100 · {opp.label}
            </>
          ) : (
            "Model surrounding change vs baseline Value Path"
          )}
        </span>
        <span className="fse-launch-chevron" aria-hidden>
          {open ? "−" : "+"}
        </span>
      </button>

      {open && (
        <div className="fse-panel panel">
          <header className="fse-head">
            <div>
              <p className="fse-eyebrow">Catalyst Simulator</p>
              <h2 className="display text-xl font-semibold">{engine.title || "Catalyst Simulator"}</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">
                {engine.subtitle ||
                  "See how future changes around this property could reshape its value."}
              </p>
            </div>
            {opp && (
              <div className="fse-opp">
                <div className="fse-opp-score">
                  <span>{opp.score}</span>
                  <small>/100</small>
                </div>
                <div>
                  <div className="fse-opp-label">Catalyst Opportunity · {opp.label}</div>
                  <p className="fse-opp-reason">{opp.primary_reason}</p>
                </div>
              </div>
            )}
          </header>

          <p className="fse-integrity">
            Auto scenarios are <strong>Hypothetical / Modeled</strong> — not observed municipal or
            corporate announcements unless separately cited.
          </p>

          {engine.detection?.message && (
            <p className="fse-detect">{engine.detection.message}</p>
          )}

          <div className="fse-stress" role="tablist" aria-label="Stress test">
            {(["baseline", "bull", "bear", "most_likely", "custom"] as const).map((key) => {
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

          <div className="fse-columns">
            <div className="fse-scenarios">
              {(
                [
                  ["likely", "Likely catalysts"],
                  ["high_impact", "High-impact catalysts"],
                  ["downside", "Downside risks"],
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
                        const openRow = expandedId === s.id;
                        return (
                          <li key={s.id} className={`fse-row ${on ? "is-on" : ""} ${key}`}>
                            <label className="fse-toggle">
                              <input
                                type="checkbox"
                                checked={on}
                                onChange={() => toggle(s.id)}
                              />
                              <span className="fse-toggle-body">
                                <span className="fse-row-title">{s.label}</span>
                                <span className="fse-row-impact">
                                  Potential impact: {pctRange(s.impact)}
                                </span>
                              </span>
                            </label>
                            <button
                              type="button"
                              className="fse-why-btn"
                              onClick={() => setExpandedId(openRow ? null : s.id)}
                            >
                              {openRow ? "Hide" : "Why"}
                            </button>
                            {openRow && (
                              <div className="fse-detail">
                                <div className="fse-meta-grid">
                                  <div>
                                    <span>Status</span>
                                    <strong>{s.stage}</strong>
                                  </div>
                                  <div>
                                    <span>Project certainty</span>
                                    <strong>{s.project_certainty_pct}%</strong>
                                  </div>
                                  <div>
                                    <span>Parcel distance</span>
                                    <strong>{s.parcel_distance_mi?.toFixed(1)} mi</strong>
                                  </div>
                                  <div>
                                    <span>Est. completion</span>
                                    <strong>
                                      ~{s.estimated_completion_offset_years?.toFixed(0)} yrs
                                    </strong>
                                  </div>
                                  <div>
                                    <span>Compatibility</span>
                                    <strong>{Math.round(s.compatibility_score || 0)}/100</strong>
                                  </div>
                                  <div>
                                    <span>Confidence</span>
                                    <strong>{s.confidence}</strong>
                                  </div>
                                </div>
                                <p className="fse-integrity-tag">{s.data_integrity}</p>
                                {s.reasoning?.headline && (
                                  <h4>{s.reasoning.headline}</h4>
                                )}
                                <ul className="fse-because">
                                  {(s.reasoning?.because || []).map((b) => (
                                    <li key={b}>{b}</li>
                                  ))}
                                </ul>
                                {(s.reasoning?.counterfactors || []).length > 0 && (
                                  <div className="fse-counter">
                                    <span>Counterfactors</span>
                                    <ul>
                                      {s.reasoning?.counterfactors?.map((c) => (
                                        <li key={c}>{c}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                                {(s.chain || []).length > 0 && (
                                  <div className="fse-chain">
                                    <span>Scenario chain</span>
                                    <ol>
                                      <li>{s.label}</li>
                                      {s.chain?.map((c) => (
                                        <li key={c.key || c.label}>{c.label}</li>
                                      ))}
                                    </ol>
                                  </div>
                                )}
                                {s.historical_analogs?.show_historical_analogs ? (
                                  <p className="fse-analogs">
                                    Historical analogues: {s.historical_analogs.comparable_count}{" "}
                                    comparable projects
                                  </p>
                                ) : (
                                  <p className="fse-analogs muted">
                                    Historical matched-property comps not yet attached — impact
                                    shown without false statistical precision.
                                  </p>
                                )}
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}

              <div className="fse-custom">
                {!customOpen ? (
                  <button type="button" className="fse-add" onClick={() => setCustomOpen(true)}>
                    + Add Custom Scenario
                  </button>
                ) : (
                  <div className="fse-custom-box">
                    <label htmlFor="fse-custom-input">Custom scenario</label>
                    <textarea
                      id="fse-custom-input"
                      rows={3}
                      value={customText}
                      onChange={(e) => setCustomText(e.target.value)}
                      placeholder='e.g. “What if Walmart opened one mile away?”'
                    />
                    {customError && <p className="fse-error">{customError}</p>}
                    <div className="fse-custom-actions">
                      <button type="button" className="btn" disabled={pending} onClick={submitCustom}>
                        {pending ? "Translating…" : "Run scenario"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => {
                          setCustomOpen(false);
                          setCustomError(null);
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="fse-path">
              <h3>Interactive Value Path</h3>
              <p className="text-sm text-[var(--muted)]">
                Baseline vs scenario-adjusted. Impact ramps from the recognition window — not applied
                entirely today.
              </p>
              {summary && (
                <div className="fse-path-stats">
                  <div>
                    <span>Today</span>
                    <strong>{money(summary.today)}</strong>
                  </div>
                  <div>
                    <span>5 years · baseline</span>
                    <strong>{money(summary.y5b)}</strong>
                    {selectedScenarios.length > 0 && (
                      <em>With catalysts: {money(summary.y5s)}</em>
                    )}
                  </div>
                  <div>
                    <span>10 years · baseline</span>
                    <strong>{money(summary.y10b)}</strong>
                    {selectedScenarios.length > 0 && (
                      <em>With catalysts: {money(summary.y10s)}</em>
                    )}
                  </div>
                  {selectedScenarios.length > 0 && (
                    <div className="fse-path-delta">
                      <span>Additional scenario value (10 yr)</span>
                      <strong>
                        {Number(summary.add) >= 0 ? "+" : ""}
                        {money(summary.add)} · {Number(summary.addPct) >= 0 ? "+" : ""}
                        {summary.addPct}%
                      </strong>
                    </div>
                  )}
                </div>
              )}
              <PathChart path={path.length ? path : applyPath(engine.baseline_points || [], combineImpacts([]), [])} />
              <div className="fse-legend">
                <span className="base">Baseline</span>
                <span className="scen">Scenario-adjusted</span>
              </div>
              {combo.interaction_notes.length > 0 && (
                <ul className="fse-notes">
                  {combo.interaction_notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              )}
              {engine.methodology_note && (
                <p className="fse-method">{engine.methodology_note}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
