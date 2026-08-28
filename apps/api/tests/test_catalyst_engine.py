"""Realism bounds for the Future Scenario / catalyst engine.

Guards against overly generous single-event and stacked what-if uplifts
while still allowing meaningful Approved near-node unlocks.
"""

from __future__ import annotations

from landsignal.services.catalyst_engine import (
    COMBINED_DISPLAY_CAP,
    apply_catalysts_to_path,
    build_stress_cases,
    combine_scenario_impacts,
    compute_scenario_impact,
    select_auto_scenarios,
)


def _screens(
    *,
    growth: float = 60,
    access: float = 55,
    flood: float = 70,
    wetland: float = 70,
    soil: float = 55,
    title: float = 60,
    strategy: float = 55,
) -> dict:
    return {
        "growth": {"score": growth},
        "access": {"score": access},
        "flood": {"score": flood},
        "wetland": {"score": wetland},
        "soil": {"score": soil},
        "title": {"score": title},
        "strategy": {"score": strategy},
    }


def test_auto_scenarios_use_pre_approval_stages():
    autos = select_auto_scenarios(
        screens=_screens(),
        strategy="hold_develop",
        acres=10.0,
        flood_zone=None,
    )
    assert autos
    for s in autos:
        assert s["stage"] in {"Proposed", "Filed", "Under Review"}
        assert s["stage"] != "Approved"


def test_single_auto_like_catalyst_is_mid_single_digits_to_low_teens():
    """Proposed sewer at ~1 mi should not print 30–50% fantasy uplifts."""
    imp = compute_scenario_impact(
        "sewer_extension",
        screens=_screens(),
        strategy="hold_develop",
        acres=10.0,
        flood_zone=None,
        distance_mi=1.0,
        stage="Proposed",
    )
    p50 = float(imp["impact"]["p50"])
    assert 0.02 <= p50 <= 0.14, p50


def test_approved_near_node_unlock_is_meaningful_but_capped():
    imp = compute_scenario_impact(
        "sewer_extension",
        screens=_screens(growth=70, access=65),
        strategy="hold_develop",
        acres=12.0,
        flood_zone=None,
        distance_mi=0.25,
        stage="Approved",
    )
    p50 = float(imp["impact"]["p50"])
    assert 0.08 <= p50 <= COMBINED_DISPLAY_CAP, p50


def test_next_door_shopping_does_not_hit_old_72pct_cap():
    imp = compute_scenario_impact(
        "shopping_center",
        screens=_screens(growth=75, access=70),
        strategy="hold_develop",
        acres=10.0,
        flood_zone=None,
        distance_mi=0.1,
        stage="Approved",
        scale="regional",
    )
    p50 = float(imp["impact"]["p50"])
    p90 = float(imp["impact"]["p90"])
    assert p50 <= COMBINED_DISPLAY_CAP, p50
    assert p90 <= COMBINED_DISPLAY_CAP, p90
    assert p50 < 0.40, p50


def test_flood_and_wetland_mute_upside():
    clear = compute_scenario_impact(
        "sewer_extension",
        screens=_screens(flood=85, wetland=85),
        strategy="hold_develop",
        acres=10.0,
        flood_zone=None,
        distance_mi=0.8,
        stage="Approved",
    )
    constrained = compute_scenario_impact(
        "sewer_extension",
        screens=_screens(flood=28, wetland=30),
        strategy="hold_develop",
        acres=10.0,
        flood_zone="AE",
        distance_mi=0.8,
        stage="Approved",
    )
    assert float(constrained["impact"]["p50"]) < float(clear["impact"]["p50"]) * 0.75


def test_bull_case_uses_top_few_not_every_upside():
    autos = select_auto_scenarios(
        screens=_screens(growth=68, access=60),
        strategy="hold_develop",
        acres=15.0,
        flood_zone=None,
    )
    stress = build_stress_cases(autos)
    bull_ids = stress["bull"]["scenario_ids"]
    upside_n = sum(1 for s in autos if float((s.get("impact") or {}).get("p50") or 0) >= 0)
    assert len(bull_ids) <= 3 or len(bull_ids) <= max(3, upside_n)
    assert len(bull_ids) <= max(3, len(stress["most_likely"]["scenario_ids"]) + 1)


def test_bull_path_y10_stays_well_under_2x():
    autos = select_auto_scenarios(
        screens=_screens(growth=68, access=60),
        strategy="hold_develop",
        acres=15.0,
        flood_zone=None,
    )
    stress = build_stress_cases(autos)
    bull_ids = set(stress["bull"]["scenario_ids"])
    bull = [s for s in autos if s["id"] in bull_ids]
    comb = combine_scenario_impacts(bull)
    assert float(comb["combined_p50"]) <= COMBINED_DISPLAY_CAP + 0.02
    baseline = [
        {"year": 2026 + i, "offset": float(i), "value_usd": 100_000} for i in range(0, 11)
    ]
    path = apply_catalysts_to_path(baseline, comb, bull)
    y10 = float(path[10]["delta_pct"])
    assert y10 <= 55.0, y10
    assert path[10]["scenario_value"] < 2.0 * path[10]["baseline_value"]
