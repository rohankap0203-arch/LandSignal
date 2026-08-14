"""Inventory health reporting — parcel universe vs active listings vs coverage."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from landsignal.geo_meta import US_STATES
from landsignal.inventory.providers import all_inventory_providers
from landsignal.inventory.schema import InventoryHealth, StateCoverage
from landsignal.settings import Settings, get_settings
from landsignal.store import MemoryStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def build_inventory_health(store: MemoryStore, settings: Settings | None = None) -> InventoryHealth:
    settings = settings or get_settings()
    data_mode = settings.data_mode
    name_by_code = {s["code"]: s["name"] for s in US_STATES}

    by_state_parcels: dict[str, int] = defaultdict(int)
    by_state_active: dict[str, int] = defaultdict(int)
    by_state_counties: dict[str, set[str]] = defaultdict(set)
    parcel_records = 0
    active_listings = 0
    cadastral_screens = 0
    demo_records = 0
    added_24h = 0
    updated_24h = 0
    stale = 0
    cutoff = _utcnow() - timedelta(hours=24)
    stale_cutoff = _utcnow() - timedelta(days=45)

    for parcel in store.parcels.values():
        st = (parcel.state or "").upper()
        if not st:
            continue
        if parcel.is_demo:
            demo_records += 1
            continue
        parcel_records += 1
        by_state_parcels[st] += 1
        if parcel.county:
            by_state_counties[st].add(parcel.county)
        listing = store.listing_for_parcel(parcel.id)
        if not listing:
            continue
        provider = (listing.provider_id or "").lower()
        # True marketed inventory vs cadastral/map screens
        if provider in {"public_vacant_gis", "blm_lpad"} or "vacant" in provider:
            cadastral_screens += 1
        elif listing.asking_price_usd and listing.asking_price_usd > 0:
            active_listings += 1
            by_state_active[st] += 1
        else:
            cadastral_screens += 1

        created = _aware(getattr(listing, "first_seen_at", None) or getattr(listing, "created_at", None))
        seen = _aware(getattr(listing, "last_seen_at", None))
        if created and created >= cutoff:
            added_24h += 1
        if seen and seen >= cutoff:
            updated_24h += 1
        if seen and seen < stale_cutoff:
            stale += 1

    states_covered = len(by_state_parcels)
    counties_covered = sum(len(v) for v in by_state_counties.values())

    by_state: list[StateCoverage] = []
    for code, name in sorted(name_by_code.items()):
        count = by_state_parcels.get(code, 0)
        by_state.append(
            StateCoverage(
                state_code=code,
                state_name=name,
                parcel_count=count,
                active_listing_count=by_state_active.get(code, 0),
                counties=len(by_state_counties.get(code, set())),
                healthy=count > 0,
            )
        )

    providers = [p.sync_status(settings) for p in all_inventory_providers()]

    warnings: list[str] = []
    if states_covered < 50:
        warnings.append(
            f"Only {states_covered}/50 states have indexed records — nationwide production "
            "listing providers are not fully connected (see provider status)."
        )
    zero_states = [s.state_code for s in by_state if s.parcel_count == 0]
    if "CA" in zero_states:
        warnings.append(
            "California has zero indexed parcels in the current store — treat as a data-health incident."
        )
    if data_mode != "production":
        warnings.append(
            f"DATA_MODE={data_mode}: statistics reflect development/public-GIS inventory, "
            "not licensed nationwide active listings."
        )
    if active_listings == 0 and parcel_records > 0:
        warnings.append(
            "Parcel records are mostly cadastral screens (vacant/ag GIS / BLM), not MLS-style "
            "active asking-price listings."
        )

    if data_mode == "production" and states_covered >= 45:
        label = "Production inventory"
    elif data_mode == "demo":
        label = "Demo inventory (synthetic / fixtures)"
    else:
        label = "Development inventory (public GIS screens + free federal feeds)"

    return InventoryHealth(
        data_mode=data_mode,  # type: ignore[arg-type]
        states_covered=states_covered,
        states_total=50,
        counties_covered=counties_covered,
        parcel_records=parcel_records,
        active_land_listings=active_listings,
        cadastral_screens=cadastral_screens,
        demo_records=demo_records,
        listings_added_24h=added_24h,
        listings_updated_24h=updated_24h,
        stale_listings=stale,
        by_state=by_state,
        providers=providers,
        inventory_label=label,
        warnings=warnings,
    )


def inventory_health_dict(store: MemoryStore, settings: Settings | None = None) -> dict[str, Any]:
    return build_inventory_health(store, settings).model_dump(mode="json")
