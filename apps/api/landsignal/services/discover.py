from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from landsignal.providers.blm_lpad import BlmLpadProvider
from landsignal.providers.listing import build_listing_providers
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
    """Pull real public inventory, normalize, enrich, score, evaluate alerts."""
    settings = settings or get_settings()
    if reset:
        store.parcels.clear()
        store.listings.clear()
        store.enrichments.clear()
        store.scores.clear()
    blm = BlmLpadProvider()
    result = await blm.search_listings(
        {
            "limit": limit,
            "min_acres": min_acres,
            "max_acres": max_acres,
            "states": states,
        }
    )
    if not result.ok or not result.data:
        # Also try other configured listing providers
        providers = build_listing_providers(settings)
        collected: list[dict] = []
        errors = [result.error] if result.error else []
        for pid, provider in providers.items():
            if pid in ("manual", "csv", "demo"):
                continue
            if provider.status().value == "NOT_CONFIGURED":
                continue
            search = await provider.search_listings({"limit": limit})
            if search.ok and search.data:
                collected.extend(search.data)
            elif search.error:
                errors.append(f"{pid}: {search.error}")
        if not collected:
            return {
                "imported": 0,
                "scored": 0,
                "errors": errors or ["No listings returned from configured providers"],
                "parcel_ids": [],
            }
        listings = collected
    else:
        listings = result.data

    parcel_ids: list[UUID] = []
    scored = 0
    for raw in listings:
        # Dedupe by provider+external_id
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
            continue
        parcel, listing = store.upsert_manual({**raw, "provider_id": raw.get("provider_id") or "blm_lpad"})
        parcel.is_demo = False
        listing.is_demo = False
        store.parcels[parcel.id] = parcel
        store.listings[listing.id] = listing
        try:
            score = await analyze_parcel(store, parcel.id, settings)
            evaluate_rules(store, score, settings)
            scored += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("discover_analyze_failed", parcel_id=str(parcel.id), error=str(exc))
        parcel_ids.append(parcel.id)

    return {
        "imported": len(parcel_ids),
        "scored": scored,
        "provider": "blm_lpad",
        "parcel_ids": [str(x) for x in parcel_ids],
        "note": "BLM LPAD tracts are real federal disposal candidates. Licensed MLS/Land.com remain NOT_CONFIGURED without vendor keys.",
    }
