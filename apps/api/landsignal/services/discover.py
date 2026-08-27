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
    from landsignal.services.memory_guard import slim_listing_raw

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
    merged = {**(listing.raw or {}), **{k: v for k, v in raw.items() if k != "polygon"}}
    listing.raw = slim_listing_raw(merged)
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
        # Never keep polygons on the hot index path.
        parcel.polygon = None
        store.parcels[parcel.id] = parcel
    return price_moved


def _wired_states(states: list[str] | None) -> list[str]:
    if states:
        return sorted({s.upper() for s in states if s})
    from landsignal.providers.public_markets import SOURCES

    return sorted(
        {
            s.state.upper()
            for s in SOURCES
            if s.state
            and "surplus" not in s.source_id
            and "fairfax" not in s.source_id
        }
    )


def _diversify(listings: list[dict], limit: int) -> list[dict]:
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
    return diversified


def _filter_rows(
    rows: list[dict],
    *,
    state_set: set[str] | None,
    min_acres: float,
    max_acres: float,
    label: str,
    source_counts: dict[str, int],
) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        if state_set and (row.get("state") or "").upper() not in state_set:
            continue
        acres = row.get("acreage")
        if acres is not None and (acres < min_acres or acres > max_acres):
            if row.get("provider_id") == "public_tax_sale" and row.get("asking_price_usd"):
                if acres < 0.05:
                    continue
            else:
                continue
        # Drop polygons during index — they OOM cloud VMs at nationwide scale.
        # Detail pages / geometry endpoints can rehydrate boundaries later.
        if row.get("polygon") is not None:
            row = {**row, "polygon": None}
        out.append(row)
        pid = row.get("provider_id") or label
        source_counts[pid] = source_counts.get(pid, 0) + 1
    return out


async def _ingest_and_score(
    store: MemoryStore,
    settings: Settings,
    listings: list[dict],
    *,
    limit: int,
    fast: bool,
) -> dict[str, Any]:
    from landsignal.services.memory_guard import (
        should_stop_heavy_work,
        should_throttle,
        snapshot,
        trim_score_lists,
    )

    listings.sort(
        key=lambda r: (
            0 if r.get("asking_price_usd") is not None else 1,
            0 if (r.get("acreage") or 0) >= 1 else 1,
            -(r.get("acreage") or 0),
        )
    )
    diversified = _diversify(listings, limit)

    parcel_ids: list[UUID] = []
    to_score: list[UUID] = []
    refreshed = 0
    new_parcel_ids: set[UUID] = set()
    price_drop_ids: set[UUID] = set()
    price_up_ids: set[UUID] = set()
    for raw in diversified:
        existing = store.listing_by_external(raw.get("provider_id"), raw.get("external_id"))
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
        parcel.polygon = None
        store.parcels[parcel.id] = parcel
        store.listings[listing.id] = listing
        parcel_ids.append(parcel.id)
        to_score.append(parcel.id)
        new_parcel_ids.add(parcel.id)

    inv_now = sum(1 for p in store.parcels.values() if not p.is_demo)
    # Concurrency collapses under memory pressure — never 24-wide on a 15Gi VM.
    if should_throttle() or inv_now >= 60_000:
        score_conc = 4 if fast else 2
        chunk = 40
    elif inv_now >= 25_000:
        score_conc = 8 if fast else 3
        chunk = 80
    else:
        score_conc = 12 if fast else 4
        chunk = 120
    sem = asyncio.Semaphore(score_conc)
    scored = 0
    stopped_early = False
    stop_reason = ""

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
                    match_parcel(
                        store, pid, origin="existing_inventory", update_kind="new_data", settings=settings
                    )
                scored += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("discover_analyze_failed", parcel_id=str(pid), error=str(exc))

    for i in range(0, len(to_score), chunk):
        stop, reason = should_stop_heavy_work()
        if stop:
            stopped_early = True
            stop_reason = reason
            log.warning(
                "discover_score_paused_memory",
                reason=reason,
                scored=scored,
                remaining=len(to_score) - i,
                **snapshot(),
            )
            break
        batch = to_score[i : i + chunk]
        await asyncio.gather(*[_score_one(pid) for pid in batch])
        trim_score_lists(store, keep=1)
        log.info(
            "discover_batch_scored",
            scored=scored,
            total=len(to_score),
            inventory=sum(1 for p in store.parcels.values() if not p.is_demo),
            concurrency=score_conc,
            **snapshot(),
        )
        if inv_now >= 20_000 and i > 0 and (i // chunk) % 6 == 0:
            try:
                from landsignal.store import persist_store

                persist_store(store)
            except Exception as exc:  # noqa: BLE001
                log.warning("discover_mid_persist_failed", error=str(exc)[:200])

    return {
        "imported": len(set(parcel_ids)),
        "refreshed": refreshed,
        "scored": scored,
        "parcel_ids": [str(x) for x in list(set(parcel_ids))[:50]],
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
    }


async def _pull_state_listings(
    *,
    states: list[str],
    limit: int,
    min_acres: float,
    max_acres: float,
    min_per_state: int,
    include_optional_providers: bool,
    settings: Settings,
) -> tuple[list[dict], dict[str, int], list[str]]:
    blm = BlmLpadProvider()
    tax = PublicTaxSaleProvider()
    surplus = PublicSurplusProvider()
    wired = max(1, len(states))
    tax_limit = max(limit, min_per_state * wired)
    tax_limit = min(1_000_000, max(500, tax_limit))

    blm_res, tax_res, surplus_res = await asyncio.gather(
        blm.search_listings(
            {
                "limit": min(30000, max(2000, min_per_state * 2)),
                "min_acres": max(1.0, min_acres),
                "max_acres": max_acres,
                "states": states,
            }
        ),
        tax.search_listings(
            {
                "limit": tax_limit,
                "min_per_state": min_per_state,
                "min_acres": min_acres,
                "offset": 0,
                "states": states,
            }
        ),
        surplus.search_listings(
            {
                "limit": min(2000, max(100, min_per_state // 2)),
                "states": states,
            }
        ),
    )

    listings: list[dict] = []
    source_counts: dict[str, int] = {}
    errors: list[str] = []
    state_set = {s.upper() for s in states}

    for res, label in (
        (blm_res, "blm_lpad"),
        (tax_res, "public_tax_sale"),
        (surplus_res, "public_surplus"),
    ):
        if res.error:
            errors.append(f"{label}: {res.error}")
        listings.extend(
            _filter_rows(
                res.data or [],
                state_set=state_set,
                min_acres=min_acres,
                max_acres=max_acres,
                label=label,
                source_counts=source_counts,
            )
        )

    if include_optional_providers:
        providers = build_listing_providers(settings)
        for pid, provider in providers.items():
            if pid in ("manual", "csv", "blm_lpad", "public_tax_sale", "public_surplus"):
                continue
            if provider.status().value == "NOT_CONFIGURED":
                continue
            search = await provider.search_listings({"limit": min(200, limit)})
            if search.ok and search.data:
                listings.extend(
                    _filter_rows(
                        search.data,
                        state_set=state_set,
                        min_acres=min_acres,
                        max_acres=max_acres,
                        label=pid,
                        source_counts=source_counts,
                    )
                )

    return listings, source_counts, errors


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
    """Pull real public inventory from free sources, enrich, score.

    Nationwide runs are progressive by state so Show Matches / live inventory
    climb as each state finishes — instead of waiting on every GIS source first.
    """
    settings = settings or get_settings()
    if reset:
        store.parcels.clear()
        store.listings.clear()
        store.enrichments.clear()
        store.scores.clear()

    min_per_state = max(500, int(getattr(settings, "discover_min_per_state", 2500) or 2500))
    state_queue = _wired_states(states)
    per_state_limit = max(min_per_state, (limit + len(state_queue) - 1) // max(1, len(state_queue)))
    per_state_limit = min(per_state_limit, max(limit, min_per_state))

    source_counts: dict[str, int] = {}
    errors: list[str] = []
    imported = 0
    refreshed = 0
    scored = 0
    sample_ids: list[str] = []
    stopped_early = False
    stop_reason = ""

    from landsignal.services.memory_guard import should_stop_heavy_work, snapshot

    for idx, st in enumerate(state_queue):
        stop, reason = should_stop_heavy_work()
        if stop:
            stopped_early = True
            stop_reason = reason
            errors.append(f"memory_guard: paused before {st} ({reason})")
            log.warning("discover_paused_memory", state=st, reason=reason, **snapshot())
            break
        log.info(
            "discover_state_start",
            state=st,
            index=idx + 1,
            of=len(state_queue),
            per_state_limit=per_state_limit,
            inventory=sum(1 for p in store.parcels.values() if not p.is_demo),
            **snapshot(),
        )
        try:
            listings, counts, state_errors = await _pull_state_listings(
                states=[st],
                limit=per_state_limit,
                min_acres=min_acres,
                max_acres=max_acres,
                min_per_state=min_per_state,
                include_optional_providers=(idx == 0),
                settings=settings,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{st}: {exc}")
            log.warning("discover_state_failed", state=st, error=str(exc)[:200])
            continue

        for k, v in counts.items():
            source_counts[k] = source_counts.get(k, 0) + v
        errors.extend(state_errors)

        batch = await _ingest_and_score(
            store, settings, listings, limit=per_state_limit, fast=fast
        )
        imported += int(batch.get("imported") or 0)
        refreshed += int(batch.get("refreshed") or 0)
        scored += int(batch.get("scored") or 0)
        sample_ids.extend(batch.get("parcel_ids") or [])
        if batch.get("stopped_early"):
            stopped_early = True
            stop_reason = str(batch.get("stop_reason") or stop_reason)
            errors.append(f"memory_guard: paused during {st} scoring ({stop_reason})")
            # Still persist what we have, then stop the nationwide walk.
            try:
                from landsignal.store import persist_store

                persist_store(store)
            except Exception as exc:  # noqa: BLE001
                log.warning("discover_state_persist_failed", state=st, error=str(exc)[:200])
            break

        try:
            from landsignal.store import persist_store

            persist_store(store)
        except Exception as exc:  # noqa: BLE001
            log.warning("discover_state_persist_failed", state=st, error=str(exc)[:200])

        log.info(
            "discover_state_done",
            state=st,
            imported_batch=batch.get("imported"),
            scored_batch=batch.get("scored"),
            inventory=sum(1 for p in store.parcels.values() if not p.is_demo),
            **snapshot(),
        )

    return {
        "imported": imported,
        "refreshed": refreshed,
        "scored": scored,
        "source_counts": source_counts,
        "providers_used": list(source_counts.keys()),
        "parcel_ids": sample_ids[:50],
        "errors": errors,
        "fast": fast,
        "states_scanned": state_queue,
        "inventory_total": sum(1 for p in store.parcels.values() if not p.is_demo),
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "memory": snapshot(),
        "note": (
            "Progressive nationwide index: BLM LPAD + county tax-sale/surplus GIS "
            f"({sum(source_counts.values())} raw rows considered; {refreshed} existing rows refreshed). "
            "Parcels appear state-by-state — hit Show matches while the scan continues. "
            "ATTOM enriches parcel intelligence on analyze; it does not invent for-sale listings. "
            "Licensed MLS/Land.com/Crexi/Regrid remain unavailable without those API keys."
            + (f" Paused early to protect VM memory: {stop_reason}." if stopped_early else "")
        ),
    }
