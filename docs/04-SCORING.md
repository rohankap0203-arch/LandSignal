# LandSignal — Scoring Framework

## Principles

1. Missing data lowers **confidence**, not automatically **quality**.  
2. Risk is displayed separately from opportunity.  
3. Global score ≠ personalized score.  
4. Strategy scores are independent; kill screens are strategy-scoped.  
5. Algorithms and weights are versioned.  
6. Every score is explainable via components + evidence.

## Versions

| ID | Status |
|---|---|
| `landsignal_score_v1` | Phase 1 default (rules) |
| `weights_default_v1` | Default weight config |

## Knowledge states

`KNOWN` | `UNKNOWN` | `ESTIMATED` | `NOT_APPLICABLE` | `TEMPORARILY_UNAVAILABLE`

## Stage 1 — strategy screens

Per strategy: `PASS` | `FAIL` | `MANUAL_REVIEW`  
A FAIL on residential subdivision does not FAIL recreational or conservation.

## Component categories (default weights — configurable)

| Category | Default weight |
|---|---|
| Valuation / Mispricing | 0.20 |
| Intrinsic Land Quality | 0.10 |
| HBU Optionality | 0.15 |
| Growth / Appreciation | 0.15 |
| Infrastructure | 0.10 |
| Liquidity | 0.08 |
| Scarcity | 0.07 |
| Catalysts | 0.05 |
| Seller Dynamics | 0.05 |
| Risk (inverted contribution) | 0.05 |

Opportunity score is a weighted blend of category scores. Risk score is computed independently (100 = highest risk).

## Strategy scores (Phase 1)

- Farmland  
- Development  
- Land Bank  
- Recreational  
- Energy  
- Timber  

`best_strategy` / `secondary_strategy` = top two by strategy score among non-FAIL strategies.

## Asymmetry score

Heuristic combining:
- margin of safety vs base value  
- upside to bull / development option  
- downside gap to liquidation bear  
- liquidity penalty  
- execution complexity penalty  

## Confidence score

Based on: source quality mix, freshness, % known attributes, geometry confidence, comps count, provider failures.

## Output contract

```json
{
  "algorithm_version": "landsignal_score_v1",
  "weight_version": "weights_default_v1",
  "opportunity": 86,
  "risk": 24,
  "confidence": 71,
  "asymmetry": 82,
  "signal": "STRONG",
  "best_strategy": "LAND_BANK",
  "secondary_strategy": "FARMLAND",
  "components": [],
  "input_hash": "sha256:...",
  "explanations": []
}
```

Signals: `EXCEPTIONAL` | `STRONG` | `WATCH` | `REJECT`
