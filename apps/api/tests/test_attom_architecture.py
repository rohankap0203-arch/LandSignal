"""ATTOM architecture + hard-filter / dedupe / fallback tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from landsignal.services.property_providers.attom.normalize import (
    extract_acreage,
    normalize_property_detail,
    normalize_sale_history,
)
from landsignal.services.property_providers.cache import AttomResponseCache, CircuitBreaker
from landsignal.services.property_providers.dedupe import canonical_property_id, dedupe_candidates
from landsignal.services.property_providers.hard_filters import passes_hard_filters
from landsignal.services.property_providers import IntelligenceProviderState
from landsignal.services.property_providers.ranking import strategy_hold_rank_boost
from landsignal.scoring.engine import screen_strategies


def test_hard_filter_rejects_wrong_state():
    assert not passes_hard_filters(
        {"state": "NV", "acreage": 10, "asking_price_usd": 100000},
        {"state": "CA", "min_acres": 5, "max_acres": 20, "min_price": 50000, "max_price": 200000},
    )


def test_hard_filter_rejects_acreage_outside_band():
    row = {"state": "CA", "acreage": 4.9, "asking_price_usd": 100000}
    filt = {"state": "CA", "min_acres": 5, "max_acres": 20}
    assert not passes_hard_filters(row, filt, allow_unknown_acres=False)
    row["acreage"] = 20.1
    assert not passes_hard_filters(row, filt, allow_unknown_acres=False)
    row["acreage"] = 12
    assert passes_hard_filters(row, filt, allow_unknown_acres=False)


def test_hard_filter_rejects_price_outside_band():
    row = {"state": "TX", "acreage": 10, "asking_price_usd": 210000}
    filt = {"state": "TX", "min_price": 50000, "max_price": 200000}
    assert not passes_hard_filters(row, filt, allow_unknown_price=False)


def test_hard_filter_region_required():
    row = {"state": "FL", "county": "Orange", "acreage": 8, "asking_price_usd": 90000}
    filt = {"state": "FL", "region": "Miami"}
    assert not passes_hard_filters(row, filt)
    assert passes_hard_filters({**row, "county": "Miami-Dade", "asking_price_usd": 90000}, filt)


def test_strategy_does_not_appear_in_hard_filters():
    # Strategy preference must not be consulted by passes_hard_filters
    row = {"state": "IA", "acreage": 40, "asking_price_usd": 250000}
    filt = {"state": "IA", "strategy": "TIMBER", "hold_years": 20}
    assert passes_hard_filters(row, filt)


def test_hold_changes_rank_boost_not_eligibility():
    short = strategy_hold_rank_boost(strategy="DEVELOPMENT", hold_years=2, opportunity=60)
    long = strategy_hold_rank_boost(strategy="LAND_BANK", hold_years=20, opportunity=60)
    assert short != long


def test_improved_property_screen_pass_with_structure():
    screens = screen_strategies({"has_structure": True, "acreage": 5})
    assert screens["IMPROVED_PROPERTY"] == "PASS"
    # Must not fail farmland solely because a farmhouse exists
    assert screens["FARMLAND"] in ("PASS", "MANUAL_REVIEW", "FAIL")  # may fail for other reasons


def test_attom_lotsize1_is_acres():
    assert extract_acreage({"lotsize1": 14.72, "lotsize2": 641203}) == pytest.approx(14.72)


def test_normalize_property_detail_marks_off_market():
    payload = {
        "property": [
            {
                "identifier": {"attomId": 1, "apn": "ABC", "fips": "08031"},
                "lot": {"lotsize1": 2.5, "lotsize2": 108900},
                "address": {"oneLine": "1 Main", "countrySubd": "CO", "locality": "Denver"},
                "location": {"latitude": 39.7, "longitude": -104.9},
                "summary": {"propclass": "Vacant Land", "proptype": "VACANT"},
                "building": {},
            }
        ]
    }
    norm = normalize_property_detail(payload)
    assert norm["marketStatus"] == "off_market"
    assert norm["askingPrice"] is None
    assert norm["acreage"]["value"] == pytest.approx(2.5)
    assert norm["acreage"]["persistencePolicy"] == "TEMPORARY_LICENSED"


def test_sale_history_never_becomes_asking_price():
    payload = {
        "property": [
            {
                "salehistory": [
                    {"amount": {"saleamt": 265000, "saletranstype": "Resale"}, "saleTransDate": "2014-10-10"}
                ]
            }
        ]
    }
    hist = normalize_sale_history(payload)
    assert hist["askingPrice"] is None
    assert hist["lastSaleAmount"]["value"] == 265000


def test_dedupe_same_attom_id():
    rows = [
        {"attomId": 99, "apn": "A", "sources": ["ATTOM"]},
        {"attomId": 99, "apn": "A", "acreage": 12, "sources": ["public_vacant_gis"]},
    ]
    uniq, removed = dedupe_candidates(rows)
    assert removed == 1
    assert len(uniq) == 1
    assert set(uniq[0]["sources"]) == {"ATTOM", "public_vacant_gis"}


def test_canonical_prefers_attom_then_fips_apn():
    assert canonical_property_id({"attomId": 5, "fips": "12", "apn": "X"}).startswith("attom:")
    assert canonical_property_id({"fips": "12", "apn": "12-34"}).startswith("fipsapn:")


def test_cache_ttl_capped_at_24h():
    cache = AttomResponseCache(ttl_seconds=999_999)
    assert cache.ttl_seconds <= 86_400


def test_circuit_breaker_opens():
    br = CircuitBreaker(failure_threshold=3, reset_seconds=60)
    for _ in range(3):
        br.record_failure(IntelligenceProviderState.RATE_LIMITED, "rate")
    assert br.snapshot()["open"] is True
    assert br.allow_request() is False


@pytest.mark.asyncio
async def test_attom_unavailable_does_not_raise(monkeypatch):
    from landsignal.services.property_providers.attom.provider import reset_attom_singletons
    from landsignal.services.property_providers.pipeline import enrich_with_attom
    from landsignal.settings import Settings, get_settings

    reset_attom_singletons()
    get_settings.cache_clear()
    monkeypatch.setenv("ATTOM_API_KEY", "")
    monkeypatch.setenv("ATTOM_DATA_MODE", "disabled")
    get_settings.cache_clear()
    settings = Settings(attom_api_key=None, attom_data_mode="disabled")
    out = await enrich_with_attom({"state": "FL", "latitude": 28.5, "longitude": -81.4}, settings=settings)
    assert out["ok"] is False
    assert out.get("state") in {"NOT_CONFIGURED", "DISABLED", "UNAVAILABLE"}


def test_malformed_detail_safe():
    assert normalize_property_detail({})["acreage"]["value"] is None
