"""Credibility + resilience tests for FL-style statewide public GIS inventory."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from landsignal.providers.public_markets import (
    ArcgisMarketSource,
    PublicTaxSaleProvider,
    _dedupe_inventory_rows,
    _fetch_arcgis_pages,
    _validate_inventory_row,
)
from landsignal.providers.statewide_inventory import (
    _norm_ct_parcels_vacant,
    _norm_nc_parcels_vacant,
    _norm_wa_parcels_vacant,
    _norm_wi_parcels_vacant,
)


def _ring(lon: float, lat: float, d: float = 0.01) -> list[list[list[float]]]:
    return [
        [
            [lon, lat],
            [lon + d, lat],
            [lon + d, lat + d],
            [lon, lat + d],
            [lon, lat],
        ]
    ]


def _valid_row(**over: Any) -> dict:
    row = {
        "provider_id": "public_vacant_gis",
        "external_id": "fl_parcels:123",
        "title": "Florida vacant · 10.0 ac · Lake",
        "acreage": 10.0,
        "state": "FL",
        "county": "Lake",
        "latitude": 28.5,
        "longitude": -81.5,
        "polygon": _ring(-81.5, 28.5),
        "status": "ACTIVE",
        "is_demo": False,
    }
    row.update(over)
    return row


def test_validate_accepts_credible_row():
    assert _validate_inventory_row(_valid_row()) is not None


@pytest.mark.parametrize(
    "over",
    [
        {"state": "XX"},
        {"acreage": 0.01},
        {"acreage": 100_000},
        {"latitude": 0.0, "longitude": 0.0},  # null island / ocean guard
        {"external_id": "no-colon"},
        {"provider_id": "mls_fake"},
        {"polygon": []},
        {"title": ""},
    ],
)
def test_validate_rejects_junk(over):
    assert _validate_inventory_row(_valid_row(**over)) is None


def test_dedupe_by_provider_external_id():
    rows = [
        _valid_row(external_id="fl_parcels:1", acreage=10),
        _valid_row(external_id="fl_parcels:1", acreage=12),
        _valid_row(external_id="fl_parcels:2", acreage=8),
    ]
    out = _dedupe_inventory_rows(rows)
    assert len(out) == 2
    assert {r["external_id"] for r in out} == {"fl_parcels:1", "fl_parcels:2"}


def test_nc_normalizer_requires_unimproved_and_polygon():
    good = {
        "type": "Feature",
        "properties": {
            "improvval": 0,
            "gisacres": 12.5,
            "landval": 40000,
            "ownname": "PRIVATE OWNER LLC",
            "parno": "ABC123",
            "cntyname": "Wake",
            "siteadd": "100 MAIN ST",
        },
        "geometry": {"type": "Polygon", "coordinates": _ring(-78.6, 35.8)},
    }
    row = _norm_nc_parcels_vacant(good)
    assert row is not None
    assert row["state"] == "NC"
    assert row["acreage"] >= 1
    assert _validate_inventory_row(row) is not None

    built = {
        **good,
        "properties": {**good["properties"], "improvval": 250000},
    }
    assert _norm_nc_parcels_vacant(built) is None


def test_wa_normalizer_landuse_and_no_building():
    feat = {
        "properties": {
            "LANDUSE_CD": 91,
            "VALUE_BLDG": 0,
            "VALUE_LAND": 12000,
            "FIPS_NR": "033",
            "PARCEL_ID_NR": "033-1",
            "SITUS_ADDRESS": None,
        },
        "geometry": {"type": "Polygon", "coordinates": _ring(-122.3, 47.6, 0.02)},
    }
    row = _norm_wa_parcels_vacant(feat)
    assert row is not None
    assert row["county"] == "King"
    assert _validate_inventory_row(row) is not None
    feat["properties"]["VALUE_BLDG"] = 90000
    assert _norm_wa_parcels_vacant(feat) is None


def test_wi_and_ct_normalizers_basic():
    wi = {
        "properties": {
            "PROPCLASS": "1",
            "GISACRES": 6.2,
            "OWNERNME1": "JANE DOE",
            "PARCELID": "WI-1",
            "PARCELSRC": "Dane",
            "SITEADRESS": "1 OAK RD",
        },
        "geometry": {"type": "Polygon", "coordinates": _ring(-89.4, 43.0)},
    }
    assert _validate_inventory_row(_norm_wi_parcels_vacant(wi)) is not None

    ct = {
        "properties": {
            "State_Use": "100",
            "State_Use_Description": "Vac Res Land",
            "Assessed_Building": 0,
            "Land_Acres": 2.5,
            "Town_Name": "Avon",
            "Owner": "JOHN SMITH",
            "Assessed_Land": 50000,
            "OBJECTID": 9,
        },
        "geometry": {"type": "Polygon", "coordinates": _ring(-72.8, 41.8)},
    }
    assert _validate_inventory_row(_norm_ct_parcels_vacant(ct)) is not None


@pytest.mark.asyncio
async def test_fetch_pages_soft_fails_on_http_errors(monkeypatch):
    src = ArcgisMarketSource(
        "demo_src",
        "Demo",
        "https://example.invalid/query",
        "FL",
        "Statewide",
        lambda raw: None,
        where="1=1",
    )

    class _Resp:
        status_code = 504

        def json(self):
            raise AssertionError("should not parse 504 body")

    class _Client:
        async def get(self, *args, **kwargs):
            return _Resp()

    rows = await _fetch_arcgis_pages(_Client(), src, target=50)  # type: ignore[arg-type]
    assert rows == []


@pytest.mark.asyncio
async def test_fetch_pages_validates_normalized_rows(monkeypatch):
    src = ArcgisMarketSource(
        "demo_src",
        "Demo",
        "https://example.invalid/query",
        "FL",
        "Statewide",
        lambda raw: _valid_row(
            external_id=f"fl_parcels:{raw['properties']['id']}",
            acreage=float(raw["properties"]["acres"]),
        ),
        where="1=1",
        page_size=2,
    )

    class _Resp:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    payloads = [
        {
            "features": [
                {"properties": {"id": "1", "acres": 10}, "geometry": None},
                {"properties": {"id": "bad", "acres": 0.01}, "geometry": None},
            ]
        },
        {"features": []},
    ]

    class _Client:
        def __init__(self):
            self.i = 0

        async def get(self, *args, **kwargs):
            payload = payloads[min(self.i, len(payloads) - 1)]
            self.i += 1
            return _Resp(payload)

    rows = await _fetch_arcgis_pages(_Client(), src, target=10)  # type: ignore[arg-type]
    assert len(rows) == 1
    assert rows[0]["external_id"] == "fl_parcels:1"


@pytest.mark.asyncio
async def test_unknown_state_filter_returns_empty():
    provider = PublicTaxSaleProvider()
    res = await provider.search_listings({"states": ["ZZ"], "limit": 10})
    assert res.ok is True
    assert res.data == []


@pytest.mark.asyncio
async def test_provider_never_raises_on_total_failure(monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "landsignal.providers.public_markets._fetch_state_inventory",
        _boom,
    )
    provider = PublicTaxSaleProvider()
    # Force a tiny in-memory source set via monkeypatch of SOURCES filtering path:
    # search_listings catches fatals and still returns ok.
    monkeypatch.setattr(
        "landsignal.providers.public_markets.SOURCES",
        [
            ArcgisMarketSource(
                "x",
                "x",
                "https://example.invalid/query",
                "FL",
                "Statewide",
                lambda raw: None,
            )
        ],
    )
    res = await provider.search_listings({"states": ["FL"], "limit": 20})
    assert res.ok is True
    assert res.data == [] or isinstance(res.data, list)
    # State-level boom is soft-failed inside gather; fatal path also ok=True.
    assert res.status.value == "CONFIGURED"


@pytest.mark.asyncio
async def test_provider_state_timeout_soft_fails(monkeypatch):
    async def _hang(*args, **kwargs):
        await asyncio.sleep(10)
        return []

    monkeypatch.setattr(
        "landsignal.providers.public_markets._STATE_FETCH_TIMEOUT_S",
        0.05,
    )
    monkeypatch.setattr(
        "landsignal.providers.public_markets._fetch_state_inventory",
        _hang,
    )
    monkeypatch.setattr(
        "landsignal.providers.public_markets.SOURCES",
        [
            ArcgisMarketSource(
                "x",
                "x",
                "https://example.invalid/query",
                "FL",
                "Statewide",
                lambda raw: None,
            )
        ],
    )
    provider = PublicTaxSaleProvider()
    res = await provider.search_listings({"states": ["FL"], "limit": 10})
    assert res.ok is True
    assert res.data == []
    assert res.error and "timed out" in res.error
