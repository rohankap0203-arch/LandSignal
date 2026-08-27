from __future__ import annotations

import hashlib
import json
from typing import Any

from landsignal.scoring.financial import asking_discount_pct, clamp, margin_of_safety

ALGORITHM_VERSION = "landsignal_score_v3_6_0"
WEIGHT_VERSION = "weights_evidence_v3_6"

# Buy-edge first: mispricing + risk-adjusted quality + real optionality.
# Unknown categories are dampened in the blend (see compute_score) so thin
# files cannot float to the top of a 100k+ Top opportunities board.
DEFAULT_WEIGHTS = {
    "valuation_mispricing": 0.28,
    "intrinsic_land_quality": 0.12,
    "hbu_optionality": 0.14,
    "growth_appreciation": 0.11,
    "infrastructure": 0.08,
    "liquidity": 0.06,
    "scarcity": 0.06,
    "catalysts": 0.05,
    "seller_dynamics": 0.05,
    "risk": 0.05,
}

STRATEGIES = [
    "FARMLAND",
    "DEVELOPMENT",
    "LAND_BANK",
    "RECREATIONAL",
    "ENERGY",
    "TIMBER",
    "IMPROVED_PROPERTY",
]


def _round1(n: float) -> float:
    return round(n * 10) / 10.0


def _stable_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _v(d: dict, key: str) -> float | None:
    item = d.get(key) or {}
    state = item.get("knowledge_state", "UNKNOWN")
    if state in ("UNKNOWN", "TEMPORARILY_UNAVAILABLE"):
        return None
    return item.get("value")


def screen_strategies(inp: dict) -> dict[str, str]:
    wetland = _v(inp, "wetland_pct")
    flood = _v(inp, "flood_zone_pct")
    max_slope = _v(inp, "max_slope_pct")
    access = _v(inp, "legal_access_confidence")
    contamination = _v(inp, "environmental_contamination")
    acreage = inp.get("acreage")

    if access is not None and access < 15:
        landlocked = "FAIL"
    elif access is not None and access < 40:
        landlocked = "MANUAL_REVIEW"
    else:
        landlocked = "PASS"

    farmland = "PASS"
    if wetland is not None and wetland > 60:
        farmland = "FAIL"
    elif max_slope is not None and max_slope > 25:
        farmland = "FAIL"
    elif landlocked == "FAIL":
        farmland = "MANUAL_REVIEW"

    if landlocked == "FAIL":
        development = "FAIL"
    elif wetland is not None and wetland > 40:
        development = "FAIL"
    elif flood is not None and flood > 50:
        development = "FAIL"
    elif contamination is not None and contamination >= 70:
        development = "FAIL"
    elif acreage is not None and acreage < 2:
        # Small lots can still be assemble / infill — don't hard-kill the thesis
        development = "MANUAL_REVIEW"
    elif wetland is not None and wetland > 20:
        development = "MANUAL_REVIEW"
    elif landlocked == "MANUAL_REVIEW":
        development = "MANUAL_REVIEW"
    else:
        development = "PASS"

    recreational = "PASS"
    if landlocked == "FAIL":
        recreational = "MANUAL_REVIEW"
    if contamination is not None and contamination >= 80:
        recreational = "FAIL"

    if acreage is not None and acreage < 10:
        energy = "FAIL"
    elif max_slope is not None and max_slope > 20:
        energy = "FAIL"
    elif wetland is not None and wetland > 35:
        energy = "FAIL"
    elif flood is not None and flood > 40:
        energy = "MANUAL_REVIEW"
    else:
        energy = "PASS"

    timber = "PASS"
    if max_slope is not None and max_slope > 45:
        timber = "MANUAL_REVIEW"
    if contamination is not None and contamination >= 80:
        timber = "FAIL"

    if landlocked == "FAIL":
        land_bank = "FAIL"
    elif contamination is not None and contamination >= 85:
        land_bank = "FAIL"
    elif landlocked == "MANUAL_REVIEW":
        land_bank = "MANUAL_REVIEW"
    else:
        land_bank = "PASS"

    # Improved Property is a selectable strategy AND a soft characteristic —
    # never auto-exclude parcels that happen to have a dwelling.
    has_structure = bool(inp.get("has_structure") or inp.get("hasStructure"))
    bldg = _v(inp, "building_sqft") or _v(inp, "buildingSqFt")
    beds = _v(inp, "bedrooms")
    if not has_structure and ((bldg is not None and bldg > 0) or (beds is not None and beds > 0)):
        has_structure = True
    if has_structure:
        improved = "PASS"
    elif landlocked == "FAIL":
        improved = "FAIL"
    else:
        improved = "MANUAL_REVIEW"

    return {
        "FARMLAND": farmland,
        "DEVELOPMENT": development,
        "LAND_BANK": land_bank,
        "RECREATIONAL": recreational,
        "ENERGY": energy,
        "TIMBER": timber,
        "IMPROVED_PROPERTY": improved,
    }


def compute_risk(inp: dict) -> tuple[float, list[str]]:
    evidence: list[str] = []
    parts: list[float] = []
    wetland = _v(inp, "wetland_pct")
    if wetland is not None:
        parts.append(clamp(wetland, 0, 100))
        if wetland > 25:
            evidence.append(f"Wetlands {wetland:.1f}% of parcel")
    flood = _v(inp, "flood_zone_pct")
    if flood is not None:
        parts.append(clamp(flood * 1.1, 0, 100))
        if flood > 20:
            evidence.append(f"Flood exposure {flood:.1f}%")
    access = _v(inp, "legal_access_confidence")
    if access is not None:
        parts.append(clamp(100 - access, 0, 100))
        if access < 50:
            evidence.append(f"Legal access confidence only {access}")
    contamination = _v(inp, "environmental_contamination")
    if contamination is not None:
        parts.append(clamp(contamination, 0, 100))
    slope = _v(inp, "max_slope_pct")
    if slope is not None:
        parts.append(clamp(slope * 2, 0, 100))
    liq = _v(inp, "liquidity_score")
    if liq is not None:
        parts.append(clamp(100 - liq, 0, 100) * 0.7)
    if not parts:
        return 50.0, ["Insufficient risk inputs — neutral risk pending data"]
    return _round1(sum(parts) / len(parts)), evidence


def compute_confidence(inp: dict) -> float:
    parts = [clamp(float(inp.get("known_attribute_ratio") or 0) * 100, 0, 100)]
    if inp.get("geometry_confidence") is not None:
        parts.append(float(inp["geometry_confidence"]))
    parts.append(clamp(float(inp.get("comps_count") or 0) * 15, 0, 100))
    confs = []
    for key in (
        "estimated_value_base_usd",
        "prime_farmland_pct",
        "wetland_pct",
        "flood_zone_pct",
        "avg_slope_pct",
    ):
        c = (inp.get(key) or {}).get("confidence")
        if c is not None:
            confs.append(float(c))
    if confs:
        parts.append(sum(confs) / len(confs))
    unavailable = sum(
        1
        for key in ("wetland_pct", "flood_zone_pct", "prime_farmland_pct", "estimated_value_base_usd")
        if (inp.get(key) or {}).get("knowledge_state") == "TEMPORARILY_UNAVAILABLE"
    )
    return _round1(clamp(sum(parts) / len(parts) - unavailable * 8, 0, 100))


def deal_readiness(inp: dict) -> float:
    score = 20.0
    access = _v(inp, "legal_access_confidence")
    if access is not None and access >= 70:
        score += 15
    if (inp.get("geometry_confidence") or 0) >= 80:
        score += 15
    if _v(inp, "flood_zone_pct") is not None:
        score += 10
    if _v(inp, "wetland_pct") is not None:
        score += 10
    if (inp.get("comps_count") or 0) >= 3:
        score += 10
    if _v(inp, "zoning_development_friendly") is not None:
        score += 10
    return _round1(clamp(score, 0, 100))


def _signal(opportunity: float, risk: float, confidence: float) -> str:
    """Surface real asymmetric process buys — exceptional requires evidence, not priors."""
    if opportunity < 34 or (risk > 85 and opportunity < 58):
        return "REJECT"
    # Confidence floors keep thin GIS scouts out of STRONG/EXCEPTIONAL on Top opportunities.
    if opportunity >= 80 and risk <= 48 and confidence >= 58:
        return "EXCEPTIONAL"
    if opportunity >= 70 and risk <= 55 and confidence >= 48:
        return "STRONG"
    if opportunity >= 64 and risk <= 60 and confidence >= 40:
        return "STRONG"
    return "WATCH"


def _parcel_tag(inp: dict) -> str:
    apn = inp.get("apn") or "no APN"
    county = inp.get("county") or "county n/a"
    state = (inp.get("state") or "US").upper()
    acres = inp.get("acreage")
    size = f"{float(acres):,.2f} ac" if acres is not None else "acreage n/a"
    return f"{apn} · {county}, {state} · {size}"


def compute_score(inp: dict, weights: dict | None = None, weight_version: str = WEIGHT_VERSION) -> dict:
    weights = weights or DEFAULT_WEIGHTS
    screens = screen_strategies(inp)
    risk, risk_evidence = compute_risk(inp)
    tag = _parcel_tag(inp)
    ask = inp.get("asking_price_usd")  # may already be expected settle for auctions
    opening_bid = inp.get("opening_bid_usd")
    is_auction = bool(inp.get("is_auction_opener"))
    auction_path = inp.get("auction_path") if isinstance(inp.get("auction_path"), dict) else None
    base = _v(inp, "estimated_value_base_usd")
    acres = inp.get("acreage") or 0
    discount = asking_discount_pct(ask, base)
    if base is None and ask is None:
        valuation_value = 45.0
        valuation_evidence = [
            f"{tag}: no ask and no model value — valuation held at {valuation_value:.0f}/100 until priced"
        ]
        valuation_ks = (inp.get("estimated_value_base_usd") or {}).get("knowledge_state", "UNKNOWN")
    elif ask is None and base is not None:
        # Unpriced process parcels: score entry optionality from scale + scarcity, not fake mispricing
        scar = _v(inp, "scarcity_score") or 50.0
        valuation_value = _round1(clamp(52 + min(float(acres), 640.0) / 640.0 * 28 + (scar - 50) * 0.3, 42, 92))
        valuation_evidence = [
            f"{tag}: no retail ask — process pricing. Screening mark ~${base:,.0f}; "
            f"scale ({float(acres):,.2f} ac) + scarcity {scar:.0f} → valuation {valuation_value:.0f}/100"
        ]
        valuation_ks = "ESTIMATED"
    elif base is None and ask is not None:
        valuation_value = 52.0
        valuation_evidence = [
            f"{tag}: ask ${ask:,.0f} present but model mark incomplete — valuation {valuation_value:.0f}/100 pending comps"
        ]
        valuation_ks = "UNKNOWN"
    else:
        # Slightly more lenient so real process edges can clear the mid/high 70s
        valuation_value = _round1(clamp(62 - discount * 1.2, 0, 100))
        if is_auction and opening_bid is not None:
            valuation_evidence = [
                f"{tag}: auction opener ${opening_bid:,.0f} ≠ settle. "
                f"Expected clear ~${ask:,.0f} vs mark ${base:,.0f} → {discount:.1f}% → valuation {valuation_value:.0f}/100 "
                f"(opener teaser would have been {(opening_bid - base) / base * 100:.0f}%)."
            ]
            if auction_path and auction_path.get("note"):
                valuation_evidence.append(str(auction_path["note"])[:220])
        else:
            valuation_evidence = [
                f"{tag}: ask ${ask:,.0f} vs mark ${base:,.0f} → {discount:.1f}% → valuation {valuation_value:.0f}/100"
            ]
        valuation_ks = "KNOWN"

    prime = _v(inp, "prime_farmland_pct")
    slope = _v(inp, "avg_slope_pct")
    q_parts = []
    q_evidence = []
    if prime is not None:
        q_parts.append(prime)
        q_evidence.append(f"{tag}: USDA prime farmland screen {prime:.1f}%")
    if slope is not None:
        q_parts.append(clamp(100 - slope * 3, 0, 100))
        q_evidence.append(f"{tag}: avg slope {slope:.1f}% → tillable/build score {clamp(100 - slope * 3, 0, 100):.0f}")
    quality_value = _round1(sum(q_parts) / len(q_parts)) if q_parts else 42.0
    quality_ks = "KNOWN" if q_parts else "UNKNOWN"
    if not q_parts:
        q_evidence = [f"{tag}: soil/slope not confirmed — quality held at cautious {quality_value:.0f}/100"]
    else:
        q_evidence.append(f"Composite land quality → {quality_value:.0f}/100")

    zoning = _v(inp, "zoning_development_friendly") or 52
    growth = _v(inp, "path_of_growth_score") or 52
    solar = _v(inp, "solar_irradiance_score") or 50
    timber = _v(inp, "timber_suitability") or 50
    wetland = _v(inp, "wetland_pct") or 20
    access = _v(inp, "legal_access_confidence") or 55
    prime_f = prime or 48

    strategy_scores = {
        "FARMLAND": 0.0
        if screens["FARMLAND"] == "FAIL"
        else _round1(clamp(prime_f * 0.7 + (100 - wetland) * 0.3, 0, 100)),
        "DEVELOPMENT": 0.0
        if screens["DEVELOPMENT"] == "FAIL"
        else _round1(clamp(zoning * 0.45 + growth * 0.35 + access * 0.2, 0, 100)),
        "LAND_BANK": 0.0
        if screens["LAND_BANK"] == "FAIL"
        else _round1(clamp(growth * 0.5 + zoning * 0.2 + access * 0.3, 0, 100)),
        "RECREATIONAL": 0.0
        if screens["RECREATIONAL"] == "FAIL"
        else _round1(clamp(40 + wetland * 0.2 + (100 - zoning) * 0.2, 0, 100)),
        "ENERGY": 0.0
        if screens["ENERGY"] == "FAIL"
        else _round1(clamp(solar * 0.6 + (40 if _v(inp, "nearest_transmission_m") is not None else 20), 0, 100)),
        "TIMBER": 0.0 if screens["TIMBER"] == "FAIL" else _round1(clamp(timber, 0, 100)),
        "IMPROVED_PROPERTY": 0.0
        if screens.get("IMPROVED_PROPERTY") == "FAIL"
        else _round1(
            clamp(
                (
                    (70 if inp.get("has_structure") or inp.get("hasStructure") else 35)
                    + (access * 0.2)
                    + ((_v(inp, "building_sqft") or _v(inp, "buildingSqFt") or 0) / 40)
                ),
                0,
                100,
            )
        ),
    }
    pass_scores = [v for k, v in strategy_scores.items() if screens[k] != "FAIL"]
    top = sorted(pass_scores, reverse=True)[:3]
    optionality_value = _round1(sum(top) / len(top)) if top else 0.0

    # Asymmetry
    downside = _v(inp, "downside_value_usd")
    upside = _v(inp, "development_upside_usd")
    liq = _v(inp, "liquidity_score")
    if ask is None or base is None:
        asymmetry = 50.0
        asym_evidence = ["Asymmetry requires ask + base value"]
    else:
        mos = margin_of_safety(ask, base)
        upside_ratio = ((upside - ask) / ask) if upside is not None and ask > 0 else 0.0
        downside_gap = max(0.0, (ask - downside) / ask) if downside is not None and ask > 0 else 0.0
        asymmetry = 50 + mos * 80 + upside_ratio * 25 - downside_gap * 40
        if liq is not None and liq < 40:
            asymmetry -= (40 - liq) * 0.4
        asymmetry = _round1(clamp(asymmetry, 0, 100))
        asym_evidence = [
            f"MoS {mos*100:.1f}%, upsideRatio {upside_ratio*100:.1f}%, downsideGap {downside_gap*100:.1f}%"
        ]

    growth_v = _v(inp, "path_of_growth_score")
    frontage = _v(inp, "road_frontage_m")
    tx = _v(inp, "nearest_transmission_m")
    infra_parts = [access if _v(inp, "legal_access_confidence") is not None else None]
    if frontage is not None:
        infra_parts.append(clamp(frontage / 5, 0, 100))
    if tx is not None:
        infra_parts.append(clamp(100 - (tx / 5000) * 100, 0, 100))
    infra_parts = [p for p in infra_parts if p is not None]
    infra = _round1(sum(infra_parts) / len(infra_parts)) if infra_parts else 50.0

    category_values = {
        "valuation_mispricing": (valuation_value, valuation_ks, valuation_evidence),
        "intrinsic_land_quality": (quality_value, quality_ks, q_evidence),
        "hbu_optionality": (
            optionality_value,
            "ESTIMATED"
            if _v(inp, "zoning_development_friendly") is None and prime is None
            else "KNOWN",
            [
                f"{tag}: top use screens "
                + ", ".join(f"{k}={v:.0f}" for k, v in sorted(strategy_scores.items(), key=lambda x: -x[1])[:3])
                + f" → optionality {optionality_value:.0f}/100"
            ],
        ),
        "growth_appreciation": (
            growth_v if growth_v is not None else 42.0,
            "UNKNOWN" if growth_v is None else "KNOWN",
            [
                f"{tag}: path-of-growth not confirmed — cautious prior 42/100 (not an edge)"
                if growth_v is None
                else f"{tag}: path-of-growth {growth_v:.0f} → growth rating {growth_v:.0f}/100"
            ],
        ),
        "infrastructure": (
            infra if infra_parts else 42.0,
            "UNKNOWN" if not infra_parts else "ESTIMATED",
            [
                f"{tag}: access/frontage/transmission incomplete — infra held at cautious 42/100"
                if not infra_parts
                else f"{tag}: infra composite {infra:.0f}/100"
                + (f"; transmission {tx:,.0f} m" if tx is not None else "")
                + (f"; access {access:.0f}" if _v(inp, "legal_access_confidence") is not None else "")
            ],
        ),
        "liquidity": (
            liq if liq is not None else 42.0,
            "UNKNOWN" if liq is None else "KNOWN",
            [
                f"{tag}: liquidity proxy missing — cautious prior 42/100 (not an edge)"
                if liq is None
                else f"{tag}: liquidity proxy {liq:.0f} → {liq:.0f}/100"
            ],
        ),
        "scarcity": (
            _v(inp, "scarcity_score") if _v(inp, "scarcity_score") is not None else 42.0,
            "UNKNOWN" if _v(inp, "scarcity_score") is None else "KNOWN",
            [
                f"{tag}: scarcity proxy missing — cautious prior 42/100 (not an edge)"
                if _v(inp, "scarcity_score") is None
                else f"{tag}: scarcity {_v(inp, 'scarcity_score'):.0f} on {float(acres):,.2f} ac → {_v(inp, 'scarcity_score'):.0f}/100"
            ],
        ),
        "catalysts": (
            _v(inp, "catalyst_score") if _v(inp, "catalyst_score") is not None else 40.0,
            "UNKNOWN" if _v(inp, "catalyst_score") is None else "KNOWN",
            [
                f"{tag}: no structured catalyst on file — cautious prior 40/100"
                if _v(inp, "catalyst_score") is None
                else f"{tag}: catalyst score {_v(inp, 'catalyst_score'):.0f}/100"
            ],
        ),
        "seller_dynamics": (
            _v(inp, "seller_pressure_score") if _v(inp, "seller_pressure_score") is not None else 42.0,
            "UNKNOWN" if _v(inp, "seller_pressure_score") is None else "KNOWN",
            [
                f"{tag}: seller-pressure proxy missing ({inp.get('provider_id') or 'listing'}) — cautious prior 42/100"
                if _v(inp, "seller_pressure_score") is None
                else f"{tag}: seller pressure {_v(inp, 'seller_pressure_score'):.0f} via {inp.get('provider_id') or 'listing'} → {_v(inp, 'seller_pressure_score'):.0f}/100"
            ],
        ),
        "risk": (
            100 - risk,
            "ESTIMATED",
            [f"{tag}: {e}" for e in risk_evidence]
            or [f"{tag}: desktop risk {risk:.0f}/100 → risk contribution {100 - risk:.0f}/100"],
        ),
    }

    # Evidence-weighted blend: UNKNOWN / thin categories cannot dominate Top opportunities.
    # KNOWN evidence keeps full weight; ESTIMATED is tempered; UNKNOWN is heavily dampened
    # and pulled toward a cautious prior so middling invent-ed 50s do not float #1 of 100k+.
    evidence_weight_scale = {
        "KNOWN": 1.0,
        "ESTIMATED": 0.78,
        "UNKNOWN": 0.30,
        "TEMPORARILY_UNAVAILABLE": 0.22,
    }
    # Valuation UNKNOWN is the hardest penalty — without price discovery, "best buy" is speculation.
    unknown_category_scale = {
        "valuation_mispricing": 0.18,
        "intrinsic_land_quality": 0.40,
        "hbu_optionality": 0.45,
        "growth_appreciation": 0.35,
        "infrastructure": 0.40,
        "liquidity": 0.40,
        "scarcity": 0.45,
        "catalysts": 0.40,
        "seller_dynamics": 0.40,
        "risk": 0.55,
    }

    components = []
    opportunity = 0.0
    effective_w_sum = 0.0
    known_core = 0
    core_categories = {
        "valuation_mispricing",
        "intrinsic_land_quality",
        "hbu_optionality",
        "growth_appreciation",
        "risk",
    }
    for category, weight in weights.items():
        value, ks, evidence = category_values[category]
        if ks == "UNKNOWN":
            scale = unknown_category_scale.get(category, 0.30)
        else:
            scale = evidence_weight_scale.get(ks, 0.50)
        eff_w = weight * scale
        effective_w_sum += eff_w
        contribution = value * eff_w
        opportunity += contribution
        if category in core_categories and ks in ("KNOWN", "ESTIMATED"):
            known_core += 1
        components.append(
            {
                "category": category,
                "label": category,
                "value": _round1(value),
                "weight": weight,
                "effective_weight": _round1(eff_w),
                "contribution": _round1(contribution),
                "knowledge_state": ks,
                "evidence": evidence,
            }
        )
    if effective_w_sum > 0:
        # Re-normalize so dampened UNKNOWN mass does not leave the score artificially low
        # on researched files — but still reflects relative evidence density via later gates.
        opportunity = opportunity / effective_w_sum * sum(weights.values())
    opportunity = _round1(clamp(opportunity, 0, 100))
    nominal_w = sum(weights.values()) or 1.0
    evidence_ratio = round(effective_w_sum / nominal_w, 3)

    # Evidence-backed lifts so real process edges can separate — tempered for map screens.
    lift = 0.0
    lift_notes: list[str] = []
    provider = str(inp.get("provider_id") or "")
    eff_discount = discount
    # Unpriced process inventory (≥5 ac): underwrite a channel entry so mispricing can surface.
    # Vacant GIS screens are NOT confirmed sales — only a mild “maybe approachable” underwrite.
    if (
        eff_discount is None
        and ask is None
        and base is not None
        and float(acres or 0) >= 5
        and provider in ("public_tax_sale", "public_surplus", "blm_lpad", "public_vacant_gis")
    ):
        underwrite = base * (
            0.62
            if provider == "public_tax_sale"
            else 0.72
            if provider == "public_surplus"
            else 0.78
            if provider == "blm_lpad"
            else 0.92  # vacant map screen — very mild approachable underwrite
        )
        eff_discount = asking_discount_pct(underwrite, base)
        lift_notes.append(
            f"{'Map-screen' if provider == 'public_vacant_gis' else 'Process'} underwrite "
            f"~${underwrite:,.0f} vs mark ${base:,.0f} ({eff_discount:.0f}% gap)"
        )
    if eff_discount is not None:
        if provider == "public_vacant_gis":
            # Soft and capped — vacant GIS alone must not manufacture a top-board buy
            if eff_discount <= -25:
                lift += 3.5
                lift_notes.append(f"Map-screen value gap (+3.5) for {eff_discount:.0f}% vs model")
            elif eff_discount <= -12:
                lift += 2.0
                lift_notes.append(f"Soft map-screen edge (+2) for {eff_discount:.0f}% vs model")
            elif eff_discount <= -5:
                lift += 1.0
                lift_notes.append(f"Mild map-screen edge (+1) for {eff_discount:.0f}% vs model")
        elif eff_discount <= -50:
            lift += 20
            lift_notes.append(f"Deep discount lift (+20) for {eff_discount:.0f}% vs model")
        elif eff_discount <= -30:
            lift += 15
            lift_notes.append(f"Strong discount lift (+15) for {eff_discount:.0f}% vs model")
        elif eff_discount <= -15:
            lift += 10
            lift_notes.append(f"Discount lift (+10) for {eff_discount:.0f}% vs model")
        elif eff_discount <= -8:
            lift += 5
            lift_notes.append(f"Mild discount lift (+5) for {eff_discount:.0f}% vs model")
    # Channel edge only when the file also shows a real price/use gap (not bare vacant GIS)
    if provider in ("public_tax_sale", "public_surplus", "blm_lpad") and (
        (eff_discount is not None and eff_discount <= -12) or float(acres or 0) >= 30
    ):
        lift += 6
        lift_notes.append("Off-MLS / process channel scout edge (+6)")
    sp = _v(inp, "seller_pressure_score")
    if sp is not None and sp >= 68 and provider != "public_vacant_gis":
        lift += 6
        lift_notes.append("Distressed / high seller-pressure channel (+6)")
    if ask is None and acres >= 40 and provider in ("public_tax_sale", "public_surplus", "blm_lpad"):
        lift += 8
        lift_notes.append("Unpriced large-tract process edge (+8)")
        if (_v(inp, "scarcity_score") or 0) >= 60:
            lift += 5
            lift_notes.append("Scarcity on large unpriced tract (+5)")
    elif ask is None and acres >= 40 and provider == "public_vacant_gis":
        lift += 1.5
        lift_notes.append("Large vacant map screen — still need an owner path (+1.5)")
    # Usable-acre quality when soil is strong and flood/wetlands are contained
    if (prime or 0) >= 45 and (wetland or 0) < 18 and (_v(inp, "flood_zone_pct") or 0) < 25:
        lift += 6
        lift_notes.append("Cleaner soil + contained flood/wetland screens (+6)")
    if risk > 75:
        lift *= 0.65
        lift_notes.append("Lift cut — elevated risk")
    elif risk > 62:
        lift *= 0.9
        lift_notes.append("Lift tempered — moderate-high risk")
    # Scale lifts by evidence density — thin files keep little of any manufactured edge
    if evidence_ratio < 0.45:
        lift *= 0.35
        if lift:
            lift_notes.append("Lift cut — thin evidence ratio")
    elif evidence_ratio < 0.65:
        lift *= 0.70
        if lift:
            lift_notes.append("Lift tempered — partial evidence")
    if lift:
        opportunity = _round1(clamp(opportunity + lift, 0, 100))

    confidence = compute_confidence(inp)

    # Depth bonus: multi-factor researched files earn a small, capped lift
    # (replaces the old sitewide opportunistic nudge that inflated thin scouts)
    if known_core >= 4 and confidence >= 62 and valuation_ks in ("KNOWN", "ESTIMATED"):
        depth_bonus = min(4.5, 1.5 + (known_core - 3) * 0.8 + (confidence - 62) * 0.04)
        opportunity = _round1(clamp(opportunity + depth_bonus, 0, 100))
        lift_notes.append(f"Research depth bonus (+{depth_bonus:.1f}) — multi-factor corroborated file")

    # Hard evidence gates for Top-opportunities integrity
    if confidence < 58:
        shrink = (58.0 - confidence) / 58.0
        opportunity = _round1(
            opportunity * (1.0 - 0.72 * shrink) + 40.0 * (0.72 * shrink)
        )
        lift_notes.append(
            f"Confidence gate — pulled toward cautious neutral (confidence {confidence:.0f})"
        )

    if valuation_ks == "UNKNOWN" and known_core <= 2:
        opportunity = min(opportunity, 48.0)
        lift_notes.append("Valuation ceiling 48 — no price discovery + thin core evidence")
    elif valuation_ks == "UNKNOWN":
        opportunity = min(opportunity, 58.0)
        lift_notes.append("Valuation ceiling 58 — no ask/baseline price discovery")

    if evidence_ratio < 0.35:
        opportunity = min(opportunity, 46.0)
        lift_notes.append("Evidence-ratio ceiling 46 — file too thin for Top opportunities")
    elif evidence_ratio < 0.50:
        opportunity = min(opportunity, 56.0)
        lift_notes.append("Evidence-ratio ceiling 56 — partial file")

    # Bare vacant GIS without corroborating land attributes cannot clear STRONG territory
    if provider == "public_vacant_gis" and known_core <= 2 and confidence < 45:
        opportunity = min(opportunity, 52.0)
        lift_notes.append("Vacant GIS map-screen ceiling 52 — needs owner path + diligence")

    opportunity = _round1(clamp(opportunity, 0, 100))

    ranked = sorted(
        [(k, v) for k, v in strategy_scores.items() if screens[k] != "FAIL"],
        key=lambda x: -x[1],
    )

    why_interesting = []
    if discount is not None and discount < -10:
        why_interesting.append(
            f"Asking price appears {abs(discount):.1f}% below model base value"
        )
    if optionality_value >= 70:
        why_interesting.append("Multiple non-failed strategies show material optionality")
    if (growth_v or 0) >= 70:
        why_interesting.append("Path-of-growth score is elevated versus distance-only heuristics")

    why_mispriced = []
    if inp.get("price_reduction_pct") is not None and inp["price_reduction_pct"] >= 10:
        why_mispriced.append(
            f"Recent price reduction of {inp['price_reduction_pct']}% may have reset economics"
        )
    if discount is not None and discount < -15 and confidence >= 60:
        why_mispriced.append("Model value / ask gap is wide with moderate-or-better confidence")

    what_could_kill = list(risk_evidence)
    if screens["DEVELOPMENT"] == "FAIL":
        what_could_kill.append("Development thesis fails stage-1 screens")
    if (access or 100) < 40:
        what_could_kill.append("Access may be legally insufficient — survey/title required")

    why_still_available = []
    if inp.get("days_on_market") is not None and inp["days_on_market"] > 120:
        why_still_available.append(
            "Extended DOM — investigate defects, marketing, or prior overpricing"
        )
    if (liq or 100) < 40:
        why_still_available.append("Thin buyer pool / low liquidity may deter institutions")
    if confidence < 55:
        why_still_available.append("Incomplete public data may be deterring underwritten bids")

    return {
        "algorithm_version": ALGORITHM_VERSION,
        "weight_version": weight_version,
        "opportunity": opportunity,
        "risk": risk,
        "confidence": confidence,
        "asymmetry": asymmetry,
        "signal": _signal(opportunity, risk, confidence),
        "best_strategy": ranked[0][0] if ranked else None,
        "secondary_strategy": ranked[1][0] if len(ranked) > 1 else None,
        "strategy_scores": strategy_scores,
        "strategy_screens": screens,
        "estimated_value_usd": base,
        "asking_discount_pct": discount if discount is not None else eff_discount,
        "deal_readiness": deal_readiness(inp),
        "evidence_ratio": evidence_ratio,
        "known_core_factors": known_core,
        "components": components,
        "explanations": [f"[{c['category']}] {e}" for c in components for e in c["evidence"]],
        "why_interesting": why_interesting + lift_notes,
        "why_mispriced": why_mispriced,
        "what_could_kill": what_could_kill,
        "why_still_available": why_still_available,
        "score_lift": _round1(lift),
        "score_lift_notes": lift_notes,
        "manual_verification": [
            "Confirm title and legal access with recorded documents",
            "Verify parcel geometry / acreage against survey or assessor polygon",
            "Confirm zoning and future land use with county staff",
            "Validate flood/wetland screening with site diligence if material",
        ],
        "asymmetry_evidence": asym_evidence,
        "input_hash": _stable_hash(
            {"input": inp, "weights": weights, "algorithm": ALGORITHM_VERSION, "weightVersion": weight_version}
        ),
    }


def personalized_score(
    global_opportunity: float,
    profile: dict,
    asking_price_usd: float | None,
    acreage: float | None,
    best_strategy: str | None,
    risk: float,
) -> float:
    score = global_opportunity
    max_price = profile.get("max_price_usd")
    min_acres = profile.get("min_acres")
    preferred = profile.get("preferred_strategies") or []
    if asking_price_usd is not None and max_price is not None and asking_price_usd > max_price:
        score -= 25
    if acreage is not None and min_acres is not None and acreage < min_acres:
        score -= 20
    # Strategy is ranking-only: preferred strategies float up; mismatches sink
    # but stay in the result set so quantity is never reduced by strategy choice.
    if preferred:
        pref_set = {str(p).upper().replace(" ", "_") for p in preferred}
        strat = (best_strategy or "").upper().replace(" ", "_")
        if strat and strat in pref_set:
            score += 12
        else:
            score -= 8
    if profile.get("risk_tolerance") == "LOW" and risk > 40:
        score -= 10
    if profile.get("risk_tolerance") == "HIGH" and risk < 60:
        score += 3
    return _round1(clamp(score, 0, 100))
