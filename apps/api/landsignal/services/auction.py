"""Auction / tax-sale clearing logic.

Opening bids and minimum bids are floors, not clearing prices. LandSignal should
not treat a $65 tax opener as a $65 buy — typical bid-up and settle bands apply.
"""

from __future__ import annotations

from typing import Any


def detect_published_price_role(listing_or_raw: Any, provider_id: str | None = None) -> str:
    """What the published dollar figure actually is — never invent a role."""
    props: dict[str, Any] = {}
    pid = provider_id
    if listing_or_raw is not None and hasattr(listing_or_raw, "raw"):
        raw = getattr(listing_or_raw, "raw", None) or {}
        pid = pid or getattr(listing_or_raw, "provider_id", None)
        props = raw.get("raw") if isinstance(raw.get("raw"), dict) else raw
        if not isinstance(props, dict):
            props = {}
    elif isinstance(listing_or_raw, dict):
        props = listing_or_raw.get("raw") if isinstance(listing_or_raw.get("raw"), dict) else listing_or_raw
        if not isinstance(props, dict):
            props = {}

    if props.get("ask_role"):
        return str(props["ask_role"])
    # Case-insensitive field scan — county GIS schemas vary.
    keyset = {str(k).lower(): v for k, v in props.items()}
    if keyset.get("lien_amount") is not None:
        return "tax_lien"
    min_bid = keyset.get("minimumbid")
    if min_bid is None:
        min_bid = keyset.get("minimum_bid")
    try:
        min_bid_n = float(min_bid) if min_bid is not None and min_bid != "" else None
    except Exception:
        min_bid_n = None
    if min_bid_n is not None and min_bid_n > 0:
        return "minimum_bid"
    if keyset.get("taxsalecost") is not None or keyset.get("tax_sale_cost") is not None:
        return "minimum_bid"
    if min_bid is not None:
        return "minimum_bid"
    if pid in ("public_tax_sale", "public_surplus"):
        return "opening_bid"
    return "asking"


def expected_auction_clearing(
    *,
    opening_bid: float | None,
    model_value: float | None,
    acres: float | None,
    provider_id: str | None,
    state: str | None = None,
) -> dict[str, Any] | None:
    """Estimate likely settle price from an opening / minimum bid.

    Returns None when the listing is not an auction-style opener.
    """
    if opening_bid is None or opening_bid <= 0:
        return None
    if provider_id not in ("public_tax_sale", "public_surplus"):
        return None

    # How cheap the opener looks vs screening value
    open_ratio = (opening_bid / model_value) if model_value and model_value > 0 else None

    # Bid-inflation priors (screening, not a promise): how far auctions typically climb
    # from a delinquency / minimum opener toward a competitive settle.
    if open_ratio is not None and open_ratio < 0.04:
        # Classic tax opener ($50–few hundred vs multi-k retail) — heavy bid-up expected
        mult_low, mult_base, mult_high = 4.0, 7.5, 14.0
        # Contested urban lots often clear much closer to land residual than the teaser implies
        settle_vs_model = 0.72
        regime = "low_opener_heavy_bidup"
    elif open_ratio is not None and open_ratio < 0.15:
        mult_low, mult_base, mult_high = 2.5, 4.5, 8.0
        settle_vs_model = 0.7
        regime = "low_opener_moderate_bidup"
    elif open_ratio is not None and open_ratio < 0.35:
        mult_low, mult_base, mult_high = 1.5, 2.3, 3.5
        settle_vs_model = 0.78
        regime = "mid_opener"
    elif open_ratio is not None and open_ratio < 0.7:
        mult_low, mult_base, mult_high = 1.12, 1.4, 1.9
        settle_vs_model = 0.88
        regime = "near_market_opener"
    else:
        # Opener already near/above model — little “bargain from the number”
        mult_low, mult_base, mult_high = 1.02, 1.12, 1.3
        settle_vs_model = 0.96
        regime = "opener_not_cheap"

    # Micro lots: more bidders relative to size → settle closer to model
    if acres is not None and acres < 1.0:
        settle_vs_model = min(0.92, settle_vs_model + 0.08)
        mult_base = max(mult_base, 6.0 if (open_ratio or 0) < 0.1 else mult_base)

    from_mult_base = opening_bid * mult_base
    from_mult_low = opening_bid * mult_low
    from_mult_high = opening_bid * mult_high

    if model_value and model_value > 0:
        from_model = model_value * settle_vs_model
        # Weight the model ceiling more — openers are noise; clearing tracks value
        expected = from_mult_base * 0.25 + from_model * 0.75
        expected = max(opening_bid, min(expected, model_value * 0.95))
        settle_low = max(opening_bid, expected * 0.65)
        settle_high = min(model_value * 0.98, max(expected * 1.25, from_mult_high))
    else:
        expected = from_mult_base
        settle_low = from_mult_low
        settle_high = from_mult_high
        expected = max(opening_bid, expected)
        settle_high = max(expected, settle_high)

    # Implied “true” discount vs model using expected settle, not the teaser opener
    settle_discount_pct = None
    if model_value and model_value > 0:
        settle_discount_pct = ((expected - model_value) / model_value) * 100.0

    opener_discount_pct = None
    if model_value and model_value > 0:
        opener_discount_pct = ((opening_bid - model_value) / model_value) * 100.0

    naive_gap = (model_value - opening_bid) if model_value else None
    realistic_edge = (model_value - expected) if model_value else None

    acres_s = f"{acres:.2f} ac" if acres is not None else "this parcel"
    st = (state or "US").upper()
    note = (
        f"Screen on {acres_s} in {st}: published ${opening_bid:,.0f} is a floor / lien figure, "
        f"not what you should expect to pay. Finish screen uses a ~{mult_base:.1f}× bid-up prior "
        f"(band {mult_low:.1f}×–{mult_high:.1f}×) → roughly "
        f"${settle_low:,.0f} – ${settle_high:,.0f}"
        + (
            f" (vs model ${model_value:,.0f})."
            if model_value
            else "."
        )
        + " Contested urban sales climb fast; thin rural auctions can finish nearer the published figure. "
        "This band is a screen — not a quoted auction result."
    )

    return {
        "is_opening_bid": True,
        "regime": regime,
        "opening_bid_usd": round(opening_bid, 2),
        "expected_settle_usd": round(expected, 2),
        "settle_low_usd": round(settle_low, 2),
        "settle_high_usd": round(settle_high, 2),
        "bid_inflation_mult_base": mult_base,
        "bid_inflation_mult_low": mult_low,
        "bid_inflation_mult_high": mult_high,
        "settle_vs_model_ratio": settle_vs_model if model_value else None,
        "opener_discount_pct": round(opener_discount_pct, 1) if opener_discount_pct is not None else None,
        "settle_discount_pct": round(settle_discount_pct, 1) if settle_discount_pct is not None else None,
        "naive_bargain_usd": round(naive_gap, 2) if naive_gap is not None else None,
        "realistic_edge_usd": round(realistic_edge, 2) if realistic_edge is not None else None,
        "comparison_price_usd": round(expected, 2),
        "note": note,
    }


def effective_comparison_price(
    ask: float | None,
    provider_id: str | None,
    model_value: float | None,
    acres: float | None,
    state: str | None,
) -> tuple[float | None, dict[str, Any] | None]:
    """Price to use for mispricing screens — settle estimate for auction channels."""
    path = expected_auction_clearing(
        opening_bid=ask,
        model_value=model_value,
        acres=acres,
        provider_id=provider_id,
        state=state,
    )
    if path:
        return path["comparison_price_usd"], path
    return ask, None
