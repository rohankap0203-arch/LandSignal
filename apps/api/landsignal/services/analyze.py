from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog

from landsignal.models import EnrichmentBundle, KnowledgeState, Provenanced, ScoreRecord, Signal, Strategy
from landsignal.providers.enrichment import build_enrichment_providers
from landsignal.scoring.engine import compute_score, personalized_score
from landsignal.settings import Settings, get_settings
from landsignal.store import MemoryStore

log = structlog.get_logger()


def _prov_num(bundle_value: dict | None, key: str, default_state: KnowledgeState = KnowledgeState.UNKNOWN) -> dict:
    if not bundle_value or key not in bundle_value or bundle_value[key] is None:
        return {"value": None, "knowledge_state": default_state.value, "confidence": None}
    return {
        "value": bundle_value[key],
        "knowledge_state": KnowledgeState.ESTIMATED.value,
        "confidence": 50,
    }


async def analyze_parcel(store: MemoryStore, parcel_id: UUID, settings: Settings | None = None) -> ScoreRecord:
    settings = settings or get_settings()
    parcel = store.parcels[parcel_id]
    listing = store.listing_for_parcel(parcel_id)
    providers = build_enrichment_providers(settings)

    parcel_dict = parcel.model_dump()
    existing = store.enrichments.get(parcel_id)

    # Live enrichment when enabled; demo fixtures retain estimates if live unavailable
    soil = flood = wetlands = terrain = None
    if settings.enable_live_gov_enrichment and not parcel.is_demo:
        soil_res = await providers["ssurgo"].enrich(parcel_dict)
        flood_res = await providers["fema_nfhl"].enrich(parcel_dict)
        wet_res = await providers["nwi"].enrich(parcel_dict)
        terrain_res = await providers["usgs_3dep"].enrich(parcel_dict)
        soil, flood, wetlands, terrain = soil_res.data, flood_res.data, wet_res.data, terrain_res.data
    elif settings.enable_live_gov_enrichment and parcel.is_demo:
        # Still attempt live calls for demo parcels but fall back to fixture provenance
        try:
            soil_res = await providers["ssurgo"].enrich(parcel_dict)
            if soil_res.data and soil_res.data.knowledge_state not in (
                KnowledgeState.TEMPORARILY_UNAVAILABLE,
                KnowledgeState.UNKNOWN,
            ):
                soil = soil_res.data
        except Exception as exc:  # noqa: BLE001
            log.warning("demo_live_soil_failed", error=str(exc))

    if existing is None:
        existing = EnrichmentBundle()
    if soil:
        existing.soil = soil
    if flood:
        existing.flood = flood
    if wetlands:
        existing.wetlands = wetlands
    if terrain:
        existing.terrain = terrain
    if existing.access.knowledge_state == KnowledgeState.UNKNOWN:
        # Heuristic only — never "legally verified"
        frontage_guess = 50.0 if parcel.polygon else None
        existing.access = Provenanced(
            value={"legal_access_confidence": frontage_guess},
            knowledge_state=KnowledgeState.ESTIMATED if frontage_guess else KnowledgeState.UNKNOWN,
            source="access_heuristic",
            confidence=25 if frontage_guess else 0,
            retrieved_at=datetime.now(timezone.utc),
            normalized={
                "legal_access_confidence": frontage_guess,
                "note": "Heuristic from geometry presence — not legal verification",
            },
        )
    store.enrichments[parcel_id] = existing

    soil_n = (existing.soil.normalized or existing.soil.value or {}) if existing.soil else {}
    flood_n = (existing.flood.normalized or existing.flood.value or {}) if existing.flood else {}
    wet_n = (existing.wetlands.normalized or existing.wetlands.value or {}) if existing.wetlands else {}
    terr_n = (existing.terrain.normalized or existing.terrain.value or {}) if existing.terrain else {}
    access_n = (existing.access.normalized or existing.access.value or {}) if existing.access else {}
    comps_n = (existing.comps.normalized or existing.comps.value or {}) if existing.comps else {}

    def wrap(value, source_prov: Provenanced | None, key: str | None = None):
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

    ask = listing.asking_price_usd if listing else None
    # Valuation: use comps fixture/model if present; else UNKNOWN (do not invent)
    est_base = comps_n.get("estimated_value_base_usd")
    score_input = {
        "asking_price_usd": ask,
        "acreage": parcel.acreage,
        "estimated_value_low_usd": wrap(comps_n.get("estimated_value_low_usd"), existing.comps),
        "estimated_value_base_usd": wrap(est_base, existing.comps),
        "estimated_value_high_usd": wrap(comps_n.get("estimated_value_high_usd"), existing.comps),
        "downside_value_usd": wrap(comps_n.get("downside_value_usd"), existing.comps),
        "development_upside_usd": wrap(comps_n.get("development_upside_usd"), existing.comps),
        "prime_farmland_pct": wrap(soil_n.get("prime_farmland_pct"), existing.soil),
        "wetland_pct": wrap(wet_n.get("wetland_pct"), existing.wetlands),
        "flood_zone_pct": wrap(flood_n.get("flood_zone_pct"), existing.flood),
        "avg_slope_pct": wrap(terr_n.get("avg_slope_pct"), existing.terrain)
        if terr_n.get("avg_slope_pct") is not None
        else {
            "value": None,
            "knowledge_state": (
                existing.terrain.knowledge_state.value
                if existing.terrain.knowledge_state != KnowledgeState.KNOWN
                else KnowledgeState.UNKNOWN.value
            ),
            "confidence": existing.terrain.confidence,
            "source": existing.terrain.source,
        },
        "max_slope_pct": wrap(terr_n.get("max_slope_pct"), existing.terrain)
        if terr_n.get("max_slope_pct") is not None
        else {
            "value": None,
            "knowledge_state": KnowledgeState.UNKNOWN.value,
            "confidence": None,
            "source": existing.terrain.source,
        },
        "legal_access_confidence": wrap(access_n.get("legal_access_confidence"), existing.access),
        "road_frontage_m": {
            "value": None,
            "knowledge_state": KnowledgeState.UNKNOWN.value,
            "confidence": None,
        },
        "nearest_transmission_m": {
            "value": None,
            "knowledge_state": KnowledgeState.UNKNOWN.value,
            "confidence": None,
        },
        "liquidity_score": wrap(comps_n.get("liquidity_score"), existing.comps)
        if comps_n.get("liquidity_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "scarcity_score": wrap(comps_n.get("scarcity_score"), existing.comps)
        if comps_n.get("scarcity_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "path_of_growth_score": wrap(comps_n.get("path_of_growth_score"), existing.comps)
        if comps_n.get("path_of_growth_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "catalyst_score": wrap(comps_n.get("catalyst_score"), existing.comps)
        if comps_n.get("catalyst_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "seller_pressure_score": wrap(comps_n.get("seller_pressure_score"), existing.comps)
        if comps_n.get("seller_pressure_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "days_on_market": listing.days_on_market if listing else None,
        "price_reduction_pct": (listing.raw or {}).get("price_reduction_pct") if listing else None,
        "environmental_contamination": {
            "value": None,
            "knowledge_state": KnowledgeState.UNKNOWN.value,
            "confidence": None,
        },
        "zoning_development_friendly": wrap(comps_n.get("zoning_development_friendly"), existing.comps)
        if comps_n.get("zoning_development_friendly") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "timber_suitability": wrap(comps_n.get("timber_suitability"), existing.comps)
        if comps_n.get("timber_suitability") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "solar_irradiance_score": wrap(comps_n.get("solar_irradiance_score"), existing.comps)
        if comps_n.get("solar_irradiance_score") is not None
        else {"value": None, "knowledge_state": KnowledgeState.UNKNOWN.value, "confidence": None},
        "geometry_confidence": parcel.geometry_confidence,
        "comps_count": int(comps_n.get("comps_count") or 0),
        "known_attribute_ratio": _known_ratio(
            [
                soil_n.get("prime_farmland_pct"),
                wet_n.get("wetland_pct"),
                flood_n.get("flood_zone_pct"),
                terr_n.get("elevation_m"),
                access_n.get("legal_access_confidence"),
                est_base,
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
        explanations=result["explanations"],
        why_interesting=result["why_interesting"],
        why_mispriced=result["why_mispriced"],
        what_could_kill=result["what_could_kill"],
        why_still_available=result["why_still_available"],
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
        input_hash=record.input_hash,
        algorithm_version=record.algorithm_version,
    )
    return record


def _known_ratio(values: list) -> float:
    if not values:
        return 0.0
    known = sum(1 for v in values if v is not None)
    return known / len(values)
