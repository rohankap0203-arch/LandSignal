"""Every catalog price/acre preset must hard-enforce — not only 20ac / $1M."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from landsignal.geo_meta import search_meta_payload
from landsignal.main import app
from landsignal.models import ListingRecord, ParcelRecord, ScoreRecord, Signal, Strategy
from landsignal.store import MemoryStore


def _seed(
    store: MemoryStore,
    *,
    eid: str,
    state: str,
    county: str,
    acres: float,
    ask: float,
    strategy: Strategy = Strategy.FARMLAND,
) -> None:
    parcel = ParcelRecord(
        parcel_id=eid,
        apn=eid,
        address=f"{county}, {state}",
        county=county,
        state=state,
        latitude=35.0,
        longitude=-95.0,
        acreage=acres,
        is_demo=False,
    )
    listing = ListingRecord(
        parcel_id=parcel.id,
        provider_id="public_vacant_gis",
        external_id=eid,
        title=f"{state} {county} {acres}ac",
        asking_price_usd=ask,
        status="ACTIVE",
        is_demo=False,
        raw={"ask_role": "assessed_land", "LandVal": ask},
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
            risk=25.0,
            confidence=80.0,
            asymmetry=12.0,
            signal=Signal.WATCH,
            best_strategy=strategy,
            secondary_strategy=Strategy.LAND_BANK,
            estimated_value_usd=ask * 2,
            asking_discount_pct=None,
            deal_readiness=55.0,
            input_hash=f"test-{eid}",
        )
    ]


@pytest.fixture
def catalog_store(monkeypatch):
    store = MemoryStore()
    samples = [
        ("tiny", "FL", "Polk", 0.4, 8_000),
        ("a1", "FL", "Polk", 1.2, 12_000),
        ("a5", "FL", "Highlands", 6.0, 40_000),
        ("a10", "TX", "Harris", 12.0, 90_000),
        ("a20", "TX", "Harris", 25.0, 180_000),
        ("a40", "NY", "Essex", 45.0, 220_000),
        ("a80", "AR", "Drew", 90.0, 310_000),
        ("a160", "MA", "Berkshire", 180.0, 480_000),
        ("a320", "NC", "Robeson", 350.0, 700_000),
        ("a640", "UT", "Tooele", 700.0, 1_200_000),
        ("rich", "CA", "Napa", 50.0, 6_000_000),
        ("energy", "FL", "Levy", 55.0, 200_000),
    ]
    for eid, st, county, ac, ask in samples:
        strat = Strategy.ENERGY if eid == "energy" else Strategy.FARMLAND
        _seed(store, eid=eid, state=st, county=county, acres=ac, ask=ask, strategy=strat)
    monkeypatch.setattr("landsignal.routers.api.get_store", lambda _seed=False: store)
    yield store


def _presets():
    meta = search_meta_payload()
    price = [
        p
        for p in meta["price_presets"]
        if p["label"] not in ("Any", "Custom…") and (p["min"] is not None or p["max"] is not None)
    ]
    acres = [
        p
        for p in meta["acre_presets"]
        if p["label"] not in ("Any", "Custom range…") and (p["min"] is not None or p["max"] is not None)
    ]
    return price, acres


@pytest.mark.asyncio
async def test_every_price_preset_is_hard(catalog_store):
    price_presets, _ = _presets()
    assert len(price_presets) >= 8
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for p in price_presets:
            params: dict = {"limit": 50}
            if p["min"] is not None:
                params["min_price"] = p["min"]
            if p["max"] is not None:
                params["max_price"] = p["max"]
            r = await client.get("/v1/radar", params=params)
            assert r.status_code == 200, p["label"]
            for row in r.json():
                ask = row.get("ask")
                assert ask is not None, p["label"]
                if p["min"] is not None:
                    assert ask >= p["min"], (p["label"], ask)
                if p["max"] is not None:
                    assert ask <= p["max"], (p["label"], ask)


@pytest.mark.asyncio
async def test_every_acre_preset_is_hard(catalog_store):
    _, acre_presets = _presets()
    assert len(acre_presets) >= 8
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for p in acre_presets:
            params: dict = {"limit": 50}
            if p["min"] is not None:
                params["min_acres"] = p["min"]
            if p["max"] is not None:
                params["max_acres"] = p["max"]
            r = await client.get("/v1/radar", params=params)
            assert r.status_code == 200, p["label"]
            rows = r.json()
            assert rows, f"expected seed hits for {p['label']}"
            for row in rows:
                ac = row.get("acres")
                assert ac is not None, p["label"]
                if p["min"] is not None:
                    assert ac >= p["min"], (p["label"], ac)
                if p["max"] is not None:
                    assert ac <= p["max"], (p["label"], ac)


@pytest.mark.asyncio
async def test_stacked_custom_bands_and_strategy(catalog_store):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={
                "state": "FL",
                "min_acres": 40,
                "max_acres": 100,
                "min_price": 100_000,
                "max_price": 300_000,
                "strategy": "ENERGY",
                "limit": 50,
            },
        )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["state"] == "FL"
    assert 40 <= row["acres"] <= 100
    assert 100_000 <= row["ask"] <= 300_000
    assert row["best_strategy"] == "ENERGY"


@pytest.mark.asyncio
async def test_region_filter_is_hard(catalog_store):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={"state": "TX", "region": "Harris", "min_acres": 1, "limit": 50},
        )
    assert r.status_code == 200
    rows = r.json()
    assert rows
    assert all("harris" in (row.get("county") or "").lower() for row in rows)
