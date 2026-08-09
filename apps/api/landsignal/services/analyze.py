from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import structlog

from landsignal.models import EnrichmentBundle, KnowledgeState, Provenanced, ScoreRecord, Signal, Strategy
from landsignal.providers.enrichment import build_enrichment_providers
from landsignal.scoring.engine import compute_score, personalized_score
from landsignal.scoring.financial import farmland_scenario
from landsignal.services.narratives import hidden_value_score, why_still_unsold
from landsignal.settings import Settings, get_settings
from landsignal.store import MemoryStore

log = structlog.get_logger()

# Coarse regional land value priors ($/acre) — ESTIMATED only, for screening when no comps vendor.
STATE_PPA_PRIOR = {
    "IA": 9500,
    "IL": 10000,
    "IN": 9000,
    "MN": 7000,
    "TX": 4500,
    "NM": 1200,
    "AZ": 2500,
    "NV": 900,
    "UT": 1800,
    "CO": 3500,
    "WY": 1100,
    "MT": 1400,
    "ID": 2800,
    "OR": 3200,
    "CA": 12000,
    "FL": 8000,
    "GA": 5500,
    "NC": 6000,
    "SC": 5000,
    "TN": 5500,
    "AL": 4000,
    "MS": 3500,
    "MO": 4500,
    "KS": 2800,
    "NE": 4500,
    "OK": 2500,
    "SD": 3000,
    "ND": 2500,
    "WI": 6500,
    "MI": 5000,
    "OH": 7000,
    "PA": 6000,
    "NY": 4500,
    "WA": 5500,
}


def _wrap(value, source_prov: Provenanced | None):
    if source_prov is None:
        return {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None}
    if source_prov.knowledge_state in (
        KnowledgeState.TEMPORARILY_UNAVAILABLE,
        KnowledgeState.UNKNOWN,
    ):
        return {
            "value": None,
            "knowledge_state": source_prov.knowledge_state.value,
            "confidence": source_prov.confidence,
            "source": source_prov.source,
        }
    return {
        "value": value,
        "knowledge_state": source_prov.knowledge_state.value,
        "confidence": source_prov.confidence,
        "source": source_prov.source,
    }


def _known_ratio(values: list) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if v is not None) / len(values)


def _estimate_value(parcel, soil_n, flood_n, wet_n, growth_n, listing=None) -> dict:
    state = (parcel.state or "").upper()
    acres = parcel.acreage or 0
    ask = listing.asking_price_usd if listing else None
    provider = listing.provider_id if listing else None

    # Small urban / tax-sale lots: do NOT apply farmland $/acre priors (creates nonsense discounts).
    # Also do NOT anchor model value to the opening bid — openers are floors, not retail.
    if acres and acres < 2.0 and provider in ("public_tax_sale", "public_surplus"):
        # Urban land residual prior ~$2–8/sqft depending on state
        psf = 4.0 if state in ("CA", "FL", "NY", "WA", "NJ") else 2.5 if state in ("TX", "IL", "GA", "NC") else 2.0
        base = acres * 43560 * psf
        # Soft floor: model shouldn't sit below a trivial multiple of opener when opener exists
        if ask and ask > 0:
            base = max(base, ask * 2.5)
        return {
            "estimated_value_low_usd": base * 0.55,
            "estimated_value_base_usd": base,
            "estimated_value_high_usd": base * 1.6,
            "downside_value_usd": max(ask or 0, base * 0.35),
            "development_upside_usd": base * 2.4,
            "comps_count": 0,
            "liquidity_score": 45,
            "scarcity_score": 40,
            "catalyst_score": 30,
            "seller_pressure_score": 70,
            "solar_irradiance_score": 40,
            "timber_suitability": 5,
            "zoning_development_friendly": 55,
            "path_of_growth_score": growth_n.get("path_of_growth_score") or 50,
            "knowledge_state": KnowledgeState.ESTIMATED,
            "confidence": 40,
            "note": (
                "Small-lot screening value from $/sqft residual (not tied to auction opener). "
                "Opening bids are floors — see auction settle path for likely clear price."
            ),
            "ppa_prior": (base / acres) if acres else None,
        }

    base_ppa = STATE_PPA_PRIOR.get(state, 3000)
    # Desert BLM tracts: lower productive ag prior
    if provider == "blm_lpad" and state in ("AZ", "NV", "NM", "UT"):
        base_ppa = min(base_ppa, 1500)
    prime = soil_n.get("prime_farmland_pct")
    wetland = wet_n.get("wetland_pct") or 0
    flood = flood_n.get("flood_zone_pct") or 0
    mult = 1.0
    if prime is not None:
        mult *= 0.75 + (prime / 100) * 0.5
    mult *= max(0.35, 1 - (wetland / 100) * 0.6)
    mult *= max(0.4, 1 - (flood / 100) * 0.4)
    growth = growth_n.get("path_of_growth_score")
    if growth is not None:
        mult *= 0.9 + (growth / 100) * 0.25
    base = base_ppa * mult * acres if acres else None
    if base is None:
        return {
            "estimated_value_low_usd": None,
            "estimated_value_base_usd": None,
            "estimated_value_high_usd": None,
            "downside_value_usd": None,
            "development_upside_usd": None,
            "comps_count": 0,
            "knowledge_state": KnowledgeState.UNKNOWN,
            "confidence": 0,
            "note": "No acreage for value prior",
        }
    return {
        "estimated_value_low_usd": base * 0.75,
        "estimated_value_base_usd": base,
        "estimated_value_high_usd": base * 1.35,
        "downside_value_usd": base * 0.65,
        "development_upside_usd": base * 2.2,
        "comps_count": 0,
        "liquidity_score": 35 if state in ("NM", "NV", "WY", "MT") else 50,
        "scarcity_score": 55,
        "catalyst_score": 25,
        "seller_pressure_score": 40,
        "solar_irradiance_score": 80 if state in ("AZ", "NM", "NV", "CA", "TX", "UT") else 55,
        "timber_suitability": 60 if state in ("OR", "WA", "ID", "MT", "ME") else 25,
        "zoning_development_friendly": 35,
        "path_of_growth_score": growth if growth is not None else 45,
        "knowledge_state": KnowledgeState.ESTIMATED,
        "confidence": 35,
        "note": f"Screening prior from state PPA ${base_ppa}/ac adjusted for soil/wetland/flood — not a closed-comp appraisal",
        "ppa_prior": base_ppa,
    }


def _retag_vacant_gis_listing(listing) -> None:
    """Vacant CAD/cadastral feeds are not confirmed tax sales."""
    if not listing or getattr(listing, "provider_id", None) != "public_tax_sale":
        return
    ext = str(getattr(listing, "external_id", None) or "")
    desc = str(getattr(listing, "description", None) or "").lower()
    if ext.startswith(("nash:", "bexar:", "dallas:", "kingwa:")) or "cadastral gis" in desc or "public cad gis" in desc:
        listing.provider_id = "public_vacant_gis"


async def analyze_parcel(
    store: MemoryStore,
    parcel_id: UUID,
    settings: Settings | None = None,
    *,
    fast: bool = False,
) -> ScoreRecord:
    settings = settings or get_settings()
    parcel = store.parcels[parcel_id]
    listing = store.listing_for_parcel(parcel_id)
    _retag_vacant_gis_listing(listing)
    if listing is not None:
        store.listings[listing.id] = listing
    providers = build_enrichment_providers(settings)
    parcel_dict = parcel.model_dump()
    existing = store.enrichments.get(parcel_id) or EnrichmentBundle()

    # Fast path skips live gov calls so bulk discover can index thousands of parcels quickly.
    # Detail pages re-run with fast=False for full soils/flood/wetlands enrichment.
    run_live = (
        (not fast)
        and settings.enable_live_gov_enrichment
        and (not parcel.is_demo or settings.force_live_on_demo)
    )
    if run_live:
        soil_res, flood_res, wet_res, terrain_res, tx_res, growth_res = await asyncio.gather(
            providers["ssurgo"].enrich(parcel_dict),
            providers["fema_nfhl"].enrich(parcel_dict),
            providers["nwi"].enrich(parcel_dict),
            providers["usgs_3dep"].enrich(parcel_dict),
            providers["hifld_transmission"].enrich(parcel_dict),
            providers["census_acs"].enrich(parcel_dict),
        )
        if soil_res.data:
            existing.soil = soil_res.data
        if flood_res.data:
            existing.flood = flood_res.data
        if wet_res.data:
            existing.wetlands = wet_res.data
        if terrain_res.data:
            existing.terrain = terrain_res.data
        if tx_res.data:
            existing.infrastructure = tx_res.data
        if growth_res.data:
            existing.growth = growth_res.data
            gn = growth_res.data.normalized or {}
            if gn.get("county_name") and not parcel.county:
                parcel.county = str(gn["county_name"]).replace(" County", "")
                store.parcels[parcel_id] = parcel

    soil_n = (existing.soil.normalized or existing.soil.value or {}) if existing.soil else {}
    flood_n = (existing.flood.normalized or existing.flood.value or {}) if existing.flood else {}
    wet_n = (existing.wetlands.normalized or existing.wetlands.value or {}) if existing.wetlands else {}
    terr_n = (existing.terrain.normalized or existing.terrain.value or {}) if existing.terrain else {}
    infra_n = (
        (existing.infrastructure.normalized or existing.infrastructure.value or {})
        if existing.infrastructure
        else {}
    )
    growth_n = (existing.growth.normalized or existing.growth.value or {}) if existing.growth else {}

    # Valuation: refresh screening prior when missing or when small-lot tax-sale needs specialized model
    needs_value = (
        not existing.comps
        or existing.comps.knowledge_state == KnowledgeState.UNKNOWN
        or not ((existing.comps.normalized or {}).get("estimated_value_base_usd"))
        or (
            listing
            and listing.provider_id in ("public_tax_sale", "public_surplus")
            and (parcel.acreage or 0) < 2.0
            and (existing.comps.source or "").startswith("state_ppa")
        )
    )
    if needs_value:
        est = _estimate_value(parcel, soil_n, flood_n, wet_n, growth_n, listing)
        existing.comps = Provenanced(
            value=est,
            knowledge_state=est["knowledge_state"],
            source=est.get("note", "screening_prior")[:80],
            confidence=est["confidence"],
            retrieved_at=datetime.now(timezone.utc),
            normalized=est,
            geographic_resolution="state_prior",
        )

    # Listing-derived ESTIMATED signals so bulk/fast scores don't all collapse to ~50
    comps_n = dict(existing.comps.normalized or existing.comps.value or {}) if existing.comps else {}
    acres = parcel.acreage or 0
    ask = listing.asking_price_usd if listing else None
    provider = listing.provider_id if listing else None
    state = (parcel.state or "").upper()
    # Vacant map screens must not keep stale tax-sale auction / pressure invents
    if provider == "public_vacant_gis":
        comps_n.pop("auction_path", None)
        comps_n["seller_pressure_score"] = 42.0
        if existing.comps:
            norm = dict(existing.comps.normalized or {})
            val = dict(existing.comps.value or {}) if isinstance(existing.comps.value, dict) else {}
            norm.pop("auction_path", None)
            val.pop("auction_path", None)
            norm["seller_pressure_score"] = 42.0
            existing.comps.normalized = norm
            if val:
                existing.comps.value = val
    if comps_n.get("seller_pressure_score") is None:
        if provider == "public_tax_sale":
            comps_n["seller_pressure_score"] = 78.0
        elif provider == "public_surplus":
            comps_n["seller_pressure_score"] = 65.0
        elif provider == "blm_lpad":
            comps_n["seller_pressure_score"] = 55.0
        elif ask is not None:
            comps_n["seller_pressure_score"] = 48.0
    if comps_n.get("liquidity_score") is None:
        if acres and acres < 2:
            comps_n["liquidity_score"] = 62.0 if state in ("CA", "FL", "IN", "OH", "GA", "PA") else 50.0
        elif acres and acres >= 80:
            comps_n["liquidity_score"] = 38.0
        else:
            comps_n["liquidity_score"] = 48.0
    if comps_n.get("scarcity_score") is None:
        if provider == "blm_lpad" and acres and acres >= 40:
            comps_n["scarcity_score"] = 72.0
        elif acres and acres >= 100:
            comps_n["scarcity_score"] = 68.0
        elif acres and acres < 1:
            comps_n["scarcity_score"] = 35.0
        else:
            comps_n["scarcity_score"] = 52.0
    if comps_n.get("catalyst_score") is None:
        comps_n["catalyst_score"] = 58.0 if provider in ("public_tax_sale", "blm_lpad") else 42.0
    if comps_n.get("path_of_growth_score") is None and not growth_n.get("path_of_growth_score"):
        # Coarse Sun Belt / metro-adjacent prior — ESTIMATED only
        sun = {"FL", "TX", "AZ", "GA", "NC", "SC", "TN", "NV"}
        comps_n["path_of_growth_score"] = 63.0 if state in sun else 48.0
    if comps_n.get("zoning_development_friendly") is None and acres and acres < 5:
        comps_n["zoning_development_friendly"] = 55.0
    if existing.comps:
        existing.comps.normalized = {**(existing.comps.normalized or {}), **comps_n}
        existing.comps.value = {**(existing.comps.value or {}), **comps_n}

    # Access heuristic — never legally verified
    if existing.access.knowledge_state == KnowledgeState.UNKNOWN:
        conf = 45.0 if parcel.polygon else (30.0 if parcel.latitude else None)
        existing.access = Provenanced(
            value={"legal_access_confidence": conf},
            knowledge_state=KnowledgeState.ESTIMATED if conf is not None else KnowledgeState.UNKNOWN,
            source="access_heuristic",
            confidence=20,
            retrieved_at=datetime.now(timezone.utc),
            normalized={
                "legal_access_confidence": conf,
                "note": "NOT legally verified — deed/easement review required",
            },
        )

    comps_n = dict(existing.comps.normalized or existing.comps.value or {}) if existing.comps else comps_n
    access_n = existing.access.normalized or existing.access.value or {}
    raw_ask = listing.asking_price_usd if listing else None
    # $0 / negative "bids" are missing prices, not free land
    ask = raw_ask if raw_ask is not None and raw_ask > 0 else None
    if listing and ask is None and raw_ask is not None and raw_ask <= 0:
        listing.asking_price_usd = None

    # Merge growth into comps path score if present
    if growth_n.get("path_of_growth_score") is not None:
        comps_n = {**comps_n, "path_of_growth_score": growth_n["path_of_growth_score"]}

    # Auction / tax-sale: score mispricing on expected settle, not the teaser opening bid
    from landsignal.services.auction import effective_comparison_price

    model_base = comps_n.get("estimated_value_base_usd")
    comparison_price, auction_path = effective_comparison_price(
        ask,
        listing.provider_id if listing else None,
        float(model_base) if model_base is not None else None,
        parcel.acreage,
        parcel.state,
    )
    if auction_path:
        comps_n["auction_path"] = auction_path
        if existing.comps:
            existing.comps.normalized = {**(existing.comps.normalized or {}), "auction_path": auction_path}
            existing.comps.value = {**(existing.comps.value or {}), "auction_path": auction_path}

    score_input = {
        "asking_price_usd": comparison_price if comparison_price is not None else ask,
        "opening_bid_usd": ask if auction_path else None,
        "is_auction_opener": bool(auction_path),
        "auction_path": auction_path,
        "acreage": parcel.acreage,
        "apn": parcel.apn,
        "county": parcel.county,
        "state": parcel.state,
        "provider_id": listing.provider_id if listing else None,
        "estimated_value_low_usd": _wrap(comps_n.get("estimated_value_low_usd"), existing.comps),
        "estimated_value_base_usd": _wrap(comps_n.get("estimated_value_base_usd"), existing.comps),
        "estimated_value_high_usd": _wrap(comps_n.get("estimated_value_high_usd"), existing.comps),
        "downside_value_usd": _wrap(comps_n.get("downside_value_usd"), existing.comps),
        "development_upside_usd": _wrap(comps_n.get("development_upside_usd"), existing.comps),
        "prime_farmland_pct": _wrap(soil_n.get("prime_farmland_pct"), existing.soil),
        "wetland_pct": _wrap(wet_n.get("wetland_pct"), existing.wetlands),
        "flood_zone_pct": _wrap(flood_n.get("flood_zone_pct"), existing.flood),
        "avg_slope_pct": _wrap(terr_n.get("avg_slope_pct"), existing.terrain)
        if terr_n.get("avg_slope_pct") is not None
        else {
            "value": None,
            "knowledge_state": KnowledgeState.UNKNOWN.value,
            "confidence": None,
            "source": existing.terrain.source if existing.terrain else None,
        },
        "max_slope_pct": _wrap(terr_n.get("max_slope_pct"), existing.terrain)
        if terr_n.get("max_slope_pct") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "legal_access_confidence": _wrap(access_n.get("legal_access_confidence"), existing.access),
        "road_frontage_m": {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "nearest_transmission_m": _wrap(infra_n.get("nearest_transmission_m"), existing.infrastructure)
        if infra_n.get("nearest_transmission_m") is not None
        else {
            "value": None,
            "knowledge_state": existing.infrastructure.knowledge_state.value
            if existing.infrastructure
            else KnowledgeState.UNKNOWN.value,
            "confidence": None,
        },
        "liquidity_score": _wrap(comps_n.get("liquidity_score"), existing.comps)
        if comps_n.get("liquidity_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "scarcity_score": _wrap(comps_n.get("scarcity_score"), existing.comps)
        if comps_n.get("scarcity_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "path_of_growth_score": _wrap(comps_n.get("path_of_growth_score"), existing.growth or existing.comps)
        if comps_n.get("path_of_growth_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "catalyst_score": _wrap(comps_n.get("catalyst_score"), existing.comps)
        if comps_n.get("catalyst_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "seller_pressure_score": _wrap(comps_n.get("seller_pressure_score"), existing.comps)
        if comps_n.get("seller_pressure_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "days_on_market": listing.days_on_market if listing else None,
        "price_reduction_pct": (listing.raw or {}).get("price_reduction_pct") if listing else None,
        "environmental_contamination": {
            "value": None,
            "knowledge_state": KnowledgeState.UNKNOWN.value,
            "confidence": None,
        },
        "zoning_development_friendly": _wrap(comps_n.get("zoning_development_friendly"), existing.comps)
        if comps_n.get("zoning_development_friendly") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "timber_suitability": _wrap(comps_n.get("timber_suitability"), existing.comps)
        if comps_n.get("timber_suitability") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "solar_irradiance_score": _wrap(comps_n.get("solar_irradiance_score"), existing.comps)
        if comps_n.get("solar_irradiance_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "geometry_confidence": parcel.geometry_confidence,
        "comps_count": int(comps_n.get("comps_count") or 0),
        "known_attribute_ratio": _known_ratio(
            [
                soil_n.get("prime_farmland_pct") or soil_n.get("farmland_classification"),
                wet_n.get("wetland_pct"),
                flood_n.get("flood_zone_pct"),
                terr_n.get("elevation_m"),
                access_n.get("legal_access_confidence"),
                comps_n.get("estimated_value_base_usd"),
                infra_n.get("nearest_transmission_m"),
            ]
        ),
        "listing_freshness_hours": 1.0,
    }

    result = compute_score(score_input)
    personal = personalized_score(
        result["opportunity"],
        store.investor_profile,
        ask,
        parcel.acreage,
        result["best_strategy"],
        result["risk"],
    )

    narrative_ctx = {
        "days_on_market": listing.days_on_market if listing else None,
        "wetland_pct": wet_n.get("wetland_pct"),
        "flood_zone_pct": flood_n.get("flood_zone_pct"),
        "legal_access_confidence": access_n.get("legal_access_confidence"),
        "asking_discount_pct": result["asking_discount_pct"],
        "liquidity_score": comps_n.get("liquidity_score"),
        "asking_price_usd": ask,
        "comparison_price_usd": comparison_price,
        "auction_path": auction_path,
        "provider_id": listing.provider_id if listing else None,
        "path_of_growth_score": comps_n.get("path_of_growth_score"),
        "zoning_development_friendly": comps_n.get("zoning_development_friendly"),
        "nearest_transmission_m": infra_n.get("nearest_transmission_m"),
        "solar_irradiance_score": comps_n.get("solar_irradiance_score"),
        "prime_farmland_pct": soil_n.get("prime_farmland_pct"),
        "acreage": parcel.acreage,
        "state": parcel.state,
        "county": parcel.county,
        "confidence": result.get("confidence"),
        "risk": result.get("risk"),
        "deal_readiness": result.get("deal_readiness"),
        "estimated_value_usd": result.get("estimated_value_usd"),
        "best_strategy": result.get("best_strategy"),
    }
    unsold = why_still_unsold(narrative_ctx)
    hidden = hidden_value_score(narrative_ctx)

    from landsignal.services.market_trajectory import build_market_trajectory

    # Lightweight score stand-in so trajectory can use mark/discount before ScoreRecord exists
    class _ScoreProxy:
        estimated_value_usd = result.get("estimated_value_usd")
        asking_discount_pct = result.get("asking_discount_pct")
        risk = result.get("risk")

    trajectory = build_market_trajectory(
        parcel=parcel,
        listing=listing,
        score=_ScoreProxy(),
        enrichment=existing,
    )
    existing.narratives = {
        "why_unsold": unsold,
        "hidden_value": hidden,
        "market_trajectory": trajectory,
    }

    # Farmland scenarios when acreage + ask or estimated value exist —
    # BASE appreciation follows this parcel's trajectory rate when available.
    purchase = ask or comps_n.get("estimated_value_base_usd")
    traj_rate = float(trajectory.get("annual_rate") or 0.03)
    scenarios = []
    if purchase and parcel.acreage:
        hold_options = [1, 3, 5, 10, 15, 30, 50, 75, 100]
        for case, rent, appr in (
            ("BEAR", 140, max(0.0, traj_rate - 0.02)),
            ("BASE", 200, traj_rate),
            ("BULL", 280, min(0.08, traj_rate + 0.02)),
        ):
            sc = farmland_scenario(
                cash_rent_per_acre=rent,
                acres=float(parcel.acreage),
                vacancy_rate=0.05,
                opex_per_acre=25,
                taxes=purchase * 0.01,
                insurance=1200,
                management=purchase * 0.005,
                purchase_price=float(purchase),
                hold_years=10,
                exit_cap_rate=0.05,
                annual_appreciation=appr,
                discount_rate=0.1,
            )
            exits = {
                str(y): round(float(purchase) * ((1 + appr) ** y), 0) for y in hold_options
            }
            rent_stack = {
                str(y): round(float(sc.get("noi") or 0) * y, 0) for y in hold_options
            }
            scenarios.append(
                {
                    "strategy": "FARMLAND",
                    "case_type": case,
                    **sc,
                    "knowledge_state": "ESTIMATED",
                    "annual_appreciation": appr,
                    "annual_appreciation_display": f"{appr*100:.1f}%/yr",
                    "cash_rent_per_acre": rent,
                    "purchase_price": float(purchase),
                    "hold_years_options": hold_options,
                    "exit_value_by_year": exits,
                    "rent_stack_by_year": rent_stack,
                }
            )
    existing.scenarios = scenarios
    store.enrichments[parcel_id] = existing

    # Augment explanations with narratives
    why_still = list(result["why_still_available"])
    if unsold.get("most_likely"):
        why_still.insert(0, f"Most likely: {unsold['most_likely']['reason']}")

    record = ScoreRecord(
        parcel_id=parcel_id,
        listing_id=listing.id if listing else None,
        algorithm_version=result["algorithm_version"],
        weight_version=result["weight_version"],
        opportunity=result["opportunity"],
        risk=result["risk"],
        confidence=result["confidence"],
        asymmetry=result["asymmetry"],
        signal=Signal(result["signal"]),
        best_strategy=Strategy(result["best_strategy"]) if result["best_strategy"] else None,
        secondary_strategy=Strategy(result["secondary_strategy"])
        if result["secondary_strategy"]
        else None,
        personalized_opportunity=personal,
        estimated_value_usd=result["estimated_value_usd"],
        asking_discount_pct=result["asking_discount_pct"],
        deal_readiness=result["deal_readiness"],
        strategy_scores=result["strategy_scores"],
        strategy_screens=result["strategy_screens"],
        components=result["components"],
        explanations=result["explanations"]
        + [f"[hidden_value] {e}" for e in hidden.get("evidence", [])],
        why_interesting=result["why_interesting"]
        + ([f"Hidden value score {hidden['hidden_value_score']}"] if hidden else []),
        why_mispriced=result["why_mispriced"],
        what_could_kill=result["what_could_kill"],
        why_still_available=why_still,
        manual_verification=result["manual_verification"],
        input_hash=result["input_hash"],
        input_snapshot=score_input,
    )
    store.scores.setdefault(parcel_id, []).append(record)
    log.info(
        "score_computed",
        parcel_id=str(parcel_id),
        opportunity=record.opportunity,
        risk=record.risk,
        confidence=record.confidence,
        signal=record.signal.value,
        input_hash=record.input_hash,
    )
    return record
