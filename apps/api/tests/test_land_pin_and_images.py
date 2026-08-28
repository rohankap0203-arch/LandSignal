from shapely.geometry import Point, Polygon

from landsignal.scoring.geospatial import interior_pin_lat_lon
from landsignal.services.location_images import _LANDISH, _max_ground_m, _max_street_m, _SKIP_LABEL


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
