"""Credible buy prices vs assessor marks / teaser openers.

Public vacant GIS often publishes a CAD land mark as asking_price_usd. Tiny
marks ($1–$100, or a few dollars per acre) are not market purchases. Using them
as “Purchase today” makes inflation / return screens look like lottery tickets.
"""

from __future__ import annotations

from typing import Any

# Absolute floors — below this, dollars are not a credible buy for underwriting.
MIN_CREDIBLE_ASK_USD = 2_500.0
# Soft floor for inventory display (cards / filters): junk CAD noise only.
MIN_DISPLAY_ASK_USD = 500.0
MIN_DISPLAY_ASK_PER_ACRE = 25.0
# When published ask is a tiny fraction of our value mark, treat as non-entry.
MAX_TEASER_TO_MARK = 0.15


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def detect_ask_role(listing_or_raw: Any = None, provider_id: str | None = None) -> str | None:
    props: dict[str, Any] = {}
    pid = provider_id
    if listing_or_raw is not None and hasattr(listing_or_raw, "raw"):
        raw = getattr(listing_or_raw, "raw", None) or {}
        pid = pid or getattr(listing_or_raw, "provider_id", None)
        props = raw.get("raw") if isinstance(raw.get("raw"), dict) else raw
        if not isinstance(props, dict):
            props = {}
    elif isinstance(listing_or_raw, dict):
        props = (
            listing_or_raw.get("raw")
            if isinstance(listing_or_raw.get("raw"), dict)
            else listing_or_raw
        )
        if not isinstance(props, dict):
            props = {}
        pid = pid or props.get("provider_id")
    role = props.get("ask_role")
    if role:
        return str(role)
    return None


def is_displayable_ask(
    ask: float | None,
    *,
    acres: float | None = None,
    provider_id: str | None = None,
    ask_role: str | None = None,
) -> bool:
    """Keep budget filters honest — drop only clear CAD junk, not rural assessed marks."""
    a = _f(ask)
    if a is None or a <= 0:
        return False
    if a < MIN_DISPLAY_ASK_USD:
        return False
    ac = _f(acres)
    if (
        ac is not None
        and ac >= 1.0
        and (a / ac) < MIN_DISPLAY_ASK_PER_ACRE
        and (ask_role == "assessed_land" or provider_id == "public_vacant_gis")
    ):
        return False
    return True


def is_credible_purchase_usd(
    ask: float | None,
    *,
    acres: float | None = None,
    mark_usd: float | None = None,
    ask_role: str | None = None,
    provider_id: str | None = None,
) -> bool:
    """True when ask is safe to treat as a real buy for return / inflation math."""
    a = _f(ask)
    if a is None or a <= 0:
        return False
    if a < MIN_CREDIBLE_ASK_USD:
        return False
    ac = _f(acres)
    if ac is not None and ac >= 5.0 and (a / ac) < 50.0 and ask_role == "assessed_land":
        # Extreme $/ac assessed teaser (e.g. $100 on 20ac) — not a purchase.
        return False
    mark = _f(mark_usd)
    if mark is not None and mark > 0 and (a / mark) < MAX_TEASER_TO_MARK:
        # Assessed / opener is a teaser vs our value — use mark for underwriting.
        if ask_role in ("assessed_land", "minimum_bid", "opening_bid", "tax_lien") or provider_id in (
            "public_vacant_gis",
            "public_tax_sale",
            "public_surplus",
        ):
            return False
    return True


def resolve_underwriting_entry(
    *,
    ask_usd: float | None,
    mark_usd: float | None,
    acres: float | None = None,
    ask_role: str | None = None,
    provider_id: str | None = None,
    auction_settle_usd: float | None = None,
) -> dict[str, Any]:
    """Pick the dollar we underwrite as day-one capital outlay.

    Returns entry_usd, entry_basis, and whether inflation UI should say Purchase vs Value.
    """
    settle = _f(auction_settle_usd)
    if settle is not None and settle > 0:
        return {
            "entry_usd": round(settle, 0),
            "entry_basis": "auction_settle",
            "purchase_label": "Expected settle",
            "treat_as_purchase": True,
        }

    ask = _f(ask_usd)
    mark = _f(mark_usd)
    if is_credible_purchase_usd(
        ask,
        acres=acres,
        mark_usd=mark,
        ask_role=ask_role,
        provider_id=provider_id,
    ):
        return {
            "entry_usd": round(ask, 0),  # type: ignore[arg-type]
            "entry_basis": "published_ask",
            "purchase_label": "Purchase today",
            "treat_as_purchase": True,
        }

    if mark is not None and mark > 0:
        # Channel discount only when we truly lack a buy — keep inflation honest.
        if provider_id in ("public_tax_sale", "public_surplus"):
            entry = mark * 0.62
            basis = "mark_process_discount"
        elif ask_role == "assessed_land" or provider_id == "public_vacant_gis":
            # Assessed mark ≠ buy-it-now. Screen on our value, not a teaser CAD ask.
            entry = mark
            basis = "value_mark"
        else:
            entry = mark * 0.85
            basis = "mark_screen_discount"
        return {
            "entry_usd": round(float(entry), 0),
            "entry_basis": basis,
            "purchase_label": "Value today" if basis == "value_mark" else "Underwritten entry",
            "treat_as_purchase": basis != "value_mark",
        }

    return {
        "entry_usd": None,
        "entry_basis": "none",
        "purchase_label": "Value today",
        "treat_as_purchase": False,
    }


def sanitize_row_asking_price(row: dict[str, Any]) -> dict[str, Any]:
    """Null junk assessed asks on inventory rows (keeps parcel; clears fake price)."""
    ask = _f(row.get("asking_price_usd"))
    if ask is None:
        return row
    acres = _f(row.get("acreage"))
    provider = str(row.get("provider_id") or "")
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    role = None
    if isinstance(raw, dict):
        role = raw.get("ask_role")
        inner = raw.get("raw")
        if role is None and isinstance(inner, dict):
            role = inner.get("ask_role")
    if is_displayable_ask(ask, acres=acres, provider_id=provider, ask_role=str(role) if role else None):
        return row
    out = dict(row)
    out["asking_price_usd"] = None
    if isinstance(raw, dict):
        out_raw = dict(raw)
        out_raw["ask_sanitized"] = "non_credible_display"
        out_raw["ask_original_usd"] = ask
        out["raw"] = out_raw
    return out
