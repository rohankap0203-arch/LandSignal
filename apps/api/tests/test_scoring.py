from landsignal.scoring.engine import compute_score, personalized_score
from landsignal.scoring.financial import asking_discount_pct, irr, npv, price_per_acre
from landsignal.scoring.geospatial import (
    buildable_acreage_estimate,
    haversine_meters,
    usable_ag_acreage_estimate,
)


def p(value, state="KNOWN", confidence=80):
    return {"value": value, "knowledge_state": state, "confidence": confidence}


def base_input(**over):
    data = {
        "asking_price_usd": 475_000,
        "acreage": 80,
        "estimated_value_low_usd": p(420_000),
        "estimated_value_base_usd": p(620_000),
        "estimated_value_high_usd": p(780_000),
        "downside_value_usd": p(405_000),
        "development_upside_usd": p(1_100_000),
        "prime_farmland_pct": p(72),
        "wetland_pct": p(8),
        "flood_zone_pct": p(5),
        "avg_slope_pct": p(3),
        "max_slope_pct": p(8),
        "legal_access_confidence": p(78),
        "road_frontage_m": p(400),
        "nearest_transmission_m": p(3500),
        "liquidity_score": p(55),
        "scarcity_score": p(60),
        "path_of_growth_score": p(68),
        "catalyst_score": p(40),
        "seller_pressure_score": p(62),
        "days_on_market": 45,
        "price_reduction_pct": 12,
        "environmental_contamination": p(5),
        "zoning_development_friendly": p(55),
        "timber_suitability": p(30),
        "solar_irradiance_score": p(70),
        "geometry_confidence": 85,
        "comps_count": 4,
        "known_attribute_ratio": 0.82,
        "listing_freshness_hours": 6,
    }
    data.update(over)
    return data


def test_price_and_discount():
    assert price_per_acre(500_000, 100) == 5000
    d = asking_discount_pct(375_000, 510_000)
    assert d is not None and abs(d - (-26.470588235294116)) < 1e-6


def test_irr_npv():
    flows = [-100, 60, 60]
    assert abs(npv(0.1, flows) - 4.132231404958678) < 1e-6
    r = irr(flows)
    assert r is not None and 0.13 < r < 0.14


def test_geospatial_no_invent_buildable():
    assert (
        buildable_acreage_estimate(100, None, 10, 5) is None
    )
    acres = usable_ag_acreage_estimate(100, 20, 80, 4)
    assert acres is not None and 50 < acres < 100


def test_haversine():
    d = haversine_meters(40.7128, -74.006, 39.9526, -75.1652)
    assert 120_000 < d < 150_000


def test_score_reproducible_and_mispricing():
    a = compute_score(base_input())
    b = compute_score(base_input())
    assert a["input_hash"] == b["input_hash"]
    assert a["opportunity"] == b["opportunity"]
    assert a["asking_discount_pct"] < -15
    assert a["opportunity"] >= 70
    assert a["signal"] in ("STRONG", "EXCEPTIONAL")
    assert a["evidence_ratio"] >= 0.7
    assert a["known_core_factors"] >= 4


def test_thin_vacant_gis_cannot_rank_as_strong_buy():
    """Bare vacant GIS map screens must not clear STRONG / top-board territory."""
    thin = compute_score(
        {
            "acreage": 40,
            "provider_id": "public_vacant_gis",
            "known_attribute_ratio": 0.15,
            "geometry_confidence": 40,
            "comps_count": 0,
        }
    )
    assert thin["opportunity"] < 55
    assert thin["signal"] == "WATCH"
    assert thin["confidence"] < 45
    assert thin["evidence_ratio"] < 0.55


def test_rich_file_outranks_thin_vacant_gis():
    """#1 of live inventory must prefer evidence-backed mispricing over thin map screens."""
    rich = compute_score(base_input())
    thin = compute_score(
        {
            "acreage": 80,
            "provider_id": "public_vacant_gis",
            "estimated_value_base_usd": p(200_000),
            "known_attribute_ratio": 0.2,
            "geometry_confidence": 50,
            "comps_count": 0,
        }
    )
    assert rich["opportunity"] > thin["opportunity"] + 15
    assert rich["confidence"] > thin["confidence"]
    assert rich["signal"] in ("STRONG", "EXCEPTIONAL")
    assert thin["signal"] == "WATCH"
    assert thin["opportunity"] < 60


def test_missing_data_lowers_confidence_not_auto_fail_quality():
    known = compute_score(base_input(flood_zone_pct=p(0)))
    unknown = compute_score(
        base_input(
            flood_zone_pct=p(None, "UNKNOWN", None),
            known_attribute_ratio=0.5,
        )
    )
    assert unknown["confidence"] < known["confidence"]


def test_wetlands_kill_dev_not_recreation():
    result = compute_score(base_input(wetland_pct=p(55)))
    assert result["strategy_screens"]["DEVELOPMENT"] == "FAIL"
    assert result["strategy_screens"]["RECREATIONAL"] != "FAIL"


def test_personalized_separate():
    g = compute_score(base_input())
    personal = personalized_score(
        g["opportunity"],
        {
            "preferred_strategies": ["FARMLAND"],
            "max_price_usd": 400_000,
            "min_acres": 100,
            "risk_tolerance": "LOW",
        },
        475_000,
        80,
        g["best_strategy"],
        g["risk"],
    )
    assert personal < g["opportunity"]


def test_no_opportunistic_nudge_on_middling_files():
    """v3.6 removed the sitewide +6 scout nudge that inflated thin inventory."""
    mid = compute_score(
        {
            "acreage": 20,
            "asking_price_usd": 300_000,
            "estimated_value_base_usd": p(310_000),
            "known_attribute_ratio": 0.35,
            "geometry_confidence": 55,
            "comps_count": 1,
            "wetland_pct": p(12),
            "flood_zone_pct": p(8),
            "legal_access_confidence": p(60),
        }
    )
    notes = " ".join(mid.get("score_lift_notes") or [])
    assert "Opportunistic scout nudge" not in notes
    assert mid["algorithm_version"] == "landsignal_score_v3_6_0"