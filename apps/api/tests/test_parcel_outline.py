"""Compact real GIS outlines for View Map — never invent squares."""

from landsignal.services.parcel_outline import (
    compact_polygon,
    is_synthetic_square,
    outline_for_parcel,
)


def test_compact_polygon_subsamples_long_rings():
    ring = [[-84.0 + i * 0.001, 30.0 + (i % 7) * 0.0005] for i in range(200)]
    ring.append(ring[0])
    out = compact_polygon([ring])
    assert out is not None
    assert len(out[0]) <= 64
    assert out[0][0] == out[0][-1]


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
    assert compact_polygon([ring]) is None
    assert outline_for_parcel(polygon=[ring]) is None


def test_outline_keeps_real_irregular_boundary():
    ring = [
        [-84.10, 30.10],
        [-84.05, 30.11],
        [-84.00, 30.09],
        [-84.02, 30.15],
        [-84.08, 30.16],
        [-84.10, 30.10],
    ]
    out = outline_for_parcel(
        polygon=[ring],
        latitude=30.12,
        longitude=-84.05,
        acreage=40.0,
    )
    assert out is not None
    assert len(out[0]) >= 4
    assert not is_synthetic_square(out)
