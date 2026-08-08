from __future__ import annotations

import asyncio
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


async def discover_opportunities(
    store: MemoryStore,
    settings: Settings | None = None,
    *,
    limit: int = 30,
    min_acres: float = 10,
    max_acres: float = 2500,
    states: list[str] | None = None,
    reset: bool = False,
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

    blm_res, tax_res, surplus_res = await asyncio.gather(
        blm.search_listings(
            {"limit": max(8, limit // 2), "min_acres": min_acres, "max_acres": max_acres, "states": states}
        ),
        tax.search_listings({"limit": max(10, limit)}),
        surplus.search_listings({"limit": max(8, limit // 2)}),
    )

    listings: list[dict] = []
    source_counts: dict[str, int] = {}
    errors: list[str] = []

    for res, label in (
        (blm_res, "blm_lpad"),
        (tax_res, "public_tax_sale"),
        (surplus_res, "public_surplus"),
    ):
        if res.error:
            errors.append(f"{label}: {res.error}")
        for row in res.data or []:
            acres = row.get("acreage")
            if acres is not None and (acres < min_acres or acres > max_acres):
                # allow tax-sale with prices even if smaller — opportunistic urban lots
                if row.get("provider_id") == "public_tax_sale" and row.get("asking_price_usd"):
                    if acres < 0.2:
                        continue
                elif acres < min_acres or acres > max_acres:
                    continue
            listings.append(row)
            pid = row.get("provider_id") or label
            source_counts[pid] = source_counts.get(pid, 0) + 1

    # Also try any other configured listing providers (skip stubs)
    providers = build_listing_providers(settings)
    for pid, provider in providers.items():
        if pid in ("manual", "csv", "blm_lpad", "public_tax_sale", "public_surplus"):
            continue
        if provider.status().value == "NOT_CONFIGURED":
            continue
        search = await provider.search_listings({"limit": limit})
        if search.ok and search.data:
            listings.extend(search.data)

    # Rank: priced first, then acreage, diversify providers
    listings.sort(
        key=lambda r: (
            0 if r.get("asking_price_usd") is not None else 1,
            0 if (r.get("acreage") or 0) >= min_acres else 1,
            -(r.get("acreage") or 0),
        )
    )

    # Diversify across providers
    by_provider: dict[str, list[dict]] = {}
    for row in listings:
        by_provider.setdefault(row.get("provider_id") or "unknown", []).append(row)
    diversified: list[dict] = []
    while len(diversified) < limit and any(by_provider.values()):
        for prov in list(by_provider.keys()):
            if by_provider.get(prov):
                diversified.append(by_provider[prov].pop(0))
            if len(diversified) >= limit:
                break
            if prov in by_provider and not by_provider[prov]:
                by_provider.pop(prov, None)

    parcel_ids: list[UUID] = []
    to_score: list[UUID] = []
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
            parcel_ids.append(existing.parcel_id)
            if store.latest_score(existing.parcel_id) is None:
                to_score.append(existing.parcel_id)
            continue
        parcel, listing = store.upsert_manual({**raw, "provider_id": raw.get("provider_id") or "manual"})
        parcel.is_demo = False
        listing.is_demo = False
        # Open parcel geometry stands in for Regrid when polygon present
        if parcel.polygon:
            parcel.geometry_confidence = max(parcel.geometry_confidence or 0, 75.0)
        store.parcels[parcel.id] = parcel
        store.listings[listing.id] = listing
        parcel_ids.append(parcel.id)
        to_score.append(parcel.id)

    # Score in parallel — sequential enrichment was making the UI feel stuck for minutes
    sem = asyncio.Semaphore(6)
    scored = 0

    async def _score_one(pid: UUID) -> None:
        nonlocal scored
        async with sem:
            try:
                score = await analyze_parcel(store, pid, settings)
                evaluate_rules(store, score, settings)
                scored += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("discover_analyze_failed", parcel_id=str(pid), error=str(exc))

    if to_score:
        await asyncio.gather(*[_score_one(pid) for pid in to_score])

    return {
        "imported": len(set(parcel_ids)),
        "scored": scored,
        "source_counts": source_counts,
        "providers_used": list(source_counts.keys()),
        "parcel_ids": [str(x) for x in parcel_ids],
        "errors": errors,
        "note": (
            "Live free public feeds: BLM LPAD + county tax-sale/surplus GIS. "
            "These approximate MLS/Land.com/Crexi/Regrid without licensed scrapers. "
            "Cursor Cloud does not provide Land.com/Crexi/Regrid API keys."
        ),
    }
