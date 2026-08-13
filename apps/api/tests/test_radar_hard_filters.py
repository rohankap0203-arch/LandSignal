"""Radar must hard-enforce stacked price/acre/state filters (never broaden them away)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from landsignal.main import app
from landsignal.models import ListingRecord, ParcelRecord, ScoreRecord, Signal, Strategy
from landsignal.store import MemoryStore


def _seed_scored_parcel(
    store: MemoryStore,
    *,
    state: str,
    county: str,
    acreage: float,
    ask: float | None,
    external_id: str,
    assessed_land: float | None = None,
    strategy: Strategy = Strategy.FARMLAND,
) -> None:
    parcel = ParcelRecord(
        parcel_id=external_id,
        apn=external_id,
        address=f"{county} County, {state}",
        county=county,
        state=state,
        latitude=27.5,
        longitude=-81.5,
        acreage=acreage,
        is_demo=False,
    )
    raw: dict = {"ask_role": "assessed_land"}
    if assessed_land is not None:
        raw["LND_VAL"] = assessed_land
    listing = ListingRecord(
        parcel_id=parcel.id,
        provider_id="public_vacant_gis",
        external_id=external_id,
        title=f"{state} vacant · {acreage} ac · {county}",
        asking_price_usd=ask,
        price_per_acre_usd=(ask / acreage) if ask and acreage else None,
        status="ACTIVE",
        is_demo=False,
        raw=raw,
    )
    store.parcels[parcel.id] = parcel
    store.listings[listing.id] = listing
    store.index_listing(listing)
    store.scores[parcel.id] = [
        ScoreRecord(
            parcel_id=parcel.id,
            listing_id=listing.id,
            algorithm_version="test",
            weight_version="test",
            opportunity=72.0,
            risk=28.0,
            confidence=80.0,
            asymmetry=10.0,
            signal=Signal.WATCH,
            best_strategy=strategy,
            secondary_strategy=Strategy.LAND_BANK,
            estimated_value_usd=ask or assessed_land or 100_000,
            asking_discount_pct=None,
            deal_readiness=55.0,
            input_hash=f"test-{external_id}",
        )
    ]


@pytest.fixture
def isolated_store(monkeypatch):
    store = MemoryStore()
    _seed_scored_parcel(
        store, state="FL", county="Polk", acreage=0.4, ask=12_000, external_id="fl-tiny"
    )
    _seed_scored_parcel(
        store, state="FL", county="Highlands", acreage=25.0, ask=180_000, external_id="fl-25"
    )
    _seed_scored_parcel(
        store, state="FL", county="Okeechobee", acreage=80.0, ask=450_000, external_id="fl-80"
    )
    _seed_scored_parcel(
        store, state="TX", county="Brewster", acreage=40.0, ask=90_000, external_id="tx-40"
    )
    monkeypatch.setattr("landsignal.routers.api.get_store", lambda _seed=False: store)
    yield store


@pytest.mark.asyncio
async def test_fl_min_acres_excludes_subacre_even_when_broaden(isolated_store):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={"state": "FL", "min_acres": 20, "broaden": True, "limit": 50},
        )
    assert r.status_code == 200
    rows = r.json()
    assert rows, "expected FL 20+ acre matches from seeded inventory"
    assert all(row["state"] == "FL" for row in rows)
    assert all((row.get("acres") or 0) >= 20 for row in rows)
    assert not any((row.get("acres") or 0) < 1 for row in rows)


@pytest.mark.asyncio
async def test_stacked_state_acres_price_filters(isolated_store):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={
                "state": "FL",
                "min_acres": 20,
                "max_acres": 50,
                "min_price": 100_000,
                "max_price": 250_000,
                "broaden": True,
                "limit": 50,
            },
        )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["state"] == "FL"
    assert 20 <= row["acres"] <= 50
    assert 100_000 <= row["ask"] <= 250_000


@pytest.mark.asyncio
async def test_no_matches_when_band_empty_does_not_leak_other_acres(isolated_store):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={"state": "FL", "min_acres": 5000, "broaden": True, "limit": 50},
        )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_budget_uses_assessed_land_when_unpriced(isolated_store):
    _seed_scored_parcel(
        isolated_store,
        state="FL",
        county="Hardee",
        acreage=30.0,
        ask=None,
        assessed_land=220_000,
        external_id="fl-assessed-30",
    )
    _seed_scored_parcel(
        isolated_store,
        state="FL",
        county="DeSoto",
        acreage=35.0,
        ask=None,
        assessed_land=900_000,
        external_id="fl-assessed-expensive",
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={
                "state": "FL",
                "min_acres": 20,
                "max_price": 250_000,
                "broaden": True,
                "limit": 50,
            },
        )
    assert r.status_code == 200
    rows = r.json()
    assert rows
    assert all((row.get("acres") or 0) >= 20 for row in rows)
    assert all((row.get("ask") or 0) <= 250_000 for row in rows)
    assert not any(row.get("acres") == 35.0 for row in rows)


@pytest.mark.asyncio
async def test_strategy_filter_is_hard(isolated_store):
    _seed_scored_parcel(
        isolated_store,
        state="FL",
        county="Levy",
        acreage=50.0,
        ask=200_000,
        external_id="fl-energy",
        strategy=Strategy.ENERGY,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={
                "state": "FL",
                "min_acres": 20,
                "strategy": "ENERGY",
                "broaden": True,
                "limit": 50,
            },
        )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["best_strategy"] == "ENERGY"


@pytest.mark.asyncio
async def test_model_estimate_never_bypasses_budget_filter(isolated_store, monkeypatch):
    """Huge estimated_value must not make a cheap ask look like it fails ≤$250k — or pass wrongly."""
    store = isolated_store
    # Cheap ask, absurd model value (the UX bug users read as "filter failed")
    _seed_scored_parcel(
        store,
        state="FL",
        county="Osceola",
        acreage=900.0,
        ask=110_000,
        external_id="fl-huge-model",
    )
    parcel_ids = [p.id for p in store.parcels.values() if p.apn == "fl-huge-model"]
    assert parcel_ids
    scores = store.scores[parcel_ids[0]]
    scores[0].estimated_value_usd = 7_000_000

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={
                "state": "FL",
                "min_acres": 20,
                "max_price": 250_000,
                "broaden": False,
                "limit": 50,
            },
        )
    assert r.status_code == 200
    rows = r.json()
    assert rows
    hit = next(row for row in rows if row.get("acres") == 900.0)
    assert hit["ask"] == 110_000
    assert hit["ask"] <= 250_000
    assert hit["estimated_value"] == 7_000_000
    # Every returned row must still satisfy the hard budget on ask, not estimate.
    assert all((row.get("ask") or 0) <= 250_000 for row in rows)
    assert all((row.get("acres") or 0) >= 20 for row in rows)
