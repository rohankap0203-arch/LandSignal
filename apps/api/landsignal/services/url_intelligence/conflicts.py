"""Data conflict engine — record disagreements; never silently overwrite."""

from __future__ import annotations

from typing import Any

# Higher = more authoritative for financial/acreage calculations
_SOURCE_RANK = {
    "USER_CONFIRMED": 100,
    "user": 100,
    "county": 90,
    "federal_dataset": 85,
    "state_dataset": 80,
    "geospatial_calculation": 75,
    "LandSignal_model": 70,
    "parcel": 68,
    "listing": 50,
    "AI_extraction": 40,
}


def _rank(source: str | None) -> int:
    if not source:
        return 30
    return _SOURCE_RANK.get(source, 35)


def record_conflict(
    field: str,
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    message: str | None = None,
) -> dict[str, Any]:
    lv = left.get("value")
    rv = right.get("value")
    primary = left if _rank(left.get("source")) >= _rank(right.get("source")) else right
    secondary = right if primary is left else left
    msg = message or (
        f"Data discrepancy detected: {field} reports {lv} from {left.get('source')} "
        f"vs {rv} from {right.get('source')}."
    )
    return {
        "field": field,
        "message": msg,
        "values": [left, right],
        "primary": primary,
        "secondary": secondary,
        "knowledgeState": "CONFLICTING",
    }


def detect_acreage_conflict(
    listing_acres: float | None,
    parcel_acres: float | None,
    *,
    listing_source: str = "listing",
    parcel_source: str = "parcel",
) -> dict[str, Any] | None:
    if listing_acres is None or parcel_acres is None:
        return None
    try:
        a, b = float(listing_acres), float(parcel_acres)
    except (TypeError, ValueError):
        return None
    if a <= 0 or b <= 0:
        return None
    ratio = max(a, b) / min(a, b)
    if ratio < 1.05:  # ~5% tolerance
        return None
    left = {"value": a, "source": listing_source, "unit": "acres", "confidence": 0.9}
    right = {"value": b, "source": parcel_source, "unit": "acres", "confidence": 0.85}
    return record_conflict(
        "acreage",
        left,
        right,
        message=(
            f"Data discrepancy detected: Listing reports {a:g} acres. "
            f"Parcel records indicate {b:g} acres."
        ),
    )


def detect_price_conflict(
    listing_price: float | None,
    other_price: float | None,
    *,
    other_source: str = "county",
) -> dict[str, Any] | None:
    if listing_price is None or other_price is None:
        return None
    try:
        a, b = float(listing_price), float(other_price)
    except (TypeError, ValueError):
        return None
    if a <= 0 or b <= 0:
        return None
    ratio = max(a, b) / min(a, b)
    if ratio < 1.25:
        return None
    return record_conflict(
        "askingPrice",
        {"value": a, "source": "listing", "unit": "USD", "confidence": 0.95},
        {"value": b, "source": other_source, "unit": "USD", "confidence": 0.7},
    )
