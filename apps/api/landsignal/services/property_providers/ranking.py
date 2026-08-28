"""Strategy + hold-period ranking weights (soft — never hard-exclude)."""

from __future__ import annotations

from typing import Any, Mapping

# Configurable weight tables — not hardcoded in UI components.
STRATEGY_RANK_WEIGHTS: dict[str, dict[str, float]] = {
    "FARMLAND": {
        "acreage_scale": 0.18,
        "ag_signal": 0.22,
        "price_attractiveness": 0.16,
        "risk_inverse": 0.12,
        "liquidity": 0.08,
        "structure_bonus": 0.04,
        "catalyst": 0.10,
        "access": 0.10,
    },
    "DEVELOPMENT": {
        "growth": 0.20,
        "infra": 0.16,
        "price_attractiveness": 0.14,
        "parcel_config": 0.10,
        "risk_inverse": 0.10,
        "structure_redev": 0.10,
        "catalyst": 0.12,
        "liquidity": 0.08,
    },
    "LAND_BANK": {
        "scarcity": 0.18,
        "growth": 0.18,
        "infra_trajectory": 0.14,
        "carry_cost": 0.12,
        "price_attractiveness": 0.12,
        "risk_inverse": 0.10,
        "structure_bonus": 0.04,
        "liquidity": 0.12,
    },
    "RECREATIONAL": {
        "amenities": 0.22,
        "access": 0.16,
        "privacy_acreage": 0.14,
        "price_attractiveness": 0.14,
        "risk_inverse": 0.12,
        "structure_bonus": 0.10,
        "liquidity": 0.12,
    },
    "ENERGY": {
        "parcel_scale": 0.20,
        "terrain": 0.14,
        "infra": 0.18,
        "price_attractiveness": 0.14,
        "risk_inverse": 0.12,
        "regulatory": 0.12,
        "structure_bonus": 0.02,
        "liquidity": 0.08,
    },
    "TIMBER": {
        "parcel_scale": 0.22,
        "forest_signal": 0.18,
        "access": 0.14,
        "price_attractiveness": 0.14,
        "risk_inverse": 0.12,
        "structure_bonus": 0.06,
        "liquidity": 0.14,
    },
    "IMPROVED_PROPERTY": {
        "structure_value": 0.22,
        "land_to_improvement": 0.14,
        "rentability": 0.12,
        "redevelopment": 0.12,
        "price_attractiveness": 0.14,
        "infra": 0.10,
        "risk_inverse": 0.08,
        "liquidity": 0.08,
    },
}

HOLD_HORIZON_WEIGHTS: dict[str, dict[str, float]] = {
    # Multipliers applied on top of strategy scores
    "short": {  # ≤3y
        "price_attractiveness": 1.35,
        "catalyst": 1.40,
        "liquidity": 1.35,
        "growth": 0.75,
        "scarcity": 0.70,
        "infra_trajectory": 0.70,
        "carry_cost": 0.85,
    },
    "medium": {  # 3–10y
        "price_attractiveness": 1.10,
        "catalyst": 1.10,
        "liquidity": 1.05,
        "growth": 1.10,
        "scarcity": 1.05,
    },
    "long": {  # 10y+
        "price_attractiveness": 0.85,
        "catalyst": 0.80,
        "liquidity": 0.85,
        "growth": 1.35,
        "scarcity": 1.40,
        "infra_trajectory": 1.35,
        "carry_cost": 1.25,
        "risk_inverse": 1.10,
    },
}


def hold_bucket(hold_years: int | None) -> str:
    if hold_years is None:
        return "medium"
    if hold_years <= 3:
        return "short"
    if hold_years <= 10:
        return "medium"
    return "long"


def strategy_hold_rank_boost(
    *,
    strategy: str | None,
    hold_years: int | None,
    opportunity: float,
    has_structure: bool = False,
    secondary_improved: bool = False,
) -> float:
    """Soft ranking boost — does not eliminate candidates."""
    s = (strategy or "").upper().replace(" ", "_")
    boost = 0.0
    if s and s in STRATEGY_RANK_WEIGHTS:
        boost += 4.0
    bucket = hold_bucket(hold_years)
    if bucket == "short":
        if s in {"ENERGY", "FARMLAND", "RECREATIONAL", "IMPROVED_PROPERTY", "DEVELOPMENT"}:
            boost += 6.0
        elif s == "LAND_BANK":
            boost -= 2.0
        boost += 1.5  # short-horizon liquidity preference
    elif bucket == "long":
        if s in {"LAND_BANK", "DEVELOPMENT", "TIMBER", "FARMLAND"}:
            boost += 6.0
        elif s in {"ENERGY", "RECREATIONAL"}:
            boost -= 1.0
        boost += 2.5  # long-horizon scarcity preference
    else:
        boost += 2.0
    if has_structure and s == "IMPROVED_PROPERTY":
        boost += 8.0
    if secondary_improved and s != "IMPROVED_PROPERTY":
        boost += 2.0
    # Mild preference to keep high opportunity near the top under preferred strategy
    boost += max(0.0, (opportunity - 50.0) * 0.04)
    return boost


def classify_improved(row: Mapping[str, Any]) -> dict[str, Any]:
    has = bool(row.get("hasStructure") or row.get("has_structure"))
    if not has:
        beds = row.get("bedrooms")
        sqft = row.get("buildingSqFt") or row.get("building_sqft")
        if isinstance(beds, dict):
            beds = beds.get("value")
        if isinstance(sqft, dict):
            sqft = sqft.get("value")
        try:
            has = (beds is not None and float(beds) > 0) or (sqft is not None and float(sqft) > 0)
        except (TypeError, ValueError):
            has = False
    return {
        "hasStructure": has,
        "improved_property": has,
        "secondary_characteristic": "IMPROVED_PROPERTY" if has else None,
    }
