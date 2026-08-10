from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile

from landsignal.models import (
    AlertRuleCreate,
    AlertRuleRecord,
    InvestorProfileUpdate,
    LandAlertNotify,
    LandAlertProfileUpsert,
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
from landsignal.services.voice import display_title
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
    from landsignal.services.land_alerts import match_parcel

    store = get_store(get_settings().demo_seed)
    settings = get_settings()
    parcel, listing = store.upsert_manual(body.model_dump())
    score = await analyze_parcel(store, parcel.id)
    alerts = evaluate_rules(store, score, settings)
    land_matches = match_parcel(
        store, parcel.id, origin="new_discovery", update_kind="new_listing", settings=settings
    )
    return {
        "parcel_id": parcel.id,
        "listing_id": listing.id,
        "score_id": score.id,
        "alerts_triggered": len(alerts),
        "land_alert_matches": len(land_matches),
    }


@router.post("/ingest/csv")
async def ingest_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    from landsignal.services.land_alerts import match_parcel

    store = get_store(get_settings().demo_seed)
    settings = get_settings()
    text = (await file.read()).decode("utf-8")
    rows = store.import_csv(text)
    results = []
    for parcel, listing in rows:
        score = await analyze_parcel(store, parcel.id)
        evaluate_rules(store, score, settings)
        match_parcel(store, parcel.id, origin="new_discovery", update_kind="new_listing", settings=settings)
        results.append({"parcel_id": parcel.id, "listing_id": listing.id, "score_id": score.id})
    return {"imported": len(results), "results": results}


@router.post("/parcels/{parcel_id}/analyze")
async def reanalyze(parcel_id: UUID) -> dict[str, Any]:
    from landsignal.services.land_alerts import match_parcel

    store = get_store(get_settings().demo_seed)
    settings = get_settings()
    if parcel_id not in store.parcels:
        raise HTTPException(404, "Parcel not found")
    score = await analyze_parcel(store, parcel_id)
    alerts = evaluate_rules(store, score, settings)
    match_parcel(store, parcel_id, origin="price_update", update_kind="new_data", settings=settings)
    return {"score": score, "alerts_triggered": len(alerts)}


PROVIDER_LABELS = {
    "blm_lpad": "Federal BLM land",
    "public_tax_sale": "County tax-delinquent sale",
    "public_surplus": "Public surplus land",
    "public_vacant_gis": "Vacant land on the public map",
    "manual": "Manual entry",
    "csv": "CSV import",
}

# External-id prefixes that are vacant CAD/cadastral screens, not confirmed tax sales.
_VACANT_GIS_PREFIXES = ("nash:", "bexar:", "dallas:", "kingwa:")


def _maybe_retag_vacant_gis(listing) -> None:
    """Correct in-memory mislabels so radar isn’t flooded by fake tax-sale edges."""
    if not listing:
        return
    ext = str(getattr(listing, "external_id", None) or "")
    desc = str(getattr(listing, "description", None) or "").lower()
    if getattr(listing, "provider_id", None) != "public_tax_sale":
        return
    if ext.startswith(_VACANT_GIS_PREFIXES) or "cadastral gis" in desc or "public cad gis" in desc:
        listing.provider_id = "public_vacant_gis"


def _provider_label(provider_id: str | None, county: str | None = None) -> str:
    """Human channel label — tax sale is only for public_tax_sale rows."""
    pid = provider_id or ""
    if pid == "public_tax_sale":
        co = (county or "").strip()
        return f"{co} County tax sale" if co else "County tax-delinquent sale"
    if pid == "blm_lpad":
        return "Federal BLM land"
    if pid == "public_surplus":
        co = (county or "").strip()
        return f"{co} surplus land" if co else "Public surplus land"
    if pid == "public_vacant_gis":
        co = (county or "").strip()
        return f"{co} vacant map screen" if co else "Vacant land on the public map"
    return PROVIDER_LABELS.get(pid, pid or "Public source")


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


def _hold_priority_boost(hold_years: int | None, strategy: str | None) -> float:
    """Soft ranking nudge only — never excludes a parcel from the result set."""
    if hold_years is None or not strategy:
        return 0.0
    s = strategy.upper()
    boost = 0.0
    if hold_years <= 5 and s in ("ENERGY", "FARMLAND", "RECREATIONAL"):
        boost += 4.0
    elif hold_years <= 15 and s in ("FARMLAND", "ENERGY", "RECREATIONAL"):
        boost += 2.0
    if hold_years >= 25 and s in ("LAND_BANK", "DEVELOPMENT", "TIMBER"):
        boost += 5.0
    elif hold_years >= 10 and s in ("LAND_BANK", "DEVELOPMENT", "TIMBER"):
        boost += 3.0
    return boost


def _apply_hold_priority(rows: list[RadarRow], hold_years: int | None) -> list[RadarRow]:
    """Re-rank within an already-selected result set using hold as one priority factor."""
    if hold_years is None or not rows:
        return rows
    for r in rows:
        strat = r.best_strategy.value if r.best_strategy else None
        boost = _hold_priority_boost(hold_years, strat)
        if boost:
            base = r.fit_score if r.fit_score is not None else r.opportunity
            nudged = max(0.0, min(100.0, float(base) + boost))
            r.fit_score = nudged
            r.personalized_opportunity = nudged
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
    # Hold period is ranking-only (never a hard filter / never shrinks the match set).
    if max_price is not None:
        profile["max_price_usd"] = max_price
    if min_acres is not None:
        profile["min_acres"] = min_acres
    if strategy and strategy.upper() not in ("ANY", "CUSTOM", ""):
        profile["preferred_strategies"] = [strategy.upper()]

    mode = (unpriced_mode or ("include" if include_unpriced else "priced")).lower()
    channel = (market_channel or "Any").strip()

    from dataclasses import dataclass

    @dataclass
    class _Cand:
        parcel_id: UUID
        listing_id: UUID
        fit: float
        opportunity: float
        risk: float
        confidence: float
        ask: float | None
        acres: float | None
        discount_pct: float | None
        strategy_soft_miss: bool
        best_strategy: Any

    def _sort_cands(cands: list[_Cand], sort_key: str | None) -> list[_Cand]:
        key = (sort_key or "fit_desc").lower()

        def discount_key(r: _Cand) -> float:
            return r.discount_pct if r.discount_pct is not None else 999.0

        if key == "score_desc":
            cands.sort(key=lambda r: (r.opportunity, r.fit), reverse=True)
        elif key == "risk_asc":
            cands.sort(key=lambda r: (r.risk, -r.fit))
        elif key == "confidence_desc":
            cands.sort(key=lambda r: (r.confidence, r.opportunity), reverse=True)
        elif key == "price_asc":
            cands.sort(key=lambda r: (r.ask is None, r.ask if r.ask is not None else 0))
        elif key == "price_desc":
            cands.sort(key=lambda r: (r.ask is None, -(r.ask or 0)))
        elif key == "acres_desc":
            cands.sort(key=lambda r: (r.acres is None, -(r.acres or 0)))
        elif key == "discount_asc":
            cands.sort(key=discount_key)
        else:
            cands.sort(key=lambda r: (r.fit, r.opportunity), reverse=True)
        return cands

    def collect_cands(*, apply_region: bool, apply_strict_channel: bool) -> list[_Cand]:
        out: list[_Cand] = []
        for parcel in store.parcels.values():
            score = store.latest_score(parcel.id)
            listing = store.listing_for_parcel(parcel.id)
            if not score or not listing or parcel.is_demo:
                continue
            _maybe_retag_vacant_gis(listing)

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
            out.append(
                _Cand(
                    parcel_id=parcel.id,
                    listing_id=listing.id,
                    fit=float(fit),
                    opportunity=float(score.opportunity),
                    risk=float(score.risk),
                    confidence=float(score.confidence),
                    ask=ask,
                    acres=parcel.acreage,
                    discount_pct=score.asking_discount_pct,
                    strategy_soft_miss=strategy_soft_miss,
                    best_strategy=score.best_strategy,
                )
            )
        return out

    def fat_row(cand: _Cand, *, broaden_reason: str | None = None) -> RadarRow | None:
        parcel = store.parcels.get(cand.parcel_id)
        listing = store.listing_for_parcel(cand.parcel_id)
        score = store.latest_score(cand.parcel_id)
        if not parcel or not listing or not score:
            return None
        strategy_soft_miss = cand.strategy_soft_miss
        fit = cand.fit
        ask = cand.ask
        enrichment = store.enrichments.get(parcel.id)

        auction_path = None
        if enrichment and enrichment.comps and listing.provider_id != "public_vacant_gis":
            auction_path = (enrichment.comps.normalized or {}).get("auction_path")
        if listing.provider_id == "public_vacant_gis":
            auction_path = None
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
        comps_n = {}
        if enrichment and enrichment.comps:
            comps_n = enrichment.comps.normalized or enrichment.comps.value or {}
        pd = price_display(
            ask,
            listing.provider_id,
            auction_path if isinstance(auction_path, dict) else None,
            score.estimated_value_usd,
            state=parcel.state,
            county=parcel.county,
            acres=parcel.acreage,
            apn=parcel.apn,
            comps_normalized=comps_n if isinstance(comps_n, dict) else {},
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
        if broaden_reason:
            reasons = [broaden_reason, *reasons][:5]
        if isinstance(auction_path, dict) and auction_path.get("expected_settle_usd"):
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

        discount_help: str | None = None
        gap_pct = settle_disc if settle_disc is not None else score.asking_discount_pct
        our_val = score.estimated_value_usd
        compare_price = None
        compare_label = "public price"
        is_auction_settle = bool(
            isinstance(auction_path, dict) and auction_path.get("expected_settle_usd")
        )
        if is_auction_settle:
            compare_price = float(auction_path["expected_settle_usd"])
            compare_label = "likely auction finish"
        elif ask is not None and ask > 0:
            compare_price = float(ask)
            compare_label = "listed / starting price"
        if gap_pct is not None and our_val is not None and our_val > 0:
            pct_abs = abs(float(gap_pct))
            acres_bit = f"{acres:,.2f}-acre " if acres is not None else ""
            place_bit = f" in {parcel.county or 'this county'}, {parcel.state or 'US'}"
            channel_bit = _provider_label(listing.provider_id, parcel.county)
            our_s = f"${our_val:,.0f}"
            if float(gap_pct) < -8 and listing.provider_id != "public_vacant_gis":
                lead = (
                    f"“Likely finish ~{pct_abs:.0f}% under our value” means "
                    if is_auction_settle
                    else f"“About {pct_abs:.0f}% under our value” means "
                )
            elif is_auction_settle:
                lead = f"“Likely finish {float(gap_pct):+.1f}% vs our value” means "
            elif score.asking_discount_pct is not None:
                lead = f"“{float(gap_pct):+.1f}% vs our value” means "
            else:
                lead = "This price gap means "
            if compare_price is not None:
                cmp_s = f"${compare_price:,.0f}"
                if float(gap_pct) < -3:
                    discount_help = (
                        f"{lead}our desktop value for this {acres_bit}{channel_bit} tract{place_bit} "
                        f"is about {our_s}, while the {compare_label} we see is about {cmp_s} — "
                        f"roughly {pct_abs:.0f}% lower. That gap is a buy-edge screen from maps, "
                        f"comps, and channel norms — not a promise you’ll close at that number. "
                        f"Auctions and negotiations often move the price; check flood, access, "
                        f"and title before you treat the gap as locked-in profit."
                    )
                elif float(gap_pct) > 3:
                    discount_help = (
                        f"{lead}our desktop value for this {acres_bit}tract{place_bit} is about {our_s}. "
                        f"The {compare_label} ({cmp_s}) sits roughly {pct_abs:.0f}% above that mark — "
                        f"so the screen does not show a clear under-value buy yet. Dig into why the "
                        f"ask is high (improvements, location, thin comps) before chasing it."
                    )
                else:
                    discount_help = (
                        f"{lead}our desktop value (~{our_s}) and the {compare_label} "
                        f"(~{cmp_s}) are close for this {acres_bit}tract{place_bit}. "
                        f"You’re not looking at a big under-value gap — underwrite the site and "
                        f"process instead of leaning on discount math."
                    )
            elif float(gap_pct) < -3:
                discount_help = (
                    f"{lead}we underwrite a process entry on this {acres_bit}{channel_bit} "
                    f"file{place_bit} about {pct_abs:.0f}% under our desktop mark of {our_s}. "
                    f"There’s no firm public ask — the gap is an optionality screen, not a "
                    f"listed sale price. Confirm the real buy path with the office before you spend."
                )
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
            enrichment=enrichment,
        )
        from landsignal.services.market_trajectory import build_market_trajectory

        traj = ((enrichment.narratives or {}).get("market_trajectory") if enrichment else None) or None
        if not isinstance(traj, dict) or not traj.get("sparkline") or not traj.get("hitches"):
            traj = build_market_trajectory(
                parcel=parcel,
                listing=listing,
                score=score,
                enrichment=enrichment,
            )
            if enrichment is not None:
                enrichment.narratives = {
                    **(enrichment.narratives or {}),
                    "market_trajectory": traj,
                }
        summary = thesis or (
            f"{_strategy_label(score.best_strategy)} · "
            f"Opportunity {score.opportunity:.0f} · Risk {score.risk:.0f} · {pd['display']}"
        )
        headline_disc = settle_disc if settle_disc is not None else score.asking_discount_pct
        if listing.provider_id == "public_vacant_gis":
            headline_disc = score.asking_discount_pct
        if listing.provider_id == "public_vacant_gis":
            acres_h = f"{acres:,.0f} ac" if acres is not None else "tract"
            headline = (
                f"Vacant map screen · {acres_h} · confirm owner path"
                if score.opportunity < 62
                else f"Worth a look · {acres_h} vacant map screen — verify it’s buyable"
            )
        elif headline_disc is not None and headline_disc < -8:
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

        scout_bits: list[str] = []

        def _nv(prov):
            if not prov:
                return {}
            return prov.normalized or prov.value or {}

        sn = fn = wn = an = gn = cn = {}
        if enrichment:
            sn = _nv(enrichment.soil)
            fn = _nv(enrichment.flood)
            wn = _nv(enrichment.wetlands)
            an = _nv(enrichment.access)
            gn = _nv(enrichment.growth)
            cn = _nv(enrichment.comps)
        try:
            prime_v = float(sn["prime_farmland_pct"]) if sn.get("prime_farmland_pct") is not None else None
        except Exception:
            prime_v = None
        try:
            flood_v = float(fn["flood_zone_pct"]) if fn.get("flood_zone_pct") is not None else None
        except Exception:
            flood_v = None
        try:
            wet_v = float(wn["wetland_pct"]) if wn.get("wetland_pct") is not None else None
        except Exception:
            wet_v = None
        try:
            access_v = (
                float(an["legal_access_confidence"]) if an.get("legal_access_confidence") is not None else None
            )
        except Exception:
            access_v = None
        try:
            growth_v = float(gn["path_of_growth_score"]) if gn.get("path_of_growth_score") is not None else None
        except Exception:
            growth_v = None
        if growth_v is None:
            try:
                growth_v = (
                    float(cn["path_of_growth_score"]) if cn.get("path_of_growth_score") is not None else None
                )
            except Exception:
                growth_v = None

        edge_pct = settle_disc if settle_disc is not None else score.asking_discount_pct
        if listing.provider_id == "public_vacant_gis":
            edge_pct = None
        elif edge_pct is not None and edge_pct <= -20:
            scout_bits.append(f"Buy edge ~{abs(edge_pct):.0f}% under our mark")
        elif edge_pct is not None and edge_pct <= -8:
            scout_bits.append(f"Modest edge ~{abs(edge_pct):.0f}% under our mark")
        if listing.provider_id == "public_tax_sale":
            scout_bits.append("tax-sale channel — process, not MLS")
        elif listing.provider_id == "blm_lpad":
            scout_bits.append("BLM disposal process")
        elif listing.provider_id == "public_surplus":
            scout_bits.append("public surplus inventory")
        elif listing.provider_id == "public_vacant_gis":
            scout_bits.append("vacant map screen — confirm owner path")
        if prime_v is not None and prime_v >= 45:
            scout_bits.append(f"~{prime_v:.0f}% prime soil")
        if flood_v is not None and flood_v >= 25:
            scout_bits.append(f"flood ~{flood_v:.0f}% — price that in")
        elif wet_v is not None and wet_v >= 20:
            scout_bits.append(f"wetlands ~{wet_v:.0f}% trim usable acres")
        if access_v is not None and access_v < 45:
            scout_bits.append("access not clear yet")
        elif access_v is not None and access_v >= 75 and len(scout_bits) < 2:
            scout_bits.append("access screen looks workable")
        if growth_v is not None and growth_v >= 65 and len(scout_bits) < 3:
            scout_bits.append(f"growth support ~{growth_v:.0f}/100")
        if score.risk is not None and score.risk >= 55 and len(scout_bits) < 3:
            scout_bits.append("higher map risk — dig in")
        if not scout_bits and score.best_strategy:
            scout_bits.append(f"Best use screen: {_strategy_label(score.best_strategy)}")
        if not scout_bits:
            scout_bits.append(
                f"{_provider_label(listing.provider_id, parcel.county)} in {parcel.county or 'this county'}"
            )
        scout_note = " · ".join(scout_bits[:3])

        return RadarRow(
            parcel_id=parcel.id,
            listing_id=listing.id,
            signal=score.signal,
            property_name=display_title(parcel, listing),
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
            discount_help=discount_help,
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
            provider_label=_provider_label(listing.provider_id, parcel.county),
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
            scout_note=scout_note,
            trajectory_regime=traj.get("regime"),
            trajectory_label=traj.get("regime_label"),
            trajectory_cagr_5y=traj.get("cagr_5y_display"),
            trajectory_sparkline=list(traj.get("sparkline") or [])[-8:],
        )

    # Phase 1: cheap filter + fit across full inventory (same match set as before)
    cands = collect_cands(apply_region=True, apply_strict_channel=True)
    broaden_reason: str | None = None
    if broaden and not cands:
        cands = collect_cands(apply_region=False, apply_strict_channel=True)
        broaden_reason = "Loosened city/region a bit so you still get real matches for your other filters."
    if broaden and not cands and (min_price is not None or max_price is not None):
        saved_min, saved_max = min_price, max_price
        min_price = None
        max_price = None
        cands = collect_cands(apply_region=False, apply_strict_channel=False)
        min_price, max_price = saved_min, saved_max
        broaden_reason = "Your exact price band had no hits — showing the closest live opportunities instead."

    ranked = _sort_cands(cands, sort)
    capped = ranked[: max(1, min(limit, 500))] if ranked else []
    if hold_years is not None and capped:
        for c in capped:
            strat = c.best_strategy.value if c.best_strategy else None
            boost = _hold_priority_boost(hold_years, strat)
            if boost:
                c.fit = max(0.0, min(100.0, float(c.fit) + boost))
        if (sort or "fit_desc").lower() in ("fit_desc", ""):
            capped = _sort_cands(capped, "fit_desc")

    # Phase 2: full presentation cards only for the capped result set
    rows: list[RadarRow] = []
    for c in capped:
        row = fat_row(c, broaden_reason=broaden_reason)
        if row is not None:
            rows.append(row)
    return rows


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
        human_access,
        human_dd_items,
        human_flood,
        human_growth,
        human_resale,
        human_slope,
        human_soil,
        human_transmission,
        human_wetlands,
    )
    from landsignal.services.presentation import price_display, rating_breakdown, sourcing_card

    store = get_store(get_settings().demo_seed)
    parcel = store.parcels.get(parcel_id)
    if not parcel:
        raise HTTPException(404, "Parcel not found")
    # Opening a parcel marks Land Alert matches as viewed (persists across sessions)
    try:
        from landsignal.services.land_alerts import DEMO_USER_ID, mark_match_viewed

        mark_match_viewed(store, DEMO_USER_ID, parcel_id)
    except Exception:  # noqa: BLE001
        pass

    from landsignal.models import KnowledgeState
    from landsignal.scoring.engine import ALGORITHM_VERSION

    def _layer_usable(prov) -> bool:
        if not prov:
            return False
        ks = prov.knowledge_state
        if ks == KnowledgeState.UNKNOWN or ks == KnowledgeState.TEMPORARILY_UNAVAILABLE:
            return False
        label = ks.value if hasattr(ks, "value") else str(ks or "")
        return label not in ("UNKNOWN", "TEMPORARILY_UNAVAILABLE", "")

    enrichment = store.enrichments.get(parcel_id)
    existing_score = store.latest_score(parcel_id)
    # Reuse cached live layers + current-algorithm score when already complete.
    # Missing layers still trigger analyze_parcel (same accuracy as before).
    already_complete = bool(
        enrichment
        and _layer_usable(enrichment.soil)
        and _layer_usable(enrichment.flood)
        and existing_score
        and getattr(existing_score, "algorithm_version", None) == ALGORITHM_VERSION
    )
    if already_complete:
        score = existing_score
    else:
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
    # Keep every CTA clickable — but rewrite dead agency URLs to a working fallback
    # so "Official page" never opens a 404 / no-results page.
    from landsignal.services.links import validate_url
    from urllib.parse import quote_plus as _qp

    google_fallback = (
        "https://www.google.com/search?q="
        + _qp(
            f"{parcel.county or ''} {parcel.state or ''} "
            f"{source.get('office') or 'county treasurer assessor'} parcel tax sale".strip()
        )
    )
    lookup_fallback = None
    for l in links:
        if l.get("kind") == "lookup" and str(l.get("url") or "").startswith("http"):
            lookup_fallback = str(l["url"])
            break
    fallback_site = source.get("website") or lookup_fallback or google_fallback

    async def _repair(url: str) -> tuple[str, str]:
        u = (url or "").strip()
        if not u.startswith("http"):
            return str(fallback_site), "replaced_missing"
        check = await validate_url(u)
        if check.get("ok"):
            return u, "ok"
        # Prefer parcel viewer, then Google — never hand the user a confirmed 404
        for candidate in (lookup_fallback, source.get("website"), google_fallback):
            c = str(candidate or "").strip()
            if not c.startswith("http") or c == u:
                continue
            c_check = await validate_url(c)
            if c_check.get("ok"):
                return c, "replaced_dead"
        return google_fallback, "replaced_dead"

    async def _annotate_one(l: dict[str, Any]) -> dict[str, Any]:
        kind = l.get("kind")
        url = str(l.get("url") or "")
        reason = "ok"
        if kind in ("primary", "contact_web") or (kind == "contact" and url.startswith("http")):
            url, reason = await _repair(url)
        elif not url and kind == "primary":
            url, reason = str(fallback_site), "replaced_missing"
        return {
            **l,
            "url": url,
            "available": True,
            "availability_reason": reason,
            "status_code": None,
        }

    import asyncio as _asyncio

    annotated = list(await _asyncio.gather(*[_annotate_one(l) for l in links])) if links else []
    if not any(l.get("kind") == "primary" for l in annotated):
        annotated.insert(
            0,
            {
                "label": "Open office page",
                "url": str(fallback_site),
                "kind": "primary",
                "available": True,
                "availability_reason": "ok",
                "status_code": None,
            },
        )
    annotated.sort(key=lambda l: 0 if l.get("kind") == "primary" else 1)
    # Keep AcquireRail website in sync with repaired primary
    primary_url = next((l["url"] for l in annotated if l.get("kind") == "primary"), fallback_site)
    if isinstance(source, dict):
        source = {**source, "website": primary_url}

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
        "access": human_access(enrichment.access if enrichment else None),
        "slope": human_slope(enrichment.terrain if enrichment else None),
        "growth": human_growth(
            enrichment.growth if enrichment else None,
            enrichment.comps if enrichment else None,
        ),
        "resale": human_resale(enrichment.comps if enrichment else None),
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
        appr = s.get("annual_appreciation")
        rent_ac = s.get("cash_rent_per_acre")
        if s.get("irr") is not None:
            plain = (
                f"{case_name}: about {float(s['irr']) * 100:.1f}% per year if cash rent"
                + (f" near ${float(rent_ac):.0f}/acre" if rent_ac is not None else "")
                + " and a later sale hold for this property"
                + (f", with land value growing about {float(appr)*100:.1f}%/yr" if appr is not None else "")
                + ". Toggle the hold length on the chart to see the land’s future dollar value."
            )
        else:
            plain = (
                "This case needs more local rent numbers before a yearly return can be shown. "
                "Pull nearby cash-rent comps, then refresh."
            )
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
    if enrichment and enrichment.comps and getattr(listing, "provider_id", None) != "public_vacant_gis":
        auction_path = (enrichment.comps.normalized or {}).get("auction_path")
    if not isinstance(auction_path, dict):
        auction_path = None
    if getattr(listing, "provider_id", None) == "public_vacant_gis":
        auction_path = None

    ask = listing.asking_price_usd if listing else None
    if ask is not None and ask <= 0:
        ask = None
    comps_n = {}
    if enrichment and enrichment.comps:
        comps_n = enrichment.comps.normalized or enrichment.comps.value or {}
    price = price_display(
        ask,
        listing.provider_id if listing else None,
        auction_path,
        score.estimated_value_usd if score else None,
        state=parcel.state,
        county=parcel.county,
        acres=parcel.acreage,
        apn=parcel.apn,
        comps_normalized=comps_n if isinstance(comps_n, dict) else {},
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
        "subtitle": f"{parcel.county}, {parcel.state}" + (f" · {parcel.acreage:,.1f} acres" if parcel.acreage else ""),
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
    from landsignal.services.outreach import build_outreach_playbook
    from landsignal.services.return_path import build_return_intelligence
    from landsignal.services.score_drivers import build_score_drivers

    _maybe_retag_vacant_gis(listing)

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

    rc = (brief.get("return_case") or {}) if isinstance(brief, dict) else {}
    entry_for_path = rc.get("entry_usd")
    if entry_for_path is None and auction_path:
        entry_for_path = auction_path.get("expected_settle_usd")
    if entry_for_path is None and isinstance(price, dict):
        entry_for_path = (
            price.get("expected_settle_usd")
            or price.get("amount_usd")
            or price.get("model_value_usd")
        )
    mark_for_path = rc.get("mark_usd") or (score.estimated_value_usd if score else None)
    traj_annual = None
    if isinstance(market_trajectory, dict):
        traj_annual = market_trajectory.get("annual_rate")

    return_intelligence = build_return_intelligence(
        parcel=parcel,
        listing=listing,
        score=score,
        enrichment=enrichment,
        entry_usd=float(entry_for_path) if entry_for_path is not None else None,
        mark_usd=float(mark_for_path) if mark_for_path is not None else None,
        hold_years=10,
        trajectory_annual=float(traj_annual) if traj_annual is not None else None,
    )
    score_drivers = (
        build_score_drivers(
            parcel=parcel,
            listing=listing,
            score=score,
            enrichment=enrichment,
            price=price if isinstance(price, dict) else None,
        )
        if score
        else {}
    )
    outreach = build_outreach_playbook(
        parcel=parcel,
        listing=listing,
        score=score,
        enrichment=enrichment,
        sourcing=source if isinstance(source, dict) else {},
        entry_usd=float(entry_for_path) if entry_for_path is not None else None,
        mark_usd=float(mark_for_path) if mark_for_path is not None else None,
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
        "brief": brief,
        "links": annotated,
        "price": price,
        "auction_path": auction_path,
        "sourcing": source,
        "cockpit": cockpit,
        "market_trajectory": market_trajectory,
        "return_intelligence": return_intelligence,
        "score_drivers": score_drivers,
        "outreach": outreach,
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
    from landsignal.services.land_alerts import curate_land_alert_feed

    store = get_store(get_settings().demo_seed)
    # Persist a cleaned feed: one alert per parcel, mappable boundary, still matching.
    cleaned = curate_land_alert_feed(store)
    if len(cleaned) != len(store.alerts):
        store.alerts[:] = cleaned
    return store.alerts


# ----- Land Alerts (preference-driven acquisition monitoring) -----


@router.get("/land-alerts/profiles")
async def list_land_alert_profiles() -> list[dict[str, Any]]:
    from landsignal.services.land_alerts import DEMO_USER_ID

    store = get_store(get_settings().demo_seed)
    rows = [p for p in store.land_alert_profiles.values() if p.user_id == DEMO_USER_ID]
    rows.sort(key=lambda p: p.updated_at, reverse=True)
    return [p.model_dump(mode="json") for p in rows]


@router.get("/land-alerts/profile")
async def get_land_alert_profile() -> dict[str, Any]:
    """Primary profile for the demo user (first active, or empty template)."""
    from landsignal.services.land_alerts import DEMO_USER_ID

    store = get_store(get_settings().demo_seed)
    rows = [p for p in store.land_alert_profiles.values() if p.user_id == DEMO_USER_ID]
    rows.sort(key=lambda p: p.updated_at, reverse=True)
    if not rows:
        return {
            "profile": None,
            "has_profile": False,
            "notify": LandAlertNotify().model_dump(mode="json"),
            "preferences": {},
        }
    p = rows[0]
    return {
        "profile": p.model_dump(mode="json"),
        "has_profile": True,
        "notify": p.notify.model_dump(mode="json"),
        "preferences": p.preferences,
    }


@router.put("/land-alerts/profile")
async def upsert_land_alert_profile(body: LandAlertProfileUpsert) -> dict[str, Any]:
    from landsignal.services.land_alerts import (
        DEMO_USER_ID,
        filter_mappable_matches,
        match_card,
        upsert_profile,
    )

    store = get_store(get_settings().demo_seed)
    profile, matches = upsert_profile(store, body, DEMO_USER_ID)
    viewable = filter_mappable_matches(store, matches)
    cards = [match_card(store, m) for m in viewable]
    cards.sort(key=lambda c: (-(c.get("preference_match_pct") or 0), -(c.get("landsignal_score") or 0)))
    return {
        "profile": profile.model_dump(mode="json"),
        "match_count": len(viewable),
        "new_count": sum(1 for m in viewable if m.status == "new"),
        "matches": cards[:100],
        "note": "Matches recalculated against existing inventory. Preference changes do not create 'new listing' notifications.",
    }


@router.post("/land-alerts/profile/{profile_id}/pause")
async def pause_land_alert(profile_id: UUID) -> dict[str, Any]:
    from landsignal.services.land_alerts import DEMO_USER_ID, set_paused

    store = get_store(get_settings().demo_seed)
    try:
        profile = set_paused(store, profile_id, True, DEMO_USER_ID)
    except KeyError:
        raise HTTPException(404, "Land Alert profile not found") from None
    return {"profile": profile.model_dump(mode="json")}


@router.post("/land-alerts/profile/{profile_id}/resume")
async def resume_land_alert(profile_id: UUID) -> dict[str, Any]:
    from landsignal.services.land_alerts import DEMO_USER_ID, rescan_profile, set_paused

    store = get_store(get_settings().demo_seed)
    try:
        profile = set_paused(store, profile_id, False, DEMO_USER_ID)
    except KeyError:
        raise HTTPException(404, "Land Alert profile not found") from None
    matches = rescan_profile(store, profile, origin="existing_inventory")
    return {"profile": profile.model_dump(mode="json"), "match_count": len(matches)}


@router.get("/land-alerts/matches")
async def list_land_alert_matches(profile_id: UUID | None = None, status: str | None = None) -> dict[str, Any]:
    from landsignal.services.land_alerts import (
        DEMO_USER_ID,
        filter_mappable_matches,
        match_card,
        matches_for_user,
    )

    store = get_store(get_settings().demo_seed)
    all_rows = filter_mappable_matches(store, matches_for_user(store, DEMO_USER_ID, profile_id))
    rows = [m for m in all_rows if m.status == status] if status else all_rows
    cards = [match_card(store, m) for m in rows]
    return {
        "matches": cards,
        "counts": {
            "new": sum(1 for m in all_rows if m.status == "new"),
            "unseen": sum(1 for m in all_rows if m.status == "unseen"),
            "viewed": sum(1 for m in all_rows if m.status == "viewed"),
            "total": len(all_rows),
        },
    }


@router.get("/parcels/{parcel_id}/geometry")
async def parcel_geometry(parcel_id: UUID) -> dict[str, Any]:
    """Lightweight map payload for Land Viewer — no live re-enrichment."""
    store = get_store(get_settings().demo_seed)
    parcel = store.parcels.get(parcel_id)
    if not parcel:
        raise HTTPException(404, "Parcel not found")
    return {
        "parcel_id": str(parcel.id),
        "latitude": parcel.latitude,
        "longitude": parcel.longitude,
        "polygon": parcel.polygon,
        "acres": parcel.acreage,
        "state": parcel.state,
        "county": parcel.county,
    }


@router.post("/land-alerts/matches/{parcel_id}/viewed")
async def mark_land_alert_viewed(parcel_id: UUID) -> dict[str, Any]:
    from landsignal.services.land_alerts import DEMO_USER_ID, mark_match_viewed
    from landsignal.store import persist_store

    store = get_store(get_settings().demo_seed)
    n = mark_match_viewed(store, DEMO_USER_ID, parcel_id)
    persist_store(store)
    return {"updated": n}


@router.delete("/land-alerts/matches/{parcel_id}/viewed")
async def unmark_land_alert_viewed(parcel_id: UUID) -> dict[str, Any]:
    from landsignal.services.land_alerts import DEMO_USER_ID, mark_match_unviewed
    from landsignal.store import persist_store

    store = get_store(get_settings().demo_seed)
    n = mark_match_unviewed(store, DEMO_USER_ID, parcel_id)
    persist_store(store)
    return {"updated": n}


@router.post("/land-alerts/mark-all-seen")
async def mark_all_land_alerts_seen(profile_id: UUID | None = None) -> dict[str, Any]:
    from landsignal.services.land_alerts import DEMO_USER_ID, mark_all_seen
    from landsignal.store import persist_store

    store = get_store(get_settings().demo_seed)
    n = mark_all_seen(store, DEMO_USER_ID, profile_id)
    persist_store(store)
    return {"updated": n}


@router.post("/land-alerts/mark-all-unseen")
async def mark_all_land_alerts_unseen(profile_id: UUID | None = None) -> dict[str, Any]:
    from landsignal.services.land_alerts import DEMO_USER_ID, mark_all_unseen
    from landsignal.store import persist_store

    store = get_store(get_settings().demo_seed)
    n = mark_all_unseen(store, DEMO_USER_ID, profile_id)
    persist_store(store)
    return {"updated": n}


@router.put("/land-alerts/notify")
async def update_land_alert_notify(body: LandAlertNotify) -> dict[str, Any]:
    from landsignal.services.land_alerts import DEMO_USER_ID
    from landsignal.store import persist_store

    store = get_store(get_settings().demo_seed)
    rows = [p for p in store.land_alert_profiles.values() if p.user_id == DEMO_USER_ID]
    if not rows:
        raise HTTPException(404, "Create a Land Alert profile first")
    rows.sort(key=lambda p: p.updated_at, reverse=True)
    profile = rows[0].model_copy(update={"notify": body})
    store.land_alert_profiles[profile.id] = profile
    persist_store(store)
    return {"profile": profile.model_dump(mode="json")}


@router.post("/land-alerts/rescan")
async def rescan_land_alerts() -> dict[str, Any]:
    from landsignal.services.land_alerts import (
        DEMO_USER_ID,
        filter_mappable_matches,
        match_card,
        rescan_profile,
    )

    store = get_store(get_settings().demo_seed)
    profiles = [p for p in store.land_alert_profiles.values() if p.user_id == DEMO_USER_ID and not p.paused]
    all_matches = []
    for p in profiles:
        all_matches.extend(rescan_profile(store, p, origin="existing_inventory"))
    viewable = filter_mappable_matches(store, all_matches)
    cards = [match_card(store, m) for m in viewable]
    return {"match_count": len(viewable), "matches": cards[:100]}


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
                "title": display_title(parcel, listing) if parcel else str(pid),
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
