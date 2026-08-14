"""Extract assessor land marks so budget filters work in every state.

Public vacant GIS rarely has a true MLS ask. County/state CAD layers expose
land assessed / market land values under many field names — including nested
under listing.raw["raw"] after persistence.
"""

from __future__ import annotations

from typing import Any

# Prefer land-only marks; never treat building/improvement totals as budget price.
_LAND_VALUE_KEYS = (
    "LND_VAL",
    "LAND_VAL",
    "Land_Value",
    "LandVal",
    "land_value",
    "LAND_VALUE",
    "LAND_AV",
    "LAND_LV",
    "LNDVALUE",
    "LndValue",
    "VALUE_LAND",
    "landval",
    "landvalue",
    "LandValue",
    "LandAppr",
    "LandAssd",
    "Assessed_Land",
    "Assessed_Land_Value",
    "assessed_land_usd",
    "LAND_MKT_VALUE",
    "MARKETLAND",
    "TOT_VAL",  # last-resort when layer only publishes total and tract is unimproved
    "Land",
)


def _as_positive_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if num > 0:
        return num
    return None


def extract_assessed_land_usd(raw: Any) -> float | None:
    """Return first positive land-value mark from a listing.raw blob (any nesting)."""
    if not isinstance(raw, dict):
        return None
    blobs: list[dict] = [raw]
    inner = raw.get("raw")
    if isinstance(inner, dict):
        blobs.append(inner)
    for blob in blobs:
        for key in _LAND_VALUE_KEYS:
            num = _as_positive_float(blob.get(key))
            if num is not None:
                return num
    return None


def backfill_listing_ask_from_assessed(listing: Any) -> bool:
    """If listing has no ask, copy assessor land value into asking_price_usd.

    Returns True when the listing was updated.
    """
    ask = getattr(listing, "asking_price_usd", None)
    if ask is not None and ask > 0:
        return False
    assessed = extract_assessed_land_usd(getattr(listing, "raw", None))
    if assessed is None:
        return False
    listing.asking_price_usd = float(assessed)
    raw = getattr(listing, "raw", None)
    if isinstance(raw, dict) and not raw.get("ask_role"):
        raw["ask_role"] = "assessed_land"
    return True


def backfill_store_assessed_asks(store: Any) -> dict[str, int]:
    """Apply assessed-land asks across the whole inventory (every state)."""
    from landsignal.services.purchase_credibility import (
        detect_ask_role,
        is_displayable_ask,
    )

    updated = 0
    scanned = 0
    cleared = 0
    for listing in list(getattr(store, "listings", {}).values()):
        scanned += 1
        if backfill_listing_ask_from_assessed(listing):
            updated += 1
        ask = getattr(listing, "asking_price_usd", None)
        if ask is None:
            continue
        parcel = getattr(store, "parcels", {}).get(getattr(listing, "parcel_id", None))
        acres = getattr(parcel, "acreage", None) if parcel else None
        role = detect_ask_role(listing)
        if not is_displayable_ask(
            ask,
            acres=acres,
            provider_id=getattr(listing, "provider_id", None),
            ask_role=role,
        ):
            raw = getattr(listing, "raw", None)
            if isinstance(raw, dict):
                raw = dict(raw)
                raw["ask_sanitized"] = "non_credible_display"
                raw["ask_original_usd"] = float(ask)
                listing.raw = raw
            listing.asking_price_usd = None
            cleared += 1
    return {"scanned": scanned, "updated": updated, "cleared_junk_asks": cleared}
