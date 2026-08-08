"""Re-run scoring from cached enrichment when the algorithm version changes."""

from __future__ import annotations

import asyncio

import structlog

from landsignal.scoring.engine import ALGORITHM_VERSION
from landsignal.services.analyze import analyze_parcel
from landsignal.store import MemoryStore

log = structlog.get_logger()


async def rescore_stale(store: MemoryStore, *, limit: int = 5000, concurrency: int = 32) -> dict:
    stale = [
        pid
        for pid, scores in store.scores.items()
        if scores and scores[-1].algorithm_version != ALGORITHM_VERSION
    ]
    # Also score parcels that somehow lack scores
    missing = [pid for pid in store.parcels if store.latest_score(pid) is None]
    targets = (stale + missing)[:limit]
    if not targets:
        return {"rescored": 0, "stale_found": 0, "algorithm_version": ALGORITHM_VERSION}

    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def one(pid):
        nonlocal done
        async with sem:
            try:
                await analyze_parcel(store, pid, fast=True)
                done += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("rescore_failed", parcel_id=str(pid), error=str(exc))

    await asyncio.gather(*[one(pid) for pid in targets])
    log.info("rescore_complete", rescored=done, stale=len(stale), missing=len(missing))
    return {
        "rescored": done,
        "stale_found": len(stale),
        "missing_found": len(missing),
        "algorithm_version": ALGORITHM_VERSION,
    }
