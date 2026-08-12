/**
 * Client hold-path engine — mirrors apps/api/landsignal/services/return_path.py
 * so factor toggles can recompute Cautious / Typical / Optimistic live.
 */
import { DEFAULT_CPI_ANNUAL, withInflation, type MoneyMode } from "@/lib/inflation";

export type ToggleFactor = {
  key: string;
  label: string;
  delta_annual?: number;
  mult?: number | null;
  bps?: number;
  plain?: string;
  affects?: "pace" | "carry" | "exit" | "entry" | "fade" | string;
  toggleable?: boolean;
  default_on?: boolean;
  direction?: string;
  kind?: string;
  /** Extra payload for carry/exit knobs */
  flood_carry_frac?: number;
  usable_frac?: number;
  exit_haircut_add?: number;
  tax_frac?: number;
};

export type HoldPathPoint = {
  year_offset: number;
  land_usd: number;
  exit_usd: number;
  noi_usd: number;
  cumulative_rent_usd: number;
  cumulative_noi_usd: number;
  cumulative_carry_usd: number;
  total_back_usd: number;
  gain_usd: number;
  starting_mark_usd: number;
  purchase_usd: number;
};

export type HoldCaseKey = "BEAR" | "BASE" | "BULL";

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

function cycleShaper(y: number): number {
  return 1.0 + 0.006 * Math.sin(y * 0.55);
}

function fatigueForYear(y: number): number {
  let fatigue = 1.0;
  if (y > 15) fatigue = Math.max(0.88, 1.0 - (y - 15) * 0.006);
  if (y > 35) fatigue = Math.max(0.80, fatigue - (y - 35) * 0.003);
  if (y > 60) fatigue = Math.max(0.74, fatigue - (y - 60) * 0.0015);
  return fatigue;
}

function caseScalars(caseKey: HoldCaseKey, uncertainty: number) {
  if (caseKey === "BEAR") {
    return {
      rent_mult: 0.72,
      appr_mult: Math.max(0.35, 1.0 - uncertainty * 1.1),
      exit_haircut: 0.08 + uncertainty * 0.12,
      carry_mult: 1.25,
      cycle_amp: 1.35 * 0.35,
    };
  }
  if (caseKey === "BULL") {
    return {
      rent_mult: 1.25,
      appr_mult: 1.0 + uncertainty * 0.85,
      exit_haircut: Math.max(0.0, 0.02 - uncertainty * 0.04),
      carry_mult: 0.9,
      cycle_amp: 0.85 * 0.35,
    };
  }
  return {
    rent_mult: 1.0,
    appr_mult: 1.0,
    exit_haircut: 0.03 + uncertainty * 0.05,
    carry_mult: 1.0,
    cycle_amp: 0.35,
  };
}

/** Recompute owned-land annual pace from enabled toggle factors. */
export function rateFromFactors(
  factors: ToggleFactor[],
  enabled: Record<string, boolean>,
): number {
  let rate = 0;
  for (const f of factors) {
    if (f.affects && f.affects !== "pace") continue;
    const on = f.toggleable === false ? true : enabled[f.key] !== false;
    if (!on) continue;
    if (f.key === "state_prior") {
      rate = Number(f.delta_annual || 0);
      continue;
    }
    if (f.mult != null && Number.isFinite(f.mult)) {
      rate *= Number(f.mult);
    } else {
      rate += Number(f.delta_annual || 0);
    }
  }
  return clamp(rate, -0.04, 0.08);
}

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

export function buildHoldCasePath(opts: {
  purchase: number;
  mark: number;
  annual: number;
  holdYears: number;
  caseKey: HoldCaseKey;
  uncertainty?: number;
  acres?: number;
  strategy?: string | null;
  provider?: string | null;
  floodCarryFrac?: number;
  usableFrac?: number;
  exitHaircutAdd?: number;
  taxFrac?: number;
  applyFade?: boolean;
  primePct?: number | null;
  state?: string | null;
}): {
  path: HoldPathPoint[];
  irr: number | null;
  purchase_usd: number;
  starting_mark_usd: number;
  hold_years: number;
  exit_usd: number | null;
  land_mark_usd: number | null;
  cumulative_rent_usd: number;
  cumulative_noi_usd: number;
  total_back_usd: number | null;
  gain_usd: number | null;
  effective_annual_used: number;
} {
  const holdYears = clamp(Math.round(opts.holdYears), 1, 100);
  const purchase = Number(opts.purchase);
  let mark0 = Number(opts.mark);
  if (!(mark0 > 0) || mark0 < purchase) mark0 = purchase;
  const uncertainty = opts.uncertainty ?? 0.35;
  const scalars = caseScalars(opts.caseKey, uncertainty);
  const acres = Math.max(0.1, Number(opts.acres || 1));
  const appr0 = clamp(Number(opts.annual) * scalars.appr_mult, -0.05, 0.14);
  const usable = clamp(Number(opts.usableFrac ?? 1), 0.35, 1);
  const floodCarry = Math.max(0, Number(opts.floodCarryFrac || 0));
  const applyFade = opts.applyFade !== false;

  // Rent prior (mirrors return_path._base_rent_per_acre)
  const st = (opts.state || "US").toUpperCase();
  const prime = opts.primePct ?? 35;
  const farmBelt = new Set(["IA", "IL", "IN", "OH", "MN", "WI", "NE", "SD", "ND", "MO", "KS"]);
  let rentPerAc = farmBelt.has(st) ? 220 : ["TX", "OK", "KS"].includes(st) ? 140 : 160;
  rentPerAc *= 0.75 + (prime / 100) * 0.55;
  const strategy = (opts.strategy || "").toUpperCase();
  if (strategy === "RECREATIONAL") rentPerAc = Math.max(40, rentPerAc * 0.35);
  else if (strategy === "ENERGY") rentPerAc = Math.max(60, rentPerAc * 0.45);
  else if (strategy === "LAND_BANK") rentPerAc = Math.max(20, rentPerAc * 0.15);
  else if (strategy === "DEVELOPMENT") rentPerAc = Math.max(30, rentPerAc * 0.2);
  let rent0 = rentPerAc * usable * acres * scalars.rent_mult;

  let taxFrac = (opts.taxFrac != null ? opts.taxFrac : 0.009) * scalars.carry_mult;
  if (acres < 2) taxFrac *= 0.55;
  if (strategy === "LAND_BANK" || strategy === "DEVELOPMENT") taxFrac *= 0.7;
  const insureFrac = (0.002 + floodCarry) * scalars.carry_mult;
  const vacancy = opts.caseKey === "BEAR" ? 0.08 : 0.05;
  const opexFrac = 0.18 * scalars.carry_mult;
  const mgmtFrac = 0.06;
  const provider = opts.provider || "";

  let land = mark0;
  let cumRent = 0;
  let cumNoi = 0;
  let cumCarry = 0;
  const path: HoldPathPoint[] = [];
  const flows = [-purchase];
  const rentSeries: number[] = [];

  for (let y = 1; y <= holdYears; y++) {
    const rawShaper = cycleShaper(y);
    const shaped = 1.0 + (rawShaper - 1.0) * scalars.cycle_amp;
    const fatigue = applyFade ? fatigueForYear(y) : 1.0;
    let shock = 1.0;
    if ([5, 22, 48].includes(y) && ["public_tax_sale", "blm_lpad", "public_surplus"].includes(provider)) {
      shock *= opts.caseKey === "BASE" ? 0.994 : opts.caseKey === "BEAR" ? 0.99 : 0.997;
    }
    const yearAppr = appr0 * fatigue;
    land = land * (1.0 + yearAppr) * shaped * shock;

    const rentCap = y <= 30 ? 0.022 : y <= 60 ? 0.014 : 0.009;
    const rentDrift = 1.0 + clamp(yearAppr * 0.42, -0.01, rentCap);
    if (y > 1) rent0 *= rentDrift;
    const egi = rent0 * (1.0 - vacancy);
    const opex = egi * opexFrac;
    const taxCreep = 1.0 + Math.min(0.25, Math.max(0, (y - 10) * 0.002));
    const taxes = land * taxFrac * taxCreep;
    const insure = land * insureFrac * (1.0 + (y > 40 ? 0.15 : 0));
    const mgmt = egi * mgmtFrac;
    let noi = egi - opex - taxes - insure - mgmt;
    if ((strategy === "LAND_BANK" || strategy === "DEVELOPMENT") && noi < 0) {
      noi = Math.min(noi, -land * 0.004);
    }
    cumNoi += noi;
    cumRent += Math.max(0, noi);
    cumCarry += Math.max(0, taxes + insure);
    rentSeries.push(noi);

    let exitHaircut = scalars.exit_haircut + Number(opts.exitHaircutAdd || 0);
    if (["public_tax_sale", "blm_lpad", "public_surplus"].includes(provider)) {
      exitHaircut += Math.max(0, 0.035 - y * 0.0012);
    }
    if (y >= 75) exitHaircut += opts.caseKey === "BEAR" ? 0.025 : 0.012;

    const markExit = land * (1.0 - exitHaircut);
    const totalBack = markExit + cumNoi;
    path.push({
      year_offset: y,
      land_usd: Math.round(land),
      exit_usd: Math.round(markExit),
      noi_usd: Math.round(noi),
      cumulative_rent_usd: Math.round(cumRent),
      cumulative_noi_usd: Math.round(cumNoi),
      cumulative_carry_usd: Math.round(cumCarry),
      total_back_usd: Math.round(totalBack),
      gain_usd: Math.round(totalBack - purchase),
      starting_mark_usd: Math.round(mark0),
      purchase_usd: Math.round(purchase),
    });
    flows.push(noi);
  }

  if (path.length) {
    flows[flows.length - 1] = rentSeries[rentSeries.length - 1] + path[path.length - 1].exit_usd;
  }
  const last = path[path.length - 1] || null;
  return {
    path,
    irr: solveIrr(flows),
    purchase_usd: Math.round(purchase),
    starting_mark_usd: Math.round(mark0),
    hold_years: holdYears,
    exit_usd: last?.exit_usd ?? null,
    land_mark_usd: last?.land_usd ?? null,
    cumulative_rent_usd: last?.cumulative_rent_usd ?? 0,
    cumulative_noi_usd: last?.cumulative_noi_usd ?? 0,
    total_back_usd: last?.total_back_usd ?? null,
    gain_usd: last?.gain_usd ?? null,
    effective_annual_used: appr0,
  };
}

export function enrichHoldEndpoint(
  built: ReturnType<typeof buildHoldCasePath>,
  cpi = DEFAULT_CPI_ANNUAL,
) {
  return withInflation(
    {
      hold_years: built.hold_years,
      purchase_usd: built.purchase_usd,
      exit_usd: built.exit_usd,
      cumulative_rent_usd: built.cumulative_rent_usd,
      total_back_usd: built.total_back_usd,
      gain_usd: built.gain_usd,
      irr: built.irr,
      path: built.path,
      land_mark_usd: built.land_mark_usd,
      starting_noi: built.path[0]?.noi_usd ?? null,
      effective_annual_used: built.effective_annual_used,
    },
    cpi,
  );
}

export function mergeEnabled(
  factors: ToggleFactor[],
  overrides: Record<string, boolean>,
): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const f of factors) {
    out[f.key] = overrides[f.key] ?? f.default_on !== false;
  }
  return out;
}

export type { MoneyMode };
