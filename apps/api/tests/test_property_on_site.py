from landsignal.services.land_gate import (
    detect_property_on_site,
    is_land_inventory,
    is_non_land_product,
    stamp_structure_flags,
)
from landsignal.services.presentation import price_display
from landsignal.scoring.engine import compute_score
from tests.test_scoring import base_input, p


def test_detect_cottage_and_ranch_house():
    assert detect_property_on_site(title="Cozy cottage on 5 acres")
    assert detect_property_on_site(title="40 ac ranch house with pasture")
    assert detect_property_on_site(raw={"IMPRVT_VAL": 85000})
    assert not detect_property_on_site(title="Vacant farmland acreage")
    assert is_non_land_product(title="Downtown condo unit 4B")


def test_inventory_keeps_rural_home_but_rejects_condo():
    assert is_land_inventory(
        provider_id="public_tax_sale",
        title="Cabin on 12 acres — tax sale",
        acreage=12.0,
        raw={"IMPRVT_VAL": 40000},
    )
    assert not is_land_inventory(
        provider_id="public_tax_sale",
        title="Condo unit downtown",
        acreage=0.1,
        raw={},
    )


def test_stamp_structure_flags():
    stamped = stamp_structure_flags({}, title="Cottage with guest house")
    assert stamped["has_structure"] is True
    assert stamped["structure_label"] == "Property on site"


def test_price_display_never_lists_land_av_as_home_sale():
    pd = price_display(
        12_000,
        "public_vacant_gis",
        ask_role="assessed_land",
        has_structure=True,
    )
    assert pd["kind"] == "assessed_land_structure"
    assert "home" in pd["display"].lower() or "home" in pd["label"].lower()
    assert "Listed price" not in pd["label"]


def test_structure_skips_vacant_bargain_lifts():
    vacantish = compute_score(
        {
            "acreage": 40,
            "provider_id": "public_vacant_gis",
            "asking_price_usd": 15_000,
            "estimated_value_base_usd": p(200_000),
            "has_structure": True,
            "known_attribute_ratio": 0.4,
            "geometry_confidence": 60,
            "comps_count": 1,
            "wetland_pct": p(5),
            "flood_zone_pct": p(5),
        }
    )
    notes = " ".join(vacantish.get("score_lift_notes") or [])
    assert "Property on site" in notes or "property on site" in notes.lower()
    assert vacantish["best_strategy"] == "IMPROVED_PROPERTY" or vacantish["strategy_screens"][
        "IMPROVED_PROPERTY"
    ] == "PASS"
