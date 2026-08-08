export type KnowledgeState =
  | "KNOWN"
  | "UNKNOWN"
  | "ESTIMATED"
  | "NOT_APPLICABLE"
  | "TEMPORARILY_UNAVAILABLE";

export type ScreenResult = "PASS" | "FAIL" | "MANUAL_REVIEW";

export type Signal = "EXCEPTIONAL" | "STRONG" | "WATCH" | "REJECT";

export type Strategy =
  | "FARMLAND"
  | "DEVELOPMENT"
  | "LAND_BANK"
  | "RECREATIONAL"
  | "ENERGY"
  | "TIMBER";

export type WeightConfig = {
  valuation_mispricing: number;
  intrinsic_land_quality: number;
  hbu_optionality: number;
  growth_appreciation: number;
  infrastructure: number;
  liquidity: number;
  scarcity: number;
  catalysts: number;
  seller_dynamics: number;
  risk: number;
};

export const DEFAULT_WEIGHTS: WeightConfig = {
  valuation_mispricing: 0.2,
  intrinsic_land_quality: 0.1,
  hbu_optionality: 0.15,
  growth_appreciation: 0.15,
  infrastructure: 0.1,
  liquidity: 0.08,
  scarcity: 0.07,
  catalysts: 0.05,
  seller_dynamics: 0.05,
  risk: 0.05,
};

export type ProvenancedNumber = {
  value: number | null;
  knowledge_state: KnowledgeState;
  confidence: number | null;
  source?: string | null;
};

export type ScoreInput = {
  asking_price_usd: number | null;
  acreage: number | null;
  estimated_value_low_usd: ProvenancedNumber;
  estimated_value_base_usd: ProvenancedNumber;
  estimated_value_high_usd: ProvenancedNumber;
  downside_value_usd: ProvenancedNumber;
  development_upside_usd: ProvenancedNumber;
  prime_farmland_pct: ProvenancedNumber;
  wetland_pct: ProvenancedNumber;
  flood_zone_pct: ProvenancedNumber;
  avg_slope_pct: ProvenancedNumber;
  max_slope_pct: ProvenancedNumber;
  legal_access_confidence: ProvenancedNumber;
  road_frontage_m: ProvenancedNumber;
  nearest_transmission_m: ProvenancedNumber;
  liquidity_score: ProvenancedNumber;
  scarcity_score: ProvenancedNumber;
  path_of_growth_score: ProvenancedNumber;
  catalyst_score: ProvenancedNumber;
  seller_pressure_score: ProvenancedNumber;
  days_on_market: number | null;
  price_reduction_pct: number | null;
  environmental_contamination: ProvenancedNumber; // 0-100 severity
  zoning_development_friendly: ProvenancedNumber; // 0-100
  timber_suitability: ProvenancedNumber; // 0-100
  solar_irradiance_score: ProvenancedNumber; // 0-100
  geometry_confidence: number | null;
  comps_count: number;
  known_attribute_ratio: number; // 0-1
  listing_freshness_hours: number | null;
};

export type ScoreComponent = {
  category: keyof WeightConfig;
  label: string;
  value: number;
  weight: number;
  contribution: number;
  knowledge_state: KnowledgeState;
  evidence: string[];
};

export type ScoreResult = {
  algorithm_version: string;
  weight_version: string;
  opportunity: number;
  risk: number;
  confidence: number;
  asymmetry: number;
  signal: Signal;
  best_strategy: Strategy | null;
  secondary_strategy: Strategy | null;
  strategy_scores: Record<Strategy, number>;
  strategy_screens: Record<Strategy, ScreenResult>;
  estimated_value_usd: number | null;
  asking_discount_pct: number | null;
  deal_readiness: number;
  components: ScoreComponent[];
  explanations: string[];
  why_interesting: string[];
  why_mispriced: string[];
  what_could_kill: string[];
  why_still_available: string[];
  manual_verification: string[];
  input_hash: string;
};
