"""Plain-English, listing-specific rating explanations.

Style: short sentences, everyday words, still packed with this listing’s
numbers (APN, $, acres, pin). Never define the category in the abstract —
always say why THIS listing got THIS score.
"""

from __future__ import annotations

from typing import Any


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _money(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"${v:,.0f}"


def _pin(parcel) -> str:
    if not parcel:
        return ""
    lat, lon = getattr(parcel, "latitude", None), getattr(parcel, "longitude", None)
    if lat is not None and lon is not None:
        return f"{float(lat):.5f}, {float(lon):.5f}"
    return ""


def _listing_label(parcel, listing) -> str:
    title = (getattr(listing, "title", None) if listing else None) or None
    apn = (getattr(parcel, "apn", None) if parcel else None) or "no APN"
    county = (getattr(parcel, "county", None) if parcel else None) or "county n/a"
    state = (getattr(parcel, "state", None) if parcel else None) or "US"
    acres = _f(getattr(parcel, "acreage", None) if parcel else None)
    size = f"{acres:,.2f} acres" if acres is not None else "size unknown"
    addr = getattr(parcel, "address", None) if parcel else None
    if not addr and listing:
        addr = (getattr(listing, "raw", None) or {}).get("address")
    head = title[:70] if title else f"Parcel {apn}"
    bits = [head, f"ID {apn}", f"{county}, {state}", size]
    if addr and str(addr)[:20].lower() not in head.lower():
        bits.append(str(addr)[:60])
    return " · ".join(bits)


def _short_name(parcel, listing) -> str:
    title = (getattr(listing, "title", None) if listing else None) or None
    apn = (getattr(parcel, "apn", None) if parcel else None) or "this parcel"
    if title:
        return title[:55]
    return f"Parcel {apn}"


def _strategy_map(score) -> dict[str, float]:
    raw = getattr(score, "strategy_scores", None) if score else None
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items() if v is not None}
    return {}


def _top_strategies(score, n: int = 3) -> str:
    items = sorted(_strategy_map(score).items(), key=lambda kv: -kv[1])[:n]
    if not items:
        return "no use scores yet"
    return ", ".join(f"{k.replace('_', ' ').title()} {v:.0f}/100" for k, v in items)


def _score_plain(value: float) -> str:
    if value >= 80:
        return f"{value:.0f}/100 (strong for this listing)"
    if value >= 65:
        return f"{value:.0f}/100 (solid for this listing)"
    if value >= 50:
        return f"{value:.0f}/100 (okay — not a standout on its own)"
    if value >= 35:
        return f"{value:.0f}/100 (weak — pulling this listing down)"
    return f"{value:.0f}/100 (very weak on this listing)"


def justify_component(
    *,
    key: str,
    value: float,
    evidence: list[str],
    knowledge_state: str,
    weight: float,
    parcel=None,
    listing=None,
    score=None,
) -> dict[str, Any]:
    name = _short_name(parcel, listing)
    full = _listing_label(parcel, listing)
    pin = _pin(parcel)
    ask = _f(getattr(listing, "asking_price_usd", None) if listing else None)
    if ask is not None and ask <= 0:
        ask = None
    est = _f(getattr(score, "estimated_value_usd", None) if score else None)
    disc = _f(getattr(score, "asking_discount_pct", None) if score else None)
    provider = getattr(listing, "provider_id", None) if listing else None
    acres = _f(getattr(parcel, "acreage", None) if parcel else None)
    opp = _f(getattr(score, "opportunity", None) if score else None)
    risk_score = _f(getattr(score, "risk", None) if score else None)
    conf = _f(getattr(score, "confidence", None) if score else None)
    evid = [e for e in (evidence or []) if e and "unknown — neutral" not in e.lower()]
    contribution = value * weight
    wt_pct = int(round(weight * 100))
    channel = {
        "public_tax_sale": "county tax sale",
        "public_surplus": "government surplus",
        "blm_lpad": "federal BLM land",
    }.get(provider or "", provider or "public listing")

    why = ""
    drivers: list[str] = []

    if key == "valuation_mispricing":
        comparison = None
        if est is not None and disc is not None:
            comparison = est * (1.0 + disc / 100.0)
        elif ask is not None:
            comparison = ask
        if comparison is not None and est is not None and disc is not None:
            raw = 58 - disc * 1.35
            cheaper = disc < 0
            gap_words = (
                f"{abs(disc):.0f}% below our estimated value"
                if cheaper
                else f"{abs(disc):.0f}% above our estimated value"
            )
            opener_bit = ""
            if ask is not None and abs(ask - comparison) / max(ask, 1) > 0.15:
                opener_bit = (
                    f" The starting bid shown publicly is {_money(ask)}, but we don’t treat that "
                    f"as the real buy price — auctions usually finish near {_money(comparison)}."
                )
            why = (
                f"{name} gets {_score_plain(value)} for price because the realistic buy price "
                f"we use is {_money(comparison)}, while our estimated value for this land is "
                f"{_money(est)} — so it’s {gap_words}."
                f"{opener_bit} "
                f"That price gap alone adds about {contribution:.0f} points to the overall "
                f"opportunity score of {opp:.0f}/100 (this category is {wt_pct}% of the total)."
            )
            drivers = [
                f"Realistic buy price used for {name}: {_money(comparison)}",
                f"Our estimated value for this land: {_money(est)}",
                f"Difference: {disc:+.1f}% → price score {value:.0f}/100",
                f"Adds ~{contribution:.0f} of the overall {opp:.0f}/100 opportunity score" if opp else f"{wt_pct}% of total score",
            ]
            if ask is not None and abs(ask - comparison) / max(ask, 1) > 0.15:
                drivers.append(f"Public starting bid (not the real buy price): {_money(ask)}")
        elif ask is None and est is not None:
            if acres is not None:
                why = (
                    f"{name} has no public sale price on this {channel} feed. "
                    f"So the price score ({value:.0f}/100) reflects how workable a "
                    f"{acres:,.2f}-acre buy looks against our estimated value of {_money(est)} — "
                    f"not a “cheap vs expensive” retail listing. "
                    f"This adds about {contribution:.0f} points to the overall {opp:.0f}/100 score."
                )
            else:
                why = (
                    f"{name} has no public sale price on this {channel} feed. "
                    f"Price score is {value:.0f}/100 based on our estimated value {_money(est)} "
                    f"and how this kind of listing usually trades."
                )
            drivers = [
                f"No public price on this listing ({channel})",
                f"Estimated value used: {_money(est)}",
                *evid[:2],
            ]
        else:
            why = (
                f"{name} is missing a price and/or estimated value, so the price score "
                f"stays at {value:.0f}/100 — we won’t invent a bargain for this parcel."
            )
            drivers = evid or ["Price and estimated value are incomplete on this listing"]

    elif key == "intrinsic_land_quality":
        soil_bits = "; ".join(evid[:2]) if evid else "soil and slope data not confirmed for this pin yet"
        why = (
            f"{name} gets {_score_plain(value)} for land quality from the soil/slope check "
            f"on this exact spot" + (f" ({pin})" if pin else "") + f": {soil_bits}. "
            f"This is {wt_pct}% of the overall score (~{contribution:.0f} points toward {opp:.0f}/100)."
        )
        drivers = evid[:4] or [f"No soil/slope confirmation for {pin or name}"]

    elif key == "hbu_optionality":
        strat = getattr(score, "best_strategy", None) if score else None
        strat_s = (
            strat.value.replace("_", " ").title()
            if strat and hasattr(strat, "value")
            else "undetermined"
        )
        tops = _top_strategies(score)
        why = (
            f"{name} gets {_score_plain(value)} for future-use options because the best fit "
            f"we see for this land is {strat_s}. "
            f"Other use scores on this same listing: {tops}. "
            f"That adds ~{contribution:.0f} points to the overall {opp:.0f}/100 score."
        )
        drivers = [f"Best use for this listing: {strat_s}", f"Use scores: {tops}", *evid[:2]]

    elif key == "growth_appreciation":
        g = evid[0] if evid else "local growth data is thin for this pin"
        why = (
            f"{name} gets {_score_plain(value)} for area growth"
            + (f" at {pin}" if pin else "")
            + f". Reason for this listing: {g}. "
            f"Worth {wt_pct}% of the total (~{contribution:.0f} points)."
        )
        drivers = evid[:3] or [f"Growth data not confirmed for {pin or name}"]

    elif key == "infrastructure":
        infra = "; ".join(evid[:2]) if evid else "road access / power distance not confirmed yet for this pin"
        why = (
            f"{name} gets {_score_plain(value)} for access & infrastructure. "
            f"For this pin: {infra}. "
            f"Adds ~{contribution:.0f} points ({wt_pct}% of total)."
        )
        drivers = evid[:4] or [f"Infrastructure not confirmed for {pin or name}"]

    elif key == "liquidity":
        why = (
            f"{name} gets {_score_plain(value)} for ease of resale because it sits on a "
            f"{channel} channel"
            + (f" and is {acres:,.2f} acres" if acres is not None else "")
            + ". Listings like this usually take longer to sell than normal MLS land. "
            f"Adds ~{contribution:.0f} points to the overall score."
        )
        drivers = evid[:3] or [f"{channel} resale difficulty → {value:.0f}/100 for this listing"]

    elif key == "scarcity":
        county = getattr(parcel, "county", None) or "this county"
        state = getattr(parcel, "state", None) or "US"
        why = (
            f"{name} gets {_score_plain(value)} for scarcity"
            + (f" as a {acres:,.2f}-acre tract" if acres is not None else "")
            + f" in {county}, {state}. "
            f"Adds ~{contribution:.0f} points ({wt_pct}% of total)."
        )
        drivers = evid[:3] or [f"Scarcity for this tract in {county}, {state} → {value:.0f}/100"]

    elif key == "catalysts":
        why = (
            f"{name} gets {_score_plain(value)} for nearby value-boosting projects. "
            f"{(evid[0] if evid else 'No clear highway, plant, or zoning catalyst is tied to this parcel ID yet')}. "
            f"Adds ~{contribution:.0f} points."
        )
        drivers = evid[:3] or [f"No catalyst on file for ID {(getattr(parcel, 'apn', None) or 'n/a')}"]

    elif key == "seller_dynamics":
        dom = getattr(listing, "days_on_market", None) if listing else None
        why = (
            f"{name} gets {_score_plain(value)} for seller / listing pressure on this "
            f"{channel} file"
            + (f" (about {dom} days on market)" if dom is not None else "")
            + ". Higher here usually means more room to negotiate on this kind of listing. "
            f"Adds ~{contribution:.0f} points."
        )
        drivers = evid[:3] or [f"Seller pressure on this {channel} listing → {value:.0f}/100"]

    elif key == "risk":
        risk_bits = "; ".join(evid[:3]) if evid else "no major flood, wetland, or access red flags on the map checks yet"
        why = (
            f"{name} has an overall risk of {risk_score:.0f}/100"
            + (f" at {pin}" if pin else "")
            + f". This “risk cushion” piece of the opportunity score is {value:.0f}/100 "
            f"(higher here means cleaner risk on the map checks). "
            f"What’s driving risk on this listing: {risk_bits}. "
            f"Adds ~{contribution:.0f} points toward opportunity {opp:.0f}/100."
        )
        drivers = evid[:4] or [f"Map risk {risk_score:.0f}/100 on this listing → cushion {value:.0f}/100"]

    else:
        why = (
            f"{name} scores {value:.0f}/100 for {key.replace('_', ' ')} from this listing’s own inputs."
        )
        drivers = evid[:3] or [f"{key} → {value:.0f} on this listing"]

    why = why.replace("..", ".").strip()

    return {
        "plain_english": why,
        "why_this_number": why,
        "drivers": drivers[:5],
        "weight_note": (
            f"For {name}, this category is {wt_pct}% of the opportunity score and adds about "
            f"{contribution:.0f} points toward {opp:.0f}/100"
            + (
                f". Risk on this listing is {risk_score:.0f}/100; how complete the file is: {conf:.0f}/100."
                if risk_score is not None and conf is not None
                else "."
            )
        ),
        "identity": full,
    }


def rating_breakdown_justified(score, parcel=None, listing=None) -> list[dict[str, Any]]:
    from landsignal.services.humanize import CATEGORY_HELP

    out = []
    for c in (score.components if score else None) or []:
        key = c.get("category") or c.get("label")
        help_row = CATEGORY_HELP.get(key, {})
        val = float(c.get("value") or 0)
        weight = float(c.get("weight") or 0)
        ks = c.get("knowledge_state") or "UNKNOWN"
        evidence = list(c.get("evidence") or [])
        just = justify_component(
            key=str(key),
            value=val,
            evidence=evidence,
            knowledge_state=str(ks),
            weight=weight,
            parcel=parcel,
            listing=listing,
            score=score,
        )
        out.append(
            {
                "key": key,
                "label": help_row.get("title") or str(key).replace("_", " ").title(),
                "simple": just["why_this_number"],
                "plain_english": just["plain_english"],
                "why_this_number": just["why_this_number"],
                "drivers": just["drivers"],
                "score": val,
                "score_display": f"{val:.0f} out of 100",
                "weight_pct": int(round(weight * 100)),
                "weight_display": just["weight_note"],
                "evidence": just["drivers"] or evidence,
                "knowledge_state": ks,
                "identity": just["identity"],
            }
        )
    return out
