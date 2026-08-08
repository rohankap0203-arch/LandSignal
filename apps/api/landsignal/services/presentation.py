from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from landsignal.services.humanize import CATEGORY_HELP


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
    """Return actionable links: source, contact/learn path, and map."""
    links: list[dict[str, str]] = []
    raw = raw or {}
    contact_q = " ".join(
        x for x in [title, apn or "", county or "", state or "", "land parcel contact seller"] if x
    )
    contact_url = f"https://www.google.com/search?q={quote_plus(contact_q)}"

    if source_url:
        label = "Official listing / source documents"
        if provider_id == "blm_lpad":
            label = "BLM plan / disposal documents"
        elif provider_id == "public_tax_sale":
            label = "County tax-sale / parcel record"
        elif provider_id == "public_surplus":
            label = "Surplus property record"
        links.append({"label": label, "url": source_url, "kind": "primary"})

    # Always provide a learn/contact path (survives if primary docs are offline)
    if provider_id == "blm_lpad":
        links.append(
            {
                "label": "Learn / contact BLM land tenure",
                "url": "https://www.blm.gov/programs/lands-and-realty/land-tenure",
                "kind": "contact",
            }
        )
    elif provider_id == "public_tax_sale" and state == "CA" and (county or "").lower().startswith("shasta"):
        links.append(
            {
                "label": "Shasta Treasurer / tax sale office",
                "url": "https://www.shastacounty.gov/treasurer-tax-collector",
                "kind": "contact",
            }
        )
    elif provider_id == "public_tax_sale" and state == "WI":
        links.append(
            {
                "label": "Sauk County land records",
                "url": "https://lrs.co.sauk.wi.us/AscentLandRecords/",
                "kind": "contact",
            }
        )
    elif provider_id == "public_tax_sale" and state == "IN":
        links.append(
            {
                "label": "Indy tax sale info / contact",
                "url": "https://www.indy.gov/activity/property-tax-sale",
                "kind": "contact",
            }
        )
    elif provider_id == "public_surplus":
        links.append(
            {
                "label": "Find surplus office / how to buy",
                "url": f"https://www.google.com/search?q={quote_plus((county or '') + ' ' + (state or '') + ' surplus property sale contact')}",
                "kind": "contact",
            }
        )
    else:
        links.append({"label": "Search seller / listing contacts", "url": contact_url, "kind": "contact"})

    if not any(l["kind"] == "primary" for l in links):
        # Promote contact to primary when no official source URL
        links[0]["kind"] = "primary"

    if latitude is not None and longitude is not None:
        links.append(
            {
                "label": "View on Google Maps",
                "url": f"https://www.google.com/maps?q={latitude},{longitude}",
                "kind": "map",
            }
        )
    else:
        q = " ".join(x for x in [apn or title, county or "", state or ""] if x)
        links.append(
            {
                "label": "Locate parcel",
                "url": f"https://www.google.com/maps/search/{quote_plus(q)}",
                "kind": "map",
            }
        )

    seen = set()
    out = []
    for link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        out.append(link)
        if len(out) >= 3:
            break
    return out


def price_display(
    ask: float | None,
    provider_id: str | None,
    auction_path: dict[str, Any] | None = None,
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
            "display": "Federal disposal (no retail ask)",
            "kind": "process",
        }
    return {
        "amount_usd": None,
        "label": "Price",
        "display": "Contact agency for pricing",
        "kind": "inquiry",
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
    enrichment,
) -> list[str]:
    reasons: list[str] = []
    if score.best_strategy:
        reasons.append(f"Best strategy fit: {score.best_strategy.value.replace('_', ' ').title()}")
    if score.asking_discount_pct is not None and score.asking_discount_pct < -10:
        reasons.append(
            f"Ask appears {abs(score.asking_discount_pct):.0f}% below screening model value"
        )
    if score.asymmetry >= 70:
        reasons.append(f"High asymmetry ({score.asymmetry:.0f}/100): upside vs downside skew")
    if score.confidence >= 55:
        reasons.append(f"Data confidence {score.confidence:.0f}/100 from government + listing provenance")
    if score.risk <= 35:
        reasons.append(f"Contained screened risk ({score.risk:.0f}/100)")
    wet = None
    if enrichment and enrichment.wetlands and enrichment.wetlands.normalized:
        wet = enrichment.wetlands.normalized.get("wetland_pct")
    if wet is not None:
        reasons.append(f"Wetland screen: {wet:.0f}% of parcel (NWI point/poly screen)")
    hold = filters.get("hold_years")
    if hold and score.best_strategy and score.best_strategy.value in ("LAND_BANK", "DEVELOPMENT", "FARMLAND"):
        reasons.append(f"Aligns with ~{hold}-year hold theses ({score.best_strategy.value})")
    roi = filters.get("target_roi")
    if roi is not None and enrichment and enrichment.scenarios:
        base = next((s for s in enrichment.scenarios if s.get("case_type") == "BASE"), None)
        if base and base.get("irr") is not None:
            reasons.append(f"Base farmland IRR screen {base['irr']*100:.1f}% vs your {float(roi)*100:.0f}% target")
    if not reasons:
        reasons.append("Passes stage-1 screens for at least one investment strategy")
    return reasons[:5]


def rating_breakdown(score) -> list[dict[str, Any]]:
    """Human-readable backed ratings from score components."""
    out = []
    for c in score.components or []:
        key = c.get("category")
        help_meta = CATEGORY_HELP.get(str(key or ""), {})
        val = float(c.get("value") or 0)
        if val >= 70:
            plain = "Looks helpful for this deal on the data we have."
        elif val >= 45:
            plain = "Mixed — worth a closer look, not a green light by itself."
        else:
            plain = "Weak on this factor — dig in before you rely on it."
        out.append(
            {
                "key": key,
                "label": help_meta.get("title") or str(key or "").replace("_", " ").title(),
                "simple": help_meta.get("simple") or "Part of the overall LandSignal screening score.",
                "plain_english": plain,
                "score": val,
                "score_display": f"{val:.0f} out of 100",
                "weight_pct": round(float(c.get("weight") or 0) * 100),
                "weight_display": f"{round(float(c.get('weight') or 0) * 100)}% of the score",
                "evidence": (c.get("evidence") or [])[:4],
                "knowledge_state": c.get("knowledge_state"),
            }
        )
    return out
