"""Parcel-specific rating justifications — every score must explain itself."""

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


def _identity(parcel, listing) -> str:
    apn = (getattr(parcel, "apn", None) if parcel else None) or "no APN"
    county = (getattr(parcel, "county", None) if parcel else None) or "county n/a"
    state = (getattr(parcel, "state", None) if parcel else None) or "US"
    acres = _f(getattr(parcel, "acreage", None) if parcel else None)
    size = f"{acres:,.2f} ac" if acres is not None else "acreage unpublished"
    return f"{apn} · {county}, {state} · {size}"


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
    """Build a unique, numeric, parcel-bound explanation for one rating bar."""
    ident = _identity(parcel, listing)
    pin = _pin(parcel)
    ask = _f(getattr(listing, "asking_price_usd", None) if listing else None)
    if ask is not None and ask <= 0:
        ask = None
    est = _f(getattr(score, "estimated_value_usd", None) if score else None)
    disc = _f(getattr(score, "asking_discount_pct", None) if score else None)
    provider = getattr(listing, "provider_id", None) if listing else None
    acres = _f(getattr(parcel, "acreage", None) if parcel else None)
    evid = [e for e in (evidence or []) if e and "unknown — neutral" not in e.lower()]

    # Band language tied to THIS number
    if value >= 80:
        band = f"{value:.0f}/100 is in the top screening band"
    elif value >= 65:
        band = f"{value:.0f}/100 clears a strong desk threshold"
    elif value >= 50:
        band = f"{value:.0f}/100 is mid-pack — usable but not decisive alone"
    elif value >= 35:
        band = f"{value:.0f}/100 is soft — this category is dragging the screen"
    else:
        band = f"{value:.0f}/100 is a hard drag on the screen"

    why = ""
    drivers: list[str] = []

    if key == "valuation_mispricing":
        # Prefer settle/comparison implied by scored discount — not teaser openers
        comparison = None
        if est is not None and disc is not None:
            comparison = est * (1.0 + disc / 100.0)
        elif ask is not None:
            comparison = ask
        if comparison is not None and est is not None and disc is not None:
            opener_note = ""
            if ask is not None and abs(ask - comparison) / max(ask, 1) > 0.15:
                opener_note = f" Published opener {_money(ask)} is not the underwrite input."
            why = (
                f"On {ident}, comparison/settle {_money(comparison)} vs screening mark {_money(est)} "
                f"produces {disc:+.1f}% — that math lands valuation at {value:.0f}/100.{opener_note} "
                f"{band}."
            )
            drivers = [
                f"Comparison / settle input: {_money(comparison)}",
                f"Screening mark: {_money(est)}",
                f"Gap used in formula: {disc:+.1f}% → score {value:.0f}",
            ]
            if ask is not None and abs(ask - comparison) / max(ask, 1) > 0.15:
                drivers.append(f"Published opener (not used as settle): {_money(ask)}")
        elif ask is None and est is not None:
            if acres is not None:
                why = (
                    f"{ident} has no retail ask ({provider or 'public'} channel). "
                    f"Entry optionality from {acres:,.2f} ac against mark {_money(est)} "
                    f"scores {value:.0f}/100. {band}."
                )
            else:
                why = (
                    f"{ident} has no retail ask ({provider or 'public'} channel). "
                    f"Mark {_money(est)} with process pricing scores {value:.0f}/100. {band}."
                )
            drivers = evid or [f"Unpriced vs mark {_money(est)} → {value:.0f}/100"]
        else:
            why = (
                f"On {ident}, ask/mark inputs are incomplete, so valuation sits at "
                f"{value:.0f}/100 instead of inventing a bargain. {band}."
            )
            drivers = evid or ["Incomplete price file"]

    elif key == "intrinsic_land_quality":
        why = (
            f"Soil/slope screen for {ident}"
            + (f" at {pin}" if pin else "")
            + f" produces {value:.0f}/100. "
            + ("; ".join(evid[:2]) + ". " if evid else "No USDA/slope hit yet — held near-neutral. ")
            + band
            + "."
        )
        drivers = evid or ["No soil/slope layer confirmed for this geometry"]

    elif key == "hbu_optionality":
        strat = getattr(score, "best_strategy", None) if score else None
        strat_s = strat.value.replace("_", " ").title() if strat and hasattr(strat, "value") else "undetermined"
        why = (
            f"Highest-and-best-use matrix on {ident} ranks {strat_s} first; "
            f"optionality composite = {value:.0f}/100. {band}."
        )
        drivers = evid or [f"Lead strategy screen: {strat_s}"]

    elif key == "growth_appreciation":
        why = (
            f"Path-of-growth screen for {ident}"
            + (f" ({pin})" if pin else "")
            + f" = {value:.0f}/100. "
            + (evid[0] + ". " if evid else "County growth layer thin — held near mid. ")
            + band
            + "."
        )
        drivers = evid or ["Growth layer not confirmed for this pin"]

    elif key == "infrastructure":
        why = (
            f"Access / frontage / transmission composite for {ident} = {value:.0f}/100. "
            + ("; ".join(evid[:2]) + ". " if evid else "Infrastructure layers incomplete. ")
            + band
            + "."
        )
        drivers = evid or ["No road/transmission/access confirmation yet"]

    elif key == "liquidity":
        why = (
            f"Exit/liquidity screen for {ident} = {value:.0f}/100 "
            f"({provider or 'public'} channel). {band}."
        )
        drivers = evid or [f"Channel {provider or 'public'} liquidity proxy → {value:.0f}"]

    elif key == "scarcity":
        why = (
            f"Scarcity screen on {ident}"
            + (f" ({acres:,.1f} ac)" if acres is not None else "")
            + f" = {value:.0f}/100. {band}."
        )
        drivers = evid or [f"Scarcity proxy → {value:.0f}/100 for this tract"]

    elif key == "catalysts":
        why = (
            f"Catalyst / near-term event screen for {ident} = {value:.0f}/100. "
            f"{band}."
        )
        drivers = evid or ["No structured catalyst on file for this APN"]

    elif key == "seller_dynamics":
        why = (
            f"Seller / process pressure for {ident} ({provider or 'listing'}) "
            f"= {value:.0f}/100. {band}."
        )
        drivers = evid or [f"Seller-pressure proxy on {provider or 'file'} → {value:.0f}"]

    elif key == "risk":
        # component value is inverted risk contribution (100-risk)
        risk_score = _f(getattr(score, "risk", None) if score else None)
        why = (
            f"Risk screen for {ident}"
            + (f" at {pin}" if pin else "")
            + f" is {risk_score:.0f}/100 overall; this category contributes "
            f"{value:.0f}/100 to opportunity (higher here = cleaner desktop risk). {band}."
        )
        drivers = evid or ["No flood/wetland/access hits in desktop file"]

    else:
        why = f"On {ident}, {key.replace('_', ' ')} screens at {value:.0f}/100. {band}."
        drivers = evid or [f"Score {value:.0f}/100 from model inputs"]

    # Weight context — why this bar matters on THIS file
    wt = int(round(weight * 100))
    weight_note = f"This category is {wt}% of LandSignal on this algorithm version."

    return {
        "plain_english": why,
        "why_this_number": why,
        "drivers": drivers[:4],
        "weight_note": weight_note,
        "identity": ident,
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
                "simple": just["why_this_number"],  # replace generic blurb with justification
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
