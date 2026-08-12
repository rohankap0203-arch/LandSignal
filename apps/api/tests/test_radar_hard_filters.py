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
    listing = ListingRecord(
        parcel_id=parcel.id,
        provider_id="public_vacant_gis",
        external_id=external_id,
        title=f"{state} vacant · {acreage} ac · {county}",
        asking_price_usd=ask,
        price_per_acre_usd=(ask / acreage) if ask and acreage else None,
        status="ACTIVE",
        is_demo=False,
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
            best_strategy=Strategy.FARMLAND,
            secondary_strategy=Strategy.LAND_BANK,
            estimated_value_usd=ask or 100_000,
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
async def test_max_price_only_keeps_unpriced_gis_rows(isolated_store):
    _seed_scored_parcel(
        isolated_store,
        state="FL",
        county="Hardee",
        acreage=30.0,
        ask=None,
        external_id="fl-unpriced-30",
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
    assert any(row.get("ask") is None and (row.get("acres") or 0) >= 20 for row in rows)
    assert all((row.get("ask") is None) or row["ask"] <= 250_000 for row in rows)
    assert all((row.get("acres") or 0) >= 20 for row in rows)
