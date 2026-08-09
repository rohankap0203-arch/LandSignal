from __future__ import annotations

from typing import Any

from landsignal.services.sourcing import build_sourcing_bundle


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
        f"No asking price is published on {channel} for {apn or 'this parcel'}.",
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
            f"No public price is listed. We estimate about ${model_value:,.0f} for "
            f"{apn or 'this parcel'} so you can still compare it with other land."
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
            if settle:
                return {
                    "amount_usd": ask,
                    "label": "Starting bid → likely finish",
                    "display": f"${ask:,.0f} start · ~${settle:,.0f} likely finish",
                    "kind": "minimum_bid",
                    "opening_bid_usd": ask,
                    "expected_settle_usd": settle,
                    "settle_low_usd": (auction_path or {}).get("settle_low_usd"),
                    "settle_high_usd": (auction_path or {}).get("settle_high_usd"),
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
        }
    return {
        "amount_usd": estimated,
            "label": "Our estimated value",
            "display": f"${estimated:,.0f}",
            "knowledge_state": knowledge or "ESTIMATED",
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
    apn = getattr(parcel, "apn", None) or "this parcel"
    auction = None
    if enrichment and enrichment.comps:
        auction = (enrichment.comps.normalized or {}).get("auction_path")
    if isinstance(auction, dict) and auction.get("expected_settle_usd") and est:
        settle = float(auction["expected_settle_usd"])
        gap = ((est - settle) / settle) * 100 if settle else 0
        reasons.append(
            f"Likely auction finish ~${settle:,.0f} vs our value ${est:,.0f} "
            f"({gap:+.0f}% room on {apn})"
        )
    elif score.asking_discount_pct is not None and score.asking_discount_pct < -10:
        reasons.append(
            f"Buy price looks about {abs(score.asking_discount_pct):.0f}% under our value estimate"
        )
    elif ask is None and est:
        reasons.append(f"No public price yet · our value estimate is ${est:,.0f}")
    if score.best_strategy:
        reasons.append(
            f"Best use we see: {score.best_strategy.value.replace('_', ' ').title()} "
            f"(opportunity {score.opportunity:.0f}/100)"
        )
    if score.risk <= 35:
        reasons.append(f"Lower risk on the map checks ({score.risk:.0f}/100)")
    elif score.risk >= 55:
        reasons.append(f"Higher risk ({score.risk:.0f}/100) — budget extra homework")
    if score.confidence >= 55:
        reasons.append(f"File looks fairly complete ({score.confidence:.0f}/100)")
    if listing and listing.provider_id == "blm_lpad":
        reasons.append("Federal BLM land — fewer retail buyers, slower process")
    if listing and listing.provider_id == "public_tax_sale":
        reasons.append("County tax-sale listing — more paperwork, often less competition")
    acres = getattr(parcel, "acreage", None)
    if acres and acres >= 40:
        reasons.append(f"Large tract ({acres:,.0f} acres) — big enough to hold on its own")
    if not reasons:
        reasons.append(f"{apn} passes the first automated checks for a closer look")
    return reasons[:5]


def build_return_thesis(
    *,
    score,
    listing,
    auction_path: dict[str, Any] | None = None,
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
        if opp >= 68 and risk <= 42 and conf >= 40 and (gap_pct is None or gap_pct >= 12)
        else "MEDIUM"
        if opp >= 52 and risk <= 58
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
    if entry and est and gap_pct is not None:
        thesis = (
            f"{interest} · plan on ~${entry:,.0f} vs our value ${est:,.0f} "
            f"({gap_pct:+.0f}%) · best use {strat}"
        )
    elif est:
        thesis = f"{interest} · our value ~${est:,.0f} · best use {strat}"
    else:
        thesis = f"{interest} · {strat} looks possible — confirm local prices"
    return thesis, conviction


def rating_breakdown(score, parcel=None, listing=None) -> list[dict[str, Any]]:
    """Parcel-bound justifications for every rating bar."""
    from landsignal.services.justify import rating_breakdown_justified

    return rating_breakdown_justified(score, parcel=parcel, listing=listing)
