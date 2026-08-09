"""Plain-English, listing-specific rating explanations.

Style: everyday words, packed with THIS listing’s numbers ($/acres/pin/channel),
never lead with raw parcel IDs, never restate the category title as filler.
"""

from __future__ import annotations

from typing import Any

from landsignal.services.voice import place_phrase, this_property


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
    place = place_phrase(parcel)
    acres = _f(getattr(parcel, "acreage", None) if parcel else None)
    size = f"{acres:,.2f} acres" if acres is not None else "size unknown"
    return f"{place} · {size}"


def _short_name(parcel, listing) -> str:
    return this_property(parcel, listing, with_place=False)


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
        return f"{value:.0f}/100 (strong here)"
    if value >= 65:
        return f"{value:.0f}/100 (solid here)"
    if value >= 50:
        return f"{value:.0f}/100 (okay — not a standout alone)"
    if value >= 35:
        return f"{value:.0f}/100 (weak — pulling the ranking down)"
    return f"{value:.0f}/100 (very weak on this file)"


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
    place = place_phrase(parcel)
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
    ppa = (est / acres) if est and acres and acres > 0 else None
    size_bit = f"{acres:,.2f}-acre" if acres is not None else "this"

    why = ""
    drivers: list[str] = []

    if key == "valuation_mispricing":
        comparison = None
        if est is not None and disc is not None:
            comparison = est * (1.0 + disc / 100.0)
        elif ask is not None:
            comparison = ask
        if comparison is not None and est is not None and disc is not None:
            cheaper = disc < 0
            gap_usd = abs(est - comparison)
            gap_words = (
                f"{abs(disc):.0f}% below our estimated value ({_money(gap_usd)} of room)"
                if cheaper
                else f"{abs(disc):.0f}% above our estimated value ({_money(gap_usd)} more expensive)"
            )
            opener_bit = ""
            if ask is not None and abs(ask - comparison) / max(ask, 1) > 0.15:
                opener_bit = (
                    f" The public starting bid is {_money(ask)}, but auctions like this in {place} "
                    f"usually finish closer to {_money(comparison)} — so we score the likely finish, "
                    f"not the teaser opener."
                )
            nuance = (
                "That gap is the main economic hook on this file — still confirm with a local broker "
                "and a site walk before you treat it as locked-in equity."
                if cheaper and abs(disc) >= 12
                else "The gap is modest, so price alone should not carry your decision; weigh risk and "
                "how complete the file is next to it."
                if cheaper
                else "Paying above our estimate only makes sense if you see a use we are under-counting "
                "(homes, energy, assemble) — otherwise this is a tougher entry."
            )
            why = (
                f"{name.capitalize()} scores {_score_plain(value)} on price: we underwrite a realistic "
                f"buy near {_money(comparison)}"
                + (f" (~{_money(ppa)}/acre)" if ppa else "")
                + f", while our estimated value for the {size_bit} tract in {place} is {_money(est)} — "
                f"so it sits {gap_words}.{opener_bit} "
                f"{nuance} This category is {wt_pct}% of the opportunity score and contributes about "
                f"{contribution:.0f} points toward {opp:.0f}/100 overall."
            )
            drivers = [
                f"Buy price we underwrite: {_money(comparison)}",
                f"Our estimated value: {_money(est)}"
                + (f" (~{_money(ppa)}/acre)" if ppa else ""),
                f"Gap: {disc:+.1f}% → category {value:.0f}/100",
                f"~{contribution:.0f} pts toward overall {opp:.0f}/100" if opp else f"{wt_pct}% of total",
            ]
            if ask is not None and abs(ask - comparison) / max(ask, 1) > 0.15:
                drivers.append(f"Published starting bid (not the real buy): {_money(ask)}")
        elif ask is None and est is not None:
            why = (
                f"{name.capitalize()} has no published sale price on this {channel} feed in {place}. "
                f"So {value:.0f}/100 here is not a “cheap listing” grade — it reflects how workable a "
                f"{size_bit} buy looks against our {_money(est)} estimate"
                + (f" (~{_money(ppa)}/acre)" if ppa else "")
                + f", given how {channel} inventory usually clears. "
                f"Your edge is process access (office, calendar, surplus rules), not outbidding a "
                f"retail crowd. Adds ~{contribution:.0f} points toward {opp:.0f}/100 "
                f"({wt_pct}% of the score)."
            )
            drivers = [
                f"No public price ({channel} in {place})",
                f"Estimate used: {_money(est)}"
                + (f" / ~{_money(ppa)} per acre" if ppa else ""),
                *evid[:2],
            ]
        else:
            why = (
                f"{name.capitalize()} is missing both a public price and a solid estimate, so this "
                f"stays at {value:.0f}/100 — we will not invent a bargain. Confirm pricing with the "
                f"selling office before ranking this above better-documented land."
            )
            drivers = evid or ["Price and estimated value are incomplete"]

    elif key == "intrinsic_land_quality":
        soil_bits = "; ".join(evid[:2]) if evid else "soil and slope not confirmed on the map yet"
        why = (
            f"On the {size_bit} ground in {place}"
            + (f" at pin {pin}" if pin else "")
            + f", the soil/slope reading scores {_score_plain(value)}. "
            f"What we see: {soil_bits}. "
            f"Higher here means more usable acres for farming, recreation, or a later resale to a "
            f"user who cares about dirt quality — not curb appeal. "
            f"{wt_pct}% of the score (~{contribution:.0f} pts toward {opp:.0f}/100)."
        )
        drivers = evid[:4] or [f"No soil/slope confirmation yet for {place}"]

    elif key == "hbu_optionality":
        strat = getattr(score, "best_strategy", None) if score else None
        strat_s = (
            strat.value.replace("_", " ").title()
            if strat and hasattr(strat, "value")
            else "undetermined"
        )
        tops = _top_strategies(score)
        why = (
            f"For {name} in {place}, the strongest fit we see is {strat_s} "
            f"({_score_plain(value)} on future-use options). "
            f"Same-file use mix: {tops}. "
            f"That matters on exit — a second use can still help you sell later even if your hold "
            f"plan is {strat_s.lower()}. Adds ~{contribution:.0f} pts ({wt_pct}% of opportunity)."
        )
        drivers = [f"Best use: {strat_s}", f"Use mix: {tops}", *evid[:2]]

    elif key == "growth_appreciation":
        g = evid[0] if evid else "local growth data is still thin for this pin"
        why = (
            f"Area growth for {name} in {place} scores {_score_plain(value)}"
            + (f" near {pin}" if pin else "")
            + f". Signal we used: {g}. "
            f"Stronger growth means more people, jobs, or development pressure moving toward this "
            f"pin — which can support a longer hold even when today’s rent is ordinary. "
            f"~{contribution:.0f} pts ({wt_pct}% of total)."
        )
        drivers = evid[:3] or [f"Growth not confirmed yet for {place}"]

    elif key == "infrastructure":
        infra = "; ".join(evid[:2]) if evid else "road access / power distance not confirmed yet"
        why = (
            f"Access and power for {name} in {place}: {_score_plain(value)}. "
            f"Pin-level reading: {infra}. "
            f"Weak access raises carry cost and scares some buyers; confirmed road frontage and "
            f"nearby power make a later resale or build much easier. "
            f"~{contribution:.0f} pts ({wt_pct}%)."
        )
        drivers = evid[:4] or [f"Infrastructure not confirmed for {place}"]

    elif key == "liquidity":
        why = (
            f"Ease of resale for {name}: {_score_plain(value)}. "
            f"It sits on a {channel} channel in {place}"
            + (f" at {acres:,.2f} acres" if acres is not None else "")
            + " — inventory like this usually takes longer than a normal MLS farm listing because "
            f"title, occupancy, or agency rules slow the buyer pool. "
            f"Lower liquidity is not automatically bad if your hold is patient; it does mean you "
            f"should not assume a quick flip. ~{contribution:.0f} pts toward {opp:.0f}/100."
        )
        drivers = evid[:3] or [f"{channel} in {place} → resale score {value:.0f}/100"]

    elif key == "scarcity":
        why = (
            f"How rare {name} is in {place}: {_score_plain(value)}"
            + (f" for a {acres:,.2f}-acre tract" if acres is not None else "")
            + ". "
            f"Harder-to-replace acreage supports asking power on exit; common small lots compete "
            f"with dozens of substitutes. "
            f"~{contribution:.0f} pts ({wt_pct}% of total)."
        )
        drivers = evid[:3] or [f"Scarcity in {place} → {value:.0f}/100"]

    elif key == "catalysts":
        cat = evid[0] if evid else (
            "No clear highway, plant, or zoning project is tied to this pin yet — "
            "so we are not inventing upside"
        )
        why = (
            f"Nearby projects that could lift value for {name} in {place}: {_score_plain(value)}. "
            f"{cat}. "
            f"Catalysts are optional upside, not a reason to overpay if the base price case is weak. "
            f"~{contribution:.0f} pts."
        )
        drivers = evid[:3] or [f"No catalyst on file for {place}"]

    elif key == "seller_dynamics":
        dom = getattr(listing, "days_on_market", None) if listing else None
        why = (
            f"Seller / channel pressure on this {channel} file in {place}: {_score_plain(value)}"
            + (f" (about {dom} days on market)" if dom is not None else "")
            + ". "
            f"Tax-sale and surplus channels often accept process-driven outcomes; higher pressure "
            f"here usually means more room to negotiate timing or price — not a guarantee of a "
            f"steal. ~{contribution:.0f} pts."
        )
        drivers = evid[:3] or [f"Seller pressure on {channel} → {value:.0f}/100"]

    elif key == "risk":
        risk_bits = "; ".join(evid[:3]) if evid else (
            "no major flood, wetland, or access red flags on the map checks yet"
        )
        why = (
            f"Map risk for {name} in {place} is {risk_score:.0f}/100"
            + (f" at pin {pin}" if pin else "")
            + f". The “risk cushion” slice of opportunity is {value:.0f}/100 "
            f"(higher cushion = cleaner map checks). Drivers: {risk_bits}. "
            f"Budget insurance, fill, or a wetland survey when flood/wetland shares are material — "
            f"many cash buyers step back, which can leave negotiating room if you price those costs. "
            f"~{contribution:.0f} pts toward {opp:.0f}/100."
        )
        drivers = evid[:4] or [f"Map risk {risk_score:.0f}/100 → cushion {value:.0f}/100"]

    else:
        why = (
            f"{name.capitalize()} scores {value:.0f}/100 on {key.replace('_', ' ')} from this "
            f"file’s own inputs in {place}."
        )
        drivers = evid[:3] or [f"{key} → {value:.0f}"]

    why = why.replace("..", ".").strip()
    if why and why[0].islower():
        why = why[0].upper() + why[1:]

    return {
        "plain_english": why,
        "why_this_number": why,
        "drivers": drivers[:6],
        "weight_note": (
            f"This category is {wt_pct}% of opportunity and adds about {contribution:.0f} points "
            f"toward {opp:.0f}/100 on {name}"
            + (
                f". Risk {risk_score:.0f}/100 · file complete {conf:.0f}/100."
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
        title = help_row.get("title") or str(key).replace("_", " ").title()
        out.append(
            {
                "key": key,
                "label": title,
                "simple": help_row.get("simple"),
                "plain_english": just["plain_english"],
                "why_this_number": just["why_this_number"],
                "score": val,
                "score_display": f"{val:.0f}/100",
                "weight_pct": round(weight * 100),
                "weight_display": just["weight_note"],
                "drivers": just["drivers"],
                "evidence": evidence,
                "knowledge_state": ks,
                "identity": just["identity"],
            }
        )
    return out
