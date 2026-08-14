"""Closest landmark API — sanity checks for kind validation and distance helpers."""

from landsignal.services.nearby import KIND_META, _haversine_m, _matches, _pick_hits


def test_kind_meta_covers_all_chips():
    expected = {"flood", "wetland", "water", "road", "power", "town", "school", "hospital"}
    assert set(KIND_META) == expected


def test_haversine_known_distance():
    # ~1 km north
    d = _haversine_m(31.0, -110.0, 31.009, -110.0)
    assert 900 < d < 1100


def test_water_match_rejects_swimming_pool():
    el = {"type": "way", "tags": {"natural": "water", "water": "swimming_pool"}}
    assert _matches("water", el) is False
    el2 = {"type": "way", "tags": {"natural": "water", "water": "reservoir"}}
    assert _matches("water", el2) is True


def test_pick_hits_orders_by_distance():
    origin = (31.44, -110.20)
    elements = [
        {"type": "node", "id": 1, "lat": 31.45, "lon": -110.20, "tags": {"amenity": "school", "name": "Far"}},
        {"type": "node", "id": 2, "lat": 31.441, "lon": -110.20, "tags": {"amenity": "school", "name": "Near"}},
    ]
    hits = _pick_hits("school", "School", origin, elements, max_miles=20, radius_m=30000)
    assert len(hits) == 2
    assert hits[0]["name"] == "Near"
    assert hits[0]["meters"] < hits[1]["meters"]
