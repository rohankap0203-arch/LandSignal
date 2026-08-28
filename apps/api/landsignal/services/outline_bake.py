"""Bake real GIS boundaries into EVERY inventory parcel (not just on View Map open).

Product rule: when a capability is required, it applies to the full nationwide book
(~138k+), not a sampled subset. Outlines are fetched from the same public cadastral
layers we invent from, then stored on the parcel so maps/alerts don't wait.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import structlog

from landsignal.services.parcel_geometry_live import fetch_real_parcel_outline
from landsignal.services.parcel_outline import compact_polygon, exact_polygon, is_synthetic_square
from landsignal.store import MemoryStore, persist_store

log = structlog.get_logger(__name__)

_BAKE_LOCK = asyncio.Lock()
_BAKE_STATUS: dict[str, Any] = {
    "running": False,
    "done": 0,
    "failed": 0,
    "skipped": 0,
    "total": 0,
    "target": 0,
}


def bake_status() -> dict[str, Any]:
    return dict(_BAKE_STATUS)


def _needs_bake(polygon: Any) -> bool:
    if is_synthetic_square(polygon):
        return True
    if exact_polygon(polygon) is None and compact_polygon(polygon) is None:
        return True
    return False


async def bake_outlines_for_inventory(
    store: MemoryStore,
    *,
    limit: int | None = None,
    concurrency: int = 8,
    only_missing: bool = True,
) -> dict[str, Any]:
    """Bake GIS outlines into all (or missing) live parcels. Safe to run in background."""
    if _BAKE_LOCK.locked():
        return {**bake_status(), "note": "bake already running"}

    async with _BAKE_LOCK:
        parcels = [p for p in store.parcels.values() if not p.is_demo]
        if only_missing:
            targets = [p for p in parcels if _needs_bake(p.polygon)]
        else:
            targets = list(parcels)
        if limit is not None:
            targets = targets[: max(0, int(limit))]

        _BAKE_STATUS.update(
            {
                "running": True,
                "done": 0,
                "failed": 0,
                "skipped": 0,
                "total": len(parcels),
                "target": len(targets),
            }
        )
        sem = asyncio.Semaphore(max(1, min(16, int(concurrency))))
        persist_every = 40

        async def one(parcel) -> str:
            async with sem:
                listing = store.listing_for_parcel(parcel.id)
                raw = (listing.raw if listing and isinstance(listing.raw, dict) else {}) or {}
                try:
                    outline = await fetch_real_parcel_outline(
                        latitude=parcel.latitude,
                        longitude=parcel.longitude,
                        state=parcel.state,
                        county=parcel.county,
                        apn=parcel.apn or (str(raw.get("apn")) if raw.get("apn") else None),
                        external_id=listing.external_id if listing else None,
                        source_id=str(raw.get("source_id") or "") or None,
                        acreage=parcel.acreage,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.info(
                        "outline_bake_failed",
                        parcel_id=str(parcel.id),
                        error=str(exc)[:160],
                    )
                    return "failed"
                if not outline:
                    return "failed"
                # Store exact ring on the parcel; persist_store will compact for disk.
                parcel.polygon = outline
                parcel.geometry_confidence = 95.0
                store.parcels[parcel.id] = parcel
                return "done"

        try:
            for i in range(0, len(targets), concurrency * 2):
                chunk = targets[i : i + concurrency * 2]
                results = await asyncio.gather(*[one(p) for p in chunk])
                for r in results:
                    if r == "done":
                        _BAKE_STATUS["done"] = int(_BAKE_STATUS["done"]) + 1
                    else:
                        _BAKE_STATUS["failed"] = int(_BAKE_STATUS["failed"]) + 1
                if (int(_BAKE_STATUS["done"]) + int(_BAKE_STATUS["failed"])) % persist_every == 0:
                    try:
                        persist_store(store)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("outline_bake_persist_failed", error=str(exc)[:160])
            try:
                persist_store(store)
            except Exception:
                pass
        finally:
            _BAKE_STATUS["running"] = False

        baked = int(_BAKE_STATUS["done"])
        failed = int(_BAKE_STATUS["failed"])
        with_poly = sum(
            1
            for p in store.parcels.values()
            if not p.is_demo and compact_polygon(p.polygon)
        )
        return {
            **bake_status(),
            "baked": baked,
            "failed": failed,
            "inventory_with_outline": with_poly,
            "inventory_total": sum(1 for p in store.parcels.values() if not p.is_demo),
            "note": "Baked real GIS outlines into inventory parcels (full book, not a sample).",
        }


async def bake_one_parcel(store: MemoryStore, parcel_id: UUID) -> dict[str, Any]:
    parcel = store.parcels.get(parcel_id)
    if not parcel:
        return {"ok": False, "error": "not_found"}
    listing = store.listing_for_parcel(parcel.id)
    raw = (listing.raw if listing and isinstance(listing.raw, dict) else {}) or {}
    outline = await fetch_real_parcel_outline(
        latitude=parcel.latitude,
        longitude=parcel.longitude,
        state=parcel.state,
        county=parcel.county,
        apn=parcel.apn or (str(raw.get("apn")) if raw.get("apn") else None),
        external_id=listing.external_id if listing else None,
        source_id=str(raw.get("source_id") or "") or None,
        acreage=parcel.acreage,
    )
    if not outline:
        return {"ok": False, "error": "no_gis_ring"}
    parcel.polygon = outline
    parcel.geometry_confidence = 95.0
    store.parcels[parcel.id] = parcel
    return {"ok": True, "vertex_count": len(outline[0]), "parcel_id": str(parcel.id)}
