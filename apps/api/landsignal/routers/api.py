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
    limit: int = 10000,
    min_acres: float = 0.1,
    max_acres: float = 50000.0,
    reset: bool = False,
    states: str | None = None,
    background: bool = True,
    fast: bool = True,
) -> dict[str, Any]:
    """Pull real public inventory. Default background=true so the UI is not blocked for minutes."""
    import asyncio

    from landsignal.store import persist_store

    store = get_store(get_settings().demo_seed)
    settings = get_settings()
    state_list = [s.strip().upper() for s in states.split(",") if s.strip()] if states else None

    async def _run() -> dict[str, Any]:
        try:
            summary = await discover_opportunities(
                store,
                settings,
                limit=limit,
                min_acres=min_acres,
                max_acres=max_acres,
                reset=reset,
                states=state_list,
                fast=fast,
            )
            try:
                persist_store(store)
            except Exception:
                pass
            return summary
        except Exception as exc:  # noqa: BLE001
            import structlog

            structlog.get_logger().exception("discover_background_failed", error=str(exc))
            return {"imported": 0, "scored": 0, "errors": [str(exc)]}

    if background:
        asyncio.create_task(_run())
        return {
            "started": True,
            "background": True,
            "limit": limit,
            "reset": reset,
            "fast": fast,
            "inventory_now": sum(1 for p in store.parcels.values() if not p.is_demo),
            "note": "Nationwide scan started. Parcels appear as they index — hit Show matches every few seconds.",
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
    limit: int = 200,
) -> list[RadarRow]:
    """Search results with investor filters. Pass nothing / omit for Any.

    broaden=True softens region/strategy when they would otherwise return zero rows,
    but never crosses a selected state boundary.
    """
    from landsignal.geo_meta import region_matches
    from landsignal.scoring.engine import personalized_score
    from landsignal.services.presentation import (
        build_action_links,
        build_return_thesis,
        match_reasons,
        price_display,
        rating_breakdown,
        sourcing_card,
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
            if ask is not None and ask <= 0:
                ask = None
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
            strategy_soft_miss = False
            if strategy and strategy.upper() not in ("ANY", "CUSTOM", ""):
                known = {"FARMLAND", "DEVELOPMENT", "LAND_BANK", "RECREATIONAL", "ENERGY", "TIMBER"}
                s_up = strategy.upper().replace(" ", "_")
                if s_up in known:
                    hit = (score.best_strategy and score.best_strategy.value == s_up) or (
                        score.secondary_strategy and score.secondary_strategy.value == s_up
                    )
                    if not hit:
                        # Soft: keep parcel but mark for fit penalty instead of hard exclude
                        strategy_soft_miss = True
                else:
                    blob = f"{listing.title} {listing.description or ''} {_strategy_label(score.best_strategy)}".lower()
                    if strategy.lower() not in blob and s_up.lower().replace("_", " ") not in blob:
                        strategy_soft_miss = True
            if min_score is not None and score.opportunity < min_score:
                continue
            if max_risk is not None and score.risk > max_risk:
                continue
            if min_confidence is not None and score.confidence < min_confidence:
                continue
            if q:
                blob = f"{listing.title} {parcel.county} {parcel.state} {parcel.apn} {listing.description or ''}".lower()
                tokens = [t for t in q.lower().replace(",", " ").split() if len(t) > 1]
                if tokens and not any(t in blob for t in tokens):
                    continue

            fit = personalized_score(
                score.opportunity,
                profile,
                ask,
                parcel.acreage,
                score.best_strategy.value if score.best_strategy else None,
                score.risk,
            )
            if strategy_soft_miss:
                fit = max(0, fit - 12)
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

            auction_path = None
            if enrichment and enrichment.comps:
                auction_path = (enrichment.comps.normalized or {}).get("auction_path")
            if not isinstance(auction_path, dict) and ask and listing.provider_id in (
                "public_tax_sale",
                "public_surplus",
            ):
                from landsignal.services.auction import expected_auction_clearing

                auction_path = expected_auction_clearing(
                    opening_bid=ask,
                    model_value=score.estimated_value_usd,
                    acres=parcel.acreage,
                    provider_id=listing.provider_id,
                    state=parcel.state,
                )
            pd = price_display(
                ask,
                listing.provider_id,
                auction_path if isinstance(auction_path, dict) else None,
                score.estimated_value_usd,
            )
            vd = value_display(
                score.estimated_value_usd,
                (enrichment.comps.knowledge_state.value if enrichment and enrichment.comps else "ESTIMATED"),
            )
            ppa = listing.price_per_acre_usd
            if ppa is None and ask and parcel.acreage:
                ppa = ask / parcel.acreage
            source = sourcing_card(
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
            links = source.get("links") or build_action_links(
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
            if strategy_soft_miss:
                reasons = [
                    "Strategy is a soft match — ranked lower, not hidden, so you still see nearby options.",
                    *reasons,
                ][:5]
            if isinstance(auction_path, dict) and auction_path.get("expected_settle_usd"):
                # Prefer the plain buy-price bullet from match_reasons
                if not any("likely auction finish" in r.lower() or "likely finish" in r.lower() for r in reasons):
                    reasons = [
                        (
                            f"Starts at ${auction_path['opening_bid_usd']:,.0f}; auctions like this "
                            f"usually finish near ${auction_path['expected_settle_usd']:,.0f} "
                            f"(about {auction_path.get('bid_inflation_mult_base', 0):.1f}× the start)"
                        ),
                        *reasons,
                    ][:5]
            acres = parcel.acreage
            acres_display = f"{acres:,.2f} acres" if acres is not None else "Acreage not published"
            settle_disc = None
            if isinstance(auction_path, dict):
                settle_disc = auction_path.get("settle_discount_pct")
            if settle_disc is not None:
                discount_display = (
                    f"Likely finish {settle_disc:+.1f}% vs our value "
                    f"(start bid looked {auction_path.get('opener_discount_pct', 0):+.0f}%)"
                )
            elif score.asking_discount_pct is not None:
                discount_display = f"{score.asking_discount_pct:+.1f}% vs our value"
            else:
                discount_display = "No public price to compare"
            risk_label = (
                "Lower risk on the map checks"
                if score.risk < 30
                else "Medium risk — dig into flood/wetlands"
                if score.risk < 55
                else "Higher risk — budget more homework"
            )
            conf_label = (
                "File looks fairly complete"
                if score.confidence >= 70
                else "Some data still missing"
                if score.confidence >= 45
                else "Thin file — double-check before bidding"
            )
            thesis, conviction = build_return_thesis(
                score=score,
                listing=listing,
                auction_path=auction_path if isinstance(auction_path, dict) else None,
            )
            from landsignal.services.market_trajectory import build_market_trajectory

            traj = ((enrichment.narratives or {}).get("market_trajectory") if enrichment else None) or None
            if not isinstance(traj, dict) or not traj.get("sparkline"):
                traj = build_market_trajectory(
                    parcel=parcel,
                    listing=listing,
                    score=score,
                    enrichment=enrichment,
                )
            summary = thesis or (
                f"{_strategy_label(score.best_strategy)} · "
                f"Opportunity {score.opportunity:.0f} · Risk {score.risk:.0f} · {pd['display']}"
            )
            headline_disc = settle_disc if settle_disc is not None else score.asking_discount_pct
            if headline_disc is not None and headline_disc < -8:
                headline = (
                    f"Likely finish ~{abs(headline_disc):.0f}% under our value"
                    if isinstance(auction_path, dict)
                    else f"About {abs(headline_disc):.0f}% under our value"
                )
            elif isinstance(auction_path, dict):
                headline = (
                    f"Starts ${auction_path.get('opening_bid_usd', 0):,.0f} → "
                    f"likely ~${auction_path.get('expected_settle_usd', 0):,.0f}"
                )
            else:
                headline = f"{conviction or 'WATCH'} interest · opportunity score {score.opportunity:.0f}/100"

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
                    rating_breakdown=rating_breakdown(score, parcel=parcel, listing=listing),
                    links=annotated,
                    latitude=parcel.latitude,
                    longitude=parcel.longitude,
                    provider_id=listing.provider_id,
                    provider_label=PROVIDER_LABELS.get(listing.provider_id, listing.provider_id or "Public source"),
                    headline_metric=headline,
                    risk_label=risk_label,
                    confidence_label=conf_label,
                    source_name=source.get("source_name"),
                    contact_office=source.get("office"),
                    contact_phone=source.get("phone"),
                    contact_website=source.get("website"),
                    how_to_buy=source.get("how_to_buy"),
                    return_thesis=thesis,
                    conviction=conviction,
                    trajectory_regime=traj.get("regime"),
                    trajectory_label=traj.get("regime_label"),
                    trajectory_cagr_5y=traj.get("cagr_5y_display"),
                    trajectory_sparkline=list(traj.get("sparkline") or [])[-8:],
                )
            )
        return out

    rows = await build_rows(apply_region=True, apply_strict_channel=True)
    # Soft broaden within the same state when region is too tight
    if broaden and not rows:
        rows = await build_rows(apply_region=False, apply_strict_channel=True)
        for r in rows:
            r.match_reasons = [
                "Loosened city/region a bit so you still get real matches for your other filters.",
                *r.match_reasons,
            ][:5]
    # Last resort: if a price band wiped everything, show unpriced + near-band in-state/all
    if broaden and not rows and (min_price is not None or max_price is not None):
        saved_min, saved_max = min_price, max_price
        min_price = None
        max_price = None
        rows = await build_rows(apply_region=False, apply_strict_channel=False)
        min_price, max_price = saved_min, saved_max
        for r in rows:
            r.match_reasons = [
                "Your exact price band had no hits — showing the closest live opportunities instead.",
                *r.match_reasons,
            ][:5]

    ranked = _sort_rows(rows, sort)
    # Cap payload so the UI stays responsive; full inventory_count lives on /search/meta
    return ranked[: max(1, min(limit, 500))]


@router.post("/rescore")
async def rescore(limit: int = 8000) -> dict[str, Any]:
    """Re-score parcels still on an older algorithm version (fast / cached enrichment)."""
    from landsignal.services.rescore import rescore_stale

    store = get_store(get_settings().demo_seed)
    return await rescore_stale(store, limit=limit)


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
    from landsignal.services.presentation import price_display, rating_breakdown, sourcing_card

    store = get_store(get_settings().demo_seed)
    parcel = store.parcels.get(parcel_id)
    if not parcel:
        raise HTTPException(404, "Parcel not found")
    # Always run full (non-fast) enrichment on detail so soils/flood are real when opened
    score = await analyze_parcel(store, parcel_id, fast=False)
    listing = store.listing_for_parcel(parcel_id)
    enrichment = store.enrichments.get(parcel_id)
    source = sourcing_card(
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
    links = source.get("links") or []
    # Every contact/posting link must stay clickable. Agency sites often block bots —
    # never gray out primary/office/lookup or surface http_XXX error codes to the UI.
    fallback_site = source.get("website") or "https://www.google.com/search?q=county+treasurer+tax+sale"
    annotated = []
    for l in links:
        url = str(l.get("url") or "")
        kind = l.get("kind")
        if not url or (kind == "primary" and not url.startswith("http")):
            url = str(fallback_site)
        annotated.append(
            {
                **l,
                "url": url,
                "available": True,
                "availability_reason": "ok",
                "status_code": None,
            }
        )
    if not any(l.get("kind") == "primary" for l in annotated):
        annotated.insert(
            0,
            {
                "label": "Open posting",
                "url": str(fallback_site),
                "kind": "primary",
                "available": True,
                "availability_reason": "ok",
                "status_code": None,
            },
        )
    annotated.sort(key=lambda l: 0 if l.get("kind") == "primary" else 1)

    dd_raw = store.dd_items.get(parcel_id, [])
    dd_guided = human_dd_items(
        [d if isinstance(d, dict) else d.model_dump() for d in dd_raw],
        score,
        enrichment,
    )
    land_readouts = {
        "soil": human_soil(
            enrichment.soil if enrichment else None,
            apn=parcel.apn,
            county=parcel.county,
            state=parcel.state,
        ),
        "flood": human_flood(enrichment.flood if enrichment else None, apn=parcel.apn),
        "wetlands": human_wetlands(enrichment.wetlands if enrichment else None),
        "transmission": human_transmission(enrichment.infrastructure if enrichment else None),
    }
    scenarios_human = []
    case_labels = {
        "BASE": "Base case (typical rents)",
        "BEAR": "Cautious case (low rents / slow appreciation)",
        "BULL": "Optimistic case (strong rents / faster appreciation)",
        "DOWNSIDE": "Cautious case",
        "UPSIDE": "Optimistic case",
        "STRESS": "Stress case",
    }
    for s in (enrichment.scenarios if enrichment else []) or []:
        case_key = str(s.get("case_type") or "Scenario")
        case_name = case_labels.get(case_key, case_key)
        if s.get("irr") is not None:
            plain = (
                f"{case_name}: about {float(s['irr']) * 100:.1f}% per year on a simple farm-rent screen "
                f"if cash rents and a later sale hold for this parcel."
            )
        else:
            plain = "This case needs more crop/rent numbers before a yearly return can be shown."
        scenarios_human.append(
            {
                **s,
                "case_label": case_name,
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

    from landsignal.services.briefing import build_intelligence_brief

    auction_path = None
    if enrichment and enrichment.comps:
        auction_path = (enrichment.comps.normalized or {}).get("auction_path")
    if not isinstance(auction_path, dict):
        auction_path = None

    ask = listing.asking_price_usd if listing else None
    if ask is not None and ask <= 0:
        ask = None
    price = price_display(
        ask,
        listing.provider_id if listing else None,
        auction_path,
        score.estimated_value_usd if score else None,
    )
    brief = build_intelligence_brief(
        parcel=parcel,
        listing=listing,
        score=score,
        enrichment=enrichment,
        price=price,
        land_readouts=land_readouts,
        scenarios_human=scenarios_human,
        dd_guided=dd_guided,
    )
    user = UUID("00000000-0000-4000-8000-000000000002")
    watched = parcel_id in store.watchlists.get(user, set())

    # XY clearing chart: price (x) vs remaining buyer competition (y)
    model_v = float(score.estimated_value_usd or 0) if score else 0.0
    opener_v = float((auction_path or {}).get("opening_bid_usd") or ask or 0)
    settle_v = float((auction_path or {}).get("expected_settle_usd") or 0)
    settle_lo = float((auction_path or {}).get("settle_low_usd") or settle_v)
    settle_hi = float((auction_path or {}).get("settle_high_usd") or settle_v)
    if auction_path and opener_v > 0 and model_v > 0:
            chart_points = [
            {"x": opener_v, "y": 100, "label": "Start", "note": "Published starting bid — almost every bidder is still in"},
            {"x": settle_lo, "y": 72, "label": "Soft day", "note": "Quiet auction — finishes on the low side"},
            {"x": settle_v, "y": 48, "label": "Likely finish", "note": "Typical contested finish for this kind of sale"},
            {"x": settle_hi, "y": 28, "label": "Hot day", "note": "Busy auction — price climbs higher"},
            {"x": model_v, "y": 12, "label": "Our value", "note": "What we think the land is worth — few tax-sale buyers pay full retail"},
        ]
    elif model_v > 0:
        chart_points = [
            {"x": model_v * 0.55, "y": 80, "label": "Deep discount", "note": "Where distressed / process buyers often land"},
            {"x": model_v * 0.75, "y": 45, "label": "Negotiated", "note": "Common brokered or surplus outcome"},
            {"x": model_v, "y": 18, "label": "Our value", "note": "Our estimated full value for this land"},
        ]
    else:
        chart_points = []

    unsold = ((enrichment.narratives or {}).get("why_unsold") if enrichment else None) or {}
    hypotheses = (unsold.get("hypotheses") if isinstance(unsold, dict) else None) or []
    cockpit = {
        "title": "Who’s still bidding at each price",
        "subtitle": f"{parcel.apn or 'Parcel'} · {parcel.county}, {parcel.state}",
        "auction_path": auction_path,
        "price": price,
        "model_value": score.estimated_value_usd if score else None,
        "chart": {
            "x_label": "Price ($)",
            "y_label": "Buyers still competing (%)",
            "points": chart_points,
        },
        "opportunity": score.opportunity if score else None,
        "risk": score.risk if score else None,
        "confidence": score.confidence if score else None,
        "deal_readiness": score.deal_readiness if score else None,
        "best_strategy": score.best_strategy.value if score and score.best_strategy else None,
        "constraints": {
            "flood": land_readouts.get("flood"),
            "wetlands": land_readouts.get("wetlands"),
            "soil": land_readouts.get("soil"),
            "transmission": land_readouts.get("transmission"),
        },
        "buyer_filters": [
            {
                "label": h.get("reason"),
                "psychology": h.get("psychology"),
                "likelihood": h.get("likelihood"),
                "evidence": h.get("evidence") or [],
            }
            for h in hypotheses[:5]
        ],
        "pin": {
            "lat": parcel.latitude,
            "lon": parcel.longitude,
            "apn": parcel.apn,
            "acres": parcel.acreage,
            "county": parcel.county,
            "state": parcel.state,
        },
        "source": source,
    }

    from landsignal.services.market_trajectory import build_market_trajectory

    market_trajectory = build_market_trajectory(
        parcel=parcel,
        listing=listing,
        score=score,
        enrichment=enrichment,
    )
    if enrichment is not None:
        enrichment.narratives = {
            **(enrichment.narratives or {}),
            "market_trajectory": market_trajectory,
        }
        store.enrichments[parcel_id] = enrichment

    return {
        "parcel": parcel,
        "listing": listing,
        "score": score,
        "enrichment": enrichment,
        "due_diligence": dd_raw,
        "due_diligence_guided": dd_guided,
        "land_readouts": land_readouts,
        "scenarios_human": scenarios_human,
        "brief": brief,
        "links": annotated,
        "price": price,
        "auction_path": auction_path,
        "sourcing": source,
        "cockpit": cockpit,
        "market_trajectory": market_trajectory,
        "rating_breakdown": rating_breakdown(score, parcel=parcel, listing=listing) if score else [],
        "score_explained": brief.get("score_story")
        or {
            "landsignal": "Overall opportunity score from 0–100 after weighing price, land quality, future uses, and risk.",
            "risk": "Higher means more things that can go wrong on the map checks (flood, wetlands, missing data).",
            "confidence": "How complete the file is. Thin files score lower on purpose — this is not a quality grade.",
        },
        "watched": watched,
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
    if store.latest_score(parcel_id) is None:
        await analyze_parcel(store, parcel_id, fast=True)
    user = UUID("00000000-0000-4000-8000-000000000002")
    store.watchlists.setdefault(user, set()).add(parcel_id)
    score = store.latest_score(parcel_id)
    listing = store.listing_for_parcel(parcel_id)
    snap = {
        "opportunity": score.opportunity if score else None,
        "risk": score.risk if score else None,
        "confidence": score.confidence if score else None,
        "ask": listing.asking_price_usd if listing else None,
        "status": listing.status if listing else None,
        "watched_at": datetime.now(timezone.utc).isoformat(),
    }
    store.watch_snapshots[parcel_id] = snap
    email = (store.investor_profile.get("notify_email") or "").strip()
    email_on = bool(store.investor_profile.get("watchlist_email_updates"))
    return {
        "watched": True,
        "parcel_id": parcel_id,
        "snapshot": snap,
        "email_updates": bool(email and email_on),
        "notify_email": email or None,
        "note": (
            f"Watching. Metric changes will notify {email}."
            if email and email_on
            else "Watching in-app. Add your email under My criteria to sync updates."
        ),
    }


@router.delete("/parcels/{parcel_id}/watch")
async def unwatch(parcel_id: UUID) -> dict[str, Any]:
    store = get_store(get_settings().demo_seed)
    user = UUID("00000000-0000-4000-8000-000000000002")
    store.watchlists.setdefault(user, set()).discard(parcel_id)
    store.watch_snapshots.pop(parcel_id, None)
    return {"watched": False, "parcel_id": parcel_id}


@router.get("/watchlist")
async def watchlist() -> dict[str, Any]:
    store = get_store(get_settings().demo_seed)
    user = UUID("00000000-0000-4000-8000-000000000002")
    items = []
    for pid in sorted(store.watchlists.get(user, set()), key=str):
        parcel = store.parcels.get(pid)
        listing = store.listing_for_parcel(pid)
        score = store.latest_score(pid)
        prev = store.watch_snapshots.get(pid) or {}
        cur = {
            "opportunity": score.opportunity if score else None,
            "risk": score.risk if score else None,
            "confidence": score.confidence if score else None,
            "ask": listing.asking_price_usd if listing else None,
            "status": listing.status if listing else None,
        }
        changes = []
        for key in ("opportunity", "risk", "confidence", "ask", "status"):
            if prev.get(key) != cur.get(key) and prev.get(key) is not None:
                changes.append({"metric": key, "from": prev.get(key), "to": cur.get(key)})
        # Keep snapshot current so the next refresh only shows new moves
        store.watch_snapshots[pid] = {**cur, "watched_at": prev.get("watched_at")}
        items.append(
            {
                "parcel_id": pid,
                "title": (listing.title if listing else None) or (parcel.apn if parcel else str(pid)),
                "location": f"{getattr(parcel, 'county', None) or '—'}, {getattr(parcel, 'state', None) or '—'}",
                "current": cur,
                "baseline": prev,
                "changes": changes,
            }
        )
    return {
        "items": items,
        "notify_email": store.investor_profile.get("notify_email") or "",
        "watchlist_email_updates": bool(store.investor_profile.get("watchlist_email_updates")),
    }
