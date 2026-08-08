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


@router.get("/radar", response_model=list[RadarRow])
async def radar() -> list[RadarRow]:
    store = get_store(get_settings().demo_seed)
    # Ensure demo parcels are scored
    for pid in list(store.parcels.keys()):
        if store.latest_score(pid) is None:
            await analyze_parcel(store, pid)
            score = store.latest_score(pid)
            if score:
                evaluate_rules(store, score, get_settings())

    rows: list[RadarRow] = []
    for parcel in store.parcels.values():
        score = store.latest_score(parcel.id)
        listing = store.listing_for_parcel(parcel.id)
        if not score:
            continue
        freshness = None
        if listing and listing.last_seen_at:
            freshness = (datetime.now(timezone.utc) - listing.last_seen_at).total_seconds() / 3600
        rows.append(
            RadarRow(
                parcel_id=parcel.id,
                listing_id=listing.id if listing else None,
                signal=score.signal,
                property_name=listing.title if listing else (parcel.apn or str(parcel.id)),
                location=f"{parcel.county or '—'}, {parcel.state or '—'}",
                acres=parcel.acreage,
                ask=listing.asking_price_usd if listing else None,
                price_per_acre=listing.price_per_acre_usd if listing else None,
                estimated_value=score.estimated_value_usd,
                discount_pct=score.asking_discount_pct,
                opportunity=score.opportunity,
                asymmetry=score.asymmetry,
                risk=score.risk,
                confidence=score.confidence,
                best_strategy=score.best_strategy,
                freshness_hours=freshness,
                status=listing.status if listing else "UNKNOWN",
                is_demo=parcel.is_demo or (listing.is_demo if listing else False),
                personalized_opportunity=score.personalized_opportunity,
            )
        )
    rows.sort(key=lambda r: r.opportunity, reverse=True)
    return rows


@router.get("/parcels/{parcel_id}")
async def parcel_detail(parcel_id: UUID) -> dict[str, Any]:
    store = get_store(get_settings().demo_seed)
    parcel = store.parcels.get(parcel_id)
    if not parcel:
        raise HTTPException(404, "Parcel not found")
    if store.latest_score(parcel_id) is None:
        await analyze_parcel(store, parcel_id)
    listing = store.listing_for_parcel(parcel_id)
    score = store.latest_score(parcel_id)
    enrichment = store.enrichments.get(parcel_id)
    return {
        "parcel": parcel,
        "listing": listing,
        "score": score,
        "enrichment": enrichment,
        "due_diligence": store.dd_items.get(parcel_id, []),
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
