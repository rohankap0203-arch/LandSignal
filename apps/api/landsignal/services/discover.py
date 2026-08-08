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

    existing_tax = sum(1 for L in store.listings.values() if L.provider_id == "public_tax_sale")
    # Ask each source for a large page — tax/surplus GIS layers have tens of thousands of rows
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
                "limit": min(8000, max(500, limit)),
                "min_acres": min_acres,
                # Continue past already-indexed rows so refresh grows toward 10k+
                "offset": 0 if reset else existing_tax,
            }
        ),
        surplus.search_listings({"limit": min(500, max(50, limit // 10))}),
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
            # Slim geometry for bulk memory — keep centroid; drop giant multipolygons
            if row.get("polygon") and acres is not None and acres < 5:
                row = {**row, "polygon": None}
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
        if parcel.polygon:
            parcel.geometry_confidence = max(parcel.geometry_confidence or 0, 75.0)
        store.parcels[parcel.id] = parcel
        store.listings[listing.id] = listing
        parcel_ids.append(parcel.id)
        to_score.append(parcel.id)

    sem = asyncio.Semaphore(24 if fast else 6)
    scored = 0

    async def _score_one(pid: UUID) -> None:
        nonlocal scored
        async with sem:
            try:
                score = await analyze_parcel(store, pid, settings, fast=fast)
                evaluate_rules(store, score, settings)
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
        "scored": scored,
        "source_counts": source_counts,
        "providers_used": list(source_counts.keys()),
        "parcel_ids": [str(x) for x in list(set(parcel_ids))[:50]],
        "errors": errors,
        "fast": fast,
        "inventory_total": sum(1 for p in store.parcels.values() if not p.is_demo),
        "note": (
            "Live free public feeds at scale: BLM LPAD + county tax-sale/surplus GIS "
            f"({sum(source_counts.values())} raw rows considered). "
            "Fast index scores first; open a parcel for full soils/flood enrichment. "
            "Licensed MLS/Land.com/Crexi/Regrid remain unavailable without API keys."
        ),
    }
