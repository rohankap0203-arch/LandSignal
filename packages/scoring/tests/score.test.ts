import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { computeLandSignalScore, personalizedScore } from "../src/score.ts";
import type { ProvenancedNumber, ScoreInput } from "../src/types.ts";

function p(
  value: number | null,
  knowledge_state: ProvenancedNumber["knowledge_state"] = "KNOWN",
  confidence: number | null = 80,
): ProvenancedNumber {
  return { value, knowledge_state, confidence };
}

function baseInput(over: Partial<ScoreInput> = {}): ScoreInput {
  return {
    asking_price_usd: 475_000,
    acreage: 80,
    estimated_value_low_usd: p(420_000),
    estimated_value_base_usd: p(620_000),
    estimated_value_high_usd: p(780_000),
    downside_value_usd: p(405_000),
    development_upside_usd: p(1_100_000),
    prime_farmland_pct: p(72),
    wetland_pct: p(8),
    flood_zone_pct: p(5),
    avg_slope_pct: p(3),
    max_slope_pct: p(8),
    legal_access_confidence: p(78),
    road_frontage_m: p(400),
    nearest_transmission_m: p(3500),
    liquidity_score: p(55),
    scarcity_score: p(60),
    path_of_growth_score: p(68),
    catalyst_score: p(40),
    seller_pressure_score: p(62),
    days_on_market: 45,
    price_reduction_pct: 12,
    environmental_contamination: p(5),
    zoning_development_friendly: p(55),
    timber_suitability: p(30),
    solar_irradiance_score: p(70),
    geometry_confidence: 85,
    comps_count: 4,
    known_attribute_ratio: 0.82,
    listing_freshness_hours: 6,
    ...over,
  };
}

describe("landsignal score v1", () => {
  it("is reproducible for identical inputs", () => {
    const a = computeLandSignalScore(baseInput());
    const b = computeLandSignalScore(baseInput());
    assert.equal(a.input_hash, b.input_hash);
    assert.equal(a.opportunity, b.opportunity);
    assert.equal(a.asymmetry, b.asymmetry);
  });

  it("does not treat missing flood as zero risk free lunch", () => {
    const knownFlood = computeLandSignalScore(baseInput({ flood_zone_pct: p(0) }));
    const unknownFlood = computeLandSignalScore(
      baseInput({
        flood_zone_pct: p(null, "UNKNOWN", null),
        known_attribute_ratio: 0.5,
      }),
    );
    assert.ok(unknownFlood.confidence < knownFlood.confidence);
  });

  it("fails development but not recreation for high wetlands", () => {
    const result = computeLandSignalScore(baseInput({ wetland_pct: p(55) }));
    assert.equal(result.strategy_screens.DEVELOPMENT, "FAIL");
    assert.notEqual(result.strategy_screens.RECREATIONAL, "FAIL");
  });

  it("flags strong mispricing opportunity", () => {
    const result = computeLandSignalScore(baseInput());
    assert.ok(result.opportunity >= 70);
    assert.ok(result.asking_discount_pct != null && result.asking_discount_pct < -15);
    assert.ok(result.why_interesting.length >= 1);
    assert.equal(result.algorithm_version, "landsignal_score_v1");
  });

  it("keeps personalized score separate from global", () => {
    const global = computeLandSignalScore(baseInput());
    const personal = personalizedScore(
      global.opportunity,
      {
        preferred_strategies: ["FARMLAND"],
        max_price_usd: 400_000,
        min_acres: 100,
        risk_tolerance: "LOW",
      },
      {
        asking_price_usd: 475_000,
        acreage: 80,
        best_strategy: global.best_strategy,
        risk: global.risk,
      },
    );
    assert.ok(personal < global.opportunity);
  });
});
