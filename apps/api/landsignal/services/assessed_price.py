"""Extract assessor land marks so budget filters work in every state.

Public vacant GIS rarely has a true MLS ask. County/state CAD layers expose
land assessed / market land values under many field names — including nested
under listing.raw["raw"] after persistence.

Accuracy rules:
- Prefer land-only fields for vacant tracts.
- Never treat building/improvement totals as a vacant-land ask.
- When a dwelling is on site and we only have land AV, do not pretend that
  land AV is the whole-property budget — use total assessed or the model mark.
"""

from __future__ import annotations

from typing import Any

# Land-only marks (never include improvement / building totals here).
_LAND_ONLY_KEYS = (
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
    "Land",
)

# Whole-parcel assessed / market totals — usable only when land-only is missing
# on unimproved tracts, or as a budget proxy when a home is on site.
_TOTAL_VALUE_KEYS = (
    "TOT_VAL",
    "TOTAL_VAL",
    "TotalValue",
    "total_value",
    "MARKET_VALUE",
    "MarketValue",
    "market_value",
    "MKT_VAL",
    "APPRAISED_VAL",
    "AppraisedValue",
    "AssessedValue",
    "assessed_value",
    "JUST_VALUE",
    "JustValue",
    "TAX_VAL",
    "TaxVal",
)

_IMPROVEMENT_VALUE_KEYS = (
    "IMPRVT_VAL",
    "impr_value",
    "IMPROVEMENT_VALUE",
    "ImprovementValue",
    "improvement_value",
    "NFMIMPVL",
    "BLDG_VAL",
    "BldgVal",
    "BuildingValue",
    "building_value",
    "IMP_VAL",
    "ImpVal",
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


def _blobs(raw: Any) -> list[dict]:
    if not isinstance(raw, dict):
        return []
    blobs: list[dict] = [raw]
    inner = raw.get("raw")
    if isinstance(inner, dict):
        blobs.append(inner)
    return blobs


def _first_key(blobs: list[dict], keys: tuple[str, ...]) -> float | None:
    for blob in blobs:
        for key in keys:
            num = _as_positive_float(blob.get(key))
            if num is not None:
                return num
    return None


def raw_has_improvement_value(raw: Any) -> bool:
    """True when CAD reports a positive building / improvement dollar mark."""
    return _first_key(_blobs(raw), _IMPROVEMENT_VALUE_KEYS) is not None


def extract_assessed_land_usd(raw: Any) -> float | None:
    """Return best land-value mark from a listing.raw blob (any nesting).

    Prefers land-only fields. Falls back to total assessed ONLY when the blob
    shows no improvement dollars — otherwise totals would overstate vacant land
    or understate a home (depending on misuse).
    """
    blobs = _blobs(raw)
    if not blobs:
        return None
    land = _first_key(blobs, _LAND_ONLY_KEYS)
    if land is not None:
        return land
    if raw_has_improvement_value(raw):
        # Improved parcel with no land-only field — do not invent a vacant ask
        # from the whole-property total.
        return None
    return _first_key(blobs, _TOTAL_VALUE_KEYS)


def extract_assessed_total_usd(raw: Any) -> float | None:
    """Whole-parcel assessed / market total when present."""
    return _first_key(_blobs(raw), _TOTAL_VALUE_KEYS)


def resolve_budget_filter_usd(
    *,
    ask: float | None = None,
    raw: Any = None,
    estimated_value_usd: float | None = None,
    has_structure: bool = False,
    ask_role: str | None = None,
    auction_settle_usd: float | None = None,
) -> float | None:
    """Dollar used for price-band filters — as honest as available data allows.

    - Auction settle when known (what you actually pay).
    - Published ask when it is a real list / opener (not land-AV-with-home).
    - Property on site + land AV only → total assessed, else model mark
      (never the land-only teaser as a whole-home budget).
    - Vacant GIS → land assessed ask / land extract.
    """
    settle = _as_positive_float(auction_settle_usd)
    if settle is not None:
        return float(settle)

    role = str(ask_role or "").strip().lower()
    ask_n = _as_positive_float(ask)
    land_av_role = role in {"assessed_land", "assessed", "land_av", "tax_assessed"}
    est = _as_positive_float(estimated_value_usd)

    # Homes with only a land-assessment mark: land AV is NOT the buy price.
    if has_structure and land_av_role:
        total = extract_assessed_total_usd(raw)
        if total is not None:
            return float(total)
        if est is not None:
            return float(est)
        # No honest whole-property dollars — unknown (fail closed when band set).
        return None

    if ask_n is not None:
        return float(ask_n)

    assessed = extract_assessed_land_usd(raw)
    if assessed is not None:
        return float(assessed)
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
