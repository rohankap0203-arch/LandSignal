import { askingDiscountPct, clamp, marginOfSafety } from "./financial.js";
import { inputHash } from "./hash.js";
import { screenStrategies } from "./screening.js";
import {
  DEFAULT_WEIGHTS,
  type KnowledgeState,
  type ProvenancedNumber,
  type ScoreComponent,
  type ScoreInput,
  type ScoreResult,
  type Signal,
  type Strategy,
  type WeightConfig,
} from "./types.js";

export const ALGORITHM_VERSION = "landsignal_score_v1";
export const WEIGHT_VERSION = "weights_default_v1";

function known(p: ProvenancedNumber): number | null {
  if (
    p.value == null ||
    p.knowledge_state === "UNKNOWN" ||
    p.knowledge_state === "TEMPORARILY_UNAVAILABLE"
  ) {
    return null;
  }
  return p.value;
}

function ks(p: ProvenancedNumber): KnowledgeState {
  return p.knowledge_state;
}

function avg(nums: Array<number | null>): number | null {
  const v = nums.filter((n): n is number => n != null);
  if (!v.length) return null;
  return v.reduce((a, b) => a + b, 0) / v.length;
}

function invertRisk(risk0to100: number): number {
  return 100 - risk0to100;
}

export function computeRisk(input: ScoreInput): {
  risk: number;
  evidence: string[];
} {
  const evidence: string[] = [];
  const parts: number[] = [];

  const wetland = known(input.wetland_pct);
  if (wetland != null) {
    parts.push(clamp(wetland, 0, 100));
    if (wetland > 25) evidence.push(`Wetlands ${wetland.toFixed(1)}% of parcel`);
  }
  const flood = known(input.flood_zone_pct);
  if (flood != null) {
    parts.push(clamp(flood * 1.1, 0, 100));
    if (flood > 20) evidence.push(`Flood exposure ${flood.toFixed(1)}%`);
  }
  const access = known(input.legal_access_confidence);
  if (access != null) {
    parts.push(clamp(100 - access, 0, 100));
    if (access < 50) evidence.push(`Legal access confidence only ${access}`);
  }
  const contamination = known(input.environmental_contamination);
  if (contamination != null) {
    parts.push(clamp(contamination, 0, 100));
    if (contamination > 30) evidence.push(`Environmental severity ${contamination}`);
  }
  const slope = known(input.max_slope_pct);
  if (slope != null) {
    parts.push(clamp(slope * 2, 0, 100));
    if (slope > 15) evidence.push(`Max slope ${slope.toFixed(1)}%`);
  }
  const liq = known(input.liquidity_score);
  if (liq != null) {
    parts.push(clamp(100 - liq, 0, 100) * 0.7);
  }

  if (!parts.length) {
    return { risk: 50, evidence: ["Insufficient risk inputs — neutral risk pending data"] };
  }
  const risk = clamp(parts.reduce((a, b) => a + b, 0) / parts.length, 0, 100);
  return { risk: round1(risk), evidence };
}

function valuationScore(input: ScoreInput): {
  value: number;
  ks: KnowledgeState;
  evidence: string[];
  discount: number | null;
  est: number | null;
} {
  const base = known(input.estimated_value_base_usd);
  const ask = input.asking_price_usd;
  const discount = askingDiscountPct(ask, base);
  const evidence: string[] = [];
  if (base == null || ask == null) {
    return {
      value: 50,
      ks: base == null ? input.estimated_value_base_usd.knowledge_state : "KNOWN",
      evidence: ["Valuation incomplete — neutral until comps/model value available"],
      discount,
      est: base,
    };
  }
  // discount negative means ask < value (good). Map -40% => ~100, 0% => 55, +30% => ~15
  const score = clamp(55 - discount * 1.2, 0, 100);
  evidence.push(
    `Ask ${ask} vs base value ${base} → discount/premium ${discount.toFixed(1)}%`,
  );
  return {
    value: round1(score),
    ks: ks(input.estimated_value_base_usd),
    evidence,
    discount,
    est: base,
  };
}

function qualityScore(input: ScoreInput): { value: number; ks: KnowledgeState; evidence: string[] } {
  const prime = known(input.prime_farmland_pct);
  const slope = known(input.avg_slope_pct);
  const evidence: string[] = [];
  const parts: number[] = [];
  if (prime != null) {
    parts.push(prime);
    evidence.push(`Prime farmland ${prime.toFixed(1)}%`);
  }
  if (slope != null) {
    parts.push(clamp(100 - slope * 3, 0, 100));
    evidence.push(`Avg slope ${slope.toFixed(1)}%`);
  }
  if (!parts.length) {
    return {
      value: 50,
      ks: "UNKNOWN",
      evidence: ["Intrinsic quality unknown — not penalized"],
    };
  }
  return { value: round1(avg(parts) ?? 50), ks: "KNOWN", evidence };
}

function optionalityScore(
  input: ScoreInput,
  screens: Record<Strategy, string>,
): { value: number; ks: KnowledgeState; evidence: string[]; strategyScores: Record<Strategy, number> } {
  const strategyScores: Record<Strategy, number> = {
    FARMLAND: 0,
    DEVELOPMENT: 0,
    LAND_BANK: 0,
    RECREATIONAL: 0,
    ENERGY: 0,
    TIMBER: 0,
  };

  const prime = known(input.prime_farmland_pct) ?? 40;
  const zoning = known(input.zoning_development_friendly) ?? 40;
  const growth = known(input.path_of_growth_score) ?? 40;
  const solar = known(input.solar_irradiance_score) ?? 40;
  const timber = known(input.timber_suitability) ?? 40;
  const wetland = known(input.wetland_pct) ?? 20;
  const access = known(input.legal_access_confidence) ?? 50;

  strategyScores.FARMLAND = screens.FARMLAND === "FAIL" ? 0 : clamp(prime * 0.7 + (100 - wetland) * 0.3, 0, 100);
  strategyScores.DEVELOPMENT =
    screens.DEVELOPMENT === "FAIL" ? 0 : clamp(zoning * 0.45 + growth * 0.35 + access * 0.2, 0, 100);
  strategyScores.LAND_BANK =
    screens.LAND_BANK === "FAIL" ? 0 : clamp(growth * 0.5 + zoning * 0.2 + access * 0.3, 0, 100);
  strategyScores.RECREATIONAL =
    screens.RECREATIONAL === "FAIL" ? 0 : clamp(40 + wetland * 0.2 + (100 - zoning) * 0.2, 0, 100);
  strategyScores.ENERGY =
    screens.ENERGY === "FAIL" ? 0 : clamp(solar * 0.6 + (known(input.nearest_transmission_m) != null ? 40 : 20), 0, 100);
  strategyScores.TIMBER = screens.TIMBER === "FAIL" ? 0 : clamp(timber, 0, 100);

  const passScores = Object.entries(strategyScores)
    .filter(([k]) => screens[k as Strategy] !== "FAIL")
    .map(([, v]) => v);
  const top = [...passScores].sort((a, b) => b - a).slice(0, 3);
  const value = round1(avg(top) ?? 0);
  return {
    value,
    ks:
      known(input.zoning_development_friendly) == null &&
      known(input.prime_farmland_pct) == null
        ? "ESTIMATED"
        : "KNOWN",
    evidence: [
      `Top strategy scores: ${Object.entries(strategyScores)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([k, v]) => `${k}=${round1(v)}`)
        .join(", ")}`,
    ],
    strategyScores: Object.fromEntries(
      Object.entries(strategyScores).map(([k, v]) => [k, round1(v)]),
    ) as Record<Strategy, number>,
  };
}

function asymmetryScore(input: ScoreInput): {
  value: number;
  ks: KnowledgeState;
  evidence: string[];
} {
  const ask = input.asking_price_usd;
  const base = known(input.estimated_value_base_usd);
  const downside = known(input.downside_value_usd);
  const upside = known(input.development_upside_usd);
  const liq = known(input.liquidity_score);
  const evidence: string[] = [];

  if (ask == null || base == null) {
    return {
      value: 50,
      ks: "UNKNOWN",
      evidence: ["Asymmetry requires ask + base value"],
    };
  }
  const mos = marginOfSafety(ask, base);
  let upsideRatio = 0;
  if (upside != null && ask > 0) {
    upsideRatio = (upside - ask) / ask;
  }
  let downsideGap = 0;
  if (downside != null && ask > 0) {
    downsideGap = Math.max(0, (ask - downside) / ask);
  }
  let score = 50 + mos * 80 + upsideRatio * 25 - downsideGap * 40;
  if (liq != null && liq < 40) {
    score -= (40 - liq) * 0.4;
    evidence.push(`Liquidity drag (${liq})`);
  }
  evidence.push(
    `MoS ${(mos * 100).toFixed(1)}%, upsideRatio ${(upsideRatio * 100).toFixed(1)}%, downsideGap ${(downsideGap * 100).toFixed(1)}%`,
  );
  return {
    value: round1(clamp(score, 0, 100)),
    ks: upside == null || downside == null ? "ESTIMATED" : ks(input.estimated_value_base_usd),
    evidence,
  };
}

export function computeConfidence(input: ScoreInput): number {
  const parts: number[] = [];
  parts.push(clamp(input.known_attribute_ratio * 100, 0, 100));
  if (input.geometry_confidence != null) parts.push(input.geometry_confidence);
  parts.push(clamp(input.comps_count * 15, 0, 100));
  const sourceConfs = [
    input.estimated_value_base_usd.confidence,
    input.prime_farmland_pct.confidence,
    input.wetland_pct.confidence,
    input.flood_zone_pct.confidence,
    input.avg_slope_pct.confidence,
  ].filter((c): c is number => c != null);
  if (sourceConfs.length) {
    parts.push(sourceConfs.reduce((a, b) => a + b, 0) / sourceConfs.length);
  }
  const unavailablePenalty =
    [
      input.wetland_pct,
      input.flood_zone_pct,
      input.prime_farmland_pct,
      input.estimated_value_base_usd,
    ].filter((p) => p.knowledge_state === "TEMPORARILY_UNAVAILABLE").length * 8;
  return round1(clamp((avg(parts) ?? 40) - unavailablePenalty, 0, 100));
}

export function dealReadiness(input: ScoreInput): number {
  let score = 20;
  if (known(input.legal_access_confidence) != null && (known(input.legal_access_confidence) ?? 0) >= 70)
    score += 15;
  else score += 0;
  if (input.geometry_confidence != null && input.geometry_confidence >= 80) score += 15;
  if (known(input.flood_zone_pct) != null) score += 10;
  if (known(input.wetland_pct) != null) score += 10;
  if (input.comps_count >= 3) score += 10;
  if (known(input.zoning_development_friendly) != null) score += 10;
  // Title/survey never auto-complete
  return round1(clamp(score, 0, 100));
}

function signalFrom(opportunity: number, risk: number, confidence: number): Signal {
  if (opportunity < 40 || (risk > 75 && opportunity < 70)) return "REJECT";
  if (opportunity >= 90 && risk <= 35 && confidence >= 70) return "EXCEPTIONAL";
  if (opportunity >= 75 && risk <= 50) return "STRONG";
  return "WATCH";
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

export function computeLandSignalScore(
  input: ScoreInput,
  weights: WeightConfig = DEFAULT_WEIGHTS,
  weightVersion = WEIGHT_VERSION,
): ScoreResult {
  const screens = screenStrategies(input);
  const { risk, evidence: riskEvidence } = computeRisk(input);
  const valuation = valuationScore(input);
  const quality = qualityScore(input);
  const optionality = optionalityScore(input, screens);
  const growth = known(input.path_of_growth_score);
  const infraAccess = known(input.legal_access_confidence);
  const infraFrontage = known(input.road_frontage_m);
  const infra = avg([
    infraAccess,
    infraFrontage == null ? null : clamp(infraFrontage / 5, 0, 100),
    known(input.nearest_transmission_m) == null
      ? null
      : clamp(100 - (known(input.nearest_transmission_m)! / 5000) * 100, 0, 100),
  ]);
  const liquidity = known(input.liquidity_score);
  const scarcity = known(input.scarcity_score);
  const catalysts = known(input.catalyst_score);
  const seller = known(input.seller_pressure_score);
  const asymmetry = asymmetryScore(input);
  const confidence = computeConfidence(input);

  const categoryValues: Record<keyof WeightConfig, { value: number; ks: KnowledgeState; evidence: string[] }> = {
    valuation_mispricing: {
      value: valuation.value,
      ks: valuation.ks,
      evidence: valuation.evidence,
    },
    intrinsic_land_quality: quality,
    hbu_optionality: {
      value: optionality.value,
      ks: optionality.ks,
      evidence: optionality.evidence,
    },
    growth_appreciation: {
      value: growth ?? 50,
      ks: growth == null ? "UNKNOWN" : ks(input.path_of_growth_score),
      evidence: growth == null ? ["Growth score unknown — neutral"] : [`Path-of-growth ${growth}`],
    },
    infrastructure: {
      value: infra ?? 50,
      ks: infra == null ? "UNKNOWN" : "ESTIMATED",
      evidence: infra == null ? ["Infrastructure unknown — neutral"] : [`Infrastructure composite ${round1(infra)}`],
    },
    liquidity: {
      value: liquidity ?? 50,
      ks: liquidity == null ? "UNKNOWN" : ks(input.liquidity_score),
      evidence: liquidity == null ? ["Liquidity unknown — neutral"] : [`Liquidity ${liquidity}`],
    },
    scarcity: {
      value: scarcity ?? 50,
      ks: scarcity == null ? "UNKNOWN" : ks(input.scarcity_score),
      evidence: scarcity == null ? ["Scarcity unknown — neutral"] : [`Scarcity ${scarcity}`],
    },
    catalysts: {
      value: catalysts ?? 40,
      ks: catalysts == null ? "UNKNOWN" : ks(input.catalyst_score),
      evidence: catalysts == null ? ["No structured catalysts"] : [`Catalyst score ${catalysts}`],
    },
    seller_dynamics: {
      value: seller ?? 40,
      ks: seller == null ? "UNKNOWN" : ks(input.seller_pressure_score),
      evidence:
        seller == null
          ? ["Seller dynamics unknown"]
          : [`Seller pressure ${seller}`, ...(input.days_on_market != null ? [`DOM ${input.days_on_market}`] : [])],
    },
    risk: {
      value: invertRisk(risk),
      ks: "ESTIMATED",
      evidence: riskEvidence,
    },
  };

  const components: ScoreComponent[] = [];
  let opportunity = 0;
  for (const [category, weight] of Object.entries(weights) as Array<[keyof WeightConfig, number]>) {
    const c = categoryValues[category];
    const contribution = c.value * weight;
    opportunity += contribution;
    components.push({
      category,
      label: category,
      value: round1(c.value),
      weight,
      contribution: round1(contribution),
      knowledge_state: c.ks,
      evidence: c.evidence,
    });
  }
  opportunity = round1(clamp(opportunity, 0, 100));

  const ranked = (Object.entries(optionality.strategyScores) as Array<[Strategy, number]>)
    .filter(([s]) => screens[s] !== "FAIL")
    .sort((a, b) => b[1] - a[1]);

  const explanations = components.flatMap((c) =>
    c.evidence.map((e) => `[${c.category}] ${e}`),
  );

  const why_interesting: string[] = [];
  if (valuation.discount != null && valuation.discount < -10) {
    why_interesting.push(
      `Asking price appears ${Math.abs(valuation.discount).toFixed(1)}% below model base value`,
    );
  }
  if (optionality.value >= 70) {
    why_interesting.push("Multiple non-failed strategies show material optionality");
  }
  if ((growth ?? 0) >= 70) {
    why_interesting.push("Path-of-growth score is elevated versus distance-only heuristics");
  }

  const why_mispriced: string[] = [];
  if (input.price_reduction_pct != null && input.price_reduction_pct >= 10) {
    why_mispriced.push(`Recent price reduction of ${input.price_reduction_pct}% may have reset economics`);
  }
  if (valuation.discount != null && valuation.discount < -15 && confidence >= 60) {
    why_mispriced.push("Model value / ask gap is wide with moderate-or-better confidence");
  }

  const what_could_kill = [...riskEvidence];
  if (screens.DEVELOPMENT === "FAIL") what_could_kill.push("Development thesis fails stage-1 screens");
  if ((known(input.legal_access_confidence) ?? 100) < 40) {
    what_could_kill.push("Access may be legally insufficient — survey/title required");
  }

  const why_still_available: string[] = [];
  if (input.days_on_market != null && input.days_on_market > 120) {
    why_still_available.push("Extended DOM — investigate defects, marketing, or prior overpricing");
  }
  if ((liquidity ?? 100) < 40) {
    why_still_available.push("Thin buyer pool / low liquidity may deter institutions");
  }
  if (confidence < 55) {
    why_still_available.push("Incomplete public data may be deterring underwritten bids");
  }

  const manual_verification = [
    "Confirm title and legal access with recorded documents",
    "Verify parcel geometry / acreage against survey or assessor polygon",
    "Confirm zoning and future land use with county staff",
    "Validate flood/wetland screening with site diligence if material",
  ];

  return {
    algorithm_version: ALGORITHM_VERSION,
    weight_version: weightVersion,
    opportunity,
    risk,
    confidence,
    asymmetry: asymmetry.value,
    signal: signalFrom(opportunity, risk, confidence),
    best_strategy: ranked[0]?.[0] ?? null,
    secondary_strategy: ranked[1]?.[0] ?? null,
    strategy_scores: optionality.strategyScores,
    strategy_screens: screens,
    estimated_value_usd: valuation.est,
    asking_discount_pct: valuation.discount,
    deal_readiness: dealReadiness(input),
    components,
    explanations,
    why_interesting,
    why_mispriced,
    what_could_kill,
    why_still_available,
    manual_verification,
    input_hash: inputHash({ input, weights, algorithm: ALGORITHM_VERSION, weightVersion }),
  };
}

export function personalizedScore(
  globalOpportunity: number,
  profile: {
    preferred_strategies: Strategy[];
    max_price_usd?: number | null;
    min_acres?: number | null;
    min_target_irr?: number | null;
    risk_tolerance?: string;
  },
  context: {
    asking_price_usd: number | null;
    acreage: number | null;
    best_strategy: Strategy | null;
    risk: number;
  },
): number {
  let score = globalOpportunity;
  if (
    context.asking_price_usd != null &&
    profile.max_price_usd != null &&
    context.asking_price_usd > profile.max_price_usd
  ) {
    score -= 25;
  }
  if (
    context.acreage != null &&
    profile.min_acres != null &&
    context.acreage < profile.min_acres
  ) {
    score -= 20;
  }
  if (
    context.best_strategy &&
    profile.preferred_strategies.length &&
    !profile.preferred_strategies.includes(context.best_strategy)
  ) {
    score -= 10;
  } else if (
    context.best_strategy &&
    profile.preferred_strategies.includes(context.best_strategy)
  ) {
    score += 5;
  }
  if (profile.risk_tolerance === "LOW" && context.risk > 40) score -= 10;
  if (profile.risk_tolerance === "HIGH" && context.risk < 60) score += 3;
  return round1(clamp(score, 0, 100));
}
