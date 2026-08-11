"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  cpiFromMeta,
  withInflation,
  type InflationMeta,
  type MoneyMode,
} from "@/lib/inflation";
import { MoneyModeControl, moneyModeShort } from "@/components/money-mode-control";
import { BuyingPowerLogic } from "@/components/buying-power-logic";
import {
  buildHoldCasePath,
  enrichHoldEndpoint,
  rateFromFactors,
  type HoldCaseKey,
  type ToggleFactor,
} from "@/lib/hold-path";

type PathPoint = {
  year_offset: number;
  land_usd?: number;
  exit_usd?: number;
  noi_usd?: number;
  cumulative_rent_usd?: number;
  cumulative_carry_usd?: number;
  total_back_usd?: number;
  gain_usd?: number;
  starting_mark_usd?: number;
  purchase_usd?: number;
};

type CaseEndpoint = {
  irr?: number | null;
  irr_display?: string;
  irr_real?: number | null;
  irr_real_display?: string;
  exit_usd?: number | null;
  exit_usd_today?: number | null;
  land_mark_usd?: number | null;
  cumulative_rent_usd?: number | null;
  cumulative_rent_usd_today?: number | null;
  total_back_usd?: number | null;
  total_back_usd_today?: number | null;
  gain_usd?: number | null;
  gain_usd_today?: number | null;
  path?: PathPoint[];
  starting_noi?: number | null;
  effective_annual_used?: number | null;
  case_label?: string;
  purchase_usd?: number | null;
  hold_years?: number;
};

type Factor = {
  key?: string;
  label?: string;
  bps?: number;
  pct_points?: number;
  direction?: string;
  kind?: string;
  plain?: string;
};

type ReturnIntel = {
  available?: boolean;
  reason?: string;
  purchase_usd?: number | null;
  mark_usd?: number | null;
  hold_years?: number;
  windows?: number[];
  inflation?: InflationMeta | null;
  model?: {
    effective_annual?: number;
    effective_annual_display?: string;
    uncertainty?: number;
    usable_frac?: number;
    flood_carry_frac?: number;
    factor_count?: number;
    place?: string;
    strategy?: string;
    acres?: number;
    state?: string;
    provider?: string;
    prime_pct?: number;
  };
  factors?: Factor[];
  all_factors?: Factor[];
  toggle_factors?: ToggleFactor[];
  endpoints?: Record<string, Record<string, CaseEndpoint>>;
  paths_100?: Record<
    string,
    {
      path?: PathPoint[];
      case_label?: string;
      purchase_usd?: number;
      starting_noi?: number;
      effective_annual_used?: number;
    }
  >;
  summary?: string;
  method?: string;
  horizon_notes?: Record<string, string>;
};

/** Legacy scenario shape — only used if return_intelligence is missing. */
type LegacyCase = {
  case?: string;
  case_label?: string;
  case_type?: string;
  summary?: string;
  plain_english?: string;
  numbers?: Record<string, unknown>;
  irr?: number | string | null;
  noi?: number;
  annual_appreciation?: number;
  annual_appreciation_display?: string;
  purchase_price?: number;
  cash_rent_per_acre?: number;
};

/** Hold-period presets on LandSignal return path. */
const HOLD_YEARS = [1, 3, 5, 10, 15, 25, 40, 60, 80, 100] as const;
const CASE_ORDER = ["BEAR", "BASE", "BULL"] as const;

function money(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function clampHoldYears(n: number): number {
  if (!Number.isFinite(n)) return 10;
  return Math.max(1, Math.min(100, Math.round(n)));
}

/** Newton IRR for cashflow series starting at t=0. */
function solveIrr(flows: number[]): number | null {
  if (flows.length < 2) return null;
  let r = 0.08;
  for (let i = 0; i < 50; i++) {
    let npv = 0;
    let d = 0;
    for (let t = 0; t < flows.length; t++) {
      const den = Math.pow(1 + r, t);
      if (!Number.isFinite(den) || den === 0) return null;
      npv += flows[t] / den;
      if (t > 0) d -= (t * flows[t]) / (den * (1 + r));
    }
    if (Math.abs(d) < 1e-12) break;
    const next = r - npv / d;
    if (!Number.isFinite(next)) break;
    if (Math.abs(next - r) < 1e-7) return next;
    r = Math.max(-0.95, Math.min(5, next));
  }
  return Number.isFinite(r) ? r : null;
}

/** Slice a 100-yr path to an exact hold and recompute endpoint stats. */
function endpointFromPath(
  full: { path?: PathPoint[]; purchase_usd?: number; starting_noi?: number; effective_annual_used?: number; case_label?: string } | undefined,
  holdYears: number,
  fallbackPurchase?: number | null,
): CaseEndpoint | null {
  const years = clampHoldYears(holdYears);
  const path = (full?.path || []).filter((p) => Number(p.year_offset) >= 1 && Number(p.year_offset) <= years);
  const purchase = Number(full?.purchase_usd || fallbackPurchase || 0);
  if (!path.length) return null;
  const last = path[path.length - 1];
  const flows = [-purchase];
  for (let i = 0; i < path.length; i++) {
    const noi = Number(path[i].noi_usd || 0);
    if (i === path.length - 1) {
      flows.push(noi + Number(path[i].exit_usd ?? path[i].land_usd ?? 0));
    } else {
      flows.push(noi);
    }
  }
  const irr = purchase > 0 ? solveIrr(flows) : null;
  return {
    irr,
    irr_display: irr != null ? `${(irr * 100).toFixed(1)}%/yr` : "n/a",
    exit_usd: last.exit_usd ?? last.land_usd ?? null,
    land_mark_usd: last.land_usd ?? null,
    cumulative_rent_usd: last.cumulative_rent_usd ?? 0,
    total_back_usd: last.total_back_usd ?? null,
    gain_usd: last.gain_usd ?? (last.total_back_usd != null && purchase ? last.total_back_usd - purchase : null),
    path,
    starting_noi: full?.starting_noi ?? null,
    effective_annual_used: full?.effective_annual_used ?? null,
    case_label: full?.case_label,
    purchase_usd: purchase || null,
    hold_years: years,
  };
}

function shortMoney(v: number): string {
  const a = Math.abs(v);
  if (a >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (a >= 10_000) return `$${Math.round(v / 1000)}k`;
  if (a >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  return money(v);
}

function caseLabel(key: string): string {
  if (key === "BEAR" || key === "DOWNSIDE" || key === "STRESS") return "Cautious";
  if (key === "BULL" || key === "UPSIDE") return "Optimistic";
  return "Typical";
}

function caseTone(key: string): string {
  if (key === "BEAR" || key === "DOWNSIDE" || key === "STRESS") return "bear";
  if (key === "BULL" || key === "UPSIDE") return "bull";
  return "base";
}

function FactorIcon({ name }: { name?: string }) {
  const k = (name || "").toLowerCase();
  const common = {
    className: "return-factor-icon",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };
  if (k.includes("flood") || k.includes("water")) {
    return (
      <svg {...common}>
        <path d="M12 3c-3 5-7 8-7 12a7 7 0 0 0 14 0c0-4-4-7-7-12z" />
      </svg>
    );
  }
  if (k.includes("soil") || k.includes("farm")) {
    return (
      <svg {...common}>
        <path d="M4 18c2-4 5-6 8-6s6 2 8 6" />
        <path d="M12 12V5" />
        <path d="M9 7c1 1 2 2 3 2s2-1 3-2" />
      </svg>
    );
  }
  if (k.includes("wet")) {
    return (
      <svg {...common}>
        <path d="M3 14c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2" />
        <path d="M3 18c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2" />
      </svg>
    );
  }
  if (k.includes("growth") || k.includes("area") || k.includes("pace")) {
    return (
      <svg {...common}>
        <path d="M4 18V10" />
        <path d="M10 18V6" />
        <path d="M16 18v-8" />
        <path d="M20 18V4" />
      </svg>
    );
  }
  if (k.includes("power") || k.includes("line") || k.includes("energy")) {
    return (
      <svg {...common}>
        <path d="M13 2 6 13h5l-1 9 8-12h-5l0-8z" />
      </svg>
    );
  }
  if (k.includes("access") || k.includes("road")) {
    return (
      <svg {...common}>
        <path d="M4 19 12 4l8 15" />
        <path d="M9 14h6" />
      </svg>
    );
  }
  if (k.includes("risk")) {
    return (
      <svg {...common}>
        <path d="M12 3 3 20h18L12 3z" />
        <path d="M12 9v5" />
        <path d="M12 17h.01" />
      </svg>
    );
  }
  if (k.includes("channel") || k.includes("sold") || k.includes("seller")) {
    return (
      <svg {...common}>
        <path d="M4 7h16" />
        <path d="M4 12h10" />
        <path d="M4 17h13" />
        <circle cx="18" cy="12" r="2" />
      </svg>
    );
  }
  if (k.includes("strateg") || k.includes("use") || k.includes("fit")) {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 8v4l3 2" />
      </svg>
    );
  }
  if (k.includes("liquid") || k.includes("scarce") || k.includes("rare") || k.includes("resale")) {
    return (
      <svg {...common}>
        <path d="M7 7h10v10H7z" />
        <path d="M3 12h4M17 12h4" />
      </svg>
    );
  }
  if (k.includes("complete") || k.includes("file")) {
    return (
      <svg {...common}>
        <path d="M7 3h7l4 4v14H7z" />
        <path d="M14 3v4h4" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="8" />
      <path d="M8 12h8" />
    </svg>
  );
}

/** Interactive multi-factor return path — curved year-by-year, not a flat diagonal. */
export function ReturnVisual({
  intel,
  cases: legacyCases,
  entryUsd,
  markUsd,
  annualRate,
  moneyMode: moneyModeProp,
  onMoneyModeChange,
}: {
  intel?: ReturnIntel | null;
  cases?: LegacyCase[];
  identity?: string;
  entryLabel?: string;
  markLabel?: string;
  entryUsd?: number | null;
  markUsd?: number | null;
  annualRate?: number | null;
  moneyMode?: MoneyMode;
  onMoneyModeChange?: (m: MoneyMode) => void;
}) {
  const windows = (intel?.windows?.length ? intel.windows : [...HOLD_YEARS]).filter((w) =>
    HOLD_YEARS.includes(w as (typeof HOLD_YEARS)[number]),
  );
  const initialHold =
    intel?.hold_years && windows.includes(intel.hold_years) ? intel.hold_years : 10;
  const [holdPreset, setHoldPreset] = useState<number | "custom">(initialHold);
  const [customHold, setCustomHold] = useState(String(initialHold));
  const holdYears =
    holdPreset === "custom" ? clampHoldYears(Number(customHold) || initialHold) : holdPreset;
  const [activeCase, setActiveCase] = useState<(typeof CASE_ORDER)[number]>("BASE");
  const [scrubYear, setScrubYear] = useState(holdYears);
  const [dragging, setDragging] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [casesHelpOpen, setCasesHelpOpen] = useState(false);
  const [moneyModeLocal, setMoneyModeLocal] = useState<MoneyMode>("today");
  const moneyMode = moneyModeProp ?? moneyModeLocal;
  const setMoneyMode = onMoneyModeChange ?? setMoneyModeLocal;
  const cpi = cpiFromMeta(intel?.inflation);
  const cpiDisplay = intel?.inflation?.cpi_display || `${(cpi * 100).toFixed(1)}%/yr`;

  const toggleFactors: ToggleFactor[] = useMemo(() => {
    const raw = (intel?.toggle_factors || intel?.all_factors || intel?.factors || []) as ToggleFactor[];
    return raw.filter((f) => f && f.key);
  }, [intel?.toggle_factors, intel?.all_factors, intel?.factors]);

  const factorSig = useMemo(
    () =>
      toggleFactors
        .map((f) => `${f.key}:${f.default_on !== false ? 1 : 0}:${f.toggleable === false ? 0 : 1}`)
        .join("|"),
    [toggleFactors],
  );

  const defaultsFromFactors = useCallback((list: ToggleFactor[]) => {
    const next: Record<string, boolean> = {};
    for (const f of list) {
      const id = String(f.key);
      next[id] = f.toggleable === false ? true : f.default_on !== false;
    }
    return next;
  }, []);

  const [enabledFactors, setEnabledFactors] = useState<Record<string, boolean>>({});
  const screensRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setEnabledFactors(defaultsFromFactors(toggleFactors));
  }, [factorSig, toggleFactors, defaultsFromFactors]);

  const resetScreens = useCallback(() => {
    setEnabledFactors(defaultsFromFactors(toggleFactors));
  }, [defaultsFromFactors, toggleFactors]);

  const jumpToScreens = useCallback(() => {
    const el = screensRef.current;
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    el.classList.remove("is-flash");
    // Force reflow so the flash animation can replay.
    void el.offsetWidth;
    el.classList.add("is-flash");
    window.setTimeout(() => el.classList.remove("is-flash"), 1200);
  }, []);

  useEffect(() => {
    setScrubYear((y) => Math.max(1, Math.min(holdYears, y)));
  }, [holdYears]);

  useEffect(() => {
    if (!casesHelpOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setCasesHelpOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [casesHelpOpen]);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const available = intel?.available !== false && Boolean(intel?.endpoints || intel?.paths_100 || toggleFactors.length);

  const purchase = Number(intel?.purchase_usd || entryUsd || markUsd || 0);
  const mark = Number(intel?.mark_usd || markUsd || purchase || 0);

  const liveModel = useMemo(() => {
    const pace = rateFromFactors(toggleFactors, enabledFactors);
    const floodOn = enabledFactors.flood_carry !== false;
    const wetOn = enabledFactors.wetland_usable !== false;
    const taxOn = enabledFactors.property_tax !== false;
    const exitOn = enabledFactors.exit_friction !== false;
    const fadeOn = enabledFactors.long_hold_fade !== false;
    const floodF = toggleFactors.find((f) => f.key === "flood_carry");
    const wetF = toggleFactors.find((f) => f.key === "wetland_usable");
    const taxF = toggleFactors.find((f) => f.key === "property_tax");
    const exitF = toggleFactors.find((f) => f.key === "exit_friction");
    return {
      annual: pace || Number(intel?.model?.effective_annual || annualRate || 0.028),
      floodCarryFrac: floodOn
        ? Number(floodF?.flood_carry_frac ?? intel?.model?.flood_carry_frac ?? 0)
        : 0,
      usableFrac: wetOn ? Number(wetF?.usable_frac ?? intel?.model?.usable_frac ?? 1) : 1,
      taxFrac: taxOn ? Number(taxF?.tax_frac ?? 0.009) : 0,
      exitHaircutAdd: exitOn ? Number(exitF?.exit_haircut_add ?? 0) : 0,
      applyFade: fadeOn,
    };
  }, [toggleFactors, enabledFactors, intel, annualRate]);

  const endpointsAtHold = useMemo(() => {
    const out: Record<string, CaseEndpoint> = {};
    const canLive = purchase > 0 && mark > 0 && toggleFactors.length > 0;
    for (const c of CASE_ORDER) {
      if (canLive) {
        const built = buildHoldCasePath({
          purchase,
          mark,
          annual: liveModel.annual,
          holdYears,
          caseKey: c as HoldCaseKey,
          uncertainty: Number(intel?.model?.uncertainty ?? 0.35),
          acres: Number(intel?.model?.acres ?? 1),
          strategy: intel?.model?.strategy,
          provider: intel?.model?.provider,
          floodCarryFrac: liveModel.floodCarryFrac,
          usableFrac: liveModel.usableFrac,
          exitHaircutAdd: liveModel.exitHaircutAdd,
          taxFrac: liveModel.taxFrac,
          applyFade: liveModel.applyFade,
          primePct: intel?.model?.prime_pct,
          state: intel?.model?.state,
        });
        const enriched = enrichHoldEndpoint(built, cpi);
        if (enriched) out[c] = enriched as CaseEndpoint;
        continue;
      }
      const fromApi = intel?.endpoints?.[String(holdYears)]?.[c];
      const base =
        fromApi ||
        endpointFromPath(intel?.paths_100?.[c], holdYears, intel?.purchase_usd) ||
        null;
      const enriched = withInflation(base, cpi);
      if (enriched) out[c] = enriched;
    }
    return out;
  }, [
    purchase,
    mark,
    toggleFactors.length,
    liveModel,
    holdYears,
    intel,
    cpi,
  ]);

  const endpoint = endpointsAtHold[activeCase];
  const path = useMemo(() => {
    const pts = (endpoint?.path || []).filter(
      (p) => Number(p.year_offset) >= 1 && Number(p.year_offset) <= holdYears,
    );
    return pts;
  }, [endpoint?.path, holdYears]);

  const bandPaths = useMemo(() => {
    const out: Record<string, PathPoint[]> = {};
    for (const c of CASE_ORDER) {
      out[c] = (endpointsAtHold[c]?.path || []).filter(
        (p) => Number(p.year_offset) >= 1 && Number(p.year_offset) <= holdYears,
      ) as PathPoint[];
    }
    return out;
  }, [endpointsAtHold, holdYears]);

  const showToday = moneyMode === "today";
  const exitShow = showToday ? endpoint?.exit_usd_today ?? endpoint?.exit_usd : endpoint?.exit_usd;
  const rentShow = showToday
    ? endpoint?.cumulative_rent_usd_today ?? endpoint?.cumulative_rent_usd
    : endpoint?.cumulative_rent_usd;
  const totalShow = showToday
    ? endpoint?.total_back_usd_today ?? endpoint?.total_back_usd
    : endpoint?.total_back_usd;
  const gainShow = showToday ? endpoint?.gain_usd_today ?? endpoint?.gain_usd : endpoint?.gain_usd;
  const irrShow = showToday ? endpoint?.irr_real ?? endpoint?.irr : endpoint?.irr;
  const irrPct = irrShow != null ? Number(irrShow) * 100 : null;

  // Keep scrub inside the selected hold window
  const scrubClamped = Math.max(1, Math.min(holdYears, scrubYear));
  const scrubPoint = path.find((p) => Number(p.year_offset) === scrubClamped) || path[path.length - 1];

  const chart = useMemo(() => {
    const series = bandPaths.BASE.length ? bandPaths : { BASE: path, BEAR: path, BULL: path };
    const purchase = Number(intel?.purchase_usd || endpoint?.purchase_usd || entryUsd || markUsd || 0);
    const startMark = Number(
      intel?.mark_usd ||
        (path[0] as PathPoint | undefined)?.starting_mark_usd ||
        purchase,
    );
    const valOf = (p: PathPoint) => {
      const y = Number(p.year_offset || 0);
      const raw = Number(p.total_back_usd ?? p.exit_usd ?? p.land_usd ?? 0);
      if (!showToday || !(y > 0) || !(raw > 0)) return raw;
      return raw / Math.pow(1 + cpi, y);
    };
    const allVals = Object.values(series)
      .flat()
      .map(valOf)
      .filter((v) => v > 0);
    if (purchase > 0) allVals.push(purchase);
    if (startMark > 0) allVals.push(startMark);
    const minV = allVals.length ? Math.min(...allVals) * 0.92 : 0;
    const maxV = allVals.length ? Math.max(...allVals) * 1.06 : 1;
    const W = 640;
    const H = 220;
    const padL = 48;
    const padR = 16;
    const padT = 18;
    const padB = 28;
    const xOf = (y: number) => padL + ((y - 0) / Math.max(1, holdYears)) * (W - padL - padR);
    const yOf = (v: number) => {
      const t = (v - minV) / Math.max(1, maxV - minV);
      return padT + (1 - t) * (H - padT - padB);
    };
    const lineFor = (pts: PathPoint[]) => {
      if (!pts.length) return "";
      // Chart starts at buy cash outlay; first land mark is usually higher (the edge).
      const start = `M ${xOf(0)} ${yOf(purchase)}`;
      const rest = pts
        .map((p) => `L ${xOf(Number(p.year_offset))} ${yOf(valOf(p))}`)
        .join(" ");
      return `${start} ${rest}`;
    };
    const step = holdYears > 40 ? 2 : 1;
    const sample = (pts: PathPoint[]) => pts.filter((_, i) => i % step === 0 || i === pts.length - 1);
    return {
      W,
      H,
      padL,
      padR,
      padT,
      padB,
      xOf,
      yOf,
      purchase,
      startMark,
      minV,
      maxV,
      bearD: lineFor(sample(series.BEAR || [])),
      baseD: lineFor(sample(series.BASE || [])),
      bullD: lineFor(sample(series.BULL || [])),
    };
  }, [
    bandPaths,
    path,
    holdYears,
    intel?.purchase_usd,
    intel?.mark_usd,
    endpoint?.purchase_usd,
    entryUsd,
    markUsd,
    showToday,
    cpi,
  ]);

  const yearFromClientX = useCallback(
    (clientX: number) => {
      const svg = svgRef.current;
      if (!svg) return holdYears;
      const rect = svg.getBoundingClientRect();
      const rel = (clientX - rect.left) / Math.max(1, rect.width);
      const x = rel * chart.W;
      const t = (x - chart.padL) / Math.max(1, chart.W - chart.padL - chart.padR);
      return Math.max(1, Math.min(holdYears, Math.round(t * holdYears)));
    },
    [chart, holdYears],
  );

  const onPointerDown = (e: ReactPointerEvent) => {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setDragging(true);
    setScrubYear(yearFromClientX(e.clientX));
  };
  const onPointerMove = (e: ReactPointerEvent) => {
    if (!dragging && e.buttons === 0) return;
    setScrubYear(yearFromClientX(e.clientX));
  };
  const onPointerUp = () => setDragging(false);

  const factors = toggleFactors;
  const factorCount = factors.length;
  const livePaceDisplay = `${(liveModel.annual * 100).toFixed(1)}%/yr`;
  const toggledOff = factors.filter((f) => f.toggleable !== false && enabledFactors[f.key] === false).length;

  // Fallback: legacy flat compound if intel missing
  if (!available) {
    return (
      <LegacyReturnVisual
        cases={legacyCases || []}
        entryUsd={entryUsd}
        markUsd={markUsd}
        annualRate={annualRate}
        reason={intel?.reason}
        factors={intel?.factors}
      />
    );
  }

  const scrubX = chart.xOf(scrubClamped);
  const scrubRaw = Number(scrubPoint?.total_back_usd ?? scrubPoint?.exit_usd ?? 0);
  const scrubVal =
    showToday && scrubRaw > 0
      ? scrubRaw / Math.pow(1 + cpi, scrubClamped)
      : scrubRaw;
  const scrubY = scrubPoint ? chart.yOf(scrubVal) : chart.yOf(chart.purchase);

  return (
    <div className="return-visual">
      <div className="return-title-row">
        <div className="return-title-kicker">Hold return</div>
        {factors.length > 0 ? (
          <button
            type="button"
            className="return-manage-screens"
            aria-controls="hold-return-screens"
            onClick={jumpToScreens}
          >
            Manage screens
          </button>
        ) : null}
        <span className="return-title-grow" aria-hidden />
        <button
          type="button"
          className={`help-q return-help-q ${helpOpen ? "on" : ""}`}
          aria-label="How this hold return works"
          aria-haspopup="dialog"
          aria-expanded={helpOpen}
          title="How this works"
          onClick={() => setHelpOpen(true)}
        >
          ?
        </button>
      </div>
      {helpOpen ? (
        <div
          className="help-modal-backdrop"
          role="presentation"
          onClick={() => setHelpOpen(false)}
        >
          <div
            className="help-modal help-modal--compact"
            role="dialog"
            aria-modal="true"
            aria-label="How hold return works"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <h4 className="display text-base font-semibold">Hold return · quick read</h4>
              <button
                type="button"
                className="help-q on"
                aria-label="Close"
                onClick={() => setHelpOpen(false)}
              >
                ×
              </button>
            </div>
            <p className="mt-2 text-sm leading-snug text-[var(--ink-soft)]">
              Not a flat %/yr line. Soil, flood, wetlands, growth, channel, carry, and exit bend the
              path
              {intel?.purchase_usd ? ` from a ~${money(intel.purchase_usd)} buy` : ""}.
            </p>
            <ul className="help-modal-list">
              <li>
                <strong>Cautious</strong>
                <span>Slower rents, softer exit, higher carry.</span>
              </li>
              <li>
                <strong>Typical</strong>
                <span>Base path for this file.</span>
              </li>
              <li>
                <strong>Optimistic</strong>
                <span>Stronger rents &amp; exit — still bounded.</span>
              </li>
            </ul>
            <p className="mt-3 text-xs leading-snug text-[var(--muted)]">
              Drag the chart · tap a factor · 1–100 yr hold.{" "}
              <strong>Future dollars</strong> = projected money back.{" "}
              <strong>Today’s dollars</strong> = that same money in purchasing power (~{cpiDisplay}{" "}
              inflation). Screen only — not an appraisal.
            </p>
          </div>
        </div>
      ) : null}

      <div className="traj-windows" role="tablist" aria-label="Hold length">
        {windows.map((y) => (
          <button
            key={y}
            type="button"
            role="tab"
            aria-selected={holdPreset === y}
            className={`traj-window-btn ${holdPreset === y ? "active" : ""}`}
            onClick={() => {
              setHoldPreset(y);
              setCustomHold(String(y));
              setScrubYear(y);
            }}
          >
            {y} yr
          </button>
        ))}
        <button
          type="button"
          role="tab"
          aria-selected={holdPreset === "custom"}
          className={`traj-window-btn ${holdPreset === "custom" ? "active" : ""}`}
          onClick={() => {
            setHoldPreset("custom");
            setScrubYear(clampHoldYears(Number(customHold) || holdYears));
          }}
        >
          Custom
        </button>
      </div>
      {holdPreset === "custom" ? (
        <div className="hold-custom-row">
          <label className="hold-custom-label">
            Hold years
            <input
              type="number"
              min={1}
              max={100}
              step={1}
              value={customHold}
              onChange={(e) => {
                const raw = e.target.value;
                setCustomHold(raw);
                const n = clampHoldYears(Number(raw));
                if (Number.isFinite(Number(raw)) && Number(raw) > 0) setScrubYear(n);
              }}
              onBlur={() => {
                const n = clampHoldYears(Number(customHold) || holdYears);
                setCustomHold(String(n));
                setScrubYear(n);
              }}
            />
          </label>
          <span className="hold-custom-hint">1–100 years</span>
        </div>
      ) : null}

      <div className="traj-head-row">
        <h3 className="display text-lg font-semibold leading-snug">
          {holdYears} yr hold · {livePaceDisplay}
          {toggledOff ? ` · ${toggledOff} screens off` : ""}
        </h3>
        <div className="traj-windows traj-windows--cases" role="tablist" aria-label="Return case">
          {CASE_ORDER.map((k) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={activeCase === k}
              className={`traj-window-btn ${activeCase === k ? "active" : ""}`}
              onClick={() => setActiveCase(k)}
            >
              {caseLabel(k)}
            </button>
          ))}
        </div>
      </div>

      <MoneyModeControl
        mode={moneyMode}
        onChange={setMoneyMode}
        cpiDisplay={cpiDisplay}
        compare={
          holdYears >= 1 &&
          endpoint?.total_back_usd != null &&
          endpoint?.total_back_usd_today != null
            ? {
                label: `Total back · ${holdYears} yr · ${caseLabel(activeCase)}`,
                today: endpoint.total_back_usd_today,
                before: endpoint.total_back_usd,
                format: shortMoney,
              }
            : null
        }
      />

      <BuyingPowerLogic
        variant="hold"
        years={holdYears}
        cpi={cpi}
        cpiDisplay={cpiDisplay}
        purchaseUsd={intel?.purchase_usd}
        markUsd={intel?.mark_usd}
        futureNominal={endpoint?.exit_usd}
        futureToday={endpoint?.exit_usd_today}
        totalBackToday={endpoint?.total_back_usd_today}
        totalBackNominal={endpoint?.total_back_usd}
      />

      <div className="return-chart-wrap">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${chart.W} ${chart.H}`}
          className="return-chart"
          role="img"
          aria-label={`Return path over ${holdYears} years`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
        >
          <defs>
            <linearGradient id="returnBand" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.18" />
              <stop offset="100%" stopColor="var(--brand)" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {/* Grid years — dedupe so 1 yr holds don’t emit [0,1,1] React keys */}
          {Array.from(new Set([0, Math.round(holdYears / 2), holdYears])).map((y) => (
            <g key={`yr-${y}`}>
              <line
                x1={chart.xOf(y)}
                x2={chart.xOf(y)}
                y1={chart.padT}
                y2={chart.H - chart.padB}
                stroke="var(--line)"
                strokeWidth="1"
              />
              <text
                x={chart.xOf(y)}
                y={chart.H - 8}
                textAnchor="middle"
                fontSize="10"
                fill="var(--muted)"
              >
                {y === 0 ? "buy" : `${y}y`}
              </text>
            </g>
          ))}
          <text x={8} y={chart.padT + 4} fontSize="10" fill="var(--muted)">
            {shortMoney(chart.maxV)}
          </text>
          <text x={8} y={chart.H - chart.padB} fontSize="10" fill="var(--muted)">
            {shortMoney(chart.minV)}
          </text>

          {chart.bearD ? (
            <path d={chart.bearD} fill="none" stroke="var(--danger)" strokeOpacity="0.35" strokeWidth="1.5" />
          ) : null}
          {chart.bullD ? (
            <path d={chart.bullD} fill="none" stroke="var(--positive)" strokeOpacity="0.4" strokeWidth="1.5" />
          ) : null}
          {chart.baseD ? (
            <path
              d={chart.baseD}
              fill="none"
              stroke="var(--brand)"
              strokeWidth={activeCase === "BASE" ? 2.75 : 2}
              className="return-path-line"
            />
          ) : null}
          {/* Active case emphasis */}
          {activeCase === "BEAR" && chart.bearD ? (
            <path d={chart.bearD} fill="none" stroke="var(--danger)" strokeWidth="2.75" />
          ) : null}
          {activeCase === "BULL" && chart.bullD ? (
            <path d={chart.bullD} fill="none" stroke="var(--positive)" strokeWidth="2.75" />
          ) : null}

          <line
            x1={scrubX}
            x2={scrubX}
            y1={chart.padT}
            y2={chart.H - chart.padB}
            stroke="var(--ink)"
            strokeOpacity="0.35"
            strokeDasharray="3 3"
          />
          <circle cx={scrubX} cy={scrubY} r="5" fill="var(--brand)" stroke="var(--bg)" strokeWidth="2" />
          <circle cx={chart.xOf(0)} cy={chart.yOf(chart.purchase)} r="3.5" fill="var(--ink)" />
        </svg>
        <div className="return-scrub-hint">
          Drag the chart · year {scrubClamped} of {holdYears} · total back{" "}
          <strong>
            {money(
              showToday && scrubPoint?.total_back_usd != null
                ? Number(scrubPoint.total_back_usd) / Math.pow(1 + cpi, scrubClamped)
                : scrubPoint?.total_back_usd,
            )}
          </strong>
          {showToday ? " in today’s dollars" : " in future dollars"}
        </div>
      </div>

      {endpoint && (
        <div className="return-future">
          <div className="return-future-head">
            <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
              After {holdYears} yr · {caseLabel(activeCase)}
            </div>
            <div className="return-future-basis">{moneyModeShort(moneyMode)}</div>
          </div>
          <div className="return-future-grid">
            <div>
              <span>Land at exit</span>
              <strong>{money(exitShow)}</strong>
              {holdYears >= 1 && endpoint.exit_usd != null && endpoint.exit_usd_today != null ? (
                <em className="return-alt-line">
                  {showToday
                    ? `${shortMoney(Number(endpoint.exit_usd))} future dollars`
                    : `${shortMoney(Number(endpoint.exit_usd_today))} today’s dollars`}
                </em>
              ) : null}
            </div>
            <div>
              <span>Rent along the way</span>
              <strong>{money(rentShow)}</strong>
              {holdYears >= 1 &&
              endpoint.cumulative_rent_usd != null &&
              endpoint.cumulative_rent_usd_today != null ? (
                <em className="return-alt-line">
                  {showToday
                    ? `${shortMoney(Number(endpoint.cumulative_rent_usd))} future dollars`
                    : `${shortMoney(Number(endpoint.cumulative_rent_usd_today))} today’s dollars`}
                </em>
              ) : null}
            </div>
            <div>
              <span>Total back</span>
              <strong>{money(totalShow)}</strong>
              {holdYears >= 1 &&
              endpoint.total_back_usd != null &&
              endpoint.total_back_usd_today != null ? (
                <em className="return-alt-line">
                  {showToday
                    ? `${shortMoney(Number(endpoint.total_back_usd))} future dollars`
                    : `${shortMoney(Number(endpoint.total_back_usd_today))} today’s dollars`}
                </em>
              ) : null}
            </div>
            <div className="return-vs-cell">
              <span>Vs buy · annualized</span>
              <strong
                className={`return-vs-buy ${(Number(gainShow) || 0) >= 0 ? "is-pos" : "is-neg"}`}
              >
                <span className="return-vs-gain">
                  {(Number(gainShow) || 0) >= 0 ? "+" : ""}
                  {shortMoney(Number(gainShow || 0))}
                </span>
                {irrPct != null ? (
                  <span className="return-vs-irr">
                    {irrPct.toFixed(1)}%/yr{showToday ? " real" : ""}
                  </span>
                ) : null}
              </strong>
              {holdYears >= 1 &&
              endpoint.irr != null &&
              endpoint.irr_real != null &&
              Number.isFinite(endpoint.irr) &&
              Number.isFinite(endpoint.irr_real) ? (
                <em className="return-alt-line">
                  {showToday
                    ? `${(Number(endpoint.irr) * 100).toFixed(1)}%/yr in future dollars`
                    : `${(Number(endpoint.irr_real) * 100).toFixed(1)}%/yr in today’s dollars`}
                </em>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {holdYears >= 50 && intel?.horizon_notes ? (
        <p className="mt-2 text-[11px] leading-snug text-[var(--muted)]">
          {intel.horizon_notes[String(holdYears)] ||
            intel.horizon_notes["100"] ||
            "Far years fade on purpose — not a straight rocket."}
        </p>
      ) : null}

      <div className="mt-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
            3 outcomes · {holdYears} yr
          </div>
          <button
            type="button"
            className={`help-q ${casesHelpOpen ? "on" : ""}`}
            aria-label="What these cases mean"
            aria-haspopup="dialog"
            aria-expanded={casesHelpOpen}
            title="What these cases mean"
            onClick={() => setCasesHelpOpen(true)}
          >
            ?
          </button>
        </div>
        {casesHelpOpen ? (
          <div
            className="help-modal-backdrop"
            role="presentation"
            onClick={() => setCasesHelpOpen(false)}
          >
            <div
              className="help-modal help-modal--compact"
              role="dialog"
              aria-modal="true"
              aria-label="What these cases mean"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-3">
                <h4 className="display text-base font-semibold">3 cases · {holdYears} yr</h4>
                <button
                  type="button"
                  className="help-q on"
                  aria-label="Close"
                  onClick={() => setCasesHelpOpen(false)}
                >
                  ×
                </button>
              </div>
              <p className="mt-1.5 text-xs leading-snug text-[var(--muted)]">
                Same buy
                {intel?.purchase_usd ? ` (${money(intel.purchase_usd)})` : ""} · same hold · rent /
                pace / exit friction shift.
              </p>
              <ul className="help-modal-list">
                <li>
                  <strong>Cautious</strong>
                  <span>Softer rents, harder exit, more carry.</span>
                </li>
                <li>
                  <strong>Typical</strong>
                  <span>Base path from this property’s screens.</span>
                </li>
                <li>
                  <strong>Optimistic</strong>
                  <span>Stronger rents & exit — still not a forever rocket.</span>
                </li>
              </ul>
              <p className="mt-2 text-[11px] text-[var(--muted)] leading-snug">
                Total back = exit + rent along the way. Screen, not promise.
              </p>
            </div>
          </div>
        ) : null}
        <div className="case-outcome-grid mt-1.5" role="list">
          {CASE_ORDER.map((k) => {
            const ep = endpointsAtHold[k];
            if (!ep) return null;
            const rate = showToday ? ep.irr_real ?? ep.irr : ep.irr;
            const pct = rate != null && Number.isFinite(Number(rate)) ? Number(rate) * 100 : null;
            const total = showToday
              ? ep.total_back_usd_today ?? ep.total_back_usd
              : ep.total_back_usd;
            const gain = showToday ? ep.gain_usd_today ?? ep.gain_usd : ep.gain_usd;
            const gainN = Number(gain);
            const pos = Number.isFinite(gainN) ? gainN >= 0 : null;
            return (
              <button
                key={k}
                type="button"
                role="listitem"
                className={`case-outcome ${activeCase === k ? "is-active" : ""} tone-${caseTone(k)}`}
                onClick={() => setActiveCase(k)}
                aria-pressed={activeCase === k}
              >
                <div className="case-outcome-row">
                  <span className="case-outcome-name">{caseLabel(k)}</span>
                  <span className="case-outcome-total tabular-nums">
                    {total != null ? shortMoney(Number(total)) : "—"}
                  </span>
                </div>
                <div className="case-outcome-meta">
                  <span
                    className={`case-outcome-delta tabular-nums ${
                      pos === true ? "is-pos" : pos === false ? "is-neg" : ""
                    }`}
                  >
                    {Number.isFinite(gainN)
                      ? `${gainN >= 0 ? "+" : ""}${shortMoney(gainN)}`
                      : "—"}
                  </span>
                  <span className="case-outcome-irr tabular-nums">
                    {pct != null
                      ? `${pct.toFixed(1)}%/yr${showToday ? " real" : ""}`
                      : "n/a"}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {factors.length > 0 ? (
        <div className="return-screens-panel mt-3" id="hold-return-screens" ref={screensRef}>
          <div className="return-screens-head">
            <div className="return-screens-kicker">
              Screens · {factorCount}
              <span className="return-screens-hint">tap on / off</span>
            </div>
            <button type="button" className="return-screens-reset" onClick={resetScreens}>
              Reset
            </button>
          </div>
          <div className="return-factor-chips" role="group" aria-label="Hold return screens">
            {factors.map((f) => {
              const id = String(f.key);
              const locked = f.toggleable === false;
              const on = locked ? true : enabledFactors[id] !== false;
              const affects = f.affects || f.kind || "pace";
              const pts =
                f.affects === "pace" && f.bps != null && Number(f.bps) !== 0
                  ? `${Number(f.bps) > 0 ? "+" : ""}${(Number(f.bps) / 100).toFixed(1)}`
                  : affects === "entry"
                    ? "in"
                    : affects === "carry"
                      ? "carry"
                      : affects === "exit"
                        ? "exit"
                        : affects === "fade"
                          ? "fade"
                          : "";
              return (
                <button
                  key={id}
                  type="button"
                  aria-pressed={on}
                  disabled={locked}
                  title={f.plain || f.label}
                  className={`return-factor-chip dir-${f.direction || "neutral"} ${
                    on ? "is-on" : "is-off"
                  } ${locked ? "is-locked" : ""}`}
                  onClick={() => {
                    if (locked) return;
                    setEnabledFactors((prev) => ({ ...prev, [id]: !on }));
                  }}
                >
                  <span className="return-factor-check" aria-hidden>
                    {locked ? "●" : on ? "✓" : "○"}
                  </span>
                  <FactorIcon name={f.key || f.label} />
                  <span className="return-factor-chip-label">{f.label}</span>
                  {pts ? <span className="return-factor-chip-pts tabular-nums">{pts}</span> : null}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Flat compound fallback when multi-factor intel is unavailable. */
function LegacyReturnVisual({
  cases,
  entryUsd,
  markUsd,
  annualRate,
  reason,
  factors,
}: {
  cases: LegacyCase[];
  entryUsd?: number | null;
  markUsd?: number | null;
  annualRate?: number | null;
  reason?: string;
  factors?: Factor[];
}) {
  const purchase = Number(entryUsd || markUsd || 0);
  return (
    <div className="return-visual">
      <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">
        Possible yearly return
      </div>
      <h3 className="display text-lg font-semibold">If you hold this property</h3>
      <p className="mt-1 text-sm text-[var(--muted)]">
        {reason ||
          "Need a buy price or value estimate before a multi-factor return path can be built."}
        {purchase > 0 ? ` Entry near ${money(purchase)}.` : ""}
      </p>
      {factors && factors.length > 0 ? (
        <div className="return-factor-grid mt-3">
          {factors.slice(0, 6).map((f) => (
            <div key={f.key || f.label} className={`return-factor dir-${f.direction || "neutral"}`}>
              <div className="font-semibold">{f.label}</div>
              <p>{f.plain}</p>
            </div>
          ))}
        </div>
      ) : cases.length ? (
        <p className="mt-2 text-[11px] text-[var(--muted)]">
          Legacy rent cases are on file, but the full path engine needs a usable entry price.
          {annualRate != null ? ` Area pace ~${(annualRate * 100).toFixed(1)}%/yr.` : ""}
        </p>
      ) : null}
    </div>
  );
}
