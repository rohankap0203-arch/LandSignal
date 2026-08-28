"""Exact GIS outlines for View Map — never invent squares."""

from landsignal.services.parcel_outline import (
    compact_polygon,
    exact_polygon,
    is_synthetic_square,
    outline_for_parcel,
    outline_matches_acreage,
    ring_area_acres,
)


def test_exact_keeps_full_irregular_ring():
    ring = [
        [-84.10, 30.10],
        [-84.05, 30.11],
        [-84.00, 30.09],
        [-84.02, 30.15],
        [-84.08, 30.16],
        [-84.10, 30.10],
    ]
    out = exact_polygon([ring])
    assert out is not None
    assert len(out[0]) >= 5
    assert not is_synthetic_square(out)


def test_compact_still_caps_inventory_rings():
    ring = [[-84.0 + i * 0.001, 30.0 + (i % 7) * 0.0005] for i in range(400)]
    ring.append(ring[0])
    out = compact_polygon([ring])
    assert out is not None
    assert len(out[0]) <= 128


def test_outline_does_not_invent_acreage_square():
    out = outline_for_parcel(
        polygon=None,
        latitude=28.5,
        longitude=-81.4,
        acreage=10.0,
    )
    assert out is None


def test_rejects_synthetic_square():
    ring = [
        [-81.9, 28.7],
        [-81.8, 28.7],
        [-81.8, 28.8],
        [-81.9, 28.8],
        [-81.9, 28.7],
    ]
    assert is_synthetic_square([ring]) is True
    assert exact_polygon([ring]) is None
    assert compact_polygon([ring]) is None


def test_acreage_match_rejects_wrong_neighbor():
    # ~1 acre square near equator-ish
    ring = [
        [-81.4000, 28.5000],
        [-81.3994, 28.5000],
        [-81.3994, 28.5006],
        [-81.4000, 28.5006],
        [-81.4000, 28.5000],
    ]
    poly = [ring]
    measured = ring_area_acres(ring)
    assert measured is not None and measured < 5
    assert outline_matches_acreage(poly, measured) is True
    assert outline_matches_acreage(poly, 200.0) is False
