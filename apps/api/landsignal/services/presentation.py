from __future__ import annotations

from typing import Any

from landsignal.services.humanize import CATEGORY_HELP
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


def price_display(
    ask: float | None,
    provider_id: str | None,
    auction_path: dict[str, Any] | None = None,
    model_value: float | None = None,
) -> dict[str, Any]:
    if ask is not None and ask > 0:
        if auction_path and auction_path.get("is_opening_bid"):
            settle = (auction_path or {}).get("expected_settle_usd")
            if settle:
                return {
                    "amount_usd": ask,
                    "label": "Opening bid → expected settle",
                    "display": f"${ask:,.0f} opener · ~${settle:,.0f} settle",
                    "kind": "minimum_bid",
                    "opening_bid_usd": ask,
                    "expected_settle_usd": settle,
                    "settle_low_usd": (auction_path or {}).get("settle_low_usd"),
                    "settle_high_usd": (auction_path or {}).get("settle_high_usd"),
                    "note": (auction_path or {}).get("note"),
                }
            return {
                "amount_usd": ask,
                "label": "Minimum / opening bid",
                "display": f"${ask:,.0f} opener (not settle)",
                "kind": "minimum_bid",
                "opening_bid_usd": ask,
            }
        return {
            "amount_usd": ask,
            "label": "Listed price",
            "display": f"${ask:,.0f}",
            "kind": "asking",
        }
    if provider_id == "blm_lpad":
        return {
            "amount_usd": None,
            "label": "Price process",
            "display": (
                f"Federal disposal · model ${model_value:,.0f}"
                if model_value
                else "Federal disposal (no retail ask)"
            ),
            "kind": "process",
            "model_value_usd": model_value,
        }
    if provider_id in ("public_tax_sale", "public_surplus"):
        return {
            "amount_usd": None,
            "label": "No published ask",
            "display": (
                f"No public ask · model ${model_value:,.0f}"
                if model_value
                else "No public ask on this feed"
            ),
            "kind": "unpriced_inventory",
            "model_value_usd": model_value,
        }
    return {
        "amount_usd": None,
        "label": "No published ask",
        "display": (
            f"No public ask · model ${model_value:,.0f}"
            if model_value
            else "No public ask on this feed"
        ),
        "kind": "inquiry",
        "model_value_usd": model_value,
    }


def value_display(estimated: float | None, knowledge: str | None) -> dict[str, Any]:
    if estimated is None:
        return {
            "amount_usd": None,
            "label": "Model value",
            "display": "Insufficient data for value estimate",
            "knowledge_state": knowledge or "UNKNOWN",
        }
    return {
        "amount_usd": estimated,
        "label": "Screening model value",
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
    """Acquisition-desk bullets — concrete, not filler."""
    reasons: list[str] = []
    est = getattr(score, "estimated_value_usd", None)
    ask = listing.asking_price_usd if listing else None
    auction = None
    if enrichment and enrichment.comps:
        auction = (enrichment.comps.normalized or {}).get("auction_path")
    if isinstance(auction, dict) and auction.get("expected_settle_usd") and est:
        settle = float(auction["expected_settle_usd"])
        gap = ((est - settle) / settle) * 100 if settle else 0
        reasons.append(
            f"Clear ~${settle:,.0f} vs mark ${est:,.0f} → {gap:+.0f}% underwrite gap"
        )
    elif score.asking_discount_pct is not None and score.asking_discount_pct < -10:
        reasons.append(
            f"Ask/settle sits {abs(score.asking_discount_pct):.0f}% under screening mark"
        )
    elif ask is None and est:
        reasons.append(f"Unpriced process channel · screen mark ${est:,.0f}")
    if score.best_strategy:
        reasons.append(
            f"Use fit: {score.best_strategy.value.replace('_', ' ').title()} "
            f"(LandSignal {score.opportunity:.0f}/100)"
        )
    if score.risk <= 35:
        reasons.append(f"Risk contained at {score.risk:.0f}/100 on desktop screens")
    elif score.risk >= 55:
        reasons.append(f"Risk {score.risk:.0f}/100 — price the friction, don’t ignore it")
    if score.confidence >= 55:
        reasons.append(f"Evidence file {score.confidence:.0f}/100 — usable for desk triage")
    if listing and listing.provider_id == "blm_lpad":
        reasons.append("BLM disposal — thin retail competition, process timeline risk")
    if listing and listing.provider_id == "public_tax_sale":
        reasons.append("Tax-sale / land-bank channel — diligence-heavy, less MLS noise")
    acres = getattr(parcel, "acreage", None)
    if acres and acres >= 40:
        reasons.append(f"Institutional scale ({acres:,.0f} ac) — hold without assembling neighbors")
    if not reasons:
        reasons.append("Clears stage-1 gates for acquisition review")
    return reasons[:5]


def build_return_thesis(
    *,
    score,
    listing,
    auction_path: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """One-line institutional thesis + conviction for radar cards."""
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
    if entry and est and gap_pct is not None:
        thesis = (
            f"{conviction}: underwrite ~${entry:,.0f} vs mark ${est:,.0f} "
            f"({gap_pct:+.0f}%) · {strat}"
        )
    elif est:
        thesis = f"{conviction}: screen mark ${est:,.0f} · {strat} desk fit"
    else:
        thesis = f"{conviction}: {strat} screen — confirm local comps"
    return thesis, conviction


def rating_breakdown(score) -> list[dict[str, Any]]:
    out = []
    for c in score.components or []:
        key = c.get("category") or c.get("label")
        help_row = CATEGORY_HELP.get(key, {})
        val = float(c.get("value") or 0)
        label = help_row.get("title") or str(key).replace("_", " ").title()
        simple = help_row.get("simple") or ""
        out.append(
            {
                "key": key,
                "label": label,
                "simple": simple,
                "plain_english": f"{simple} Score {val:.0f}/100." if simple else f"Category score {val:.0f}/100.",
                "score": val,
                "score_display": f"{val:.0f} out of 100",
                "weight_pct": int(round(float(c.get("weight") or 0) * 100)),
                "weight_display": f"{int(round(float(c.get('weight') or 0) * 100))}% of the score",
                "evidence": c.get("evidence") or [],
                "knowledge_state": c.get("knowledge_state") or "UNKNOWN",
            }
        )
    return out
