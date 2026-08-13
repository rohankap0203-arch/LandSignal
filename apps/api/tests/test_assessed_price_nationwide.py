"""Assessed-land asks must power budget filters in every state, not just Texas."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from landsignal.main import app
from landsignal.models import ListingRecord, ParcelRecord, ScoreRecord, Signal, Strategy
from landsignal.services.assessed_price import (
    backfill_listing_ask_from_assessed,
    extract_assessed_land_usd,
)
from landsignal.store import MemoryStore


def test_extract_nested_land_av_and_landval():
    assert extract_assessed_land_usd({"raw": {"LAND_AV": 250_000}}) == 250_000
    assert extract_assessed_land_usd({"raw": {"LandVal": 180_000}}) == 180_000
    assert extract_assessed_land_usd({"LAND_VAL": 90_000}) == 90_000
    assert extract_assessed_land_usd({"raw": {"LNDVALUE": 55_000}}) == 55_000
    assert extract_assessed_land_usd({"raw": {"LAND_LV": 40_000}}) == 40_000


def test_backfill_sets_ask_and_role():
    listing = ListingRecord(
        parcel_id=ParcelRecord(
            parcel_id="x",
            apn="x",
            address="x",
            county="Test",
            state="NY",
            latitude=1,
            longitude=1,
            acreage=40,
            is_demo=False,
        ).id,
        provider_id="public_vacant_gis",
        external_id="ny:1",
        title="t",
        asking_price_usd=None,
        status="ACTIVE",
        is_demo=False,
        raw={"raw": {"LAND_AV": 310_000}},
    )
    assert backfill_listing_ask_from_assessed(listing) is True
    assert listing.asking_price_usd == 310_000
    assert listing.raw.get("ask_role") == "assessed_land"


def _seed(store: MemoryStore, *, state: str, acres: float, land_key: str, land_val: float, eid: str):
    parcel = ParcelRecord(
        parcel_id=eid,
        apn=eid,
        address=f"{state} County",
        county="County",
        state=state,
        latitude=40.0,
        longitude=-90.0,
        acreage=acres,
        is_demo=False,
    )
    listing = ListingRecord(
        parcel_id=parcel.id,
        provider_id="public_vacant_gis",
        external_id=eid,
        title=f"{state} vacant",
        asking_price_usd=None,
        status="ACTIVE",
        is_demo=False,
        raw={"raw": {land_key: land_val, "ask_role": "assessed_land"}},
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
            opportunity=70.0,
            risk=30.0,
            confidence=80.0,
            asymmetry=10.0,
            signal=Signal.WATCH,
            best_strategy=Strategy.FARMLAND,
            secondary_strategy=Strategy.LAND_BANK,
            estimated_value_usd=land_val,
            asking_discount_pct=None,
            deal_readiness=50.0,
            input_hash=f"test-{eid}",
        )
    ]


@pytest.fixture
def multi_state_store(monkeypatch):
    store = MemoryStore()
    _seed(store, state="NY", acres=40, land_key="LAND_AV", land_val=400_000, eid="ny-1")
    _seed(store, state="NJ", acres=25, land_key="LAND_VAL", land_val=220_000, eid="nj-1")
    _seed(store, state="MA", acres=30, land_key="LAND_VAL", land_val=350_000, eid="ma-1")
    _seed(store, state="AR", acres=80, land_key="landvalue", land_val=150_000, eid="ar-1")
    _seed(store, state="WI", acres=45, land_key="LNDVALUE", land_val=275_000, eid="wi-1")
    _seed(store, state="VT", acres=50, land_key="LAND_LV", land_val=190_000, eid="vt-1")
    _seed(store, state="TN", acres=35, land_key="LandAppr", land_val=480_000, eid="tn-1")
    # Over budget — must be excluded
    _seed(store, state="NY", acres=40, land_key="LAND_AV", land_val=2_500_000, eid="ny-expensive")
    monkeypatch.setattr("landsignal.routers.api.get_store", lambda _seed=False: store)
    yield store


@pytest.mark.asyncio
async def test_budget_filter_works_across_states(multi_state_store):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for state in ("NY", "NJ", "MA", "AR", "WI", "VT", "TN"):
            r = await client.get(
                "/v1/radar",
                params={"state": state, "min_acres": 20, "max_price": 1_000_000, "limit": 20},
            )
            assert r.status_code == 200, state
            rows = r.json()
            assert rows, f"expected priced matches for {state}"
            assert all((row.get("acres") or 0) >= 20 for row in rows), state
            assert all((row.get("ask") or 0) <= 1_000_000 for row in rows), state
            assert all((row.get("state") or "").upper() == state for row in rows), state
