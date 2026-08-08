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
    reasons: list[str] = []
    if score.asking_discount_pct is not None and score.asking_discount_pct < -10:
        reasons.append(f"Settle/ask sits {abs(score.asking_discount_pct):.0f}% under screening model")
    if score.best_strategy:
        reasons.append(f"Best strategy fit: {score.best_strategy.value.replace('_', ' ').title()}")
    if score.confidence >= 60:
        reasons.append(f"Evidence confidence {score.confidence:.0f}/100")
    if score.risk <= 35:
        reasons.append(f"Lower screened risk ({score.risk:.0f}/100)")
    if listing and listing.provider_id == "blm_lpad":
        reasons.append("Federal disposal channel — fewer retail bidders")
    if listing and listing.provider_id == "public_tax_sale":
        reasons.append("Public tax-sale / county inventory channel")
    if not reasons:
        reasons.append("Passes stage-1 strategy screens")
    return reasons[:5]


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
