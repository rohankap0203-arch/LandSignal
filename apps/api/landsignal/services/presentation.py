from __future__ import annotations

from typing import Any

from landsignal.services.sourcing import build_sourcing_bundle
from landsignal.services.voice import this_property


def build_action_links(
    *,
    provider_id: str | None,
    source_url: str | None,
    title: str,
    apn: str | None,
    state: str | None,
    county: str | None,
    latitude: float | None,
    longitude: float | None,
    raw: dict | None = None,
) -> list[dict[str, str]]:
    """Return actionable links: source posting, contact, parcel lookup, map."""
    bundle = build_sourcing_bundle(
        provider_id=provider_id,
        source_url=source_url,
        title=title,
        apn=apn,
        state=state,
        county=county,
        latitude=latitude,
        longitude=longitude,
        raw=raw,
    )
    return bundle["links"]


def sourcing_card(
    *,
    provider_id: str | None,
    source_url: str | None,
    title: str,
    apn: str | None,
    state: str | None,
    county: str | None,
    latitude: float | None,
    longitude: float | None,
    raw: dict | None = None,
) -> dict[str, Any]:
    return build_sourcing_bundle(
        provider_id=provider_id,
        source_url=source_url,
        title=title,
        apn=apn,
        state=state,
        county=county,
        latitude=latitude,
        longitude=longitude,
        raw=raw,
    )


def estimate_source(
    *,
    ask: float | None,
    model_value: float | None,
    provider_id: str | None,
    state: str | None,
    county: str | None,
    acres: float | None,
    apn: str | None,
    comps_normalized: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Plain-English provenance when no public asking price is published."""
    if ask is not None and ask > 0:
        return None
    if model_value is None:
        return {
            "headline": "Why there’s no dollar price yet",
            "summary": (
                "This feed has not published a sale price for this parcel, and we don’t have enough "
                "acres / local inputs yet to publish a dollar estimate either."
            ),
            "bullets": [
                "Check the official page or call the office for current pricing.",
                "Refresh this file after more map layers finish loading.",
            ],
        }

    n = comps_normalized or {}
    st = (state or "this state").upper() if state else "this state"
    ppa = n.get("ppa_prior")
    channel = {
        "public_tax_sale": "a county tax-sale / land-bank feed",
        "public_surplus": "a government surplus feed",
        "blm_lpad": "a federal BLM land feed",
    }.get(provider_id or "", "a public land feed")
    bullets: list[str] = [
        f"No asking price is published on {channel} for this property.",
    ]
    if acres and acres < 2 and provider_id in ("public_tax_sale", "public_surplus"):
        bullets.append(
            f"For this small {acres:,.2f}-acre lot, we estimate value from typical "
            f"city/suburban land prices in {st} (dollars per square foot), not farm-per-acre tables."
        )
    elif acres and ppa:
        bullets.append(
            f"Starting math: about ${float(ppa):,.0f} per acre for typical land in {st} "
            f"× {acres:,.2f} acres."
        )
        bullets.append(
            "Then we nudge that number using soil, flood, and wetlands on this exact map pin "
            "(better soil → higher; more flood/wetlands → lower)."
        )
    elif acres:
        bullets.append(
            f"Starting math uses typical land prices in {st} × {acres:,.2f} acres, "
            f"then adjusts for soil, flood, and wetlands on this pin."
        )
    else:
        bullets.append(
            f"Starting math uses typical land prices in {st}, then adjusts for what we know about this pin."
        )
    if county:
        bullets.append(f"Location used: {county}, {st}.")
    bullets.append(
        "This is a first-look estimate for ranking — not an appraisal, and not what you will definitely pay."
    )
    return {
        "headline": "Where our estimate comes from",
        "summary": (
            f"No public price is listed. We estimate about ${model_value:,.0f} for this property "
            f"so you can still compare it with other land."
        ),
        "amount_usd": model_value,
        "bullets": bullets,
    }


def price_display(
    ask: float | None,
    provider_id: str | None,
    auction_path: dict[str, Any] | None = None,
    model_value: float | None = None,
    *,
    state: str | None = None,
    county: str | None = None,
    acres: float | None = None,
    apn: str | None = None,
    comps_normalized: dict[str, Any] | None = None,
) -> dict[str, Any]:
    src = estimate_source(
        ask=ask,
        model_value=model_value,
        provider_id=provider_id,
        state=state,
        county=county,
        acres=acres,
        apn=apn,
        comps_normalized=comps_normalized,
    )
    if ask is not None and ask > 0:
        if auction_path and auction_path.get("is_opening_bid"):
            settle = (auction_path or {}).get("expected_settle_usd")
            lo = (auction_path or {}).get("settle_low_usd")
            hi = (auction_path or {}).get("settle_high_usd")
            if settle:
                # Prefer a finish band when available; still reads as start → likely finish.
                if lo and hi and float(hi) > float(lo):
                    display = (
                        f"${ask:,.0f} start · ~${float(lo):,.0f} – ${float(hi):,.0f} likely finish"
                    )
                else:
                    display = f"${ask:,.0f} start · ~${float(settle):,.0f} likely finish"
                return {
                    "amount_usd": ask,
                    "label": "Starting bid → likely finish",
                    "display": display,
                    "kind": "minimum_bid",
                    "opening_bid_usd": ask,
                    "expected_settle_usd": settle,
                    "settle_low_usd": lo,
                    "settle_high_usd": hi,
                    "note": (auction_path or {}).get("note"),
                    "estimate_source": None,
                }
            return {
                "amount_usd": ask,
                "label": "Starting bid (not final price)",
                "display": f"${ask:,.0f} start (usually finishes higher)",
                "kind": "minimum_bid",
                "opening_bid_usd": ask,
                "estimate_source": None,
            }
        return {
            "amount_usd": ask,
            "label": "Listed price",
            "display": f"${ask:,.0f}",
            "kind": "asking",
            "estimate_source": None,
        }
    if provider_id == "blm_lpad":
        return {
            "amount_usd": None,
            "label": "No public price yet",
            "display": (
                f"Federal land · our estimate ${model_value:,.0f}"
                if model_value
                else "Federal land (no public price yet)"
            ),
            "kind": "process",
            "model_value_usd": model_value,
            "estimate_source": src,
        }
    if provider_id in ("public_tax_sale", "public_surplus"):
        return {
            "amount_usd": None,
            "label": "No public price yet",
            "display": (
                f"No public price · our estimate ${model_value:,.0f}"
                if model_value
                else "No public price on this feed"
            ),
            "kind": "unpriced_inventory",
            "model_value_usd": model_value,
            "estimate_source": src,
        }
    return {
        "amount_usd": None,
        "label": "No public price yet",
        "display": (
            f"No public price · our estimate ${model_value:,.0f}"
            if model_value
            else "No public price on this feed"
        ),
        "kind": "inquiry",
        "model_value_usd": model_value,
        "estimate_source": src,
    }


def value_display(estimated: float | None, knowledge: str | None) -> dict[str, Any]:
    if estimated is None:
        return {
            "amount_usd": None,
            "label": "Our estimated value",
            "display": "Not enough data yet for a dollar estimate",
            "knowledge_state": knowledge or "UNKNOWN",
            "basis": "today_dollars",
            "basis_label": "in today’s $",
        }
    return {
        "amount_usd": estimated,
        "label": "Our estimated value",
        "display": f"${estimated:,.0f}",
        "knowledge_state": knowledge or "ESTIMATED",
        "basis": "today_dollars",
        "basis_label": "in today’s $",
    }


def match_reasons(
    *,
    score,
    parcel,
    listing,
    filters: dict[str, Any],
    enrichment=None,
) -> list[str]:
    """Short, plain reasons unique to this listing."""
    reasons: list[str] = []
    est = getattr(score, "estimated_value_usd", None)
    ask = listing.asking_price_usd if listing else None
    apn = getattr(parcel, "apn", None) or ""
    prop = this_property(parcel, listing)
    auction = None
    if enrichment and enrichment.comps:
        auction = (enrichment.comps.normalized or {}).get("auction_path")
    if isinstance(auction, dict) and auction.get("expected_settle_usd") and est:
        settle = float(auction["expected_settle_usd"])
        gap = ((est - settle) / settle) * 100 if settle else 0
        reasons.append(f"Likely finish ~${settle:,.0f} vs value ${est:,.0f} ({gap:+.0f}%)")
    elif score.asking_discount_pct is not None and score.asking_discount_pct < -10:
        reasons.append(f"About {abs(score.asking_discount_pct):.0f}% under our value estimate")
    elif ask is None and est:
        reasons.append(f"No public price · estimate ${est:,.0f}")
    if score.best_strategy:
        reasons.append(f"Best use: {score.best_strategy.value.replace('_', ' ').title()}")
    if score.risk <= 35:
        reasons.append(f"Lower map risk ({score.risk:.0f}/100)")
    elif score.risk >= 55:
        reasons.append(f"Higher risk ({score.risk:.0f}/100)")
    if listing and listing.provider_id == "blm_lpad":
        reasons.append("Federal BLM — slower process")
    if listing and listing.provider_id == "public_tax_sale":
        reasons.append("County tax sale — more paperwork")
    acres = getattr(parcel, "acreage", None)
    if acres and acres >= 40:
        reasons.append(f"Large tract ({acres:,.0f} acres)")
    if not reasons:
        reasons.append("Passes first automated checks")
    return reasons[:3]


def _card_nuance(enrichment) -> str | None:
    """One cheap nuance clause for search cards (no full path engine)."""
    if not enrichment:
        return None
    bits: list[str] = []

    def _n(attr: str) -> dict:
        prov = getattr(enrichment, attr, None)
        if not prov:
            return {}
        return prov.normalized or prov.value or {}

    soil = _n("soil")
    flood = _n("flood")
    wet = _n("wetlands")
    growth = _n("growth") or _n("comps")
    try:
        prime = float(soil.get("prime_farmland_pct")) if soil.get("prime_farmland_pct") is not None else None
    except Exception:
        prime = None
    try:
        flood_pct = float(flood.get("flood_zone_pct")) if flood.get("flood_zone_pct") is not None else None
    except Exception:
        flood_pct = None
    try:
        wet_pct = float(wet.get("wetland_pct")) if wet.get("wetland_pct") is not None else None
    except Exception:
        wet_pct = None
    try:
        g = growth.get("path_of_growth_score")
        growth_score = float(g) if g is not None else None
    except Exception:
        growth_score = None

    if flood_pct is not None and flood_pct >= 20:
        bits.append(f"flood ~{flood_pct:.0f}% slows the path")
    elif wet_pct is not None and wet_pct >= 15:
        bits.append(f"wetlands ~{wet_pct:.0f}% trim usable acres")
    elif prime is not None and prime >= 45:
        bits.append(f"~{prime:.0f}% prime soil supports rent")
    elif growth_score is not None and growth_score >= 65:
        bits.append("growth corridor lifts the hold case")
    if not bits:
        return "path bends with local screens — not a flat line"
    return bits[0]


def build_return_thesis(
    *,
    score,
    listing,
    auction_path: dict[str, Any] | None = None,
    enrichment=None,
) -> tuple[str | None, str | None]:
    """One plain line for cards: buy price vs our value + conviction."""
    est = getattr(score, "estimated_value_usd", None)
    ask = listing.asking_price_usd if listing else None
    settle = None
    if isinstance(auction_path, dict):
        settle = auction_path.get("expected_settle_usd")
    entry = settle or (ask if ask and ask > 0 else None)
    provider = listing.provider_id if listing else None
    if entry is None and est:
        entry = est * (0.62 if provider in ("public_tax_sale", "public_surplus") else 0.85)
    opp = float(getattr(score, "opportunity", 0) or 0)
    risk = float(getattr(score, "risk", 0) or 0)
    conf = float(getattr(score, "confidence", 0) or 0)
    gap_pct = ((est - entry) / entry * 100) if est and entry else None
    conviction = (
        "HIGH"
        if opp >= 66 and risk <= 55 and conf >= 32 and (gap_pct is None or gap_pct >= 10)
        else "MEDIUM"
        if opp >= 50 and risk <= 62
        else "WATCH"
    )
    strat = (
        score.best_strategy.value.replace("_", " ").title()
        if score.best_strategy
        else "Land"
    )
    interest = (
        "Strong interest"
        if conviction == "HIGH"
        else "Moderate interest"
        if conviction == "MEDIUM"
        else "Worth watching"
    )
    # Keep card thesis to 1 tight line (detail page carries the multi-factor path)
    if entry and est and gap_pct is not None:
        thesis = f"{interest} · ~${entry:,.0f} buy vs ${est:,.0f} value ({gap_pct:+.0f}%)"
    elif est:
        thesis = f"{interest} · value ~${est:,.0f} · {strat}"
    else:
        thesis = f"{interest} · {strat} possible"
    return thesis, conviction


def rating_breakdown(score, parcel=None, listing=None) -> list[dict[str, Any]]:
    """Parcel-bound justifications for every rating bar."""
    from landsignal.services.justify import rating_breakdown_justified

    return rating_breakdown_justified(score, parcel=parcel, listing=listing)
