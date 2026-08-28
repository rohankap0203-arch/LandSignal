from shapely.geometry import Point, Polygon

from landsignal.scoring.geospatial import interior_pin_lat_lon
from landsignal.services.location_images import (
    _LANDISH,
    _max_ground_m,
    _max_street_m,
    _SKIP_LABEL,
    build_instant_images,
    build_location_images,
)


def test_interior_pin_stays_on_crescent_not_lake_hole():
    """C-shaped waterfront parcel: geometric centroid sits in the water; pin must not."""
    ring = [
        (-100.0, 40.0),
        (-99.0, 40.0),
        (-99.0, 41.0),
        (-99.4, 41.0),
        (-99.4, 40.4),
        (-99.6, 40.4),
        (-99.6, 41.0),
        (-100.0, 41.0),
        (-100.0, 40.0),
    ]
    poly = Polygon(ring)
    lat, lon = interior_pin_lat_lon(poly)
    pin = Point(lon, lat)
    assert poly.contains(pin) or poly.covers(pin)
    # Classic centroid is outside this crescent
    assert not poly.contains(poly.centroid)


def test_location_image_radii_stay_tight():
    assert _max_street_m(5) <= 700
    assert _max_street_m(640) <= 1200
    assert _max_ground_m(5) <= 1200
    assert _max_ground_m(640) <= 1800


def test_skip_label_blocks_civic_junk():
    assert _SKIP_LABEL.search("Portrait of Mayor Smith")
    assert _SKIP_LABEL.search("City Hall interior")
    assert _SKIP_LABEL.search("Baseball stadium lights")
    assert not _SKIP_LABEL.search("Rural pasture near creek")
    assert _LANDISH.search("Pasture and creek along farm road")


def test_instant_gallery_is_immediate_and_on_pin():
    payload = build_instant_images(lat=31.44, lon=-110.2, acres=40, title="Test")
    assert payload["ok"] is True
    assert payload["phase"] == "instant"
    assert payload["count"] >= 2
    kinds = [i["kind"] for i in payload["images"]]
    assert "aerial" in kinds
    assert "streetview" in kinds
    # Instant path must not depend on upstream JSON — aerial URLs are constructed.
    aerial = next(i for i in payload["images"] if i["kind"] == "aerial")
    assert "export" in aerial["url"] or "mapbox.com" in aerial["url"]
    assert aerial.get("thumb_url")


def test_full_mode_returns_aerial_lead_even_without_upstreams(monkeypatch):
    import landsignal.services.location_images as li

    monkeypatch.setattr(li, "_kartaview_street", lambda *a, **k: [])
    monkeypatch.setattr(li, "_wikimedia_ground", lambda *a, **k: [])
    # Clear cache between runs
    li._CACHE.clear()
    payload = build_location_images(lat=28.1, lon=-81.6, acres=20, mode="full")
    assert payload["ok"] is True
    assert payload["images"][0]["kind"] == "aerial"
    assert any(i["kind"] == "streetview" for i in payload["images"])
