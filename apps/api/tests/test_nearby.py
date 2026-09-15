"""Closest landmark API — sanity checks for kind validation and distance helpers."""

from landsignal.services.nearby import (
    KIND_META,
    _detail,
    _haversine_m,
    _hit_relation,
    _matches,
    _pick_hits,
)

LEGACY_KINDS = {"flood", "wetland", "water", "road", "power", "town", "school", "hospital"}

NEW_KINDS = {
    "highway",
    "airport",
    "railroad",
    "electric",
    "transmission",
    "water_main",
    "sewer",
    "gas",
    "fiber",
    "substation",
    "cell",
    "wildfire",
    "conservation",
    "grocery",
    "fire",
    "police",
    "park",
    "employer",
    "landfill",
    "mine",
    "prison",
    "hazmat",
}


def test_kind_meta_covers_all_chips():
    """Existing chips remain; new site-intelligence kinds are a superset."""
    assert LEGACY_KINDS.issubset(set(KIND_META))
    assert NEW_KINDS.issubset(set(KIND_META))
    for kind, meta in KIND_META.items():
        assert meta.get("label")
        assert meta.get("max_miles")
        assert meta.get("radii_m")
        assert meta.get("parts")


def test_haversine_known_distance():
    # ~1 km north
    d = _haversine_m(31.0, -110.0, 31.009, -110.0)
    assert 900 < d < 1100


def test_water_match_rejects_swimming_pool():
    el = {"type": "way", "tags": {"natural": "water", "water": "swimming_pool"}}
    assert _matches("water", el) is False
    el2 = {"type": "way", "tags": {"natural": "water", "water": "reservoir"}}
    assert _matches("water", el2) is True


def test_transmission_vs_electric_match():
    tower = {"type": "node", "tags": {"power": "tower"}}
    pole = {"type": "node", "tags": {"power": "pole"}}
    line = {"type": "way", "tags": {"power": "line"}}
    minor = {"type": "way", "tags": {"power": "minor_line"}}

    assert _matches("transmission", tower) is True
    assert _matches("transmission", line) is True
    assert _matches("transmission", pole) is False
    assert _matches("transmission", minor) is False

    assert _matches("electric", pole) is True
    assert _matches("electric", minor) is True
    assert _matches("electric", tower) is False
    assert _matches("electric", line) is False

    # Backward-compatible power still accepts both major + distribution.
    assert _matches("power", tower) is True
    assert _matches("power", pole) is True
    assert _matches("power", line) is True
    assert _matches("power", minor) is True


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


def test_pick_hits_enrichment_fields():
    origin = (31.44, -110.20)
    elements = [
        {
            "type": "node",
            "id": 9,
            "lat": 31.441,
            "lon": -110.20,
            "tags": {"amenity": "fire_station", "name": "Station 1"},
        }
    ]
    hits = _pick_hits("fire", "Fire station", origin, elements, max_miles=30, radius_m=40000)
    assert len(hits) == 1
    hit = hits[0]
    assert hit["measurement"] == "boundary_distance_m"
    assert hit["source"] == "OpenStreetMap"
    assert hit["confidence"] == "estimated"
    assert hit["facility_type"] == "amenity=fire_station"
    assert hit["relation"] in {"intersects_likely", "frontage_possible", "nearby", "distant"}
    assert hit["disclaimer"] is None


def test_utility_and_road_disclaimers():
    origin = (31.44, -110.20)
    power_els = [
        {"type": "node", "id": 1, "lat": 31.441, "lon": -110.20, "tags": {"power": "tower"}},
    ]
    power_hits = _pick_hits("power", "Power line", origin, power_els, max_miles=18, radius_m=28000)
    assert power_hits[0]["disclaimer"] == "Proximity ≠ confirmed service availability"

    road_els = [
        {
            "type": "node",
            "id": 2,
            "lat": 31.441,
            "lon": -110.20,
            "tags": {"highway": "secondary", "name": "Main St", "source": "osrm_nearest"},
        }
    ]
    road_hits = _pick_hits("road", "Paved road", origin, road_els, max_miles=12, radius_m=25000)
    assert road_hits[0]["disclaimer"] == "Proximity ≠ confirmed legal access"
    assert road_hits[0]["source"] == "OSRM"


def test_flood_adjacent_detail_wording():
    el = {"type": "way", "tags": {"waterway": "stream", "name": "Dry Creek"}}
    assert "Adjacent or overlapping" in (_detail("flood", el, meters=12) or "")
    assert "flood-adjacency" in (_detail("flood", el, meters=200) or "").lower()


def test_flood_mapped_confidence_and_disclaimer():
    origin = (31.44, -110.20)
    elements = [
        {
            "type": "node",
            "id": 3,
            "lat": 31.4401,
            "lon": -110.20,
            "tags": {"hazard": "flood", "name": "SFHA proxy"},
        }
    ]
    hits = _pick_hits("flood", "Flood zone", origin, elements, max_miles=15, radius_m=22000)
    assert hits[0]["confidence"] == "mapped"
    assert hits[0]["disclaimer"] == "OSM flood-adjacency proxy — not FEMA SFHA"
    assert hits[0]["relation"] == "intersects_likely"
    assert "Adjacent or overlapping" in (hits[0]["detail"] or "")


def test_hit_relation_frontage():
    assert _hit_relation("road", 20) == "frontage_possible"
    assert _hit_relation("water", 25) == "frontage_possible"
    assert _hit_relation("water", 32) == "intersects_likely"
    assert _hit_relation("flood", 20) == "intersects_likely"
    assert _hit_relation("school", 500) == "nearby"
    assert _hit_relation("school", 5000) == "distant"
