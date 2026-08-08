/**
 * Pure financial helpers for land underwriting.
 * All monetary units USD unless noted. Rates are decimals (0.08 = 8%).
 */

export function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

export function pricePerAcre(
  priceUsd: number | null | undefined,
  acreage: number | null | undefined,
): number | null {
  if (priceUsd == null || acreage == null || acreage <= 0) return null;
  return priceUsd / acreage;
}

export function askingDiscountPct(
  askingUsd: number | null | undefined,
  estimatedValueUsd: number | null | undefined,
): number | null {
  if (
    askingUsd == null ||
    estimatedValueUsd == null ||
    estimatedValueUsd <= 0 ||
    askingUsd < 0
  ) {
    return null;
  }
  // Negative => asking below estimate (discount to buyer)
  return ((askingUsd - estimatedValueUsd) / estimatedValueUsd) * 100;
}

export function marginOfSafety(
  purchaseUsd: number,
  baseValueUsd: number,
): number {
  if (baseValueUsd <= 0) return 0;
  return (baseValueUsd - purchaseUsd) / baseValueUsd;
}

export function noiFromRent(
  grossRent: number,
  vacancyRate: number,
  opex: number,
  taxes: number,
  insurance: number,
  management: number,
): number {
  const egI = grossRent * (1 - vacancyRate);
  return egI - opex - taxes - insurance - management;
}

export function capRate(noi: number, value: number): number | null {
  if (value <= 0) return null;
  return noi / value;
}

export function cashOnCash(annualCashFlow: number, equityIn: number): number | null {
  if (equityIn <= 0) return null;
  return annualCashFlow / equityIn;
}

/** NPV of cash flows; cashFlows[0] is t=0 (usually negative purchase). */
export function npv(discountRate: number, cashFlows: number[]): number {
  return cashFlows.reduce(
    (acc, cf, t) => acc + cf / Math.pow(1 + discountRate, t),
    0,
  );
}

/**
 * IRR via bisection. Returns null if no bracketed root.
 */
export function irr(
  cashFlows: number[],
  guessLow = -0.99,
  guessHigh = 10,
  tol = 1e-6,
  maxIter = 200,
): number | null {
  if (cashFlows.length < 2) return null;
  let lo = guessLow;
  let hi = guessHigh;
  let npvLo = npv(lo, cashFlows);
  let npvHi = npv(hi, cashFlows);
  if (npvLo * npvHi > 0) return null;
  for (let i = 0; i < maxIter; i++) {
    const mid = (lo + hi) / 2;
    const npvMid = npv(mid, cashFlows);
    if (Math.abs(npvMid) < tol) return mid;
    if (npvLo * npvMid <= 0) {
      hi = mid;
      npvHi = npvMid;
    } else {
      lo = mid;
      npvLo = npvMid;
    }
  }
  return (lo + hi) / 2;
}

export function breakevenLandValue(
  stabilizedNoi: number,
  targetCapRate: number,
): number | null {
  if (targetCapRate <= 0) return null;
  return stabilizedNoi / targetCapRate;
}

export type AgScenarioInput = {
  cashRentPerAcre: number;
  acres: number;
  vacancyRate: number;
  opexPerAcre: number;
  taxes: number;
  insurance: number;
  management: number;
  purchasePrice: number;
  holdYears: number;
  exitCapRate: number;
  annualAppreciation: number;
  discountRate: number;
};

export type AgScenarioResult = {
  grossRent: number;
  noi: number;
  capRate: number | null;
  cashOnCash: number | null;
  irr: number | null;
  npv: number;
  breakevenLandValue: number | null;
};

export function farmlandScenario(input: AgScenarioInput): AgScenarioResult {
  const grossRent = input.cashRentPerAcre * input.acres;
  const noi = noiFromRent(
    grossRent,
    input.vacancyRate,
    input.opexPerAcre * input.acres,
    input.taxes,
    input.insurance,
    input.management,
  );
  const flows: number[] = [-input.purchasePrice];
  for (let y = 1; y <= input.holdYears; y++) {
    flows.push(noi);
  }
  const exitValue =
    input.purchasePrice * Math.pow(1 + input.annualAppreciation, input.holdYears);
  // Approximate exit via appreciation path; also expose cap-based breakeven separately
  flows[flows.length - 1] += exitValue;
  return {
    grossRent,
    noi,
    capRate: capRate(noi, input.purchasePrice),
    cashOnCash: cashOnCash(noi, input.purchasePrice),
    irr: irr(flows),
    npv: npv(input.discountRate, flows),
    breakevenLandValue: breakevenLandValue(noi, input.exitCapRate),
  };
}
