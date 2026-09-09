"""Cold states auto-index so Show matches is never empty for lack of inventory."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from landsignal.main import app
from landsignal.models import ListingRecord, ParcelRecord, ScoreRecord, Signal, Strategy
from landsignal.store import MemoryStore


def _seed(store: MemoryStore, *, state: str, external_id: str, acreage: float = 40.0, ask: float = 120_000) -> None:
    parcel = ParcelRecord(
        parcel_id=external_id,
        apn=external_id,
        address=f"{state} County",
        county="Test",
        state=state,
        latitude=30.0,
        longitude=-97.0,
        acreage=acreage,
        is_demo=False,
    )
    listing = ListingRecord(
        parcel_id=parcel.id,
        provider_id="public_vacant_gis",
        external_id=external_id,
        title=f"{state} vacant · {acreage} ac",
        asking_price_usd=ask,
        price_per_acre_usd=ask / acreage,
        status="ACTIVE",
        is_demo=False,
        raw={},
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
            estimated_value_usd=ask,
            asking_discount_pct=None,
            deal_readiness=55.0,
            input_hash=f"test-{external_id}",
        )
    ]


@pytest.mark.asyncio
async def test_cold_state_triggers_sync_fill_then_returns_matches(monkeypatch):
    store = MemoryStore()
    _seed(store, state="FL", external_id="fl-only")

    calls: list[dict] = []

    async def fake_discover(store_arg, settings, **kwargs):
        calls.append(kwargs)
        # Simulate indexing the requested cold state.
        states = kwargs.get("states") or ["TX"]
        for st in states:
            _seed(store_arg, state=st, external_id=f"{st.lower()}-auto", acreage=55.0, ask=200_000)
        return {"imported": 1, "scored": 1, "inventory_total": len(store_arg.parcels)}

    monkeypatch.setattr("landsignal.routers.api.get_store", lambda _seed=False: store)
    monkeypatch.setattr("landsignal.routers.api.discover_opportunities", fake_discover)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={"state": "TX", "broaden": True, "limit": 50},
        )
    assert r.status_code == 200
    rows = r.json()
    assert calls, "expected auto-discover for cold TX"
    assert calls[0].get("states") == ["TX"]
    assert rows, "expected TX matches after sync fill"
    assert all(row["state"] == "TX" for row in rows)


@pytest.mark.asyncio
async def test_stocked_state_skips_auto_discover(monkeypatch):
    store = MemoryStore()
    _seed(store, state="FL", external_id="fl-stocked", acreage=30.0, ask=150_000)
    calls: list[dict] = []

    async def fake_discover(*_a, **kwargs):
        calls.append(kwargs)
        return {"imported": 0, "scored": 0}

    monkeypatch.setattr("landsignal.routers.api.get_store", lambda _seed=False: store)
    monkeypatch.setattr("landsignal.routers.api.discover_opportunities", fake_discover)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(
            "/v1/radar",
            params={"state": "FL", "broaden": True, "limit": 50},
        )
    assert r.status_code == 200
    assert r.json()
    assert calls == []
