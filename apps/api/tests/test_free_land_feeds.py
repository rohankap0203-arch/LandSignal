"""Tests for free public land feeds (no licensed MLS / Land.com)."""

from __future__ import annotations

from landsignal.providers.free_land_feeds import (
    build_sources,
    _norm_az_asld_mineral,
    _norm_broward_vacant,
    _norm_ct_vacant_cama,
    _norm_cuyahoga_vacant,
    _norm_la_county_vacant,
    _norm_rochester_vacant,
    _norm_txdot_surplus,
)
from landsignal.providers.public_markets import SOURCES as ALL_SOURCES


def _ring(lon: float, lat: float, d: float = 0.01) -> list[list[list[float]]]:
    return [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]


def test_free_land_feeds_registered_in_global_sources():
    ids = {s.source_id for s in build_sources()}
    assert "ct_vacant_cama" in ids
    assert "ca_la_vacant" in ids
    assert "fl_broward_vacant" in ids
    assert "txdot_surplus" in ids
    all_ids = {s.source_id for s in ALL_SOURCES}
    assert ids.issubset(all_ids)


def test_ct_vacant_normalizer():
    row = _norm_ct_vacant_cama(
        {
            "properties": {
                "Parcel_ID": "145-15A",
                "Town_Name": "Bridgeport",
                "Land_Acres": 1.275,
                "Assessed_Land": 178221,
                "State_Use_Description": "Vac Res Land",
                "Location": "88 GROVERS AV",
            },
            "geometry": {"type": "Polygon", "coordinates": _ring(-73.2, 41.18)},
        }
    )
    assert row is not None
    assert row["state"] == "CT"
    assert row["provider_id"] == "public_vacant_gis"
    assert row["acreage"] >= 1


def test_la_county_rejects_improved():
    assert (
        _norm_la_county_vacant(
            {
                "properties": {
                    "AIN": "1",
                    "APN": "1",
                    "Roll_ImpValue": 50000,
                    "Roll_LandValue": 100000,
                },
                "geometry": {"type": "Polygon", "coordinates": _ring(-118.2, 34.1, 0.02)},
            }
        )
        is None
    )


def test_la_county_accepts_vacant_acreage():
    row = _norm_la_county_vacant(
        {
            "properties": {
                "AIN": "5473022005",
                "APN": "5473-022-005",
                "Roll_ImpValue": 0,
                "Roll_LandValue": 250000,
                "UseDescription": "Vacant",
                "SitusCity": "LOS ANGELES CA",
            },
            "geometry": {"type": "Polygon", "coordinates": _ring(-118.2, 34.1, 0.02)},
        }
    )
    assert row is not None
    assert row["state"] == "CA"
    assert row["county"] == "Los Angeles"
    assert row["acreage"] >= 1


def test_broward_and_cuyahoga_and_rochester():
    br = _norm_broward_vacant(
        {
            "properties": {
                "FOLIO": "123",
                "Land_Size_In_Acres": 2.5,
                "Land_And_Building_Value": 80000,
                "SITE_ADDRESS": "1 MAIN ST",
                "CITYNAME": "DAVIE",
            },
            "geometry": {"type": "Polygon", "coordinates": _ring(-80.2, 26.1)},
        }
    )
    assert br and br["state"] == "FL" and br["acreage"] == 2.5

    cu = _norm_cuyahoga_vacant(
        {
            "properties": {
                "parcelpin": "001",
                "tax_assessed_improvement": 0,
                "parcel_acreage": 3.0,
                "tax_assessed_land": 12000,
                "parcel_city": "Cleveland",
            },
            "geometry": {"type": "Polygon", "coordinates": _ring(-81.7, 41.5)},
        }
    )
    assert cu and cu["state"] == "OH"

    ro = _norm_rochester_vacant(
        {
            "properties": {"PARCELID": "R1", "SHAPEACRES": 1.2, "CURRENT_LAND_VALUE": 9000},
            "geometry": {"type": "Polygon", "coordinates": _ring(-77.6, 43.15)},
        }
    )
    assert ro and ro["state"] == "NY"


def test_txdot_surplus_and_az_trust():
    tx = _norm_txdot_surplus(
        {
            "properties": {
                "Job_Piece_Vault": "JP1",
                "Parcel": "P1",
                "County": "Travis",
                "Acres_Remaining": 4.5,
                "Name": "Excess ROW",
                "SALE_SIGN": "Y",
            },
            "geometry": {"x": -97.7, "y": 30.3},
        }
    )
    assert tx and tx["provider_id"] == "public_surplus" and tx["state"] == "TX"

    az = _norm_az_asld_mineral(
        {
            "properties": {
                "parcelnumber": "AZ-1",
                "acres": 40,
                "county": "Maricopa",
                "openstatus": "Open",
                "classification": "Surface",
            },
            "geometry": {"type": "Polygon", "coordinates": _ring(-112.0, 33.4, 0.05)},
        }
    )
    assert az and az["state"] == "AZ"
