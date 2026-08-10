/** Long-run CPI screen — keep in sync with apps/api/landsignal/services/inflation.py */
export const DEFAULT_CPI_ANNUAL = 0.025;

export type InflationMeta = {
  cpi_annual?: number;
  cpi_display?: string;
  plain?: string;
  label_today?: string;
  label_nominal?: string;
};

export function cpiFromMeta(meta?: InflationMeta | null): number {
  const n = Number(meta?.cpi_annual);
  return Number.isFinite(n) && n >= 0 && n < 0.2 ? n : DEFAULT_CPI_ANNUAL;
}

/** Future nominal $ → purchasing power in today’s dollars. */
export function deflate(nominal: number | null | undefined, years: number, cpi = DEFAULT_CPI_ANNUAL): number | null {
  const n = Number(nominal);
  const y = Number(years);
  if (!Number.isFinite(n) || !Number.isFinite(y) || y < 0) return null;
  return n / Math.pow(1 + cpi, y);
}

export function realRate(nominalRate: number | null | undefined, cpi = DEFAULT_CPI_ANNUAL): number | null {
  const r = Number(nominalRate);
  if (!Number.isFinite(r)) return null;
  return (1 + r) / (1 + cpi) - 1;
}

type PathPoint = {
  year_offset?: number;
  noi_usd?: number | null;
  exit_usd?: number | null;
  land_usd?: number | null;
  total_back_usd?: number | null;
  gain_usd?: number | null;
  cumulative_rent_usd?: number | null;
};

export type MoneyMode = "today" | "nominal";

/** Enrich a return endpoint with today’s-$ totals + real IRR from its path. */
export function withInflation<T extends {
  hold_years?: number | null;
  purchase_usd?: number | null;
  exit_usd?: number | null;
  cumulative_rent_usd?: number | null;
  total_back_usd?: number | null;
  gain_usd?: number | null;
  irr?: number | null;
  path?: PathPoint[] | null;
  exit_usd_today?: number | null;
  cumulative_rent_usd_today?: number | null;
  total_back_usd_today?: number | null;
  gain_usd_today?: number | null;
  irr_real?: number | null;
}>(endpoint: T | null | undefined, cpi = DEFAULT_CPI_ANNUAL): T | null {
  if (!endpoint) return null;
  if (
    endpoint.exit_usd_today != null &&
    endpoint.total_back_usd_today != null &&
    endpoint.irr_real != null
  ) {
    return endpoint;
  }

  const years = Math.max(0, Number(endpoint.hold_years || 0));
  const purchase = Number(endpoint.purchase_usd || 0);
  const path = endpoint.path || [];
  if (!(purchase > 0) || !path.length || !(years > 0)) {
    return {
      ...endpoint,
      exit_usd_today: deflate(endpoint.exit_usd, years, cpi),
      cumulative_rent_usd_today: endpoint.cumulative_rent_usd_today ?? null,
      total_back_usd_today: endpoint.total_back_usd_today ?? null,
      gain_usd_today: endpoint.gain_usd_today ?? null,
      irr_real: endpoint.irr_real ?? null,
    };
  }

  let rentToday = 0;
  const flowsReal = [-purchase];
  for (let i = 0; i < path.length; i++) {
    const pt = path[i];
    const y = Number(pt.year_offset || i + 1);
    const noi = Number(pt.noi_usd || 0);
    // Match path accounting: cumulative rent only banks non-negative NOI.
    rentToday += Math.max(0, noi) / Math.pow(1 + cpi, y);
    const exitBit =
      i === path.length - 1 ? Number(pt.exit_usd ?? pt.land_usd ?? 0) : 0;
    flowsReal.push((noi + exitBit) / Math.pow(1 + cpi, y));
  }

  const exitToday = deflate(endpoint.exit_usd, years, cpi);
  const totalToday = (exitToday || 0) + rentToday;
  const gainToday = totalToday - purchase;
  const irrReal = solveIrr(flowsReal);

  return {
    ...endpoint,
    exit_usd_today: exitToday != null ? Math.round(exitToday) : null,
    cumulative_rent_usd_today: Math.round(rentToday),
    total_back_usd_today: Math.round(totalToday),
    gain_usd_today: Math.round(gainToday),
    irr_real: irrReal,
  };
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
