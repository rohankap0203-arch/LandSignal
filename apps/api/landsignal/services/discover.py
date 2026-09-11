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
    from landsignal.services.land_gate import stamp_structure_flags

    listing.raw = slim_listing_raw(
        stamp_structure_flags(
            merged,
            title=listing.title,
            description=listing.description,
            address=str(merged.get("address") or merged.get("Address") or ""),
        )
    )
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
        from landsignal.services.parcel_outline import compact_polygon

        outline = compact_polygon(raw.get("polygon"))
        if outline:
            parcel.polygon = outline
            parcel.geometry_confidence = 88.0
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


def _inventory_by_state(store: MemoryStore) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in store.parcels.values():
        if p.is_demo or not p.state:
            continue
        st = p.state.upper()
        counts[st] = counts.get(st, 0) + 1
    return counts


def _coverage_first_queue(
    store: MemoryStore,
    states: list[str] | None,
    *,
    min_per_state: int,
) -> list[str]:
    """Prefer states with zero / thin inventory so all 50 appear before we deepen A–I.

    When the caller did not pin an explicit state list, skip states already at the
    per-state floor — otherwise every nationwide run restarts at AK and stalls
    the map at ~14 alphabetical states.
    """
    wired = _wired_states(states)
    counts = _inventory_by_state(store)
    if states is None:
        gaps = [st for st in wired if counts.get(st, 0) < min_per_state]
        if gaps:
            wired = gaps
    # 0 inventory first, then below floor, then (if explicit) already-full.
    return sorted(
        wired,
        key=lambda st: (
            0 if counts.get(st, 0) <= 0 else 1 if counts.get(st, 0) < min_per_state else 2,
            st,
        ),
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
            continue
        from landsignal.services.land_gate import is_land_inventory, stamp_structure_flags

        raw_for_gate = row.get("raw") if isinstance(row.get("raw"), dict) else row
        if not is_land_inventory(
            provider_id=row.get("provider_id"),
            title=str(row.get("title") or ""),
            description=str(row.get("description") or ""),
            address=str(row.get("address") or ""),
            acreage=acres if isinstance(acres, (int, float)) else None,
            raw=raw_for_gate if isinstance(raw_for_gate, dict) else None,
        ):
            continue
        # Stamp structure so radar can hard-split Property on site vs vacant land.
        stamped = stamp_structure_flags(
            raw_for_gate if isinstance(raw_for_gate, dict) else {},
            title=str(row.get("title") or ""),
            description=str(row.get("description") or ""),
            address=str(row.get("address") or ""),
        )
        row = {**row, "raw": stamped, "has_structure": bool(stamped.get("has_structure"))}
        # Keep a compact REAL GIS outline only (≤64 verts) — never invent squares.
        from landsignal.services.parcel_outline import compact_polygon

        outline = compact_polygon(row.get("polygon"))
        row = {**row, "polygon": outline}
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
    from landsignal.models import ScoreRecord, Signal
    from landsignal.scoring.engine import ALGORITHM_VERSION, WEIGHT_VERSION
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
    stubbed = 0
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
        from landsignal.services.parcel_outline import compact_polygon

        outline = compact_polygon(raw.get("polygon") or parcel.polygon)
        parcel.polygon = outline
        if outline:
            parcel.geometry_confidence = 88.0
        store.parcels[parcel.id] = parcel
        store.listings[listing.id] = listing
        parcel_ids.append(parcel.id)
        to_score.append(parcel.id)
        new_parcel_ids.add(parcel.id)

    # Fast nationwide discover: stub-score every new parcel so Show Matches can
    # list them immediately. Full live analyze still runs on parcel open.
    # Without this, scoring a 20k CA batch blocked thin-state deepen for many minutes.
    if fast:
        for pid in to_score:
            if store.latest_score(pid) is not None:
                continue
            listing = store.listing_for_parcel(pid)
            store.scores.setdefault(pid, []).append(
                ScoreRecord(
                    parcel_id=pid,
                    listing_id=listing.id if listing else None,
                    algorithm_version=ALGORITHM_VERSION,
                    weight_version=WEIGHT_VERSION,
                    opportunity=48.0,
                    risk=45.0,
                    confidence=28.0,
                    asymmetry=0.0,
                    signal=Signal.WATCH,
                    deal_readiness=35.0,
                    explanations=[
                        "Bulk-indexed from public GIS. Open the parcel for full live analysis."
                    ],
                    why_interesting=["Public cadastral inventory with real assessor geometry."],
                    input_hash="discover_stub_v1",
                    input_snapshot={"stub": True},
                )
            )
            stubbed += 1
        trim_score_lists(store, keep=1)
        return {
            "imported": len(new_parcel_ids),
            "refreshed": refreshed,
            "scored": stubbed,
            "parcel_ids": [str(p) for p in parcel_ids[:50]],
            "stopped_early": False,
            "stop_reason": "",
            "stubbed": True,
            "memory": snapshot(),
        }

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

    return {
        "imported": len(new_parcel_ids),
        "refreshed": refreshed,
        "scored": scored,
        "parcel_ids": [str(p) for p in parcel_ids[:50]],
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "memory": snapshot(),
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
    paint: bool = False,
    page_offset: int = 0,
) -> tuple[list[dict], dict[str, int], list[str]]:
    blm = BlmLpadProvider()
    tax = PublicTaxSaleProvider()
    surplus = PublicSurplusProvider()
    wired = max(1, len(states))
    # Paint mode: enough per state to leave real Show Matches, still fast nationwide.
    if paint:
        tax_limit = max(200, min(limit, 1200))
        tax_min = max(200, min(min_per_state, tax_limit))
        blm_limit = min(1500, max(200, tax_limit))
        surplus_limit = min(400, max(50, tax_limit // 3))
        tax_offset = 0
    else:
        tax_limit = max(limit, min_per_state * wired)
        tax_limit = min(1_000_000, max(800, tax_limit))
        tax_min = min_per_state
        blm_limit = min(40000, max(3000, min_per_state * 2))
        surplus_limit = min(3000, max(150, min_per_state // 2))
        # Skip the already-painted head window so deepen ingests new parcels.
        tax_offset = max(0, int(page_offset or 0))

    blm_res, tax_res, surplus_res = await asyncio.gather(
        blm.search_listings(
            {
                "limit": blm_limit,
                "min_acres": max(1.0, min_acres),
                "max_acres": max_acres,
                "states": states,
            }
        ),
        tax.search_listings(
            {
                "limit": tax_limit,
                "min_per_state": tax_min,
                "min_acres": min_acres,
                "offset": tax_offset,
                "states": states,
            }
        ),
        surplus.search_listings(
            {
                "limit": surplus_limit,
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
    state_queue = _coverage_first_queue(store, states, min_per_state=min_per_state)
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
    states_done: list[str] = []

    from landsignal.services.memory_guard import should_stop_heavy_work, snapshot

    # Pull several gap states at once (GIS I/O bound), then ingest quickly with stub
    # scores so every thin state gets depth — not just the first fat GIS state.
    wave_size = 8
    # Hard cap per state so a dead ArcGIS endpoint cannot stall the nationwide walk.
    # Deepen passes need enough time for statewide vacant GIS pages (~2–3k/state).
    state_wall_clock_s = 320.0
    log.info(
        "discover_coverage_queue",
        states=len(state_queue),
        sample=state_queue[:12],
        inventory_by_state_n=len(_inventory_by_state(store)),
        min_per_state=min_per_state,
        **snapshot(),
    )

    async def _run_one_state(
        st: str, *, include_optional: bool, paint: bool, existing_n: int = 0
    ) -> dict[str, Any]:
        pull_limit = min(per_state_limit, 2500) if paint else per_state_limit
        pull_min = min(min_per_state, pull_limit) if paint else min_per_state
        # Deepen past the paint head so ArcGIS offset pages return unseen parcels.
        page_offset = 0 if paint else max(0, int(existing_n or 0))
        try:
            listings, counts, state_errors = await asyncio.wait_for(
                _pull_state_listings(
                    states=[st],
                    limit=pull_limit,
                    min_acres=min_acres,
                    max_acres=max_acres,
                    min_per_state=pull_min,
                    include_optional_providers=include_optional,
                    settings=settings,
                    paint=paint,
                    page_offset=page_offset,
                ),
                timeout=state_wall_clock_s,
            )
        except asyncio.TimeoutError:
            log.warning("discover_state_wall_timeout", state=st, timeout_s=state_wall_clock_s)
            return {
                "state": st,
                "listings": [],
                "counts": {},
                "errors": [f"{st}: wall-clock timeout ({state_wall_clock_s:.0f}s)"],
                "batch": None,
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("discover_state_failed", state=st, error=str(exc)[:200])
            return {
                "state": st,
                "listings": [],
                "counts": {},
                "errors": [f"{st}: {exc}"],
                "batch": None,
            }
        return {
            "state": st,
            "listings": listings,
            "counts": counts,
            "errors": state_errors,
            "batch": None,
        }

    for wave_start in range(0, len(state_queue), wave_size):
        stop, reason = should_stop_heavy_work()
        if stop:
            stopped_early = True
            stop_reason = reason
            errors.append(f"memory_guard: paused before wave ({reason})")
            log.warning("discover_paused_memory", reason=reason, **snapshot())
            break

        wave = state_queue[wave_start : wave_start + wave_size]
        live_counts = _inventory_by_state(store)
        log.info(
            "discover_wave_start",
            states=wave,
            index=wave_start + 1,
            of=len(state_queue),
            inventory=sum(1 for p in store.parcels.values() if not p.is_demo),
            **snapshot(),
        )
        pulled = await asyncio.gather(
            *[
                _run_one_state(
                    st,
                    include_optional=(wave_start == 0 and i == 0),
                    paint=live_counts.get(st, 0) <= 0,
                    existing_n=int(live_counts.get(st, 0) or 0),
                )
                for i, st in enumerate(wave)
            ]
        )

        for item in pulled:
            st = item["state"]
            for k, v in (item.get("counts") or {}).items():
                source_counts[k] = source_counts.get(k, 0) + v
            errors.extend(item.get("errors") or [])

            stop, reason = should_stop_heavy_work()
            if stop:
                stopped_early = True
                stop_reason = reason
                errors.append(f"memory_guard: paused before ingest {st} ({reason})")
                break

            listings = item.get("listings") or []
            if not listings:
                states_done.append(st)
                continue

            # First-pass paint for brand-new states: thicker batch so coverage + depth
            # land together; later gap-fill deepens toward min_per_state (~5000 → ~255k).
            state_limit = per_state_limit
            if live_counts.get(st, 0) <= 0:
                state_limit = min(per_state_limit, 1500)

            batch = await _ingest_and_score(
                store, settings, listings, limit=state_limit, fast=fast
            )
            imported += int(batch.get("imported") or 0)
            refreshed += int(batch.get("refreshed") or 0)
            scored += int(batch.get("scored") or 0)
            sample_ids.extend(batch.get("parcel_ids") or [])
            states_done.append(st)

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
                states_with_inventory=len(_inventory_by_state(store)),
                **snapshot(),
            )
            if batch.get("stopped_early"):
                stopped_early = True
                stop_reason = str(batch.get("stop_reason") or stop_reason)
                errors.append(f"memory_guard: paused during {st} scoring ({stop_reason})")
                break
        if stopped_early:
            break

    # Keep deepening until every state hits the ~4k floor (~204k nationwide)
    # or we hit memory / import budget. Always serve the thinnest states first.
    deepen_passes = 0
    while not stopped_early and deepen_passes < 36:
        by_now = _inventory_by_state(store)
        gaps = sorted(
            (st for st in state_queue if by_now.get(st, 0) < min_per_state),
            key=lambda st: (int(by_now.get(st, 0) or 0), st),
        )
        if not gaps:
            break
        remaining = max(0, int(limit) - imported - refreshed)
        if remaining < 50:
            break
        deepen_passes += 1
        log.info(
            "discover_deepen_pass",
            pass_n=deepen_passes,
            gaps=len(gaps),
            sample=gaps[:12],
            remaining=remaining,
            min_per_state=min_per_state,
            **snapshot(),
        )
        for i in range(0, len(gaps), wave_size):
            stop, reason = should_stop_heavy_work()
            if stop:
                stopped_early = True
                stop_reason = reason
                errors.append(f"memory_guard: paused deepen ({reason})")
                break
            wave = gaps[i : i + wave_size]
            live_counts = _inventory_by_state(store)
            pulled = await asyncio.gather(
                *[
                    _run_one_state(
                        st,
                        include_optional=True,
                        paint=False,
                        existing_n=int(live_counts.get(st, 0) or 0),
                    )
                    for st in wave
                ]
            )
            for item in pulled:
                st = item["state"]
                for k, v in (item.get("counts") or {}).items():
                    source_counts[k] = source_counts.get(k, 0) + v
                errors.extend(item.get("errors") or [])
                listings = item.get("listings") or []
                if not listings:
                    continue
                need = max(0, min_per_state - int(live_counts.get(st, 0) or 0))
                # Ask for a fat page past the current head so deepen actually grows.
                state_limit = max(400, min(max(need, 1500), remaining, per_state_limit))
                batch = await _ingest_and_score(
                    store, settings, listings, limit=state_limit, fast=fast
                )
                imported += int(batch.get("imported") or 0)
                refreshed += int(batch.get("refreshed") or 0)
                scored += int(batch.get("scored") or 0)
                sample_ids.extend(batch.get("parcel_ids") or [])
                if st not in states_done:
                    states_done.append(st)
                try:
                    from landsignal.store import persist_store

                    persist_store(store)
                except Exception as exc:  # noqa: BLE001
                    log.warning("discover_deepen_persist_failed", state=st, error=str(exc)[:200])
                if batch.get("stopped_early"):
                    stopped_early = True
                    stop_reason = str(batch.get("stop_reason") or stop_reason)
                    break
                remaining = max(0, int(limit) - imported - refreshed)
            if stopped_early:
                break

    # Surplus fill: after every state has had deepen attempts, grow ALL states that
    # still have headroom — thinnest first — until ~255k nationwide. Never let one
    # fat state (e.g. CA) monopolize the wave while MS/GA/OH stay near zero.
    target_total = max(
        min_per_state * 51,
        int(getattr(settings, "discover_target_total", 255_000) or 255_000),
    )
    max_per_state = max(
        min_per_state,
        int(getattr(settings, "discover_max_per_state", 15_000) or 15_000),
    )
    surplus_passes = 0
    while not stopped_early and surplus_passes < 24:
        by_now = _inventory_by_state(store)
        inv_now = sum(1 for p in store.parcels.values() if not p.is_demo)
        if inv_now >= target_total:
            break
        remaining = max(0, int(limit) - imported - refreshed)
        if remaining < 100:
            break
        need_total = target_total - inv_now
        # Thinnest-first across every state still under the per-state ceiling.
        wave_pool = sorted(
            (st for st in state_queue if by_now.get(st, 0) < max_per_state),
            key=lambda st: (int(by_now.get(st, 0) or 0), st),
        )[:32]
        if not wave_pool:
            break
        surplus_passes += 1
        log.info(
            "discover_surplus_pass",
            pass_n=surplus_passes,
            inventory=inv_now,
            target_total=target_total,
            need_total=need_total,
            wave=wave_pool[:16],
            remaining=remaining,
            **snapshot(),
        )
        for i in range(0, len(wave_pool), wave_size):
            stop, reason = should_stop_heavy_work()
            if stop:
                stopped_early = True
                stop_reason = reason
                errors.append(f"memory_guard: paused surplus ({reason})")
                break
            wave = wave_pool[i : i + wave_size]
            live_counts = _inventory_by_state(store)
            pulled = await asyncio.gather(
                *[
                    _run_one_state(
                        st,
                        include_optional=True,
                        paint=False,
                        existing_n=int(live_counts.get(st, 0) or 0),
                    )
                    for st in wave
                ]
            )
            for item in pulled:
                st = item["state"]
                for k, v in (item.get("counts") or {}).items():
                    source_counts[k] = source_counts.get(k, 0) + v
                errors.extend(item.get("errors") or [])
                listings = item.get("listings") or []
                if not listings:
                    continue
                headroom = max(0, max_per_state - int(live_counts.get(st, 0) or 0))
                if headroom < 50:
                    continue
                inv_live = sum(1 for p in store.parcels.values() if not p.is_demo)
                need_now = max(0, target_total - inv_live)
                # Equal-ish chunks so 8 thin states each grow instead of one eating 6k.
                state_limit = max(
                    300,
                    min(headroom, need_now // max(1, len(wave)), remaining, 2500),
                )
                if state_limit < 50:
                    continue
                batch = await _ingest_and_score(
                    store, settings, listings, limit=state_limit, fast=fast
                )
                imported += int(batch.get("imported") or 0)
                refreshed += int(batch.get("refreshed") or 0)
                scored += int(batch.get("scored") or 0)
                sample_ids.extend(batch.get("parcel_ids") or [])
                if st not in states_done:
                    states_done.append(st)
                try:
                    from landsignal.store import persist_store

                    persist_store(store)
                except Exception as exc:  # noqa: BLE001
                    log.warning("discover_surplus_persist_failed", state=st, error=str(exc)[:200])
                if batch.get("stopped_early"):
                    stopped_early = True
                    stop_reason = str(batch.get("stop_reason") or stop_reason)
                    break
                remaining = max(0, int(limit) - imported - refreshed)
                if sum(1 for p in store.parcels.values() if not p.is_demo) >= target_total:
                    break
            if stopped_early or sum(1 for p in store.parcels.values() if not p.is_demo) >= target_total:
                break

    by_state = _inventory_by_state(store)
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
        "states_done": states_done,
        "deepen_passes": deepen_passes,
        "surplus_passes": surplus_passes,
        "inventory_total": sum(1 for p in store.parcels.values() if not p.is_demo),
        "inventory_states": len(by_state),
        "inventory_by_state": dict(sorted(by_state.items())),
        "stopped_early": stopped_early,
        "stop_reason": stop_reason,
        "memory": snapshot(),
        "note": (
            "Coverage-first nationwide index: gap states (0 / below floor) are filled before "
            "deepening states already at the per-state target, then surplus-fill toward "
            f"~{target_total:,} total from rich public GIS feeds. "
            f"{sum(source_counts.values())} raw rows considered; {refreshed} existing rows refreshed. "
            f"{len(by_state)} states currently in live inventory. "
            f"Deepen passes={deepen_passes}; surplus passes={surplus_passes}; "
            f"floor={min_per_state}/state (cap {max_per_state}). "
            "ATTOM enriches parcel intelligence on analyze; it does not invent for-sale listings."
            + (f" Paused early to protect VM memory: {stop_reason}." if stopped_early else "")
        ),
    }
