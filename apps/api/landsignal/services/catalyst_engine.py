"""Catalyst Simulator / Future Scenario Engine.

Models how future environmental changes around a parcel could alter its
projected land value relative to the baseline Value Path.

Design principles
-----------------
- No universal hard-coded event percentages (e.g. "restaurant = +5%").
- Impact is multiplicative across distance, compatibility, market sensitivity,
  scale, stage certainty, infrastructure/zoning fit, HBU, cycle, and supply.
- Three impact channels: immediate repricing, appreciation-rate change, HBU
  transformation.
- Hypothetical / modeled scenarios are labeled as such — never presented as
  observed municipal or corporate facts.
- Catalyst interactions are correlation-aware (no naive additive stacking).
"""

from __future__ import annotations

import math
import re
from typing import Any

# ---------------------------------------------------------------------------
# Extensible event taxonomy
# ---------------------------------------------------------------------------

EVENT_TAXONOMY: dict[str, dict[str, Any]] = {
    "major_retailer": {
        "label": "Major retailer opens nearby",
        "category": "retail",
        "default_bucket": "high_impact",
        "correlation_group": "commercial_growth",
        "distance_half_life_mi": 1.2,
        "base_channels": {"immediate": 0.2394, "rate": 0.0213, "hbu": 0.1064},
        "preferred_strategies": {"flip", "hold_develop", "subdivide"},
        "needs_road_access": True,
        "chain": ["utility_expansion", "residential_growth", "land_use_intensification"],
    },
    "major_restaurant": {
        "label": "Major restaurant / franchise opens nearby",
        "category": "retail",
        "default_bucket": "likely",
        "correlation_group": "commercial_growth",
        "distance_half_life_mi": 0.55,
        "base_channels": {"immediate": 0.154, "rate": 0.0154, "hbu": 0.077},
        "preferred_strategies": {"flip", "hold_develop"},
        "needs_road_access": True,
        "chain": ["traffic_increase", "commercial_growth"],
    },
    "shopping_center": {
        "label": "Shopping center / mall is built",
        "category": "retail",
        "default_bucket": "high_impact",
        "correlation_group": "commercial_growth",
        "distance_half_life_mi": 2.0,
        "base_channels": {"immediate": 0.312, "rate": 0.0312, "hbu": 0.208},
        "preferred_strategies": {"flip", "hold_develop", "subdivide"},
        "needs_road_access": True,
        "chain": ["residential_growth", "utility_expansion", "road_expansion"],
    },
    "master_planned_community": {
        "label": "Master-planned community begins nearby",
        "category": "residential",
        "default_bucket": "high_impact",
        "correlation_group": "suburban_expansion",
        "distance_half_life_mi": 3.5,
        "base_channels": {"immediate": 0.168, "rate": 0.0336, "hbu": 0.168},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "subdivide", "flip"},
        "needs_road_access": False,
        "chain": ["utility_expansion", "school_opening", "retail_follow_on", "population_growth"],
    },
    "city_expansion": {
        "label": "City expands toward parcel",
        "category": "growth",
        "default_bucket": "likely",
        "correlation_group": "suburban_expansion",
        "distance_half_life_mi": 8.0,
        "base_channels": {"immediate": 0.1134, "rate": 0.0454, "hbu": 0.1512},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "subdivide", "flip"},
        "needs_road_access": False,
        "chain": ["annexation", "utility_expansion", "zoning_change", "residential_growth"],
    },
    "major_employer": {
        "label": "Major employer relocates nearby",
        "category": "employment",
        "default_bucket": "high_impact",
        "correlation_group": "employment_node",
        "distance_half_life_mi": 6.0,
        "base_channels": {"immediate": 0.1, "rate": 0.02, "hbu": 0.075},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "subdivide", "flip"},
        "needs_road_access": False,
        "chain": ["residential_growth", "retail_follow_on", "road_expansion"],
    },
    "highway_interchange": {
        "label": "Highway interchange is added",
        "category": "access",
        "default_bucket": "high_impact",
        "correlation_group": "access_upgrade",
        "distance_half_life_mi": 4.5,
        "base_channels": {"immediate": 0.2268, "rate": 0.0292, "hbu": 0.2592},
        "preferred_strategies": {"hold_develop", "flip", "subdivide", "hold_appreciate"},
        "needs_road_access": True,
        "chain": ["commercial_development", "utility_expansion", "residential_growth", "land_use_intensification"],
    },
    "road_widened": {
        "label": "Road is widened",
        "category": "access",
        "default_bucket": "likely",
        "correlation_group": "access_upgrade",
        "distance_half_life_mi": 1.5,
        "base_channels": {"immediate": 0.055, "rate": 0.0088, "hbu": 0.044},
        "preferred_strategies": {"flip", "hold_develop", "subdivide"},
        "needs_road_access": True,
        "chain": ["commercial_growth", "traffic_increase"],
    },
    "road_paved": {
        "label": "Road becomes paved",
        "category": "access",
        "default_bucket": "likely",
        "correlation_group": "access_upgrade",
        "distance_half_life_mi": 0.8,
        "base_channels": {"immediate": 0.092, "rate": 0.0069, "hbu": 0.0805},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "flip", "subdivide"},
        "needs_road_access": True,
        "chain": ["residential_growth", "entitlement_easier"],
    },
    "sewer_extension": {
        "label": "Municipal sewer reaches parcel",
        "category": "utilities",
        "default_bucket": "high_impact",
        "correlation_group": "utility_infrastructure",
        "distance_half_life_mi": 1.0,
        "base_channels": {"immediate": 0.2, "rate": 0.015, "hbu": 0.3},
        "preferred_strategies": {"hold_develop", "subdivide", "flip"},
        "needs_road_access": False,
        "service_boundary_sensitive": True,
        "chain": ["density_entitlement", "residential_growth", "commercial_development"],
    },
    "municipal_water": {
        "label": "Municipal water reaches parcel",
        "category": "utilities",
        "default_bucket": "high_impact",
        "correlation_group": "utility_infrastructure",
        "distance_half_life_mi": 1.2,
        "base_channels": {"immediate": 0.15, "rate": 0.0125, "hbu": 0.225},
        "preferred_strategies": {"hold_develop", "subdivide", "flip"},
        "needs_road_access": False,
        "service_boundary_sensitive": True,
        "chain": ["density_entitlement", "residential_growth"],
    },
    "electrical_expansion": {
        "label": "Electrical infrastructure expands",
        "category": "utilities",
        "default_bucket": "likely",
        "correlation_group": "utility_infrastructure",
        "distance_half_life_mi": 2.0,
        "base_channels": {"immediate": 0.044, "rate": 0.0044, "hbu": 0.066},
        "preferred_strategies": {"hold_develop", "flip"},
        "needs_road_access": False,
        "chain": ["industrial_feasibility", "residential_growth"],
    },
    "broadband": {
        "label": "Broadband reaches parcel",
        "category": "utilities",
        "default_bucket": "likely",
        "correlation_group": "utility_infrastructure",
        "distance_half_life_mi": 3.0,
        "base_channels": {"immediate": 0.039, "rate": 0.0078, "hbu": 0.039},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "flip"},
        "needs_road_access": False,
        "chain": ["remote_work_demand", "residential_growth"],
    },
    "school_university": {
        "label": "New school / university opens",
        "category": "amenities",
        "default_bucket": "likely",
        "correlation_group": "amenity_demand",
        "distance_half_life_mi": 3.0,
        "base_channels": {"immediate": 0.0891, "rate": 0.0149, "hbu": 0.0594},
        "preferred_strategies": {"hold_appreciate", "subdivide", "flip"},
        "needs_road_access": False,
        "chain": ["residential_growth", "retail_follow_on"],
    },
    "hospital": {
        "label": "Hospital opens",
        "category": "amenities",
        "default_bucket": "high_impact",
        "correlation_group": "employment_node",
        "distance_half_life_mi": 4.0,
        "base_channels": {"immediate": 0.092, "rate": 0.0138, "hbu": 0.0575},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "flip"},
        "needs_road_access": False,
        "chain": ["residential_growth", "medical_office_demand"],
    },
    "public_transit": {
        "label": "Public transit reaches area",
        "category": "access",
        "default_bucket": "likely",
        "correlation_group": "access_upgrade",
        "distance_half_life_mi": 2.5,
        "base_channels": {"immediate": 0.0805, "rate": 0.0115, "hbu": 0.069},
        "preferred_strategies": {"hold_develop", "flip", "subdivide"},
        "needs_road_access": False,
        "chain": ["density_entitlement", "residential_growth"],
    },
    "airport_expansion": {
        "label": "Airport expands",
        "category": "access",
        "default_bucket": "high_impact",
        "correlation_group": "access_upgrade",
        "distance_half_life_mi": 8.0,
        "base_channels": {"immediate": 0.066, "rate": 0.0088, "hbu": 0.088},
        "preferred_strategies": {"hold_develop", "flip"},
        "needs_road_access": False,
        "chain": ["industrial_demand", "employment_growth"],
        "externality_risk": 0.15,
    },
    "industrial_facility": {
        "label": "New industrial facility opens",
        "category": "employment",
        "default_bucket": "likely",
        "correlation_group": "employment_node",
        "distance_half_life_mi": 5.0,
        "base_channels": {"immediate": 0.055, "rate": 0.011, "hbu": 0.044},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "flip"},
        "needs_road_access": False,
        "chain": ["residential_demand", "road_expansion"],
        "externality_risk": 0.2,
    },
    "zoning_change": {
        "label": "Zoning changes (higher intensity)",
        "category": "entitlement",
        "default_bucket": "high_impact",
        "correlation_group": "entitlement",
        "distance_half_life_mi": 0.3,
        "base_channels": {"immediate": 0.24, "rate": 0.0096, "hbu": 0.336},
        "preferred_strategies": {"hold_develop", "flip", "subdivide"},
        "needs_road_access": False,
        "chain": ["density_entitlement", "land_use_intensification"],
    },
    "annexation": {
        "label": "Parcel becomes annexed",
        "category": "entitlement",
        "default_bucket": "likely",
        "correlation_group": "entitlement",
        "distance_half_life_mi": 0.5,
        "base_channels": {"immediate": 0.12, "rate": 0.0144, "hbu": 0.168},
        "preferred_strategies": {"hold_develop", "flip", "subdivide"},
        "needs_road_access": False,
        "chain": ["utility_expansion", "zoning_change"],
    },
    "density_entitlement": {
        "label": "Density entitlement increases",
        "category": "entitlement",
        "default_bucket": "high_impact",
        "correlation_group": "entitlement",
        "distance_half_life_mi": 0.3,
        "base_channels": {"immediate": 0.192, "rate": 0.012, "hbu": 0.288},
        "preferred_strategies": {"hold_develop", "subdivide", "flip"},
        "needs_road_access": False,
        "chain": ["land_use_intensification"],
    },
    "neighbor_approval": {
        "label": "Neighboring parcel receives development approval",
        "category": "entitlement",
        "default_bucket": "likely",
        "correlation_group": "suburban_expansion",
        "distance_half_life_mi": 0.75,
        "base_channels": {"immediate": 0.0858, "rate": 0.0114, "hbu": 0.0715},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "flip", "subdivide"},
        "needs_road_access": False,
        "chain": ["utility_expansion", "retail_follow_on"],
    },
    "land_conserved": {
        "label": "Nearby land is conserved",
        "category": "amenities",
        "default_bucket": "likely",
        "correlation_group": "amenity_demand",
        "distance_half_life_mi": 2.0,
        "base_channels": {"immediate": 0.04, "rate": 0.004, "hbu": 0.02},
        "preferred_strategies": {"hold_appreciate", "recreation"},
        "needs_road_access": False,
        "chain": ["scarcity_premium"],
        "sign": 1,
    },
    "park_recreation": {
        "label": "New park / recreation facility opens",
        "category": "amenities",
        "default_bucket": "likely",
        "correlation_group": "amenity_demand",
        "distance_half_life_mi": 1.5,
        "base_channels": {"immediate": 0.0625, "rate": 0.0075, "hbu": 0.025},
        "preferred_strategies": {"hold_appreciate", "flip", "recreation"},
        "needs_road_access": False,
        "chain": ["residential_premium"],
    },
    "population_growth": {
        "label": "Population growth accelerates",
        "category": "demand",
        "default_bucket": "likely",
        "correlation_group": "suburban_expansion",
        "distance_half_life_mi": 12.0,
        "base_channels": {"immediate": 0.065, "rate": 0.0325, "hbu": 0.065},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "subdivide", "flip"},
        "needs_road_access": False,
        "chain": ["retail_follow_on", "school_opening"],
    },
    "employment_decline": {
        "label": "Employment declines",
        "category": "downside",
        "default_bucket": "downside",
        "correlation_group": "economic_stress",
        "distance_half_life_mi": 15.0,
        "base_channels": {"immediate": -0.1352, "rate": -0.027, "hbu": -0.0676},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["population_contraction", "oversupply"],
        "sign": -1,
    },
    "employer_closes": {
        "label": "Local major employer closes",
        "category": "downside",
        "default_bucket": "downside",
        "correlation_group": "economic_stress",
        "distance_half_life_mi": 10.0,
        "base_channels": {"immediate": -0.1755, "rate": -0.0351, "hbu": -0.0878},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["employment_decline", "population_contraction"],
        "sign": -1,
    },
    "flood_risk_increase": {
        "label": "Flood risk increases",
        "category": "downside",
        "default_bucket": "downside",
        "correlation_group": "environmental_risk",
        "distance_half_life_mi": 1.0,
        "base_channels": {"immediate": -0.2268, "rate": -0.0151, "hbu": -0.189},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["insurance_deterioration", "lending_friction"],
        "sign": -1,
    },
    "wildfire_risk_increase": {
        "label": "Wildfire risk increases",
        "category": "downside",
        "correlation_group": "environmental_risk",
        "default_bucket": "downside",
        "distance_half_life_mi": 4.0,
        "base_channels": {"immediate": -0.169, "rate": -0.0169, "hbu": -0.1352},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["insurance_deterioration"],
        "sign": -1,
    },
    "contamination": {
        "label": "Contamination occurs nearby",
        "category": "downside",
        "default_bucket": "downside",
        "correlation_group": "environmental_risk",
        "distance_half_life_mi": 1.5,
        "base_channels": {"immediate": -0.2704, "rate": -0.0101, "hbu": -0.2366},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["lending_friction", "entitlement_harder"],
        "sign": -1,
    },
    "brownfield_cleanup": {
        "label": "Nearby brownfield / Superfund cleaned up",
        "category": "amenities",
        "default_bucket": "likely",
        "correlation_group": "environmental_remediation",
        "distance_half_life_mi": 2.0,
        "base_channels": {"immediate": 0.077, "rate": 0.0088, "hbu": 0.066},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "flip"},
        "needs_road_access": False,
        "chain": ["residential_growth", "commercial_development"],
    },
    "landfill": {
        "label": "Landfill opens nearby",
        "category": "downside",
        "default_bucket": "downside",
        "correlation_group": "nuisance",
        "distance_half_life_mi": 3.0,
        "base_channels": {"immediate": -0.2744, "rate": -0.0157, "hbu": -0.196},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["amenity_decline"],
        "sign": -1,
    },
    "quarry_mining": {
        "label": "Quarry / mining operation begins",
        "category": "downside",
        "default_bucket": "downside",
        "correlation_group": "nuisance",
        "distance_half_life_mi": 2.5,
        "base_channels": {"immediate": -0.125, "rate": -0.0075, "hbu": -0.1},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["amenity_decline"],
        "sign": -1,
    },
    "water_availability_worse": {
        "label": "Water availability deteriorates",
        "category": "downside",
        "default_bucket": "downside",
        "correlation_group": "resource_constraint",
        "distance_half_life_mi": 20.0,
        "base_channels": {"immediate": -0.1352, "rate": -0.0203, "hbu": -0.2704},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["development_moratorium"],
        "sign": -1,
    },
    "environmental_restrictions": {
        "label": "Environmental restrictions increase",
        "category": "downside",
        "default_bucket": "downside",
        "correlation_group": "entitlement_friction",
        "distance_half_life_mi": 5.0,
        "base_channels": {"immediate": -0.09, "rate": -0.009, "hbu": -0.18},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["entitlement_harder"],
        "sign": -1,
    },
    "ag_economics_change": {
        "label": "Agricultural economics change",
        "category": "demand",
        "default_bucket": "likely",
        "correlation_group": "ag_cycle",
        "distance_half_life_mi": 25.0,
        "base_channels": {"immediate": 0.03, "rate": 0.008, "hbu": 0.02},
        "preferred_strategies": {"farm", "hold_appreciate"},
        "needs_road_access": False,
        "chain": [],
    },
    "residential_subdivision": {
        "label": "Nearby residential subdivision (≈2,000 homes)",
        "category": "residential",
        "default_bucket": "high_impact",
        "correlation_group": "suburban_expansion",
        "distance_half_life_mi": 2.5,
        "base_channels": {"immediate": 0.1512, "rate": 0.0269, "hbu": 0.1176},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "flip", "subdivide"},
        "needs_road_access": False,
        "chain": ["retail_follow_on", "school_opening", "utility_expansion"],
    },
    "distribution_center": {
        "label": "Amazon-scale distribution center nearby",
        "category": "employment",
        "default_bucket": "high_impact",
        "correlation_group": "employment_node",
        "distance_half_life_mi": 7.0,
        "base_channels": {"immediate": 0.1312, "rate": 0.0263, "hbu": 0.1125},
        "preferred_strategies": {"hold_appreciate", "hold_develop", "flip"},
        "needs_road_access": True,
        "chain": ["road_expansion", "residential_demand", "retail_follow_on"],
        "externality_risk": 0.12,
    },
    "neighbor_industrial": {
        "label": "Neighboring parcel becomes industrial",
        "category": "downside",
        "default_bucket": "downside",
        "correlation_group": "nuisance",
        "distance_half_life_mi": 0.6,
        "base_channels": {"immediate": -0.1456, "rate": -0.0109, "hbu": -0.1274},
        "preferred_strategies": set(),
        "needs_road_access": False,
        "chain": ["amenity_decline"],
        "sign": -1,
        "externality_risk": 0.35,
    },
}

STAGE_CERTAINTY: dict[str, float] = {
    "Rumored": 0.12,
    "Proposed": 0.22,
    "Filed": 0.35,
    "Under Review": 0.45,
    "Approved": 0.62,
    "Funded": 0.72,
    "Permitted": 0.78,
    "Land Acquired": 0.82,
    "Construction Started": 0.88,
    "Under Construction": 0.92,
    "Nearly Complete": 0.96,
    "Operational": 1.0,
    "Cancelled": 0.0,
}

EVIDENCE_TIERS = [
    "same_municipality",
    "same_county",
    "neighboring_counties",
    "same_metro",
    "similar_state_markets",
    "similar_nationwide",
    "published_research",
]

DATA_INTEGRITY_LABELS = (
    "Observed Fact",
    "Officially Announced",
    "Approved",
    "Estimated",
    "Modeled",
    "Hypothetical",
    "User-Created Scenario",
)

STRATEGY_MAP = {
    "DEVELOPMENT": "hold_develop",
    "LAND_BANK": "hold_appreciate",
    "RECREATIONAL": "recreation",
    "FARMLAND": "farm",
    "TIMBER": "farm",
    "ENERGY": "hold_develop",
    "FLIP": "flip",
    "SUBDIVIDE": "subdivide",
    "hold_develop": "hold_develop",
    "hold_appreciate": "hold_appreciate",
    "recreation": "recreation",
    "farm": "farm",
    "flip": "flip",
    "subdivide": "subdivide",
}


def normalize_strategy(raw: Any) -> str:
    if raw is None:
        return "hold_appreciate"
    if hasattr(raw, "value"):
        raw = raw.value
    key = str(raw).strip()
    return STRATEGY_MAP.get(key, STRATEGY_MAP.get(key.upper(), "hold_appreciate"))


def screens_from_score_context(
    score: Any,
    enrichment: Any = None,
) -> list[dict[str, Any]]:
    """Map Land Signal score components / snapshot into catalyst screen inputs."""
    comps: dict[str, float] = {}
    if score is not None:
        for c in getattr(score, "components", None) or []:
            if isinstance(c, dict) and c.get("category") is not None:
                try:
                    comps[str(c["category"])] = float(c.get("value") or 50)
                except (TypeError, ValueError):
                    pass

    snap = getattr(score, "input_snapshot", None) or {}
    if not isinstance(snap, dict):
        snap = {}

    def _snap_val(key: str) -> float | None:
        blob = snap.get(key)
        if isinstance(blob, dict) and blob.get("value") is not None:
            try:
                return float(blob["value"])
            except (TypeError, ValueError):
                return None
        if blob is not None and not isinstance(blob, dict):
            try:
                return float(blob)
            except (TypeError, ValueError):
                return None
        return None

    growth = _snap_val("path_of_growth_score")
    if growth is None:
        growth = comps.get("growth_appreciation", 50.0)

    access = _snap_val("legal_access_confidence")
    if access is None:
        access = comps.get("infrastructure", 50.0)

    flood_pct = _snap_val("flood_zone_pct")
    if flood_pct is not None:
        flood = _clip(100.0 - flood_pct, 0, 100)
    else:
        # Higher risk component ⇒ weaker flood screen.
        risk = comps.get("risk", 50.0)
        flood = _clip(100.0 - (risk - 40.0), 25, 90)

    title = access
    strategy_fit = comps.get("hbu_optionality", 50.0)

    # Enrichment flood override when present
    if enrichment is not None:
        flood_layer = getattr(enrichment, "flood", None)
        if flood_layer is not None:
            attrs = getattr(flood_layer, "attributes", None) or {}
            if isinstance(attrs, dict):
                for k in ("flood_zone_pct", "pct_in_floodplain", "sfha_pct"):
                    if attrs.get(k) is not None:
                        try:
                            flood = _clip(100.0 - float(attrs[k]), 0, 100)
                            break
                        except (TypeError, ValueError):
                            pass

    return [
        {"key": "growth", "score": float(growth)},
        {"key": "access", "score": float(access)},
        {"key": "flood", "score": float(flood)},
        {"key": "title", "score": float(title)},
        {"key": "strategy", "score": float(strategy_fit)},
    ]


def flood_zone_label(enrichment: Any = None, snap: dict[str, Any] | None = None) -> str | None:
    if enrichment is not None:
        flood_layer = getattr(enrichment, "flood", None)
        if flood_layer is not None:
            attrs = getattr(flood_layer, "attributes", None) or {}
            if isinstance(attrs, dict):
                for k in ("zone", "flood_zone", "sfha_zone", "label"):
                    if attrs.get(k):
                        return str(attrs[k])
    return None


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _screen_map(screens: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for s in screens or []:
        key = str(s.get("key") or "").strip()
        if key:
            out[key] = s
    return out


def _score(screens: dict[str, dict[str, Any]], key: str, default: float = 50.0) -> float:
    s = screens.get(key) or {}
    try:
        return float(s.get("score", default))
    except (TypeError, ValueError):
        return default


def distance_decay(distance_mi: float, half_life_mi: float) -> float:
    """Exponential decay by catalyst-specific half-life (not a hard radius)."""
    d = max(0.0, float(distance_mi))
    hl = max(0.05, float(half_life_mi))
    return math.exp(-math.log(2.0) * d / hl)


def parcel_compatibility_score(
    event_key: str,
    *,
    screens: dict[str, dict[str, Any]],
    strategy: str,
    acres: float | None,
    flood_zone: str | None,
) -> tuple[float, list[str]]:
    """0–100: does this catalyst actually benefit (or harm) THIS parcel?"""
    meta = EVENT_TAXONOMY[event_key]
    reasons: list[str] = []
    score = 48.0

    growth = _score(screens, "growth")
    access = _score(screens, "access")
    flood = _score(screens, "flood")
    title = _score(screens, "title")
    strategy_fit = _score(screens, "strategy")

    preferred = meta.get("preferred_strategies") or set()
    if preferred and strategy in preferred:
        score += 14
        reasons.append(f"Strategy fit: {strategy.replace('_', ' ')} aligns with this catalyst")
    elif preferred and strategy:
        score -= 6
        reasons.append("Strategy fit is only partial for this catalyst")

    if meta.get("needs_road_access"):
        if access >= 70:
            score += 12
            reasons.append("Strong road access supports commercial / traffic-sensitive catalysts")
        elif access < 45:
            score -= 18
            reasons.append("Weak road access reduces compatibility with traffic-driven catalysts")
        else:
            score += 2

    if event_key in {"sewer_extension", "municipal_water", "density_entitlement", "zoning_change", "annexation"}:
        if growth >= 60:
            score += 10
            reasons.append("Growth corridor context increases infrastructure / entitlement upside")
        if acres and acres >= 5:
            score += 8
            reasons.append(f"{acres:.1f} acres provide developable mass if utilities/entitlements improve")
        elif acres and acres < 1.5:
            score -= 4
            reasons.append("Small acreage limits densification upside")

    if event_key in {"major_restaurant", "major_retailer", "shopping_center"}:
        # Secluded / recreation-leaning parcels may see externalities, not windfalls.
        if strategy in {"recreation", "hold_appreciate"} and access < 55:
            score -= 16
            reasons.append("Secluded / recreational context — retail traffic can be an externality")
        if access >= 65 and strategy in {"flip", "hold_develop", "subdivide"}:
            score += 10
            reasons.append("Roadside / developable profile can capture retail node spillover")

    if meta.get("default_bucket") == "downside" or meta.get("sign", 1) < 0:
        if event_key == "flood_risk_increase":
            if flood < 55 or (flood_zone and str(flood_zone).upper() not in {"", "X", "AREA OF MINIMAL FLOOD HAZARD"}):
                score += 20  # already exposed → higher relevance of downside
                reasons.append("Existing flood exposure makes further risk reclassification highly material")
            else:
                score += 6
                reasons.append("Currently lower flood screen — downside is plausible but less parcel-specific")
        if event_key in {"landfill", "quarry_mining", "neighbor_industrial", "contamination"}:
            if strategy in {"recreation", "hold_appreciate", "flip"}:
                score += 12
                reasons.append("Amenity-sensitive use makes nuisance catalysts more damaging")
        # For downside, "compatibility" = how strongly the harm applies to this parcel
        score = _clip(score, 0, 100)
        return score, reasons

    if flood < 40:
        score -= 10
        reasons.append("Flood constraints reduce ability to capitalize on growth catalysts")
    if title < 45:
        score -= 6
        reasons.append("Title / access friction can mute catalyst capitalization")

    if strategy_fit >= 70:
        score += 6

    score = _clip(score, 0, 100)
    if not reasons:
        reasons.append("Compatibility based on zoning-adjacent screens, access, growth, and strategy fit")
    return score, reasons


def local_market_sensitivity(screens: dict[str, dict[str, Any]], strategy: str) -> float:
    growth = _score(screens, "growth")
    # Thin / slower markets transmit catalysts less efficiently.
    sens = 0.55 + (growth / 100.0) * 0.55
    if strategy in {"hold_develop", "subdivide", "flip"}:
        sens += 0.08
    return _clip(sens, 0.4, 1.25)


def market_cycle_adjustment(screens: dict[str, dict[str, Any]]) -> float:
    growth = _score(screens, "growth")
    # Hot corridors capitalize sooner; soft markets discount.
    return _clip(0.75 + (growth - 50.0) / 200.0, 0.65, 1.15)


def supply_demand_adjustment(screens: dict[str, dict[str, Any]], acres: float | None) -> float:
    growth = _score(screens, "growth")
    adj = 0.9 + (growth - 50.0) / 250.0
    if acres and acres >= 20:
        # Larger tracts more sensitive to oversupply of developable land.
        adj -= 0.05
    return _clip(adj, 0.7, 1.2)


def event_scale_factor(scale: str | None) -> float:
    return {
        "local": 0.7,
        "neighborhood": 0.85,
        "corridor": 1.0,
        "municipal": 1.15,
        "regional": 1.3,
        "major": 1.45,
    }.get((scale or "corridor").lower(), 1.0)


def highest_best_use_multiplier(
    event_key: str,
    *,
    screens: dict[str, dict[str, Any]],
    strategy: str,
    acres: float | None,
) -> float:
    meta = EVENT_TAXONOMY[event_key]
    hbu = 1.0
    if meta.get("category") in {"utilities", "entitlement", "access"}:
        if strategy in {"hold_develop", "subdivide", "flip"}:
            hbu += 0.25
        if acres and acres >= 5:
            hbu += 0.1
        if _score(screens, "growth") >= 65:
            hbu += 0.08
    if meta.get("sign", 1) < 0 and meta.get("category") == "downside":
        if strategy in {"hold_develop", "subdivide"}:
            hbu += 0.15  # HBU damage more severe for developable land
    return _clip(hbu, 0.5, 1.8)


def infrastructure_compatibility(event_key: str, screens: dict[str, dict[str, Any]]) -> float:
    access = _score(screens, "access")
    if EVENT_TAXONOMY[event_key].get("service_boundary_sensitive"):
        # Utility catalysts matter most where access exists but utilities lag.
        return _clip(0.7 + (access / 100.0) * 0.45, 0.55, 1.25)
    if EVENT_TAXONOMY[event_key].get("needs_road_access"):
        return _clip(0.5 + (access / 100.0) * 0.7, 0.4, 1.2)
    return 1.0


def zoning_compatibility(event_key: str, strategy: str, screens: dict[str, dict[str, Any]]) -> float:
    # Without full zoning GIS, use strategy + growth as proxy for future land-use fit.
    growth = _score(screens, "growth")
    base = 0.85 + (growth - 50.0) / 300.0
    if event_key in {"zoning_change", "density_entitlement", "annexation"}:
        if strategy in {"hold_develop", "subdivide", "flip"}:
            base += 0.2
        else:
            base -= 0.05
    if event_key in {"major_restaurant", "major_retailer", "shopping_center"}:
        if strategy in {"recreation", "farm"}:
            base -= 0.25  # use conflict
        elif strategy in {"flip", "hold_develop"}:
            base += 0.1
    return _clip(base, 0.4, 1.35)


def compute_scenario_impact(
    event_key: str,
    *,
    screens: dict[str, dict[str, Any]],
    strategy: str,
    acres: float | None,
    flood_zone: str | None,
    distance_mi: float,
    stage: str,
    scale: str | None = None,
    driving_distance_mi: float | None = None,
    travel_time_min: float | None = None,
) -> dict[str, Any]:
    meta = EVENT_TAXONOMY[event_key]
    # Prefer driving distance when it makes the catalyst less accessible than crow-flies.
    effective_dist = float(distance_mi)
    if driving_distance_mi is not None:
        effective_dist = max(effective_dist, float(driving_distance_mi) * 0.85)
    if travel_time_min is not None and travel_time_min > 0:
        # Soft penalty when travel time implies poor connectivity.
        effective_dist *= 1.0 + max(0.0, (travel_time_min / 12.0) - effective_dist) * 0.08

    decay = distance_decay(effective_dist, float(meta["distance_half_life_mi"]))
    compat, compat_reasons = parcel_compatibility_score(
        event_key, screens=screens, strategy=strategy, acres=acres, flood_zone=flood_zone
    )
    compat_f = compat / 100.0
    sens = local_market_sensitivity(screens, strategy)
    scale_f = event_scale_factor(scale)
    stage_f = STAGE_CERTAINTY.get(stage, 0.4)
    infra_f = infrastructure_compatibility(event_key, screens)
    zoning_f = zoning_compatibility(event_key, strategy, screens)
    hbu_f = highest_best_use_multiplier(event_key, screens=screens, strategy=strategy, acres=acres)
    cycle_f = market_cycle_adjustment(screens)
    supply_f = supply_demand_adjustment(screens, acres)

    channels = meta["base_channels"]
    # Core drivers (must stay strong): distance, parcel fit, project certainty.
    # Secondary modulators refine the estimate but are dampened toward 1.0 so
    # multiplying ~7 adjustments cannot crush a real catalyst to ~0%.
    core = decay * (0.28 + 0.72 * compat_f) * (0.45 + 0.55 * stage_f)

    def _dampen(m: float, weight: float = 0.55) -> float:
        return 1.0 + (float(m) - 1.0) * weight

    mod = (
        _dampen(sens, 0.65)
        * _dampen(scale_f, 0.75)
        * _dampen(infra_f, 0.55)
        * _dampen(zoning_f, 0.55)
        * _dampen(hbu_f, 0.7)
        * _dampen(cycle_f, 0.5)
        * _dampen(supply_f, 0.45)
    )
    factor = core * mod

    # Adjacency / frontage premium — catalysts next door hit harder than half-life decay alone.
    if effective_dist <= 0.15:
        factor *= 1.55
    elif effective_dist <= 0.35:
        factor *= 1.28
    elif effective_dist <= 0.75:
        factor *= 1.12

    # Externality haircut for catalysts that can help markets but hurt amenity parcels.
    ext = float(meta.get("externality_risk") or 0.0)
    if ext > 0 and strategy in {"recreation", "hold_appreciate"} and compat < 55:
        factor *= max(0.2, 1.0 - ext * 0.85 - (55 - compat) / 140.0)

    immediate = float(channels.get("immediate", 0.0)) * factor
    rate = float(channels.get("rate", 0.0)) * factor
    hbu = float(channels.get("hbu", 0.0)) * factor

    # Nonlinear HBU: only material when compatibility and stage are meaningful.
    if abs(hbu) > 0 and (compat < 40 or stage_f < 0.35):
        hbu *= 0.45

    # Combined multiperiod impact proxy used for UI ranges (10-year horizon lens).
    combined = immediate + hbu + rate * 8.0
    # Soft absolute cap — opportunistic but not fantasy.
    combined = _clip(combined, -0.65, 0.85)

    # Confidence / dispersion from evidence quality proxies (no fabricated comps).
    evidence_n = 0  # real comps not yet wired — do not invent
    evidence_tier = "modeled_structural"
    local_similarity = "Modeled"
    if evidence_n >= 20:
        dispersion = 0.28
        confidence = "High"
    elif evidence_n >= 8:
        dispersion = 0.38
        confidence = "Moderate"
    else:
        # Structural model only — wider bands, never false precision.
        dispersion = 0.55
        confidence = "Low–Moderate"

    # Stage & compatibility tighten or widen the band.
    dispersion *= 1.15 - 0.25 * stage_f
    dispersion *= 1.1 - 0.2 * compat_f
    dispersion = _clip(dispersion, 0.22, 0.85)

    p50 = combined
    p10 = combined * (1.0 - dispersion) if combined >= 0 else combined * (1.0 + dispersion)
    p90 = combined * (1.0 + dispersion) if combined >= 0 else combined * (1.0 - dispersion)
    # Keep ordering for negatives; bound display bands to institutional ranges.
    lo, mid, hi = sorted([p10, p50, p90])
    lo = _clip(lo, -0.6, 0.85)
    mid = _clip(mid, -0.6, 0.85)
    hi = _clip(hi, -0.6, 0.85)

    return {
        "event_key": event_key,
        "factors": {
            "base_event_effect": {
                "immediate": channels.get("immediate", 0.0),
                "rate": channels.get("rate", 0.0),
                "hbu": channels.get("hbu", 0.0),
            },
            "distance_decay": round(decay, 4),
            "parcel_compatibility": round(compat, 1),
            "local_market_sensitivity": round(sens, 3),
            "event_scale": round(scale_f, 3),
            "development_stage_certainty": round(stage_f, 3),
            "infrastructure_compatibility": round(infra_f, 3),
            "zoning_compatibility": round(zoning_f, 3),
            "highest_best_use_impact": round(hbu_f, 3),
            "market_cycle_adjustment": round(cycle_f, 3),
            "supply_demand_adjustment": round(supply_f, 3),
            "effective_distance_mi": round(effective_dist, 2),
        },
        "channels": {
            "immediate_repricing": round(immediate, 4),
            "appreciation_rate_change": round(rate, 5),
            "hbu_transformation": round(hbu, 4),
        },
        "impact": {
            "p10": round(lo, 4),
            "p50": round(mid, 4),
            "p90": round(hi, 4),
            "display_low_pct": round(lo * 100, 1),
            "display_high_pct": round(hi * 100, 1),
            "central_pct": round(mid * 100, 1),
        },
        "compatibility_score": round(compat, 1),
        "compatibility_reasons": compat_reasons,
        "confidence": confidence,
        "confidence_why": [
            f"{evidence_n} comparable historical observations with parcel-level match"
            if evidence_n
            else "Structural model — historical matched-property comps not yet attached for this market",
            f"Project certainty ({stage}): {round(stage_f * 100)}%",
            f"Parcel compatibility: {round(compat)}/100",
            f"Evidence tier: {evidence_tier.replace('_', ' ')}",
            f"Local similarity: {local_similarity}",
        ],
        "evidence": {
            "comparable_count": evidence_n,
            "tier": evidence_tier,
            "show_historical_analogs": evidence_n > 0,
            "analogs": [],  # populated only when real data exists
        },
    }


def _default_distance(event_key: str, screens: dict[str, dict[str, Any]]) -> float:
    """Heuristic distance assumption for auto-surfaced hypotheticals (labeled as such)."""
    hl = float(EVENT_TAXONOMY[event_key]["distance_half_life_mi"])
    access = _score(screens, "access")
    growth = _score(screens, "growth")
    # Better access / growth → catalysts assumed closer on the path of expansion.
    # Keep well inside the half-life so auto scenarios remain economically meaningful.
    base = hl * (0.95 - growth / 180.0 - access / 280.0)
    return _clip(base, hl * 0.18, hl * 1.35)


def _default_stage(event_key: str, screens: dict[str, dict[str, Any]]) -> str:
    """Illustrative what-if stage for auto-surfaced Hypothetical scenarios.

    Auto scenarios ask \"what if this catalyst materialized,\" so we evaluate at
    Approved certainty by default. Growth still shapes distance, timing, and
    market sensitivity — not whether the what-if is worth showing.
    """
    _ = event_key, screens
    return "Approved"


def _timing_years(event_key: str, stage: str, screens: dict[str, dict[str, Any]]) -> dict[str, Any]:
    stage_f = STAGE_CERTAINTY.get(stage, 0.4)
    growth = _score(screens, "growth")
    # Faster corridors recognize earlier.
    lead = 6.0 - growth / 25.0 - stage_f * 2.5
    lead = _clip(lead, 1.0, 8.0)
    completion = lead + (2.5 if stage_f < 0.6 else 1.2)
    return {
        "announcement_year_offset": round(max(0.0, lead - 2.0), 1),
        "expected_approval_year_offset": round(lead, 1),
        "construction_start_offset": round(lead + 0.5, 1),
        "expected_completion_offset": round(completion, 1),
        "value_recognition_start_offset": round(max(0.5, lead * 0.55), 1),
        "value_recognition_full_offset": round(completion + 0.5, 1),
    }


def build_reasoning(event_key: str, impact: dict[str, Any], parcel_ctx: dict[str, Any]) -> dict[str, Any]:
    meta = EVENT_TAXONOMY[event_key]
    factors = impact["factors"]
    reasons = list(impact.get("compatibility_reasons") or [])
    counter: list[str] = []
    timing = parcel_ctx.get("timing") or {}
    if timing.get("expected_completion_offset", 0) >= 4:
        counter.append(
            f"Completion is approximately {timing['expected_completion_offset']:.0f} years away — "
            "markets may price gradually, not all at once"
        )
    if factors["distance_decay"] < 0.45:
        counter.append("Distance decay materially reduces impact at the assumed separation")
    if impact["compatibility_score"] < 50:
        counter.append("Parcel compatibility is only moderate — catalyst may not fully translate to this tract")
    if not reasons:
        reasons.append("Impact reflects multiplicative structural factors, not a flat national percentage")
    return {
        "headline": f"Why {meta['label'].lower()} matters",
        "because": reasons[:6],
        "counterfactors": counter,
        "confidence": impact["confidence"],
        "confidence_why": impact["confidence_why"],
    }


def select_auto_scenarios(
    *,
    screens: dict[str, dict[str, Any]],
    strategy: str,
    acres: float | None,
    flood_zone: str | None,
) -> list[dict[str, Any]]:
    """Surface ~10–12 economically relevant hypothetical scenarios for this parcel."""
    growth = _score(screens, "growth")
    access = _score(screens, "access")
    flood = _score(screens, "flood")

    candidates: list[tuple[float, str, str]] = []  # priority, key, bucket

    def add(key: str, bucket: str, priority: float) -> None:
        candidates.append((priority, key, bucket))

    # —— Likely (common path-of-progress catalysts) ——
    add("city_expansion", "likely", 88 + growth / 10)
    add("population_growth", "likely", 78 + growth / 12)
    add("neighbor_approval", "likely", 74)
    add("broadband", "likely", 66)
    add("school_university", "likely", 62)
    add("road_widened" if access >= 55 else "road_paved", "likely", 80)
    add("major_restaurant", "likely", 70 + access / 8)
    add("park_recreation", "likely", 52)
    if growth >= 50:
        add("residential_subdivision", "likely", 68)

    # —— Downside (moderate / ambient risks) ——
    add("employment_decline", "downside", 70)
    add("wildfire_risk_increase", "downside", 66)
    add("environmental_restrictions", "downside", 64)
    add("water_availability_worse", "downside", 62)
    add("quarry_mining", "downside", 58)

    # —— High impact: both bullish unlocks AND severe bear shocks ——
    if strategy in {"hold_develop", "subdivide", "flip"} or (acres or 0) >= 5:
        add("sewer_extension", "high_impact", 96)
        add("municipal_water", "high_impact", 90)
        add("zoning_change", "high_impact", 86)
        add("density_entitlement", "high_impact", 78)
    add("shopping_center", "high_impact", 72 + access / 10)  # mall / retail node
    add("major_retailer", "high_impact", 70 + access / 12)
    if growth >= 55 or access >= 55:
        add("highway_interchange", "high_impact", 74)
        add("master_planned_community", "high_impact", 76)
    if access >= 50:
        add("distribution_center", "high_impact", 60)
    add("annexation", "high_impact", 64)
    # Severe downside also lives under High impact (bear side of the ledger)
    add("flood_risk_increase", "high_impact", 94 if flood < 55 else 82)
    add("landfill", "high_impact", 88)
    add("neighbor_industrial", "high_impact", 84)
    add("employer_closes", "high_impact", 80)
    add("contamination", "high_impact", 76)

    # Dedupe keeping highest priority
    best: dict[str, tuple[float, str]] = {}
    for pri, key, bucket in candidates:
        if key not in best or pri > best[key][0]:
            best[key] = (pri, bucket)

    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])
    picked: list[tuple[str, str]] = []
    counts = {"likely": 0, "high_impact": 0, "downside": 0}
    # Prefer: ~4 likely, ~3 ambient downside, ~5 high-impact (bull + bear)
    limits = {"likely": 4, "downside": 3, "high_impact": 5}

    hi_up = [
        (k, b)
        for k, (pri, b) in ranked
        if b == "high_impact" and float(EVENT_TAXONOMY[k]["base_channels"].get("immediate", 0)) >= 0
    ]
    hi_dn = [
        (k, b)
        for k, (pri, b) in ranked
        if b == "high_impact" and float(EVENT_TAXONOMY[k]["base_channels"].get("immediate", 0)) < 0
    ]
    # Seed high-impact with both bull and bear sides first
    for key, bucket in hi_up[:3] + hi_dn[:2]:
        if counts[bucket] >= limits[bucket]:
            continue
        if any(k == key for k, _ in picked):
            continue
        picked.append((key, bucket))
        counts[bucket] += 1

    for key, (pri, bucket) in ranked:
        if len(picked) >= 12:
            break
        if counts[bucket] >= limits[bucket]:
            continue
        if any(k == key for k, _ in picked):
            continue
        picked.append((key, bucket))
        counts[bucket] += 1

    # Fill any thin buckets from remaining ranked
    for key, (pri, bucket) in ranked:
        if len(picked) >= 12:
            break
        if any(k == key for k, _ in picked):
            continue
        if counts[bucket] < limits[bucket]:
            picked.append((key, bucket))
            counts[bucket] += 1

    if counts["downside"] == 0 and counts["high_impact"] == 0:
        picked = picked[:11] + [("flood_risk_increase", "high_impact")]

    scale_for = {
        "shopping_center": "major",
        "major_retailer": "major",
        "major_restaurant": "neighborhood",
        "highway_interchange": "regional",
        "distribution_center": "regional",
        "sewer_extension": "municipal",
        "municipal_water": "municipal",
        "city_expansion": "municipal",
    }

    scenarios: list[dict[str, Any]] = []
    for key, bucket in picked[:12]:
        meta = EVENT_TAXONOMY[key]
        stage = _default_stage(key, screens)
        dist = _default_distance(key, screens)
        # Retail / mall auto-scenarios assume nearby-node proximity when access supports it
        if key in {"major_restaurant", "major_retailer", "shopping_center"} and access >= 50:
            dist = min(dist, 0.35 if key == "major_restaurant" else 0.85)
        timing = _timing_years(key, stage, screens)
        # Retail nodes get recognized faster once open / approved
        if key in {"major_restaurant", "major_retailer", "shopping_center"}:
            timing = {
                **timing,
                "value_recognition_start_offset": min(float(timing["value_recognition_start_offset"]), 1.0),
                "value_recognition_full_offset": min(float(timing["value_recognition_full_offset"]), 3.5),
            }
        impact = compute_scenario_impact(
            key,
            screens=screens,
            strategy=strategy,
            acres=acres,
            flood_zone=flood_zone,
            distance_mi=dist,
            stage=stage,
            scale=scale_for.get(key, "corridor"),
        )
        chain = meta.get("chain") or []
        scenarios.append(
            {
                "id": f"auto_{key}",
                "event_key": key,
                "label": meta["label"],
                "category": meta["category"],
                "bucket": bucket,
                "data_integrity": "Hypothetical",
                "data_integrity_note": (
                    "Auto-surfaced as a parcel-relevant what-if. Not an observed, announced, "
                    "or approved project unless separately detected with citations."
                ),
                "stage": stage,
                "project_certainty_pct": round(STAGE_CERTAINTY.get(stage, 0.4) * 100),
                "parcel_distance_mi": round(dist, 2),
                "estimated_completion_offset_years": timing["expected_completion_offset"],
                "timing": timing,
                "correlation_group": meta.get("correlation_group"),
                "chain": [
                    {
                        "key": c,
                        "label": EVENT_TAXONOMY[c]["label"] if c in EVENT_TAXONOMY else c.replace("_", " ").title(),
                    }
                    for c in chain
                ],
                "impact": impact["impact"],
                "channels": impact["channels"],
                "factors": impact["factors"],
                "compatibility_score": impact["compatibility_score"],
                "confidence": impact["confidence"],
                "reasoning": build_reasoning(key, impact, {"timing": timing}),
                "historical_analogs": impact["evidence"],
                "enabled_default": False,
            }
        )
    return scenarios


def combine_scenario_impacts(selected: list[dict[str, Any]]) -> dict[str, Any]:
    """Correlation-aware combination — no naive additive stacking."""
    if not selected:
        return {
            "immediate": 0.0,
            "rate": 0.0,
            "hbu": 0.0,
            "combined_p10": 0.0,
            "combined_p50": 0.0,
            "combined_p90": 0.0,
            "interaction_notes": [],
        }

    # Group by correlation group
    groups: dict[str, list[dict[str, Any]]] = {}
    independents: list[dict[str, Any]] = []
    for s in selected:
        g = s.get("correlation_group") or f"independent:{s.get('event_key')}"
        if g.startswith("independent:"):
            independents.append(s)
        else:
            groups.setdefault(g, []).append(s)

    notes: list[str] = []
    imm = rate = hbu = 0.0
    p10 = p50 = p90 = 0.0

    def add_channels(item: dict[str, Any], weight: float = 1.0) -> None:
        nonlocal imm, rate, hbu, p10, p50, p90
        ch = item.get("channels") or {}
        imp = item.get("impact") or {}
        imm += float(ch.get("immediate_repricing") or 0) * weight
        rate += float(ch.get("appreciation_rate_change") or 0) * weight
        hbu += float(ch.get("hbu_transformation") or 0) * weight
        p10 += float(imp.get("p10") or 0) * weight
        p50 += float(imp.get("p50") or 0) * weight
        p90 += float(imp.get("p90") or 0) * weight

    for s in independents:
        add_channels(s, 1.0)

    for g, items in groups.items():
        if len(items) == 1:
            add_channels(items[0], 1.0)
            continue
        # Sort by abs central impact
        items_sorted = sorted(items, key=lambda x: abs(float((x.get("impact") or {}).get("p50") or 0)), reverse=True)
        # Primary full weight; overlapping effects diminish.
        add_channels(items_sorted[0], 1.0)
        for i, item in enumerate(items_sorted[1:], start=1):
            w = 0.45 / i  # diminishing overlap
            add_channels(item, w)

    # Complementary boost: utilities + entitlement together unlock nonlinear HBU
    keys = {s.get("event_key") for s in selected}
    util = keys & {"sewer_extension", "municipal_water", "electrical_expansion"}
    entitle = keys & {"zoning_change", "density_entitlement", "annexation"}
    if util and entitle:
        boost = 0.035
        hbu += boost
        p50 += boost
        p10 += boost * 0.6
        p90 += boost * 1.3

    # Soft cap to avoid absurd stacking
    def soft_cap(x: float, cap: float = 0.75) -> float:
        if x == 0:
            return 0.0
        sign = 1 if x > 0 else -1
        ax = abs(x)
        if ax <= cap:
            return x
        return sign * (cap + (ax - cap) * 0.35)

    return {
        "immediate": round(soft_cap(imm), 4),
        "rate": round(soft_cap(rate, 0.04), 5),
        "hbu": round(soft_cap(hbu), 4),
        "combined_p10": round(soft_cap(p10), 4),
        "combined_p50": round(soft_cap(p50), 4),
        "combined_p90": round(soft_cap(p90), 4),
        "interaction_notes": [],
    }


def apply_catalysts_to_path(
    baseline_points: list[dict[str, Any]],
    combination: dict[str, Any],
    selected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Overlay scenario-adjusted path with timed recognition (not all impact at t=0)."""
    if not baseline_points:
        return []

    # Recognition window from earliest selected catalyst
    if selected:
        start = min(float((s.get("timing") or {}).get("value_recognition_start_offset") or 2) for s in selected)
        full = max(float((s.get("timing") or {}).get("value_recognition_full_offset") or 6) for s in selected)
    else:
        start, full = 2.0, 6.0

    imm = float(combination.get("immediate") or 0)
    rate = float(combination.get("rate") or 0)
    hbu = float(combination.get("hbu") or 0)

    # Prefer forward path (offset >= 0). Fall back to raw points if offsets absent.
    forward = [p for p in baseline_points if p.get("offset") is not None and float(p["offset"]) >= 0]
    series = forward if forward else baseline_points

    out: list[dict[str, Any]] = []
    for pt in series:
        if pt.get("offset") is not None:
            y = float(pt["offset"])
        else:
            # Assume first point is today when offsets are missing.
            y = float(pt.get("year") or 0)
            if out and series and series[0].get("year") is not None:
                y = float(pt.get("year") or 0) - float(series[0].get("year") or 0)
        base_v = float(
            pt.get("value_usd")
            or pt.get("estimated_value")
            or pt.get("value")
            or 0
        )
        if full <= start:
            w = 1.0 if y >= full else 0.0
        else:
            w = 0.0 if y <= start else (1.0 if y >= full else (y - start) / (full - start))
        # Smoothstep
        w = w * w * (3 - 2 * w)

        # Rate compounds along the path relative to baseline growth already in path:
        # apply extra rate on top of baseline level as years elapse after recognition start.
        rate_mult = (1.0 + rate) ** max(0.0, y - start) if y > start else 1.0
        level_mult = 1.0 + (imm + hbu) * w
        scen_v = base_v * level_mult * (rate_mult if w > 0 else 1.0)
        # Blend rate effect with recognition weight
        if w < 1 and y > start:
            scen_v = base_v + (scen_v - base_v) * max(w, 0.35)

        out.append(
            {
                "year": pt.get("year"),
                "offset": y,
                "baseline_value": round(base_v),
                "scenario_value": round(scen_v),
                "delta_value": round(scen_v - base_v),
                "delta_pct": round(((scen_v / base_v) - 1.0) * 100, 1) if base_v else 0.0,
                "recognition_weight": round(w, 3),
            }
        )
    return out


def catalyst_opportunity_score(
    scenarios: list[dict[str, Any]],
    screens: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """0–100: how favorably positioned is the parcel for plausible future changes."""
    upside = [s for s in scenarios if s.get("bucket") != "downside"]
    downside = [s for s in scenarios if s.get("bucket") == "downside"]

    def mag(s: dict[str, Any]) -> float:
        return abs(float((s.get("impact") or {}).get("p50") or 0))

    up_score = 0.0
    for s in upside:
        cert = float(s.get("project_certainty_pct") or 20) / 100.0
        compat = float(s.get("compatibility_score") or 50) / 100.0
        # Down-weight highly speculative (rumored + tiny certainty)
        speculative_pen = 0.55 if s.get("stage") == "Rumored" else 1.0
        up_score += mag(s) * 100 * cert * compat * speculative_pen

    down_pen = 0.0
    for s in downside:
        cert = float(s.get("project_certainty_pct") or 20) / 100.0
        compat = float(s.get("compatibility_score") or 50) / 100.0
        down_pen += mag(s) * 80 * cert * compat

    growth = _score(screens, "growth")
    raw = 42 + growth * 0.22 + min(28, up_score * 1.8) - min(22, down_pen * 1.6)
    score = int(round(_clip(raw, 0, 100)))

    if score >= 75:
        label = "Strong"
    elif score >= 55:
        label = "Moderate"
    elif score >= 35:
        label = "Mixed"
    else:
        label = "Limited"

    primary = ""
    if growth >= 65 and any(s.get("event_key") in {"city_expansion", "sewer_extension", "highway_interchange"} for s in upside):
        primary = (
            "Sits in a growth path where utilities, entitlements, or expansion could reshape use."
        )
    elif any(s.get("event_key") == "sewer_extension" for s in upside):
        primary = "Developable acres could gain if municipal utilities extend here."
    elif downside and mag(max(downside, key=mag)) > (mag(max(upside, key=mag)) if upside else 0):
        primary = "Downside environmental or demand risks weigh on opportunity."
    elif upside:
        top = max(upside, key=mag)
        primary = f"Top lever on this file: {top.get('label') or 'nearby catalyst'}."

    return {
        "score": score,
        "label": label,
        "primary_reason": primary,
        "components": {
            "plausible_upside_magnitude": round(up_score, 3),
            "downside_pressure": round(down_pen, 3),
            "growth_screen": growth,
        },
    }


def build_stress_cases(
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    upside = sorted(
        [s for s in scenarios if float((s.get("impact") or {}).get("p50") or 0) >= 0],
        key=lambda s: float((s.get("impact") or {}).get("p50") or 0),
        reverse=True,
    )
    downside = sorted(
        [s for s in scenarios if float((s.get("impact") or {}).get("p50") or 0) < 0],
        key=lambda s: float((s.get("impact") or {}).get("p50") or 0),  # more negative first
    )

    # Most Likely: only the top 2 compatible "likely" catalysts
    likely = [s for s in scenarios if s.get("bucket") == "likely" and float((s.get("impact") or {}).get("p50") or 0) >= 0]
    if not likely:
        likely = upside[:2]
    most_likely_ids = [
        s["id"]
        for s in sorted(
            likely,
            key=lambda s: abs(float((s.get("impact") or {}).get("p50") or 0))
            * float(s.get("compatibility_score") or 50)
            * float(s.get("project_certainty_pct") or 20),
            reverse=True,
        )[:2]
    ]

    # Bull / Bear must select meaningfully MORE than Most Likely
    bull_ids = [s["id"] for s in upside]  # all favorable autos
    if len(bull_ids) <= len(most_likely_ids):
        bull_ids = [s["id"] for s in upside[: max(4, len(most_likely_ids) + 2)]]

    bear_ids = [s["id"] for s in downside]  # all adverse autos
    if len(bear_ids) <= len(most_likely_ids):
        bear_ids = [s["id"] for s in downside[: max(4, len(most_likely_ids) + 2)]]

    return {
        "baseline": {"scenario_ids": [], "label": "Baseline", "description": "Existing Value Path only."},
        "bull": {
            "scenario_ids": bull_ids,
            "label": "Bull Case",
            "description": "All favorable plausible catalysts on this file (broader than Most Likely).",
        },
        "bear": {
            "scenario_ids": bear_ids,
            "label": "Bear Case",
            "description": "All material downside catalysts on this file (broader than Most Likely).",
        },
        "most_likely": {
            "scenario_ids": most_likely_ids,
            "label": "Most Likely",
            "description": "Narrow set of the most compatible likely catalysts.",
        },
        "custom": {
            "scenario_ids": [],
            "label": "Custom",
            "description": "User-selected scenarios.",
        },
    }


CUSTOM_PATTERNS: list[tuple[re.Pattern[str], str, dict[str, Any]]] = [
    (re.compile(r"\bwalmart\b|\bmajor retailer\b|\bhome depot\b|\bcostco\b", re.I), "major_retailer", {"scale": "major"}),
    (re.compile(r"\bchick[- ]?fil[- ]?a\b|\brestaurant\b|\bfranchise\b", re.I), "major_restaurant", {"scale": "neighborhood"}),
    (re.compile(r"\bmall\b|\bshopping center\b|\bstrip (mall|center)\b", re.I), "shopping_center", {"scale": "major"}),
    (re.compile(r"\bmaster[- ]?planned\b|\bHOA community\b", re.I), "master_planned_community", {"scale": "municipal"}),
    (re.compile(r"\bcity\b.*\b(expand|annex)|\bannex(ed|ation)?\b|\bpart of the city\b", re.I), "annexation", {"scale": "municipal"}),
    (re.compile(r"\bcity expands\b|\bsuburban expansion\b", re.I), "city_expansion", {"scale": "municipal"}),
    (re.compile(r"\bamazon\b|\bdistribution center\b|\bfulfillment\b|\bwarehouse\b", re.I), "distribution_center", {"scale": "regional"}),
    (re.compile(r"\bemployer\b|\bheadquarters\b|\bplant opens\b", re.I), "major_employer", {"scale": "regional"}),
    (re.compile(r"\binterchange\b|\bhighway\b|\bfreeway\b|\binterstate\b", re.I), "highway_interchange", {"scale": "regional"}),
    (re.compile(r"\broad .*(widen|widened)\b|\bwidened\b", re.I), "road_widened", {"scale": "corridor"}),
    (re.compile(r"\bpaved\b|\bpave the road\b", re.I), "road_paved", {"scale": "local"}),
    (re.compile(r"\bsewer\b", re.I), "sewer_extension", {"scale": "municipal"}),
    (re.compile(r"\bmunicipal water\b|\bwater (reaches|extends|comes)\b", re.I), "municipal_water", {"scale": "municipal"}),
    (re.compile(r"\bbroadband\b|\bfiber\b", re.I), "broadband", {"scale": "municipal"}),
    (re.compile(r"\bschool\b|\buniversity\b", re.I), "school_university", {"scale": "municipal"}),
    (re.compile(r"\bhospital\b|\bmedical center\b", re.I), "hospital", {"scale": "regional"}),
    (re.compile(r"\btransit\b|\blight rail\b|\bbus rapid\b", re.I), "public_transit", {"scale": "municipal"}),
    (re.compile(r"\bairport\b", re.I), "airport_expansion", {"scale": "regional"}),
    (re.compile(r"\bzoning\b|\brezone\b", re.I), "zoning_change", {"scale": "local"}),
    (re.compile(r"\bdensity\b|\bentitlement\b", re.I), "density_entitlement", {"scale": "local"}),
    (re.compile(r"\b([\d,]+)\s*(homes|houses|units|residences)\b", re.I), "residential_subdivision", {"scale": "municipal"}),
    (re.compile(r"\bindustrial\b", re.I), "neighbor_industrial", {"scale": "local"}),
    (re.compile(r"\bflood\b", re.I), "flood_risk_increase", {"scale": "local"}),
    (re.compile(r"\bwildfire\b", re.I), "wildfire_risk_increase", {"scale": "corridor"}),
    (re.compile(r"\blandfill\b", re.I), "landfill", {"scale": "corridor"}),
    (re.compile(r"\bcontaminat", re.I), "contamination", {"scale": "local"}),
    (re.compile(r"\bpark\b|\brecreation\b", re.I), "park_recreation", {"scale": "local"}),
]


_WORD_DIST = {
    "half": 0.5,
    "a half": 0.5,
    "one": 1.0,
    "a": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
}


def _parse_distance_mi(text: str) -> float | None:
    m = re.search(r"([\d.]+)\s*(miles?|mi)\b", text, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)\s*(feet|ft)\b", text, re.I)
    if m:
        return float(m.group(1)) / 5280.0
    m = re.search(
        r"\b(a half|half|one|two|three|four|five|six|seven|eight|nine|ten|a)\s+(miles?|mi)\b",
        text,
        re.I,
    )
    if m:
        return _WORD_DIST.get(m.group(1).lower())
    if re.search(r"\bnext door\b|\badjacent\b|\bneighboring\b|\bright next\b|\bnext to (my |the )?land\b|\beside (my |the )?(parcel|land|property)\b", text, re.I):
        return 0.08
    return None


def materialize_scenario(
    *,
    event_key: str,
    screens: dict[str, dict[str, Any]],
    strategy: str,
    acres: float | None,
    flood_zone: str | None,
    distance_mi: float | None = None,
    stage: str | None = None,
    scale: str | None = None,
    data_integrity: str = "Hypothetical",
    scenario_id: str | None = None,
    raw_text: str | None = None,
    bucket: str | None = None,
) -> dict[str, Any]:
    """Build a full scenario payload from taxonomy + parcel context."""
    meta = EVENT_TAXONOMY[event_key]
    st = stage or _default_stage(event_key, screens)
    dist = float(distance_mi) if distance_mi is not None else _default_distance(event_key, screens)
    timing = _timing_years(event_key, st, screens)
    impact = compute_scenario_impact(
        event_key,
        screens=screens,
        strategy=strategy,
        acres=acres,
        flood_zone=flood_zone,
        distance_mi=dist,
        stage=st,
        scale=scale or "corridor",
    )
    chain = meta.get("chain") or []
    return {
        "id": scenario_id or f"custom_{event_key}",
        "event_key": event_key,
        "label": meta["label"],
        "category": meta["category"],
        "bucket": bucket or meta.get("default_bucket") or "likely",
        "data_integrity": data_integrity,
        "data_integrity_note": (
            "User-created what-if translated into structured Scenario Engine variables."
            if data_integrity == "User-Created Scenario"
            else (
                "Modeled / hypothetical scenario. Not an observed, announced, or approved "
                "project unless separately detected with citations."
            )
        ),
        "stage": st,
        "project_certainty_pct": round(STAGE_CERTAINTY.get(st, 0.4) * 100),
        "parcel_distance_mi": round(dist, 2),
        "estimated_completion_offset_years": timing["expected_completion_offset"],
        "timing": timing,
        "correlation_group": meta.get("correlation_group"),
        "chain": [
            {
                "key": c,
                "label": EVENT_TAXONOMY[c]["label"] if c in EVENT_TAXONOMY else c.replace("_", " ").title(),
            }
            for c in chain
        ],
        "impact": impact["impact"],
        "channels": impact["channels"],
        "factors": impact["factors"],
        "compatibility_score": impact["compatibility_score"],
        "confidence": impact["confidence"],
        "reasoning": build_reasoning(event_key, impact, {"timing": timing}),
        "historical_analogs": impact["evidence"],
        "enabled_default": False,
        "raw_text": raw_text,
    }


def build_custom_scenario_from_text(
    text: str,
    *,
    screens: list[dict[str, Any]] | None,
    strategy: str | None,
    acres: float | None,
    flood_zone: str | None,
) -> dict[str, Any]:
    parsed = parse_custom_scenario(text)
    if not parsed.get("ok"):
        return parsed
    smap = _screen_map(screens)
    strat = (strategy or "hold_appreciate").strip() or "hold_appreciate"
    scenario = materialize_scenario(
        event_key=str(parsed["event_key"]),
        screens=smap,
        strategy=strat,
        acres=acres,
        flood_zone=flood_zone,
        distance_mi=parsed.get("distance_mi"),
        stage=str(parsed.get("stage") or "Proposed"),
        scale=str(parsed.get("scale") or "corridor"),
        data_integrity="User-Created Scenario",
        scenario_id=f"user_{parsed['event_key']}_{abs(hash(text)) % 10_000}",
        raw_text=text,
        bucket=EVENT_TAXONOMY[str(parsed["event_key"])].get("default_bucket"),
    )
    return {"ok": True, "parsed": parsed, "scenario": scenario}


def parse_custom_scenario(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {"ok": False, "error": "Enter a scenario question first."}

    event_key = None
    extras: dict[str, Any] = {}
    for pat, key, ex in CUSTOM_PATTERNS:
        if pat.search(raw):
            event_key = key
            extras = dict(ex)
            break

    if not event_key:
        return {
            "ok": False,
            "error": (
                "Could not map that question to a known catalyst type yet. "
                "Try referencing sewer, zoning, highway, retailer, annexation, flood, etc."
            ),
            "supported_examples": [
                "What if Walmart opened one mile away?",
                "What if this area becomes part of the city?",
                "What if sewer reaches the property?",
                "What if 2,000 houses are developed nearby?",
                "What if Amazon builds a distribution center 5 miles away?",
                "What if the neighboring parcel becomes industrial?",
            ],
        }

    dist = _parse_distance_mi(raw)
    # Natural-language "what if" defaults to Approved illustrative certainty unless
    # the user specifies rumor / funded / under construction / etc.
    stage = "Approved"
    if re.search(r"\bfunded\b", raw, re.I):
        stage = "Funded"
    elif re.search(r"\bunder construction\b", raw, re.I):
        stage = "Under Construction"
    elif re.search(r"\bpermitted\b", raw, re.I):
        stage = "Permitted"
    elif re.search(r"\bapproved\b", raw, re.I):
        stage = "Approved"
    elif re.search(r"\brumor", raw, re.I):
        stage = "Rumored"
    elif re.search(r"\bproposed\b", raw, re.I):
        stage = "Proposed"

    return {
        "ok": True,
        "event_key": event_key,
        "label": EVENT_TAXONOMY[event_key]["label"],
        "distance_mi": dist,
        "stage": stage,
        "scale": extras.get("scale", "corridor"),
        "data_integrity": "User-Created Scenario",
        "raw_text": raw,
    }


def build_catalyst_engine(
    *,
    screens: list[dict[str, Any]] | None,
    strategy: str | None,
    acres: float | None,
    flood_zone: str | None,
    market_trajectory: dict[str, Any] | None,
    detected_catalysts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Full payload for parcel detail."""
    smap = _screen_map(screens)
    strat = (strategy or "hold_appreciate").strip() or "hold_appreciate"
    scenarios = select_auto_scenarios(
        screens=smap, strategy=strat, acres=acres, flood_zone=flood_zone
    )
    opportunity = catalyst_opportunity_score(scenarios, smap)
    stress = build_stress_cases(scenarios)

    baseline_points: list[dict[str, Any]] = []
    if market_trajectory and isinstance(market_trajectory.get("points"), list):
        baseline_points = list(market_trajectory["points"])

    detected = detected_catalysts or []
    # Architecture hook for automatic detection — empty until data feeds exist.
    detection = {
        "enabled": False,
        "count": len(detected),
        "items": detected,
        "message": (
            "Automatic catalyst detection is architected for comprehensive plans, "
            "permits, DOT projects, utility capital plans, annexations, and environmental "
            "records. No cited external catalysts are attached to this parcel yet."
        ),
        "sources_supported": [
            "Local comprehensive plans",
            "Planning-board filings",
            "Zoning applications",
            "Building permits",
            "DOT transportation projects",
            "Infrastructure capital plans",
            "Utility expansion plans",
            "City council / county development documents",
            "Annexation proposals",
            "Economic-development announcements",
            "Environmental / FEMA records",
            "Population & traffic projections",
            "Satellite / development-change signals",
            "Parcel transactions & assemblages",
        ],
    }

    return {
        "version": 1,
        "title": "Catalyst Simulator",
        "button_label": "Future Scenario Engine",
        "subtitle": "See how future changes around this property could reshape its value.",
        "methodology_note": (
            "Impacts are multiplicative across distance decay, parcel compatibility, "
            "local market sensitivity, event scale, development-stage certainty, "
            "infrastructure/zoning fit, highest-and-best-use, and cycle/supply adjustments. "
            "Universal flat percentages are not used. Auto scenarios are Hypothetical/Modeled "
            "unless a cited external source is attached."
        ),
        "opportunity": opportunity,
        "scenarios": scenarios,
        "stress_cases": stress,
        "baseline_points": baseline_points,
        "detection": detection,
        "taxonomy_size": len(EVENT_TAXONOMY),
        "stage_certainty": STAGE_CERTAINTY,
        "data_integrity_labels": list(DATA_INTEGRITY_LABELS),
        "evidence_hierarchy": EVIDENCE_TIERS,
    }


def simulate_selection(
    engine: dict[str, Any],
    scenario_ids: list[str],
    custom_scenarios: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_id = {s["id"]: s for s in engine.get("scenarios") or []}
    selected = [by_id[i] for i in scenario_ids if i in by_id]
    for c in custom_scenarios or []:
        selected.append(c)
    combo = combine_scenario_impacts(selected)
    path = apply_catalysts_to_path(engine.get("baseline_points") or [], combo, selected)
    return {
        "selected_ids": [s.get("id") for s in selected],
        "combination": combo,
        "path": path,
        "summary": _path_summary(path),
    }


def _path_summary(path: list[dict[str, Any]]) -> dict[str, Any]:
    if not path:
        return {}
    today = path[0]
    at5 = next((p for p in path if float(p.get("offset") or 0) >= 5), path[min(1, len(path) - 1)])
    at10 = next((p for p in path if float(p.get("offset") or 0) >= 10), path[-1])
    return {
        "today_value": today.get("baseline_value", today.get("estimated_value")),
        "y5_baseline": at5.get("baseline_value"),
        "y5_scenario": at5.get("scenario_value"),
        "y10_baseline": at10.get("baseline_value"),
        "y10_scenario": at10.get("scenario_value"),
        "additional_value": at10.get("delta_value"),
        "additional_pct": at10.get("delta_pct"),
    }
