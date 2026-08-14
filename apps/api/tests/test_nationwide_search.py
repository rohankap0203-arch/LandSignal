"""Automated nationwide search / inventory regression tests.

Covers:
- 50-state geographic catalog completeness
- hard-filter AND semantics (state / region / price / acres)
- strategy + hold as ranking-only
- California broad-search regression
- exact vs near match separation
- provider adapter scaffolding
- inventory health metrics distinction
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from landsignal.geo_meta import US_STATES, region_matches, regions_for_state, search_meta_payload
from landsignal.inventory.dedupe import merge_duplicates, strong_keys
from landsignal.inventory.health import build_inventory_health
from landsignal.inventory.providers import all_inventory_providers
from landsignal.models import ListingRecord, ParcelRecord, ScoreRecord, Signal, Strategy
from landsignal.settings import Settings
from landsignal.store import MemoryStore


def _square(lon: float, lat: float, acres: float = 10.0) -> list[list[list[float]]]:
    side = max(0.001, (acres**0.5) * 0.001)
    return [
        [
            [lon, lat],
            [lon + side, lat],
            [lon + side, lat + side],
            [lon, lat + side],
            [lon, lat],
        ]
    ]


def _seed_parcel(
    store: MemoryStore,
    *,
    state: str,
    county: str,
    acres: float,
    price: float | None,
    lat: float,
    lon: float,
    strategy: Strategy = Strategy.LAND_BANK,
    opportunity: float = 70.0,
    external_id: str | None = None,
    provider_id: str = "public_vacant_gis",
) -> ParcelRecord:
    apn = external_id or f"{state.lower()}-{county.lower()}-{uuid4().hex[:8]}"
    parcel = ParcelRecord(
        parcel_id=apn,
        apn=apn,
        address=f"{county} County, {state}",
        county=county,
        state=state,
        latitude=lat,
        longitude=lon,
        polygon=_square(lon, lat, acres),
        acreage=acres,
        geometry_confidence=80,
        is_demo=False,
    )
    listing = ListingRecord(
        parcel_id=parcel.id,
        provider_id=provider_id,
        external_id=apn,
        asking_price_usd=price,
        price_per_acre_usd=(price / acres) if price and acres else None,
        listed_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        days_on_market=10,
        title=f"{county} {state} · {acres} ac",
        description="test inventory",
        is_demo=False,
        raw={"ask_role": "assessed_land"} if provider_id == "public_vacant_gis" else {},
    )
    score = ScoreRecord(
        parcel_id=parcel.id,
        listing_id=listing.id,
        opportunity=opportunity,
        asymmetry=50,
        risk=30,
        confidence=60,
        deal_readiness=55,
        signal=Signal.STRONG if opportunity >= 70 else Signal.WATCH,
        best_strategy=strategy,
        secondary_strategy=Strategy.RECREATIONAL,
        estimated_value_usd=(price or 0) * 1.2 if price else 100_000,
        asking_discount_pct=-10 if price else None,
        algorithm_version="test",
        weight_version="test",
        input_hash=f"test-{apn}",
    )
    store.parcels[parcel.id] = parcel
    store.listings[listing.id] = listing
    store.index_listing(listing)
    store.scores[parcel.id] = [score]
    return parcel


@pytest.fixture
def nationwide_store() -> MemoryStore:
    store = MemoryStore()
    coords = {
        "CA": (34.1, -117.3, "San Bernardino"),
        "TX": (31.0, -99.0, "McCulloch"),
        "FL": (28.5, -81.5, "Lake"),
        "NY": (42.7, -73.8, "Albany"),
        "WA": (47.5, -120.5, "Chelan"),
    }
    for s in US_STATES:
        code = s["code"]
        if code == "DC":
            continue
        lat, lon, county = coords.get(code, (39.0, -98.0, "Statewide"))
        lat = lat + (ord(code[0]) % 5) * 0.01
        lon = lon - (ord(code[-1]) % 5) * 0.01
        price = 250_000.0 if code != "WY" else 80_000.0
        acres = 25.0 if code != "RI" else 3.0
        _seed_parcel(
            store,
            state=code,
            county=county if code in coords else f"{s['name']} County",
            acres=acres,
            price=price,
            lat=lat,
            lon=lon,
            opportunity=60 + (ord(code[0]) % 20),
        )
    _seed_parcel(
        store,
        state="CA",
        county="Riverside",
        acres=40,
        price=400_000,
        lat=33.7,
        lon=-116.2,
        strategy=Strategy.DEVELOPMENT,
        opportunity=82,
        external_id="ca-riverside-40",
    )
    _seed_parcel(
        store,
        state="CA",
        county="Shasta",
        acres=12,
        price=180_000,
        lat=40.6,
        lon=-122.4,
        strategy=Strategy.TIMBER,
        opportunity=71,
        external_id="ca-shasta-12",
    )
    _seed_parcel(
        store,
        state="CA",
        county="Fresno",
        acres=55,
        price=520_000,
        lat=36.7,
        lon=-119.8,
        strategy=Strategy.FARMLAND,
        opportunity=75,
        external_id="ca-fresno-55",
    )
    return store


def test_geo_catalog_has_all_50_states():
    codes = [s["code"] for s in US_STATES if s["code"] != "DC"]
    assert len(codes) == 50
    assert len(set(codes)) == 50
    assert all("fips" in s and s["fips"] for s in US_STATES)
    assert "CA" in codes and "TX" in codes and "WY" in codes


def test_every_state_has_region_taxonomy():
    for s in US_STATES:
        regs = regions_for_state(s["code"])
        assert regs[0] == "Any"
        assert len(regs) >= 2


def test_california_macro_regions_map_to_counties():
    assert region_matches(
        region="Southern California", state="CA", county="San Bernardino", title="vacant"
    )
    assert region_matches(region="Northern California", state="CA", county="Shasta", title="x")
    assert region_matches(region="Central California", state="CA", county="Fresno", title="x")
    assert not region_matches(
        region="Southern California", state="CA", county="Shasta", title="timber north"
    )


def test_search_meta_lists_all_states():
    payload = search_meta_payload([])
    assert len(payload["state_codes"]) == 52  # Any + 50 + DC
    assert "CA" in payload["regions_by_state"]
    assert "Southern California" in payload["regions_by_state"]["CA"]


@pytest.mark.asyncio
async def test_california_broad_search_not_zero(nationwide_store, monkeypatch):
    from landsignal.routers import api as api_mod

    monkeypatch.setattr(api_mod, "get_store", lambda *a, **k: nationwide_store)
    monkeypatch.setattr(api_mod, "get_settings", lambda: Settings(demo_seed=False, data_mode="development"))
    rows = await api_mod.radar(state="CA", broaden=True, limit=100)
    exact = [r for r in rows if r.match_tier == "exact"]
    assert len(exact) >= 1
    assert all((r.state or "").upper() == "CA" for r in exact)


@pytest.mark.asyncio
async def test_hard_filters_and_semantics(nationwide_store, monkeypatch):
    from landsignal.routers import api as api_mod

    monkeypatch.setattr(api_mod, "get_store", lambda *a, **k: nationwide_store)
    monkeypatch.setattr(api_mod, "get_settings", lambda: Settings(demo_seed=False))
    rows = await api_mod.radar(
        state="CA",
        region="Southern California",
        min_price=100_000,
        max_price=500_000,
        min_acres=10,
        max_acres=50,
        broaden=False,
        limit=100,
    )
    assert rows, "expected at least Riverside 40ac/$400k"
    for r in rows:
        assert r.match_tier == "exact"
        assert (r.state or "").upper() == "CA"
        assert r.ask is not None and 100_000 <= r.ask <= 500_000
        assert r.acres is not None and 10 <= r.acres <= 50
        assert region_matches(
            region="Southern California", state=r.state, county=r.county, title=r.property_name
        )


@pytest.mark.asyncio
async def test_hard_filters_exclude_out_of_band(nationwide_store, monkeypatch):
    from landsignal.routers import api as api_mod

    monkeypatch.setattr(api_mod, "get_store", lambda *a, **k: nationwide_store)
    monkeypatch.setattr(api_mod, "get_settings", lambda: Settings(demo_seed=False))
    rows = await api_mod.radar(
        state="CA",
        min_price=100_000,
        max_price=500_000,
        min_acres=10,
        max_acres=50,
        broaden=False,
        limit=100,
    )
    for r in rows:
        assert r.ask is not None and r.ask <= 500_000
        assert r.acres is not None and r.acres <= 50


@pytest.mark.asyncio
async def test_strategy_ranks_but_does_not_exclude(nationwide_store, monkeypatch):
    from landsignal.routers import api as api_mod

    monkeypatch.setattr(api_mod, "get_store", lambda *a, **k: nationwide_store)
    monkeypatch.setattr(api_mod, "get_settings", lambda: Settings(demo_seed=False))
    without = await api_mod.radar(state="CA", broaden=False, limit=100)
    with_strat = await api_mod.radar(state="CA", strategy="DEVELOPMENT", broaden=False, limit=100)
    assert len(with_strat) == len(without)
    assert all((r.state or "").upper() == "CA" for r in with_strat)


@pytest.mark.asyncio
async def test_near_matches_separated_when_exact_empty(nationwide_store, monkeypatch):
    from landsignal.routers import api as api_mod

    monkeypatch.setattr(api_mod, "get_store", lambda *a, **k: nationwide_store)
    monkeypatch.setattr(api_mod, "get_settings", lambda: Settings(demo_seed=False))
    rows = await api_mod.radar(
        state="CA",
        min_price=401_000,
        max_price=410_000,
        min_acres=39,
        max_acres=41,
        broaden=True,
        limit=20,
    )
    if rows:
        assert all(r.match_tier == "near" for r in rows)
        assert all(r.near_match_reason for r in rows)
        assert all((r.state or "").upper() == "CA" for r in rows)


@pytest.mark.asyncio
async def test_all_50_states_broad_inventory(nationwide_store, monkeypatch):
    from landsignal.routers import api as api_mod

    monkeypatch.setattr(api_mod, "get_store", lambda *a, **k: nationwide_store)
    monkeypatch.setattr(api_mod, "get_settings", lambda: Settings(demo_seed=False))
    missing: list[str] = []
    for s in US_STATES:
        if s["code"] == "DC":
            continue
        rows = await api_mod.radar(state=s["code"], broaden=False, limit=5)
        exact = [r for r in rows if r.match_tier == "exact"]
        if not exact:
            missing.append(s["code"])
        else:
            assert all((r.state or "").upper() == s["code"] for r in exact)
    assert not missing, f"states missing broad inventory in test store: {missing}"


@pytest.mark.asyncio
async def test_custom_numeric_ranges(nationwide_store, monkeypatch):
    from landsignal.routers import api as api_mod

    monkeypatch.setattr(api_mod, "get_store", lambda *a, **k: nationwide_store)
    monkeypatch.setattr(api_mod, "get_settings", lambda: Settings(demo_seed=False))
    rows = await api_mod.radar(
        state="CA",
        min_price=137_500,
        max_price=638_250,
        min_acres=17.5,
        max_acres=83,
        broaden=False,
        limit=50,
    )
    for r in rows:
        assert 137_500 <= (r.ask or 0) <= 638_250
        assert 17.5 <= (r.acres or 0) <= 83


def test_inventory_health_distinguishes_parcels_vs_active(nationwide_store):
    settings = Settings(data_mode="development", demo_seed=False)
    health = build_inventory_health(nationwide_store, settings)
    assert health.states_covered >= 50
    assert health.parcel_records >= 50
    assert "Development inventory" in health.inventory_label
    assert health.states_total == 50
    ca = next(s for s in health.by_state if s.state_code == "CA")
    assert ca.parcel_count >= 1
    assert ca.healthy


def test_provider_adapters_report_not_configured_without_keys():
    settings = Settings(data_mode="development")
    statuses = [p.sync_status(settings) for p in all_inventory_providers()]
    by_id = {s.provider_id: s for s in statuses}
    assert by_id["attom"].status == "NOT_CONFIGURED"
    assert by_id["public_records"].status == "HEALTHY"
    assert by_id["blm_lpad"].status == "HEALTHY"


def test_dedupe_merges_same_apn_across_providers():
    rows = [
        {
            "state": "CA",
            "apn": "123-456-789",
            "provider_id": "attom",
            "external_id": "a1",
            "acreage": 10,
            "latitude": 34.0,
            "longitude": -117.0,
            "asking_price_usd": 100_000,
        },
        {
            "state": "CA",
            "apn": "123-456-789",
            "provider_id": "mls_reso",
            "external_id": "m1",
            "acreage": 10.1,
            "latitude": 34.0,
            "longitude": -117.0,
            "asking_price_usd": 105_000,
            "source_url": "https://example.com",
            "description": "fuller",
        },
    ]
    merged, n = merge_duplicates(rows)
    assert n >= 1
    assert len(merged) == 1
    assert strong_keys(rows[0])


@pytest.mark.asyncio
async def test_search_estimate_facets(nationwide_store, monkeypatch):
    from landsignal.routers import api as api_mod

    monkeypatch.setattr(api_mod, "get_store", lambda *a, **k: nationwide_store)
    monkeypatch.setattr(api_mod, "get_settings", lambda: Settings(demo_seed=False))
    est = await api_mod.search_estimate(state="CA")
    assert est["exact_match_count"] >= 1
    assert isinstance(est["facets"]["regions"], list)
    assert isinstance(est["facets"]["price_ranges"], list)
