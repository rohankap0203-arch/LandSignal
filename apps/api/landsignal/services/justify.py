"""Hyper-specific, listing-unique rating justifications.

Every sentence must answer: why THIS listing got THIS number — with the
exact inputs (APN, title, pin, settle, mark, soil %, strategy scores).
No category definitions. No generic band copy.
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
    size = f"{acres:,.2f} ac" if acres is not None else "acreage unpublished"
    addr = getattr(parcel, "address", None) if parcel else None
    if not addr and listing:
        addr = (getattr(listing, "raw", None) or {}).get("address")
    head = title[:70] if title else f"APN {apn}"
    bits = [head, f"APN {apn}", f"{county}, {state}", size]
    if addr:
        bits.append(str(addr)[:60])
    return " · ".join(bits)


def _strategy_map(score) -> dict[str, float]:
    raw = getattr(score, "strategy_scores", None) if score else None
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items() if v is not None}
    return {}


def _top_strategies(score, n: int = 3) -> str:
    items = sorted(_strategy_map(score).items(), key=lambda kv: -kv[1])[:n]
    if not items:
        return "no strategy scores on file"
    return ", ".join(f"{k.replace('_', ' ').title()} {v:.0f}" for k, v in items)


def _neighbor_note(value: float, formula_preview: str | None = None) -> str:
    """One line on what moved this listing onto this exact integer score."""
    lo = max(0, int(value) - 5)
    hi = min(100, int(value) + 5)
    base = f"This listing landed at {value:.0f}/100 (not {lo} or {hi})"
    if formula_preview:
        return f"{base} because {formula_preview}."
    return f"{base} from the inputs below."


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
    label = _listing_label(parcel, listing)
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
            clamped = max(0.0, min(100.0, raw))
            opener_bit = ""
            if ask is not None and abs(ask - comparison) / max(ask, 1) > 0.15:
                opener_bit = (
                    f" The published opener on this listing is {_money(ask)} — "
                    f"ignored as settle; underwrite uses {_money(comparison)}."
                )
            why = (
                f"«{label}» scored {value:.0f}/100 on valuation because its comparison/settle "
                f"{_money(comparison)} sits {disc:+.1f}% vs its screening mark {_money(est)}. "
                f"Formula on this file: 58 − ({disc:.1f} × 1.35) = {raw:.1f} → clamped {clamped:.0f}. "
                f"{_neighbor_note(value, f'settle {_money(comparison)} vs mark {_money(est)} ({disc:+.1f}%)')}."
                f"{opener_bit} "
                f"This bar alone contributes ~{contribution:.1f} points to LandSignal "
                f"{opp:.0f}/100 ({wt_pct}% weight)."
            )
            drivers = [
                f"Listing settle/comparison used: {_money(comparison)}",
                f"This listing’s screening mark: {_money(est)}",
                f"Gap on this file: {disc:+.1f}% → raw {raw:.1f} → {value:.0f}/100",
                f"Contribution to overall LandSignal: {contribution:.1f} of {opp:.0f}" if opp else f"Weight {wt_pct}%",
            ]
            if ask is not None and abs(ask - comparison) / max(ask, 1) > 0.15:
                drivers.append(f"Published opener on listing (not settle): {_money(ask)}")
        elif ask is None and est is not None:
            scar_bit = evid[0] if evid else "scale/scarcity entry curve"
            if acres is not None:
                why = (
                    f"«{label}» has no retail ask on the {provider or 'public'} feed, so valuation "
                    f"scores process-entry optionality: {acres:,.2f} ac against mark {_money(est)} "
                    f"→ {value:.0f}/100 ({scar_bit}). "
                    f"{_neighbor_note(value, f'{acres:,.2f} ac unpriced vs {_money(est)} mark')} "
                    f"Contributes ~{contribution:.1f} pts to LandSignal {opp:.0f}/100."
                )
            else:
                why = (
                    f"«{label}» has no retail ask on the {provider or 'public'} feed; "
                    f"mark {_money(est)} with process pricing → {value:.0f}/100. "
                    f"{_neighbor_note(value)}"
                )
            drivers = [
                f"No ask on this listing · channel {provider or 'public'}",
                f"Mark used: {_money(est)}",
                *evid[:2],
            ]
        else:
            why = (
                f"«{label}» is missing ask and/or mark, so valuation is held at {value:.0f}/100 "
                f"instead of inventing a bargain for this APN. {_neighbor_note(value)}."
            )
            drivers = evid or ["Ask/mark incomplete on this listing file"]

    elif key == "intrinsic_land_quality":
        soil_bits = "; ".join(evid[:3]) if evid else "no USDA/slope confirmation on this geometry yet"
        why = (
            f"«{label}»" + (f" @ {pin}" if pin else "") + f" got land-quality {value:.0f}/100 "
            f"from this geometry’s soil/slope screen only: {soil_bits}. "
            f"{_neighbor_note(value, soil_bits[:90])}. "
            f"Contributes ~{contribution:.1f} pts ({wt_pct}% weight) to LandSignal {opp:.0f}/100."
        )
        drivers = evid[:4] or [f"No soil/slope layer for pin {pin or 'n/a'} on this listing"]

    elif key == "hbu_optionality":
        strat = getattr(score, "best_strategy", None) if score else None
        strat_s = (
            strat.value.replace("_", " ").title()
            if strat and hasattr(strat, "value")
            else "undetermined"
        )
        tops = _top_strategies(score)
        why = (
            f"«{label}» optionality is {value:.0f}/100 because its use matrix ranks "
            f"{strat_s} first among surviving screens. Top scores on this listing: {tops}. "
            f"{_neighbor_note(value, f'lead use {strat_s}; composite of top strategies')}. "
            f"Contributes ~{contribution:.1f} pts to LandSignal {opp:.0f}/100."
        )
        drivers = [f"Lead use on this listing: {strat_s}", f"Strategy stack: {tops}", *evid[:2]]

    elif key == "growth_appreciation":
        g = evid[0] if evid else "county growth layer thin for this pin"
        why = (
            f"«{label}»" + (f" @ {pin}" if pin else "") + f" growth rating is {value:.0f}/100 "
            f"from path-of-growth for this county/pin: {g}. "
            f"{_neighbor_note(value, g[:90])}. "
            f"Contributes ~{contribution:.1f} pts ({wt_pct}% weight)."
        )
        drivers = evid[:3] or [f"Growth not confirmed at {pin or label}"]

    elif key == "infrastructure":
        infra = "; ".join(evid[:2]) if evid else "access/frontage/transmission incomplete on this pin"
        why = (
            f"«{label}» infrastructure is {value:.0f}/100 from this pin’s access/transmission "
            f"composite: {infra}. {_neighbor_note(value, infra[:90])}. "
            f"Contributes ~{contribution:.1f} pts."
        )
        drivers = evid[:4] or [f"No infra confirmation for {pin or 'this listing'}"]

    elif key == "liquidity":
        ch = provider or "public"
        why = (
            f"«{label}» liquidity is {value:.0f}/100 because exitability is proxied from the "
            f"{ch} channel on this exact file"
            + (f" ({acres:,.2f} ac)" if acres is not None else "")
            + f". {_neighbor_note(value, f'{ch} channel liquidity proxy')}. "
            f"Contributes ~{contribution:.1f} pts."
        )
        drivers = evid[:3] or [f"{ch} liquidity proxy → {value:.0f} for this listing"]

    elif key == "scarcity":
        why = (
            f"«{label}» scarcity is {value:.0f}/100"
            + (f" on a {acres:,.2f}-ac tract" if acres is not None else "")
            + f" in {(getattr(parcel, 'county', None) or 'this county')}, "
            f"{(getattr(parcel, 'state', None) or 'US')}. "
            f"{_neighbor_note(value)}. Contributes ~{contribution:.1f} pts."
        )
        drivers = evid[:3] or [f"Scarcity proxy for this tract → {value:.0f}/100"]

    elif key == "catalysts":
        why = (
            f"«{label}» catalyst score is {value:.0f}/100 — "
            f"{(evid[0] if evid else 'no structured near-term catalyst tied to this APN on the public file')}. "
            f"{_neighbor_note(value)}. Contributes ~{contribution:.1f} pts."
        )
        drivers = evid[:3] or [f"No catalyst event on APN {(getattr(parcel, 'apn', None) or 'n/a')}"]

    elif key == "seller_dynamics":
        ch = provider or "listing"
        dom = getattr(listing, "days_on_market", None) if listing else None
        why = (
            f"«{label}» seller/process pressure is {value:.0f}/100 from the "
            f"{ch} channel dynamics on this file"
            + (f" (DOM {dom})" if dom is not None else "")
            + f". {_neighbor_note(value, f'{ch} seller-pressure proxy')}. "
            f"Contributes ~{contribution:.1f} pts."
        )
        drivers = evid[:3] or [f"Seller pressure on this {ch} file → {value:.0f}"]

    elif key == "risk":
        risk_bits = "; ".join(evid[:3]) if evid else "no flood/wetland/access hits on this desktop file"
        why = (
            f"«{label}»" + (f" @ {pin}" if pin else "") + f" carries overall risk "
            f"{risk_score:.0f}/100; this opportunity component is {value:.0f}/100 "
            f"(= 100 − risk). Drivers on this listing: {risk_bits}. "
            f"{_neighbor_note(value, risk_bits[:90])}. "
            f"Contributes ~{contribution:.1f} pts to LandSignal {opp:.0f}/100."
        )
        drivers = evid[:4] or [f"Desktop risk {risk_score:.0f} on this listing → component {value:.0f}"]

    else:
        why = (
            f"«{label}» {key.replace('_', ' ')} = {value:.0f}/100 from this listing’s inputs. "
            f"{_neighbor_note(value)}."
        )
        drivers = evid[:3] or [f"{key} → {value:.0f} on this listing"]

    # Drop accidental double periods
    why = why.replace("..", ".").replace(". .", ".")

    return {
        "plain_english": why,
        "why_this_number": why,
        "drivers": drivers[:5],
        "weight_note": (
            f"On «{label}», this bar is {wt_pct}% of LandSignal and adds ~{contribution:.1f} "
            f"toward the overall {opp:.0f}/100"
            + (f" (risk {risk_score:.0f}, confidence {conf:.0f})" if risk_score is not None and conf is not None else "")
            + "."
        ),
        "identity": label,
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
