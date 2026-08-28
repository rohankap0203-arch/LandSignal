"""Compact yellow-outline helpers for View Map."""

from landsignal.services.parcel_outline import (
    acreage_square_polygon,
    compact_polygon,
    outline_for_parcel,
)


def test_compact_polygon_subsamples_long_rings():
    ring = [[-84.0 + i * 0.001, 30.0 + (i % 7) * 0.0005] for i in range(200)]
    ring.append(ring[0])
    out = compact_polygon([ring])
    assert out is not None
    assert len(out[0]) <= 28
    assert out[0][0] == out[0][-1]


def test_outline_falls_back_to_acreage_square():
    out = outline_for_parcel(
        polygon=None,
        latitude=28.5,
        longitude=-81.4,
        acreage=10.0,
    )
    assert out is not None
    assert len(out[0]) == 5
    # Closed square around the pin
    lons = [p[0] for p in out[0][:-1]]
    lats = [p[1] for p in out[0][:-1]]
    assert min(lons) < -81.4 < max(lons)
    assert min(lats) < 28.5 < max(lats)


def test_acreage_square_caps_absurd_acreage():
    tiny = acreage_square_polygon(-100.0, 35.0, 0.01)
    huge = acreage_square_polygon(-100.0, 35.0, 1_000_000)
    assert tiny is not None and huge is not None
    # Both still closed rings
    assert tiny[0][0] == tiny[0][-1]
    assert huge[0][0] == huge[0][-1]


def test_outline_prefers_real_polygon_over_square():
    ring = [
        [-84.1, 30.1],
        [-84.0, 30.1],
        [-84.0, 30.2],
        [-84.1, 30.2],
        [-84.1, 30.1],
    ]
    out = outline_for_parcel(
        polygon=[ring],
        latitude=30.15,
        longitude=-84.05,
        acreage=40.0,
    )
    assert out is not None
    # Should keep the rectangular land shape, not a pin square
    assert abs(out[0][0][0] - (-84.1)) < 1e-6
