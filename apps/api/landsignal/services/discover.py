from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from landsignal.providers.blm_lpad import BlmLpadProvider
from landsignal.providers.listing import build_listing_providers
from landsignal.providers.public_markets import PublicSurplusProvider, PublicTaxSaleProvider
from landsignal.services.alerts import evaluate_rules
from landsignal.services.analyze import analyze_parcel
from landsignal.settings import Settings, get_settings
from landsignal.store import MemoryStore

log = structlog.get_logger()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _refresh_listing(store: MemoryStore, listing, raw: dict[str, Any]) -> bool:
    """Push live feed fields onto an existing listing. Returns True if price moved."""
    price_moved = False
    new_ask = raw.get("asking_price_usd")
    if new_ask is not None and new_ask != listing.asking_price_usd:
        listing.asking_price_usd = new_ask
        acres = store.parcels.get(listing.parcel_id)
        ac = acres.acreage if acres else None
        listing.price_per_acre_usd = (new_ask / ac) if new_ask and ac else listing.price_per_acre_usd
        price_moved = True
    if raw.get("source_url"):
        listing.source_url = raw["source_url"]
    if raw.get("title"):
        listing.title = raw["title"]
    if raw.get("description"):
        listing.description = raw["description"]
    listing.last_seen_at = _utcnow()
    listing.raw = {**(listing.raw or {}), **{k: v for k, v in raw.items() if k != "polygon"}}
    store.listings[listing.id] = listing
    store.index_listing(listing)
    parcel = store.parcels.get(listing.parcel_id)
    if parcel:
        if raw.get("latitude") is not None:
            parcel.latitude = raw["latitude"]
        if raw.get("longitude") is not None:
            parcel.longitude = raw["longitude"]
        if raw.get("acreage") is not None:
            parcel.acreage = raw["acreage"]
        if raw.get("polygon"):
            parcel.polygon = raw["polygon"]
        store.parcels[parcel.id] = parcel
    return price_moved


async def discover_opportunities(
    store: MemoryStore,
    settings: Settings | None = None,
    *,
    limit: int = 10000,
    min_acres: float = 0.1,
    max_acres: float = 50000,
    states: list[str] | None = None,
    reset: bool = False,
    fast: bool = True,
) -> dict[str, Any]:
    """Pull real public inventory from all free configured sources, enrich, score."""
    settings = settings or get_settings()
    if reset:
        store.parcels.clear()
        store.listings.clear()
        store.enrichments.clear()
        store.scores.clear()

    blm = BlmLpadProvider()
    tax = PublicTaxSaleProvider()
    surplus = PublicSurplusProvider()

    # Ask each source for a large page — tax/surplus GIS layers have tens of thousands of rows.
    # Always start county layers at offset 0: a global offset skips brand-new sources that have
    # fewer rows than already-indexed inventory. Dedup happens below via external_id.
    blm_res, tax_res, surplus_res = await asyncio.gather(
        blm.search_listings(
            {
                "limit": min(2500, max(200, limit // 4)),
                "min_acres": max(1.0, min_acres),
                "max_acres": max_acres,
                "states": states,
            }
        ),
        tax.search_listings(
            {
                # Statewide vacant GIS (esp. FL_Parcels) can fill Zillow-scale land inventory.
                "limit": min(100000, max(500, limit)),
                "min_acres": min_acres,
                "offset": 0,
                "states": states,
            }
        ),
        surplus.search_listings(
            {
                "limit": min(800, max(50, limit // 8)),
                "states": states,
            }
        ),
    )

    listings: list[dict] = []
    source_counts: dict[str, int] = {}
    errors: list[str] = []
    state_set = {s.upper() for s in states} if states else None

    for res, label in (
        (blm_res, "blm_lpad"),
        (tax_res, "public_tax_sale"),
        (surplus_res, "public_surplus"),
    ):
        if res.error:
            errors.append(f"{label}: {res.error}")
        for row in res.data or []:
            if state_set and (row.get("state") or "").upper() not in state_set:
                continue
            acres = row.get("acreage")
            if acres is not None and (acres < min_acres or acres > max_acres):
                if row.get("provider_id") == "public_tax_sale" and row.get("asking_price_usd"):
                    if acres < 0.05:
                        continue
                else:
                    continue
            # Slim only oversized rings (memory) — never drop real parcel boundaries for small lots.
            poly = row.get("polygon")
            if poly and isinstance(poly, list) and poly and isinstance(poly[0], list):
                ring = poly[0]
                if len(ring) > 2500:
                    row = {**row, "polygon": [ring[:: max(1, len(ring) // 800)] + [ring[-1]]]}
            listings.append(row)
            pid = row.get("provider_id") or label
            source_counts[pid] = source_counts.get(pid, 0) + 1

    providers = build_listing_providers(settings)
    for pid, provider in providers.items():
        if pid in ("manual", "csv", "blm_lpad", "public_tax_sale", "public_surplus"):
            continue
        if provider.status().value == "NOT_CONFIGURED":
            continue
        search = await provider.search_listings({"limit": min(200, limit)})
        if search.ok and search.data:
            listings.extend(search.data)

    listings.sort(
        key=lambda r: (
            0 if r.get("asking_price_usd") is not None else 1,
            0 if (r.get("acreage") or 0) >= 1 else 1,
            -(r.get("acreage") or 0),
        )
    )

    # Fair nationwide mix: round-robin by state, then by provider inside each state.
    by_state_provider: dict[str, dict[str, list[dict]]] = {}
    for row in listings:
        st = (row.get("state") or "??").upper()
        prov = row.get("provider_id") or "unknown"
        by_state_provider.setdefault(st, {}).setdefault(prov, []).append(row)
    diversified: list[dict] = []
    while len(diversified) < limit and by_state_provider:
        for st in list(by_state_provider.keys()):
            provs = by_state_provider.get(st) or {}
            if not provs:
                by_state_provider.pop(st, None)
                continue
            for prov in list(provs.keys()):
                if provs.get(prov):
                    diversified.append(provs[prov].pop(0))
                if not provs.get(prov):
                    provs.pop(prov, None)
                if len(diversified) >= limit:
                    break
            if not provs:
                by_state_provider.pop(st, None)
            if len(diversified) >= limit:
                break

    parcel_ids: list[UUID] = []
    to_score: list[UUID] = []
    refreshed = 0
    new_parcel_ids: set[UUID] = set()
    price_drop_ids: set[UUID] = set()
    price_up_ids: set[UUID] = set()
    for raw in diversified:
        existing = next(
            (
                L
                for L in store.listings.values()
                if L.provider_id == raw.get("provider_id")
                and L.external_id == raw.get("external_id")
            ),
            None,
        )
        if existing:
            old_ask = existing.asking_price_usd
            price_moved = _refresh_listing(store, existing, raw)
            refreshed += 1
            parcel_ids.append(existing.parcel_id)
            if store.latest_score(existing.parcel_id) is None or price_moved:
                to_score.append(existing.parcel_id)
            if price_moved and existing.asking_price_usd is not None and old_ask is not None:
                if existing.asking_price_usd < old_ask:
                    price_drop_ids.add(existing.parcel_id)
                elif existing.asking_price_usd > old_ask:
                    price_up_ids.add(existing.parcel_id)
            continue
        parcel, listing = store.upsert_manual({**raw, "provider_id": raw.get("provider_id") or "manual"})
        parcel.is_demo = False
        listing.is_demo = False
        if parcel.polygon:
            parcel.geometry_confidence = max(parcel.geometry_confidence or 0, 75.0)
        store.parcels[parcel.id] = parcel
        store.listings[listing.id] = listing
        parcel_ids.append(parcel.id)
        to_score.append(parcel.id)
        new_parcel_ids.add(parcel.id)

    sem = asyncio.Semaphore(24 if fast else 6)
    scored = 0

    async def _score_one(pid: UUID) -> None:
        nonlocal scored
        async with sem:
            try:
                score = await analyze_parcel(store, pid, settings, fast=fast)
                evaluate_rules(store, score, settings)
                from landsignal.services.land_alerts import match_parcel

                if pid in new_parcel_ids:
                    match_parcel(
                        store, pid, origin="new_discovery", update_kind="new_listing", settings=settings
                    )
                elif pid in price_drop_ids:
                    match_parcel(
                        store, pid, origin="price_update", update_kind="price_drop", settings=settings
                    )
                elif pid in price_up_ids:
                    match_parcel(
                        store, pid, origin="price_update", update_kind="price_increase", settings=settings
                    )
                else:
                    # Re-score only — do not treat as a notify-worthy "price update".
                    match_parcel(
                        store, pid, origin="existing_inventory", update_kind="new_data", settings=settings
                    )
                scored += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("discover_analyze_failed", parcel_id=str(pid), error=str(exc))

    # Score in chunks so radar can see inventory while the rest indexes
    chunk = 200
    for i in range(0, len(to_score), chunk):
        batch = to_score[i : i + chunk]
        await asyncio.gather(*[_score_one(pid) for pid in batch])
        log.info("discover_batch_scored", scored=scored, total=len(to_score))

    return {
        "imported": len(set(parcel_ids)),
        "refreshed": refreshed,
        "scored": scored,
        "source_counts": source_counts,
        "providers_used": list(source_counts.keys()),
        "parcel_ids": [str(x) for x in list(set(parcel_ids))[:50]],
        "errors": errors,
        "fast": fast,
        "inventory_total": sum(1 for p in store.parcels.values() if not p.is_demo),
        "note": (
            "Live free public feeds at scale: BLM LPAD + county tax-sale/surplus GIS "
            f"({sum(source_counts.values())} raw rows considered; {refreshed} existing rows refreshed). "
            "Fast index scores first; open a parcel for full soils/flood enrichment. "
            "Licensed MLS/Land.com/Crexi/Regrid remain unavailable without API keys."
        ),
    }
