"""Accuracy guards: standings midrank + credible purchase underwriting."""

from __future__ import annotations

from landsignal.services.purchase_credibility import (
    is_credible_purchase_usd,
    is_displayable_ask,
    resolve_underwriting_entry,
    sanitize_row_asking_price,
)
from landsignal.services.score_standings import _percentile_rank, build_confidence_factors


def test_midrank_percentile_ties_are_not_zero_or_hundred():
    # Almost all files share risk=45 — old strict-below ranked them at 0% → “safer than 100%”.
    vals = [30.0] + [45.0] * 199
    p = _percentile_rank(sorted(vals), 45.0)
    assert 40.0 <= p <= 60.0
    safer = 100.0 - p
    assert 40.0 <= safer <= 60.0


def test_midrank_true_lowest_is_elite():
    vals = [20.0] + [45.0] * 99
    p = _percentile_rank(sorted(vals), 20.0)
    assert p < 5.0
    safer = 100.0 - p
    assert safer > 95.0


def test_confidence_factors_are_five():
    rows = build_confidence_factors(enrichment=None, score=None, conf=40.0)
    assert len(rows) == 5
    keys = {r["key"] for r in rows}
    assert "soil" in keys and "flood" in keys and "wetlands" in keys and "value" in keys


def test_junk_ask_sanitized_from_inventory_row():
    row = {
        "provider_id": "public_vacant_gis",
        "asking_price_usd": 100.0,
        "acreage": 20.0,
        "raw": {"ask_role": "assessed_land"},
    }
    out = sanitize_row_asking_price(row)
    assert out["asking_price_usd"] is None
    assert out["raw"].get("ask_original_usd") == 100.0


def test_displayable_ask_keeps_rural_assessed():
    assert is_displayable_ask(
        11_540,
        acres=107,
        provider_id="public_vacant_gis",
        ask_role="assessed_land",
    )


def test_teaser_ask_not_credible_vs_mark():
    assert not is_credible_purchase_usd(
        100,
        acres=20,
        mark_usd=180_000,
        ask_role="assessed_land",
        provider_id="public_vacant_gis",
    )
    assert not is_credible_purchase_usd(
        11_540,
        acres=107,
        mark_usd=879_000,
        ask_role="assessed_land",
        provider_id="public_vacant_gis",
    )


def test_resolve_uses_value_mark_for_assessed_teaser():
    resolved = resolve_underwriting_entry(
        ask_usd=100,
        mark_usd=180_000,
        acres=20,
        ask_role="assessed_land",
        provider_id="public_vacant_gis",
    )
    assert resolved["entry_usd"] == 180_000
    assert resolved["treat_as_purchase"] is False
    assert resolved["purchase_label"] == "Value today"
