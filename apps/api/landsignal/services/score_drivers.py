"""Hyper-specific bullets for Opportunity / Risk / Completeness meters."""

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


def _clean(s: str) -> str:
    t = (s or "").strip()
    # Drop APN-leading evidence tags like "123 · County, ST · 10 ac: …"
    if ": " in t and " · " in t.split(": ", 1)[0]:
        t = t.split(": ", 1)[1].strip()
    return t


def build_score_drivers(
    *,
    parcel,
    listing,
    score,
    enrichment=None,
    price: dict | None = None,
) -> dict[str, Any]:
    """3–5 tailored bullets per meter so buyers can judge if it’s a real buy."""
    place = place_phrase(parcel)
    prop = this_property(parcel, listing, with_place=True, with_acres=True)
    opp = _f(getattr(score, "opportunity", None)) or 0.0
    risk = _f(getattr(score, "risk", None)) or 0.0
    conf = _f(getattr(score, "confidence", None)) or 0.0
    disc = _f(getattr(score, "asking_discount_pct", None))
    est = _f(getattr(score, "estimated_value_usd", None))
    strat = getattr(score, "best_strategy", None)
    strat_s = strat.value.replace("_", " ").title() if strat and hasattr(strat, "value") else (str(strat) if strat else None)
    provider = getattr(listing, "provider_id", None) if listing else None
    acres = _f(getattr(parcel, "acreage", None))

    soil_n = {}
    flood_n = {}
    wet_n = {}
    if enrichment:
        if enrichment.soil:
            soil_n = enrichment.soil.normalized or enrichment.soil.value or {}
        if enrichment.flood:
            flood_n = enrichment.flood.normalized or enrichment.flood.value or {}
        if enrichment.wetlands:
            wet_n = enrichment.wetlands.normalized or enrichment.wetlands.value or {}

    prime = _f(soil_n.get("prime_farmland_pct"))
    flood = _f(flood_n.get("flood_zone_pct"))
    wet = _f(wet_n.get("wetland_pct"))

    # --- Opportunity ---
    opp_bullets: list[str] = []
    if disc is not None and est is not None:
        entry = est * (1 + disc / 100.0)
        opp_bullets.append(
            f"Buy screen ~{_money(entry)} vs our value {_money(est)} ({disc:+.0f}%) for {prop}."
        )
    elif est is not None:
        opp_bullets.append(f"Our value screen for {prop}: {_money(est)} (no public ask yet).")
    if strat_s:
        opp_bullets.append(f"Best-use screen: {strat_s} on this file in {place}.")
    for note in (getattr(score, "why_interesting", None) or [])[:3]:
        c = _clean(str(note))
        if c and c not in opp_bullets:
            opp_bullets.append(c)
    # Top weighted components
    comps = sorted(
        getattr(score, "components", None) or [],
        key=lambda c: abs(float(c.get("contribution") or 0)),
        reverse=True,
    )
    for c in comps[:3]:
        label = str(c.get("label") or c.get("category") or "").replace("_", " ")
        val = _f(c.get("value"))
        if label and val is not None:
            line = f"{label.title()} contributes {val:.0f}/100 to opportunity."
            if line not in opp_bullets:
                opp_bullets.append(line)
    if provider == "public_tax_sale":
        opp_bullets.append(
            "Channel edge: county tax-delinquent sale — Google/Zillow rarely underwrite these."
        )
    elif provider == "blm_lpad":
        opp_bullets.append(
            "Channel edge: federal BLM disposal — public process inventory, not MLS retail."
        )
    if opp >= 75:
        verdict = "Looks like a priority scout — edge is showing on price and/or use."
    elif opp >= 60:
        verdict = "Promising enough to open the full file — confirm access and land checks."
    elif opp >= 45:
        verdict = "Mixed edge — only pursue if the use thesis fits your plan."
    else:
        verdict = "Weak opportunity screen — better files likely exist in the queue."

    # --- Risk ---
    risk_bullets: list[str] = []
    if flood is not None:
        risk_bullets.append(f"Flood overlap screen: {flood:.0f}% on the FEMA layer for this pin.")
    if wet is not None:
        risk_bullets.append(f"Wetland screen: {wet:.0f}% — can cut usable acres.")
    for kill in (getattr(score, "what_could_kill", None) or [])[:3]:
        c = _clean(str(kill))
        if c and c not in risk_bullets:
            risk_bullets.append(c)
    # Risk component evidence
    for c in comps:
        if str(c.get("category") or "") == "risk":
            for e in (c.get("evidence") or [])[:2]:
                ce = _clean(str(e))
                if ce and ce not in risk_bullets:
                    risk_bullets.append(ce)
    if not risk_bullets:
        risk_bullets.append(f"Desktop risk {risk:.0f}/100 for {prop} — thin map evidence so far.")
    if risk <= 35:
        risk_verdict = "Lower map risk — still verify title and access before bidding."
    elif risk <= 55:
        risk_verdict = "Moderate risk — budget homework on flood/wetlands/access."
    else:
        risk_verdict = "Elevated risk — treat as a specialist file, not a casual buy."

    # --- Completeness ---
    conf_bullets: list[str] = []
    conf_bullets.append(f"File completeness {conf:.0f}/100 for {prop}.")
    known_bits = []
    if prime is not None:
        known_bits.append(f"soil (~{prime:.0f}% prime)")
    if flood is not None:
        known_bits.append("flood")
    if wet is not None:
        known_bits.append("wetlands")
    if est is not None:
        known_bits.append("value mark")
    if known_bits:
        conf_bullets.append("On file: " + ", ".join(known_bits) + ".")
    missing = []
    if prime is None:
        missing.append("prime soil")
    if flood is None:
        missing.append("flood")
    if wet is None:
        missing.append("wetlands")
    if missing:
        conf_bullets.append("Still thin: " + ", ".join(missing) + ".")
    conf_bullets.append("Thin files score lower on purpose — not a quality grade.")

    return {
        "opportunity": {
            "verdict": verdict,
            "bullets": opp_bullets[:5],
        },
        "risk": {
            "verdict": risk_verdict,
            "bullets": risk_bullets[:5],
        },
        "confidence": {
            "verdict": (
                "Fairly complete desktop file."
                if conf >= 65
                else "Some layers missing — double-check before you bid."
                if conf >= 40
                else "Thin file — treat numbers as a first look only."
            ),
            "bullets": conf_bullets[:5],
        },
        "buy_lens": {
            "headline": verdict,
            "acres": acres,
            "place": place,
            "strategy": strat_s,
            "channel": provider,
        },
    }
