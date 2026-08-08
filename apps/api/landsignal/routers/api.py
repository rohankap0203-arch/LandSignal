from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile

from landsignal.models import (
    AlertRuleCreate,
    AlertRuleRecord,
    InvestorProfileUpdate,
    ManualIngestRequest,
    ProviderInfo,
    ProviderStatus,
    RadarRow,
)
from landsignal.providers.enrichment import build_enrichment_providers
from landsignal.providers.listing import build_listing_providers
from landsignal.services.alerts import create_rule, evaluate_rules
from landsignal.services.analyze import analyze_parcel
from landsignal.services.discover import discover_opportunities
from landsignal.services.memo import generate_memo, verdict_from_score
from landsignal.settings import get_settings
from landsignal.store import get_store

router = APIRouter()


def _provider_infos() -> list[ProviderInfo]:
    settings = get_settings()
    listing = build_listing_providers(settings)
    enrich = build_enrichment_providers(settings)
    infos: list[ProviderInfo] = []
    for p in listing.values():
        st = p.status()
        infos.append(
            ProviderInfo(
                id=p.id,
                kind="LISTING",
                name=p.name,
                status=st,
                detail=None
                if st == ProviderStatus.CONFIGURED
                else "NOT_CONFIGURED — credentials or licensed adapter required",
            )
        )
    for p in enrich.values():
        st = p.status()
        detail = None
        if p.id == "mapbox":
            detail = None
        if st == ProviderStatus.NOT_CONFIGURED:
            detail = "NOT_CONFIGURED"
        infos.append(ProviderInfo(id=p.id, kind="ENRICHMENT", name=p.name, status=st, detail=detail))
    # Mapbox / messaging as config status
    infos.append(
        ProviderInfo(
            id="mapbox",
            kind="ENRICHMENT",
            name="Mapbox",
            status=ProviderStatus.CONFIGURED if settings.mapbox_token else ProviderStatus.NOT_CONFIGURED,
            detail=None if settings.mapbox_token else "NOT_CONFIGURED — set MAPBOX_TOKEN / NEXT_PUBLIC_MAPBOX_TOKEN",
        )
    )
    infos.append(
        ProviderInfo(
            id="smtp",
            kind="ALERTING",
            name="Email Delivery",
            status=ProviderStatus.CONFIGURED if settings.smtp_url else ProviderStatus.NOT_CONFIGURED,
            detail=None if settings.smtp_url else "NOT_CONFIGURED — set SMTP_URL",
        )
    )
    sms_ok = bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number)
    infos.append(
        ProviderInfo(
            id="twilio",
            kind="ALERTING",
            name="Twilio SMS",
            status=ProviderStatus.CONFIGURED if sms_ok else ProviderStatus.NOT_CONFIGURED,
            detail=None if sms_ok else "NOT_CONFIGURED — set TWILIO_* secrets",
        )
    )
    return infos


@router.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "landsignal-api",
        "store_backend": settings.store_backend,
        "database_configured": bool(settings.database_url),
        "redis_configured": bool(settings.redis_url),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/providers", response_model=list[ProviderInfo])
async def providers() -> list[ProviderInfo]:
    return _provider_infos()


@router.post("/discover")
async def discover(
    limit: int = 24,
    min_acres: float = 20.0,
    max_acres: float = 2500.0,
    reset: bool = False,
) -> dict[str, Any]:
    """Pull real public inventory (BLM LPAD + any configured licensed feeds), enrich, score."""
    store = get_store(get_settings().demo_seed)
    return await discover_opportunities(
        store,
        get_settings(),
        limit=limit,
        min_acres=min_acres,
        max_acres=max_acres,
        reset=reset,
    )


@router.post("/ingest/manual")
async def ingest_manual(body: ManualIngestRequest) -> dict[str, Any]:
    store = get_store(get_settings().demo_seed)
    parcel, listing = store.upsert_manual(body.model_dump())
    score = await analyze_parcel(store, parcel.id)
    alerts = evaluate_rules(store, score, get_settings())
    return {
        "parcel_id": parcel.id,
        "listing_id": listing.id,
        "score_id": score.id,
        "alerts_triggered": len(alerts),
    }


@router.post("/ingest/csv")
async def ingest_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    store = get_store(get_settings().demo_seed)
    text = (await file.read()).decode("utf-8")
    rows = store.import_csv(text)
    results = []
    for parcel, listing in rows:
        score = await analyze_parcel(store, parcel.id)
        evaluate_rules(store, score, get_settings())
        results.append({"parcel_id": parcel.id, "listing_id": listing.id, "score_id": score.id})
    return {"imported": len(results), "results": results}


@router.post("/parcels/{parcel_id}/analyze")
async def reanalyze(parcel_id: UUID) -> dict[str, Any]:
    store = get_store(get_settings().demo_seed)
    if parcel_id not in store.parcels:
        raise HTTPException(404, "Parcel not found")
    score = await analyze_parcel(store, parcel_id)
    alerts = evaluate_rules(store, score, get_settings())
    return {"score": score, "alerts_triggered": len(alerts)}


PROVIDER_LABELS = {
    "blm_lpad": "Federal BLM disposal",
    "public_tax_sale": "County tax sale",
    "public_surplus": "Public surplus",
    "manual": "Manual entry",
    "csv": "CSV import",
}


def _strategy_label(s) -> str:
    if not s:
        return "Undetermined"
    return s.value.replace("_", " ").title()


@router.get("/radar", response_model=list[RadarRow])
async def radar(
    state: str | None = None,
    region: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_acres: float | None = None,
    max_acres: float | None = None,
    strategy: str | None = None,
    min_score: float | None = None,
    max_risk: float | None = None,
    min_confidence: float | None = None,
    hold_years: int | None = None,
    target_roi: float | None = None,
    include_unpriced: bool = True,
    q: str | None = None,
) -> list[RadarRow]:
    """Search results with investor filters. Pass nothing / omit for Any."""
    from landsignal.scoring.engine import personalized_score
    from landsignal.services.presentation import (
        build_action_links,
        match_reasons,
        price_display,
        rating_breakdown,
        value_display,
    )

    store = get_store(get_settings().demo_seed)
    for pid in list(store.parcels.keys()):
        if store.latest_score(pid) is None:
            await analyze_parcel(store, pid)

    filters = {
        "state": state,
        "region": region,
        "hold_years": hold_years,
        "target_roi": target_roi,
    }

    profile = dict(store.investor_profile)
    if hold_years is not None:
        profile["target_hold_years_min"] = hold_years
        profile["target_hold_years_max"] = hold_years
    if target_roi is not None:
        profile["min_target_irr"] = target_roi
    if max_price is not None:
        profile["max_price_usd"] = max_price
    if min_acres is not None:
        profile["min_acres"] = min_acres
    if strategy and strategy.upper() != "ANY":
        profile["preferred_strategies"] = [strategy.upper()]

    rows: list[RadarRow] = []
    for parcel in store.parcels.values():
        score = store.latest_score(parcel.id)
        listing = store.listing_for_parcel(parcel.id)
        if not score or not listing:
            continue
        if parcel.is_demo:
            continue

        # Filters (None / missing = Any)
        if state and state.upper() not in ("ANY", "") and (parcel.state or "").upper() != state.upper():
            continue
        region_hay = f"{parcel.county or ''} {parcel.state or ''} {listing.title or ''}".lower()
        if region and region.lower() not in ("any", ""):
            token = region.lower().replace(" county", "").strip()
            if token not in region_hay and region.lower() not in region_hay:
                continue
        ask = listing.asking_price_usd
        if not include_unpriced and (ask is None or ask <= 0):
            continue
        if min_price is not None and (ask is None or ask < min_price):
            continue
        if max_price is not None and ask is not None and ask > max_price:
            continue
        if min_acres is not None and (parcel.acreage is None or parcel.acreage < min_acres):
            continue
        if max_acres is not None and parcel.acreage is not None and parcel.acreage > max_acres:
            continue
        if strategy and strategy.upper() not in ("ANY", ""):
            if not score.best_strategy or score.best_strategy.value != strategy.upper():
                # allow secondary
                if not score.secondary_strategy or score.secondary_strategy.value != strategy.upper():
                    continue
        if min_score is not None and score.opportunity < min_score:
            continue
        if max_risk is not None and score.risk > max_risk:
            continue
        if min_confidence is not None and score.confidence < min_confidence:
            continue
        if q:
            blob = f"{listing.title} {parcel.county} {parcel.state} {parcel.apn} {listing.description or ''}".lower()
            if q.lower() not in blob:
                continue

        fit = personalized_score(
            score.opportunity,
            profile,
            ask,
            parcel.acreage,
            score.best_strategy.value if score.best_strategy else None,
            score.risk,
        )
        # Hold / ROI soft fit adjustments
        if hold_years is not None:
            if hold_years <= 5 and score.best_strategy and score.best_strategy.value in ("ENERGY", "FARMLAND"):
                fit = min(100, fit + 4)
            if hold_years >= 10 and score.best_strategy and score.best_strategy.value in ("LAND_BANK", "DEVELOPMENT", "TIMBER"):
                fit = min(100, fit + 5)
        if target_roi is not None:
            enrichment = store.enrichments.get(parcel.id)
            base_sc = None
            if enrichment and enrichment.scenarios:
                base_sc = next((s for s in enrichment.scenarios if s.get("case_type") == "BASE"), None)
            if base_sc and base_sc.get("irr") is not None:
                if base_sc["irr"] + 1e-9 >= target_roi:
                    fit = min(100, fit + 6)
                else:
                    fit = max(0, fit - 8)

        enrichment = store.enrichments.get(parcel.id)
        pd = price_display(ask, listing.provider_id)
        vd = value_display(
            score.estimated_value_usd,
            (enrichment.comps.knowledge_state.value if enrichment and enrichment.comps else "ESTIMATED"),
        )
        ppa = listing.price_per_acre_usd
        if ppa is None and ask and parcel.acreage:
            ppa = ask / parcel.acreage
        links = build_action_links(
            provider_id=listing.provider_id,
            source_url=listing.source_url,
            title=listing.title or "",
            apn=parcel.apn,
            state=parcel.state,
            county=parcel.county,
            latitude=parcel.latitude,
            longitude=parcel.longitude,
            raw=listing.raw,
        )
        reasons = match_reasons(
            score=score,
            parcel=parcel,
            listing=listing,
            filters=filters,
            enrichment=enrichment,
        )
        acres = parcel.acreage
        acres_display = f"{acres:,.2f} acres" if acres is not None else "Acreage not published"
        discount_display = (
            f"{score.asking_discount_pct:+.1f}% vs model"
            if score.asking_discount_pct is not None
            else "No retail ask to compare"
        )
        risk_label = (
            "Lower screened risk"
            if score.risk < 30
            else "Moderate screened risk"
            if score.risk < 55
            else "Elevated screened risk"
        )
        conf_label = (
            "Strong evidence base"
            if score.confidence >= 70
            else "Moderate evidence base"
            if score.confidence >= 45
            else "Thin evidence — verify manually"
        )
        summary = (
            f"{_strategy_label(score.best_strategy)} thesis · "
            f"LandSignal {score.opportunity:.0f}/100 · Risk {score.risk:.0f}/100 · "
            f"{pd['display']}"
        )
        headline = (
            f"{abs(score.asking_discount_pct):.0f}% below model"
            if score.asking_discount_pct is not None and score.asking_discount_pct < -8
            else f"Asymmetry {score.asymmetry:.0f}/100"
        )

        rows.append(
            RadarRow(
                parcel_id=parcel.id,
                listing_id=listing.id,
                signal=score.signal,
                property_name=listing.title or parcel.apn or str(parcel.id),
                location=f"{parcel.county or 'County TBD'}, {parcel.state or 'US'}",
                state=parcel.state,
                county=parcel.county,
                region=f"{parcel.county or ''}, {parcel.state or ''}".strip(", "),
                acres=acres,
                acres_display=acres_display,
                ask=ask,
                price_display=pd["display"],
                price_label=pd["label"],
                price_per_acre=ppa,
                price_per_acre_display=f"${ppa:,.0f}/ac" if ppa else "n/a — no priced ask",
                estimated_value=score.estimated_value_usd,
                estimated_value_display=vd["display"],
                value_knowledge=vd["knowledge_state"],
                discount_pct=score.asking_discount_pct,
                discount_display=discount_display,
                opportunity=score.opportunity,
                asymmetry=score.asymmetry,
                risk=score.risk,
                confidence=score.confidence,
                deal_readiness=score.deal_readiness,
                best_strategy=score.best_strategy,
                best_strategy_label=_strategy_label(score.best_strategy),
                secondary_strategy_label=_strategy_label(score.secondary_strategy),
                freshness_hours=(
                    (datetime.now(timezone.utc) - listing.last_seen_at).total_seconds() / 3600
                    if listing.last_seen_at
                    else None
                ),
                status=listing.status,
                status_label="Available" if listing.status == "ACTIVE" else listing.status.title(),
                is_demo=False,
                personalized_opportunity=fit,
                fit_score=fit,
                summary=summary,
                match_reasons=reasons,
                rating_breakdown=rating_breakdown(score),
                links=links,
                latitude=parcel.latitude,
                longitude=parcel.longitude,
                provider_id=listing.provider_id,
                provider_label=PROVIDER_LABELS.get(listing.provider_id, listing.provider_id or "Public source"),
                headline_metric=headline,
                risk_label=risk_label,
                confidence_label=conf_label,
            )
        )

    rows.sort(key=lambda r: (r.fit_score or 0, r.opportunity), reverse=True)
    return rows


@router.get("/search/meta")
async def search_meta() -> dict[str, Any]:
    """Filter option lists derived from live inventory."""
    store = get_store(get_settings().demo_seed)
    states = sorted({(p.state or "").upper() for p in store.parcels.values() if p.state and not p.is_demo})
    regions = sorted(
        {
            f"{p.county}, {p.state}"
            for p in store.parcels.values()
            if p.county and p.state and not p.is_demo
        }
    )
    return {
        "states": ["Any", *states],
        "regions": ["Any", *regions],
        "strategies": [
            "Any",
            "FARMLAND",
            "DEVELOPMENT",
            "LAND_BANK",
            "RECREATIONAL",
            "ENERGY",
            "TIMBER",
        ],
        "hold_years": ["Any", 3, 5, 7, 10, 15, 20],
        "target_roi": ["Any", 0.08, 0.10, 0.12, 0.15, 0.20],
        "price_presets": [
            {"label": "Any", "min": None, "max": None},
            {"label": "Under $50k", "min": None, "max": 50000},
            {"label": "$50k–$250k", "min": 50000, "max": 250000},
            {"label": "$250k–$1M", "min": 250000, "max": 1000000},
            {"label": "$1M+", "min": 1000000, "max": None},
        ],
        "acre_presets": [
            {"label": "Any", "min": None, "max": None},
            {"label": "1–20 ac", "min": 1, "max": 20},
            {"label": "20–100 ac", "min": 20, "max": 100},
            {"label": "100–500 ac", "min": 100, "max": 500},
            {"label": "500+ ac", "min": 500, "max": None},
        ],
    }


@router.get("/parcels/{parcel_id}")
async def parcel_detail(parcel_id: UUID) -> dict[str, Any]:
    from landsignal.services.presentation import build_action_links, price_display, rating_breakdown

    store = get_store(get_settings().demo_seed)
    parcel = store.parcels.get(parcel_id)
    if not parcel:
        raise HTTPException(404, "Parcel not found")
    if store.latest_score(parcel_id) is None:
        await analyze_parcel(store, parcel_id)
    listing = store.listing_for_parcel(parcel_id)
    score = store.latest_score(parcel_id)
    enrichment = store.enrichments.get(parcel_id)
    links = build_action_links(
        provider_id=listing.provider_id if listing else None,
        source_url=listing.source_url if listing else None,
        title=(listing.title if listing else None) or "",
        apn=parcel.apn,
        state=parcel.state,
        county=parcel.county,
        latitude=parcel.latitude,
        longitude=parcel.longitude,
        raw=listing.raw if listing else None,
    )
    return {
        "parcel": parcel,
        "listing": listing,
        "score": score,
        "enrichment": enrichment,
        "due_diligence": store.dd_items.get(parcel_id, []),
        "links": links,
        "price": price_display(listing.asking_price_usd if listing else None, listing.provider_id if listing else None),
        "rating_breakdown": rating_breakdown(score) if score else [],
        "disclaimer": "Screening intelligence only — not an appraisal, legal opinion, or purchase authorization.",
        "mapbox_status": "CONFIGURED" if get_settings().mapbox_token else "NOT_CONFIGURED",
    }


@router.get("/parcels/{parcel_id}/scores")
async def parcel_scores(parcel_id: UUID) -> dict[str, Any]:
    store = get_store(get_settings().demo_seed)
    if parcel_id not in store.parcels:
        raise HTTPException(404, "Parcel not found")
    return {"scores": store.scores.get(parcel_id, [])}


@router.post("/parcels/{parcel_id}/memo")
async def parcel_memo(parcel_id: UUID) -> dict[str, str]:
    store = get_store(get_settings().demo_seed)
    if parcel_id not in store.parcels:
        raise HTTPException(404, "Parcel not found")
    if store.latest_score(parcel_id) is None:
        await analyze_parcel(store, parcel_id)
    md = generate_memo(store, parcel_id)
    score = store.latest_score(parcel_id)
    assert score
    return {
        "markdown": md,
        "verdict": verdict_from_score(
            score.opportunity, score.risk, score.confidence, score.deal_readiness
        ),
    }


@router.post("/alerts/rules")
async def create_alert_rule(body: AlertRuleCreate) -> AlertRuleRecord:
    store = get_store(get_settings().demo_seed)
    return create_rule(store, body.name, body.predicate, body.channels)


@router.get("/alerts")
async def list_alerts() -> list:
    store = get_store(get_settings().demo_seed)
    return store.alerts


@router.get("/investor-profile")
async def get_profile() -> dict[str, Any]:
    return get_store(get_settings().demo_seed).investor_profile


@router.put("/investor-profile")
async def put_profile(body: InvestorProfileUpdate) -> dict[str, Any]:
    store = get_store(get_settings().demo_seed)
    return store.update_profile(body)


@router.post("/parcels/{parcel_id}/watch")
async def watch(parcel_id: UUID) -> dict[str, Any]:
    store = get_store(get_settings().demo_seed)
    if parcel_id not in store.parcels:
        raise HTTPException(404, "Parcel not found")
    user = UUID("00000000-0000-4000-8000-000000000002")
    store.watchlists.setdefault(user, set()).add(parcel_id)
    return {"watched": True, "parcel_id": parcel_id}
