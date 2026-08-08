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
    limit: int = 48,
    min_acres: float = 1.0,
    max_acres: float = 2500.0,
    reset: bool = False,
    states: str | None = None,
    background: bool = True,
) -> dict[str, Any]:
    """Pull real public inventory. Default background=true so the UI is not blocked for minutes."""
    import asyncio

    store = get_store(get_settings().demo_seed)
    settings = get_settings()
    state_list = [s.strip().upper() for s in states.split(",") if s.strip()] if states else None

    async def _run() -> dict[str, Any]:
        return await discover_opportunities(
            store,
            settings,
            limit=limit,
            min_acres=min_acres,
            max_acres=max_acres,
            reset=reset,
            states=state_list,
        )

    if background:
        asyncio.create_task(_run())
        return {
            "started": True,
            "background": True,
            "limit": limit,
            "reset": reset,
            "inventory_now": sum(1 for p in store.parcels.values() if not p.is_demo),
            "note": "Scan started in background. Results appear as parcels finish scoring — refresh search shortly.",
        }
    return await _run()


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


def _normalize_state(state: str | None) -> str | None:
    if not state or state.upper() in ("ANY", ""):
        return None
    raw = state.strip()
    if "—" in raw:
        raw = raw.split("—", 1)[0].strip()
    if "-" in raw and len(raw) > 2:
        # tolerate "CA - California"
        left = raw.split("-", 1)[0].strip()
        if len(left) == 2:
            raw = left
    return raw.upper()[:2] if len(raw) >= 2 else raw.upper()


def _sort_rows(rows: list[RadarRow], sort: str | None) -> list[RadarRow]:
    key = (sort or "fit_desc").lower()

    def discount_key(r: RadarRow) -> float:
        # more negative discount = bigger bargain
        return r.discount_pct if r.discount_pct is not None else 999.0

    if key == "score_desc":
        rows.sort(key=lambda r: (r.opportunity, r.fit_score or 0), reverse=True)
    elif key == "risk_asc":
        rows.sort(key=lambda r: (r.risk, -(r.fit_score or 0)))
    elif key == "confidence_desc":
        rows.sort(key=lambda r: (r.confidence, r.opportunity), reverse=True)
    elif key == "price_asc":
        rows.sort(key=lambda r: (r.ask is None, r.ask if r.ask is not None else 0))
    elif key == "price_desc":
        rows.sort(key=lambda r: (r.ask is None, -(r.ask or 0)))
    elif key == "acres_desc":
        rows.sort(key=lambda r: (r.acres is None, -(r.acres or 0)))
    elif key == "discount_asc":
        rows.sort(key=discount_key)
    else:
        rows.sort(key=lambda r: (r.fit_score or 0, r.opportunity), reverse=True)
    return rows


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
    unpriced_mode: str | None = None,
    market_channel: str | None = None,
    sort: str | None = "fit_desc",
    q: str | None = None,
    broaden: bool = True,
) -> list[RadarRow]:
    """Search results with investor filters. Pass nothing / omit for Any."""
    from landsignal.geo_meta import region_matches
    from landsignal.scoring.engine import personalized_score
    from landsignal.services.presentation import (
        build_action_links,
        match_reasons,
        price_display,
        rating_breakdown,
        value_display,
    )

    store = get_store(get_settings().demo_seed)
    # Never block search on enrichment — unscored parcels are omitted until discover finishes them

    state_code = _normalize_state(state)
    filters = {
        "state": state_code,
        "region": region,
        "hold_years": hold_years,
        "target_roi": target_roi,
        "market_channel": market_channel,
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
    if strategy and strategy.upper() not in ("ANY", "CUSTOM", ""):
        profile["preferred_strategies"] = [strategy.upper()]

    mode = (unpriced_mode or ("include" if include_unpriced else "priced")).lower()
    channel = (market_channel or "Any").strip()

    async def build_rows(*, apply_region: bool, apply_strict_channel: bool) -> list[RadarRow]:
        out: list[RadarRow] = []
        for parcel in store.parcels.values():
            score = store.latest_score(parcel.id)
            listing = store.listing_for_parcel(parcel.id)
            if not score or not listing or parcel.is_demo:
                continue

            if state_code and (parcel.state or "").upper() != state_code:
                continue
            if apply_region and not region_matches(
                region=region,
                state=parcel.state,
                county=parcel.county,
                title=listing.title,
            ):
                continue

            ask = listing.asking_price_usd
            priced = ask is not None and ask > 0
            if mode == "priced" and not priced:
                continue
            if mode == "unpriced_only" and priced:
                continue
            if channel and channel.upper() not in ("ANY", ""):
                if channel == "priced_only":
                    if not priced:
                        continue
                elif apply_strict_channel and listing.provider_id != channel and not (
                    channel == "manual" and listing.provider_id in ("manual", "csv")
                ):
                    continue

            if min_price is not None and (ask is None or ask < min_price):
                continue
            if max_price is not None and ask is not None and ask > max_price:
                continue
            if min_acres is not None and (parcel.acreage is None or parcel.acreage < min_acres):
                continue
            if max_acres is not None and parcel.acreage is not None and parcel.acreage > max_acres:
                continue
            if strategy and strategy.upper() not in ("ANY", "CUSTOM", ""):
                known = {"FARMLAND", "DEVELOPMENT", "LAND_BANK", "RECREATIONAL", "ENERGY", "TIMBER"}
                s_up = strategy.upper().replace(" ", "_")
                if s_up in known:
                    if not score.best_strategy or score.best_strategy.value != s_up:
                        if not score.secondary_strategy or score.secondary_strategy.value != s_up:
                            continue
                else:
                    blob = f"{listing.title} {listing.description or ''} {_strategy_label(score.best_strategy)}".lower()
                    if strategy.lower() not in blob and s_up.lower().replace("_", " ") not in blob:
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
            if hold_years is not None:
                if hold_years <= 5 and score.best_strategy and score.best_strategy.value in ("ENERGY", "FARMLAND"):
                    fit = min(100, fit + 4)
                if hold_years >= 10 and score.best_strategy and score.best_strategy.value in (
                    "LAND_BANK",
                    "DEVELOPMENT",
                    "TIMBER",
                ):
                    fit = min(100, fit + 5)
            enrichment = store.enrichments.get(parcel.id)
            if target_roi is not None:
                base_sc = None
                if enrichment and enrichment.scenarios:
                    base_sc = next((s for s in enrichment.scenarios if s.get("case_type") == "BASE"), None)
                if base_sc and base_sc.get("irr") is not None:
                    if base_sc["irr"] + 1e-9 >= target_roi:
                        fit = min(100, fit + 6)
                    else:
                        fit = max(0, fit - 8)

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
            # Fast path for search cards: assume links work; detail page validates & grays dead ones.
            annotated = [
                {**l, "available": True, "availability_reason": "deferred", "status_code": None}
                for l in links
            ]

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

            out.append(
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
                    links=annotated,
                    latitude=parcel.latitude,
                    longitude=parcel.longitude,
                    provider_id=listing.provider_id,
                    provider_label=PROVIDER_LABELS.get(listing.provider_id, listing.provider_id or "Public source"),
                    headline_metric=headline,
                    risk_label=risk_label,
                    confidence_label=conf_label,
                )
            )
        return out

    rows = await build_rows(apply_region=True, apply_strict_channel=True)
    # Never return a blank wall — broaden region/channel, then price/acres soft fallback note via reasons
    if broaden and not rows:
        rows = await build_rows(apply_region=False, apply_strict_channel=True)
        for r in rows:
            r.match_reasons = [
                "Exact region had no inventory — showing best matches in your selected state/filters.",
                *r.match_reasons,
            ][:5]
    if broaden and not rows:
        rows = await build_rows(apply_region=False, apply_strict_channel=False)
        for r in rows:
            r.match_reasons = [
                "No exact channel matches — showing closest live public opportunities.",
                *r.match_reasons,
            ][:5]

    return _sort_rows(rows, sort)


@router.get("/search/meta")
async def search_meta() -> dict[str, Any]:
    """Nationwide filter catalog + live inventory hints."""
    from landsignal.geo_meta import search_meta_payload

    store = get_store(get_settings().demo_seed)
    inventory_regions = sorted(
        {
            f"{p.county}, {p.state}"
            for p in store.parcels.values()
            if p.county and p.state and not p.is_demo
        }
    )
    inventory_states = sorted(
        {(p.state or "").upper() for p in store.parcels.values() if p.state and not p.is_demo}
    )
    payload = search_meta_payload(inventory_regions)
    payload["inventory_states"] = inventory_states
    payload["inventory_count"] = sum(1 for p in store.parcels.values() if not p.is_demo)
    return payload


@router.get("/parcels/{parcel_id}")
async def parcel_detail(parcel_id: UUID) -> dict[str, Any]:
    from landsignal.services.humanize import (
        human_dd_items,
        human_flood,
        human_soil,
        human_transmission,
        human_wetlands,
    )
    from landsignal.services.links import annotate_links
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
    # Only validate non-map links; maps/search are assumed reachable (keeps page snappy)
    non_map = [l for l in links if l.get("kind") != "map"]
    maps = [{**l, "available": True, "availability_reason": "ok", "status_code": 200} for l in links if l.get("kind") == "map"]
    checked = await annotate_links(non_map)
    annotated = checked + maps
    # Promote first available non-map link if primary is dead
    if annotated and not annotated[0].get("available"):
        for i, link in enumerate(annotated):
            if link.get("available") and link.get("kind") != "map":
                annotated[0], annotated[i] = annotated[i], annotated[0]
                break

    dd_raw = store.dd_items.get(parcel_id, [])
    dd_guided = human_dd_items(
        [d if isinstance(d, dict) else d.model_dump() for d in dd_raw],
        score,
        enrichment,
    )
    land_readouts = {
        "soil": human_soil(enrichment.soil if enrichment else None),
        "flood": human_flood(enrichment.flood if enrichment else None),
        "wetlands": human_wetlands(enrichment.wetlands if enrichment else None),
        "transmission": human_transmission(enrichment.infrastructure if enrichment else None),
    }
    scenarios_human = []
    case_names = {
        "BASE": "Typical",
        "DOWNSIDE": "Cautious",
        "UPSIDE": "Optimistic",
        "STRESS": "Stress",
    }
    for s in (enrichment.scenarios if enrichment else []) or []:
        case_key = str(s.get("case_type") or "Scenario")
        case_name = case_names.get(case_key, case_key)
        if s.get("irr") is not None:
            plain = (
                f"{case_name} farmland screen: about {float(s['irr']) * 100:.1f}% IRR "
                "if the assumptions hold."
            )
        else:
            plain = "This case needs more crop/rent inputs before an IRR can be shown."
        scenarios_human.append(
            {
                **s,
                "case_label": {
                    "BASE": "Base case (typical)",
                    "DOWNSIDE": "Cautious case",
                    "UPSIDE": "Optimistic case",
                    "STRESS": "Stress case",
                }.get(case_key, case_key),
                "irr_display": f"{float(s['irr']) * 100:.1f}% per year" if s.get("irr") is not None else "Not enough data",
                "noi_display": f"${float(s.get('noi') or 0):,.0f} / year",
                "npv_display": f"${float(s.get('npv') or 0):,.0f}",
                "breakeven_display": (
                    f"${float(s['breakeven_land_value']):,.0f}"
                    if s.get("breakeven_land_value") is not None
                    else "Not enough data"
                ),
                "plain_english": plain,
            }
        )

    return {
        "parcel": parcel,
        "listing": listing,
        "score": score,
        "enrichment": enrichment,
        "due_diligence": dd_raw,
        "due_diligence_guided": dd_guided,
        "land_readouts": land_readouts,
        "scenarios_human": scenarios_human,
        "links": annotated,
        "price": price_display(listing.asking_price_usd if listing else None, listing.provider_id if listing else None),
        "rating_breakdown": rating_breakdown(score) if score else [],
        "score_explained": {
            "landsignal": "Overall opportunity score from 0–100 after weighing price, quality, options, and risk.",
            "risk": "Higher means more things that can go wrong on a desktop screen (flood, wetlands, thin data).",
            "confidence": "How complete the evidence file is. Thin files get lower confidence, not fake quality.",
            "fit": "How well this parcel matches the criteria you set on Search / My criteria.",
            "deal_readiness": "How much manual homework remains before a human could responsibly bid.",
        },
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
