"use client";

import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

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

function shortMoney(v: number): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const a = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (a >= 1_000_000) {
    const m = a / 1_000_000;
    return `${sign}$${m >= 10 ? Math.round(m) : m.toFixed(1)}M`;
  }
  if (a >= 10_000) return `${sign}$${Math.round(a / 1000)}k`;
  if (a >= 1000) return `${sign}$${(a / 1000).toFixed(1)}k`;
  return `${sign}$${Math.round(a)}`;
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
  if (lo < 0 && hi <= 0) return `${fmt(Math.min(lo, hi))} to ${fmt(Math.max(lo, hi))}`;
  return `${fmt(Math.min(lo, hi))} to ${fmt(Math.max(lo, hi))}`;
}

function dollarRange(impact?: Impact, baseToday?: number | null): string | null {
  if (!impact || !(baseToday && baseToday > 0)) return null;
  const lo = Number(impact.display_low_pct);
  const hi = Number(impact.display_high_pct);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
  const a = (baseToday * lo) / 100;
  const b = (baseToday * hi) / 100;
  const low = Math.min(a, b);
  const high = Math.max(a, b);
  const fmt = (x: number) => `${x > 0 ? "+" : ""}${shortMoney(x)}`.replace("+-", "-");
  if (Math.abs(high - low) < 50) return fmt(low);
  return `${fmt(low)} to ${fmt(high)}`;
}

function softCap(x: number, cap = 0.85): number {
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
  const at = (y: number) =>
    path.find((p) => Number(p.offset) >= y) || path[path.length - 1];
  const today = path[0];
  const horizons = [5, 10, 20, 40, 60, 80] as const;
  const years: Record<number, { b: number; s: number }> = {};
  for (const y of horizons) {
    const p = at(y);
    years[y] = {
      b: Number(p.baseline_value || 0),
      s: Number(p.scenario_value || 0),
    };
  }
  const y10 = years[10];
  return {
    today: today.baseline_value,
    years,
    add: y10.s - y10.b,
    addPct: y10.b ? Math.round(((y10.s / y10.b - 1) * 1000)) / 10 : 0,
  };
}

function Tip({ label, children }: { label: string; children: ReactNode }) {
  const [on, setOn] = useState(false);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    if (!on || !btnRef.current) return;
    const place = () => {
      const r = btnRef.current!.getBoundingClientRect();
      const width = Math.min(304, window.innerWidth - 24);
      let left = r.right - width;
      left = Math.max(12, Math.min(left, window.innerWidth - width - 12));
      const top = r.bottom + 8;
      setPos({ top, left, width });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [on]);

  useEffect(() => {
    if (!on) return;
    const close = () => setOn(false);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    // delay so the opening click doesn't immediately close
    const t = window.setTimeout(() => {
      window.addEventListener("click", close);
    }, 0);
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("click", close);
    };
  }, [on]);

  return (
    <span className={`help-tip tone-panel fse-tip ${on ? "is-open" : ""}`} onClick={(e) => e.stopPropagation()}>
      <button
        ref={btnRef}
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
      {on && pos && typeof document !== "undefined"
        ? createPortal(
            <span
              className="fse-tip-portal"
              role="tooltip"
              style={{ top: pos.top, left: pos.left, width: pos.width }}
              onClick={(e) => e.stopPropagation()}
            >
              {children}
            </span>,
            document.body,
          )
        : null}
    </span>
  );
}

type DollarParticle = {
  id: number;
  x: number;
  delay: number;
  size: number;
  drift: number;
  tone: "up" | "down";
  glyph: string;
};

function DollarBurst({ burst }: { burst: { id: number; tone: "up" | "down" } | null }) {
  const [parts, setParts] = useState<DollarParticle[]>([]);

  useEffect(() => {
    if (!burst) return;
    const next: DollarParticle[] = Array.from({ length: 7 }, (_, i) => ({
      id: burst.id * 100 + i,
      x: 18 + Math.random() * 64,
      delay: Math.random() * 0.22,
      size: 12 + Math.random() * 10,
      drift: (Math.random() - 0.5) * 48,
      tone: burst.tone,
      glyph: "$",
    }));
    setParts(next);
    const t = window.setTimeout(() => setParts([]), 1300);
    return () => window.clearTimeout(t);
  }, [burst]);

  if (!parts.length) return null;
  return (
    <div className="fse-dollar-burst" aria-hidden>
      {parts.map((p) => (
        <span
          key={p.id}
          className={`fse-dollar ${p.tone}`}
          style={{
            left: `${p.x}%`,
            animationDelay: `${p.delay}s`,
            fontSize: `${p.size}px`,
            ["--drift" as string]: `${p.drift}px`,
          }}
        >
          {p.glyph}
        </span>
      ))}
    </div>
  );
}

function PathChart({
  path,
  active,
}: {
  path: PathPoint[];
  active: boolean;
}) {
  const [hoverX, setHoverX] = useState<number | null>(null);
  if (path.length < 2) return null;

  const marks = [0, 5, 10, 20, 40, 60, 80];
  const w = 560;
  const h = 128;
  const pad = { t: 10, r: 10, b: 20, l: 6 };
  const xs = path.map((p) => Number(p.offset || 0));
  const ys = path.flatMap((p) => [Number(p.baseline_value || 0), Number(p.scenario_value || 0)]);
  const minX = Math.min(...xs);
  const maxX = Math.max(Math.max(...xs), 80);
  const minY = Math.min(...ys) * 0.98;
  const maxY = Math.max(...ys) * 1.02 || 1;
  const sx = (x: number) =>
    pad.l + ((x - minX) / Math.max(0.001, maxX - minX)) * (w - pad.l - pad.r);
  const sy = (y: number) =>
    pad.t + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - pad.t - pad.b);

  const atYear = (y: number) => {
    const hit = path.find((p) => Number(p.offset) >= y) || path[path.length - 1];
    return {
      year: y,
      base: Number(hit.baseline_value || 0),
      scen: Number(hit.scenario_value || 0),
    };
  };

  const line = (key: "baseline_value" | "scenario_value") =>
    path
      .map(
        (p, i) =>
          `${i ? "L" : "M"}${sx(Number(p.offset || 0)).toFixed(1)},${sy(Number(p[key] || 0)).toFixed(1)}`,
      )
      .join(" ");

  const band = (() => {
    if (!active) return "";
    const forward = path
      .map((p) => `${sx(Number(p.offset || 0)).toFixed(1)},${sy(Number(p.scenario_value || 0)).toFixed(1)}`)
      .join(" ");
    const back = [...path]
      .reverse()
      .map((p) => `${sx(Number(p.offset || 0)).toFixed(1)},${sy(Number(p.baseline_value || 0)).toFixed(1)}`)
      .join(" ");
    return `M${forward} L${back} Z`;
  })();

  const hoverYear =
    hoverX == null
      ? null
      : Math.round(minX + ((hoverX - pad.l) / Math.max(1, w - pad.l - pad.r)) * (maxX - minX));
  const hover = hoverYear == null ? null : atYear(Math.max(0, Math.min(maxX, hoverYear)));
  const last = atYear(Math.min(80, maxX));
  const delta = last.scen - last.base;
  const deltaPct = last.base ? ((last.scen / last.base - 1) * 100) : 0;

  const onMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * w;
    setHoverX(Math.max(pad.l, Math.min(w - pad.r, x)));
  };

  return (
    <div className="fse-chart-wrap">
      <div className="fse-chart-readout">
        {hover ? (
          <>
            <span>{hover.year === 0 ? "Today" : `Year ${hover.year}`}</span>
            <strong>{shortMoney(active ? hover.scen : hover.base)}</strong>
            {active ? <em>vs {shortMoney(hover.base)}</em> : null}
          </>
        ) : active ? (
          <>
            <span>80 yr delta</span>
            <strong className={delta >= 0 ? "up" : "down"}>
              {delta >= 0 ? "+" : ""}
              {shortMoney(delta)} ({deltaPct >= 0 ? "+" : ""}
              {deltaPct.toFixed(0)}%)
            </strong>
          </>
        ) : (
          <>
            <span>Drag chart to inspect</span>
            <strong>{shortMoney(last.base)}</strong>
            <em>@ 80 yr baseline</em>
          </>
        )}
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="fse-chart"
        role="img"
        aria-label="Value path"
        onPointerMove={onMove}
        onPointerLeave={() => setHoverX(null)}
      >
        {marks.map((y) => (
          <line
            key={y}
            x1={sx(y)}
            x2={sx(y)}
            y1={pad.t}
            y2={h - pad.b}
            className="fse-chart-grid"
          />
        ))}
        {band ? <path d={band} className={`fse-chart-band ${delta >= 0 ? "up" : "down"}`} /> : null}
        <path d={line("baseline_value")} className="fse-chart-base" />
        <path d={line("scenario_value")} className={`fse-chart-scen ${active ? "is-on" : ""}`} />
        {marks.map((y) => {
          const pt = atYear(y);
          const val = active ? pt.scen : pt.base;
          return (
            <circle
              key={`d-${y}`}
              cx={sx(y)}
              cy={sy(val)}
              r={y === 0 ? 2.8 : 2.2}
              className={`fse-chart-dot ${active ? "scen" : "base"}`}
            />
          );
        })}
        {hover ? (
          <>
            <line
              x1={sx(hover.year)}
              x2={sx(hover.year)}
              y1={pad.t}
              y2={h - pad.b}
              className="fse-chart-hover"
            />
            <circle
              cx={sx(hover.year)}
              cy={sy(active ? hover.scen : hover.base)}
              r={3.4}
              className="fse-chart-dot hover"
            />
          </>
        ) : null}
        {marks.map((y) => (
          <text key={`t-${y}`} x={sx(y)} y={h - 4} textAnchor="middle" className="fse-chart-label">
            {y === 0 ? "0" : y}
          </text>
        ))}
      </svg>
    </div>
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
  engine,
}: {
  parcelId?: string;
  engine: Engine | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [stress, setStress] = useState("custom");
  const [burst, setBurst] = useState<{ id: number; tone: "up" | "down" } | null>(null);
  const burstSeq = useRef(0);

  const scenarios = useMemo(() => [...(engine?.scenarios || [])], [engine]);

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
  const baseToday = useMemo(() => {
    const pts = engine?.baseline_points || [];
    const today =
      pts.find((p) => Number(p.offset) === 0) ||
      pts.find((p) => (p.offset == null || Number(p.offset) >= 0) && (p.value_usd || p.baseline_value));
    const fromPt = Number(today?.value_usd ?? today?.baseline_value ?? 0);
    if (fromPt > 0) return fromPt;
    const fromSummary = Number(summary?.today ?? 0);
    return fromSummary > 0 ? fromSummary : null;
  }, [engine?.baseline_points, summary?.today]);

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

  const applyStress = (key: string) => {
    setStress(key);
    const ids = engine.stress_cases?.[key]?.scenario_ids || [];
    setSelected(new Set(ids));
    if (key === "bull" || key === "bear") {
      burstSeq.current += 1;
      setBurst({ id: burstSeq.current, tone: key === "bear" ? "down" : "up" });
    }
  };

  const opp = engine.opportunity;
  const hasSel = selectedScenarios.length > 0;

  const toggle = (id: string, scenario?: Scenario) => {
    setStress("custom");
    setSelected((prev) => {
      const next = new Set(prev);
      const turningOn = !next.has(id);
      if (turningOn) next.add(id);
      else next.delete(id);
      if (turningOn) {
        const central = Number(scenario?.impact?.central_pct ?? 0);
        const tone: "up" | "down" =
          central < 0 || scenario?.bucket === "downside" ? "down" : "up";
        // High-impact bear items are still bucket=high_impact but negative
        const finalTone: "up" | "down" = central < 0 ? "down" : tone === "down" ? "down" : "up";
        burstSeq.current += 1;
        setBurst({ id: burstSeq.current, tone: finalTone });
      }
      return next;
    });
  };

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
            <DollarBurst burst={burst} />
            <header className="fse-modal-head">
              <div className="fse-modal-title-row">
                <h2 className="display fse-modal-title">Future Scenario Engine</h2>
                {opp?.score != null ? (
                  <span className="fse-title-score" title="Catalyst Opportunity">
                    {opp.score}
                    <small>/100</small>
                    <em>{opp.label}</em>
                  </span>
                ) : null}
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

            {opp?.primary_reason ? (
              <p className="fse-opp-reason-line">{opp.primary_reason}</p>
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

            <div className="fse-work">
              <nav className="fse-steps" aria-label="How to use">
                <div className={`fse-step ${!hasSel ? "is-active" : "is-done"}`}>
                  <span className="fse-step-num" title="Choose catalysts">
                    1
                  </span>
                </div>
                <div className="fse-step-rail" aria-hidden />
                <div className={`fse-step ${hasSel ? "is-active" : ""}`}>
                  <span className="fse-step-num" title="See value shift">
                    2
                  </span>
                </div>
              </nav>

              <div className="fse-body">
              <div className="fse-scenarios">
                {(
                  [
                    ["likely", "Likely"],
                    ["downside", "Downside"],
                    ["high_impact", "High impact"],
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
                          const dollars = dollarRange(s.impact, baseToday);
                          const isBear = Number(s.impact?.central_pct) < 0;
                          return (
                            <li
                              key={s.id}
                              className={`fse-row ${on ? "is-on" : ""} ${key} ${isBear ? "is-bear" : ""}`}
                            >
                              <label className="fse-toggle">
                                <input
                                  type="checkbox"
                                  checked={on}
                                  onChange={() => toggle(s.id, s)}
                                />
                                <span className="fse-toggle-body">
                                  <span className="fse-row-title">{shortLabel(s.label)}</span>
                                  <span className="fse-row-impact">
                                    {pctRange(s.impact)}
                                    {dollars ? <span className="fse-row-dollars">{dollars}</span> : null}
                                  </span>
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
                                {dollars ? (
                                  <span>
                                    Modeled value move vs today (~{money(baseToday)}): {dollars}
                                  </span>
                                ) : null}
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
                    <div className="fse-path-today">
                      <span>Today</span>
                      <strong>{money(summary.today)}</strong>
                    </div>
                    <div className="fse-path-years">
                      {([5, 10, 20, 40, 60, 80] as const).map((y) => {
                        const row = summary.years[y];
                        const shown = hasSel ? row.s : row.b;
                        return (
                          <div key={y} className="fse-path-bubble">
                            <span>{y} yr</span>
                            <strong title={money(shown)}>{shortMoney(shown)}</strong>
                            {hasSel ? (
                              <em title={`Baseline ${money(row.b)}`}>vs {shortMoney(row.b)}</em>
                            ) : null}
                          </div>
                        );
                      })}
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

                <PathChart path={chartPath} active={hasSel} />
                <div className="fse-legend">
                  <span className="base">Baseline</span>
                  <span className="scen">With selected</span>
                </div>
                {combo.notes[0] ? <p className="fse-note">{combo.notes[0]}</p> : null}
              </div>
            </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
