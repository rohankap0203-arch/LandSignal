"""Plain-English reasons a buyer can trust — why THIS file scored this way."""

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


def build_score_drivers(
    *,
    parcel,
    listing,
    score,
    enrichment=None,
    price: dict | None = None,
) -> dict[str, Any]:
    """2–4 short, specific reasons — feedback, not metric soup."""
    place = place_phrase(parcel)
    acres = _f(getattr(parcel, "acreage", None))
    size = f"{acres:,.1f}-acre " if acres is not None else ""
    opp = _f(getattr(score, "opportunity", None)) or 0.0
    risk = _f(getattr(score, "risk", None)) or 0.0
    conf = _f(getattr(score, "confidence", None)) or 0.0
    disc = _f(getattr(score, "asking_discount_pct", None))
    est = _f(getattr(score, "estimated_value_usd", None))
    strat = getattr(score, "best_strategy", None)
    strat_s = (
        strat.value.replace("_", " ").title()
        if strat and hasattr(strat, "value")
        else (str(strat).replace("_", " ").title() if strat else None)
    )
    provider = getattr(listing, "provider_id", None) if listing else None

    soil_n = flood_n = wet_n = access_n = growth_n = comps_n = {}
    if enrichment:
        if enrichment.soil:
            soil_n = enrichment.soil.normalized or enrichment.soil.value or {}
        if enrichment.flood:
            flood_n = enrichment.flood.normalized or enrichment.flood.value or {}
        if enrichment.wetlands:
            wet_n = enrichment.wetlands.normalized or enrichment.wetlands.value or {}
        if enrichment.access:
            access_n = enrichment.access.normalized or enrichment.access.value or {}
        if enrichment.growth:
            growth_n = enrichment.growth.normalized or enrichment.growth.value or {}
        if enrichment.comps:
            comps_n = enrichment.comps.normalized or enrichment.comps.value or {}

    prime = _f(soil_n.get("prime_farmland_pct"))
    flood = _f(flood_n.get("flood_zone_pct"))
    wet = _f(wet_n.get("wetland_pct"))
    access = _f(access_n.get("legal_access_confidence"))
    growth = _f(growth_n.get("path_of_growth_score")) or _f(comps_n.get("path_of_growth_score"))

    # --- Opportunity: why buy THIS one ---
    opp_bullets: list[str] = []
    if disc is not None and disc <= -20 and est is not None:
        buy = est * (1 + disc / 100.0)
        opp_bullets.append(
            f"You may get in near {_money(buy)} while we mark this {size}land around {_money(est)}."
        )
    elif disc is not None and est is not None:
        buy = est * (1 + disc / 100.0)
        opp_bullets.append(
            f"Buy near {_money(buy)} vs our {_money(est)} value — a smaller edge, still worth a look."
        )
    elif est is not None:
        opp_bullets.append(f"No public ask yet; our first value read is about {_money(est)}.")

    if provider == "public_tax_sale":
        opp_bullets.append(f"This is a county tax-sale style file in {place} — not a normal Zillow listing.")
    elif provider == "blm_lpad":
        opp_bullets.append(f"Federal BLM disposal land in {place} — public process, not MLS retail.")
    elif provider == "public_surplus":
        opp_bullets.append(f"Public surplus inventory in {place} — agency sells, not a broker.")
    elif provider == "public_vacant_gis":
        opp_bullets.append(
            f"This started as vacant land on the {place} public map — confirm owner / sale path before you treat it as a buy."
        )

    if strat_s:
        opp_bullets.append(f"Best fit we see here: {strat_s}.")
    if growth is not None and growth >= 65:
        opp_bullets.append(f"Local growth around {place} looks supportive for a hold.")
    if prime is not None and prime >= 45:
        opp_bullets.append(f"Soil screen shows about {prime:.0f}% prime farmland — helps farm or rent plans.")

    acres_note = f"{acres:,.1f} acres" if acres is not None else "this tract"
    if opp >= 72:
        verdict = f"Strong candidate — {acres_note} in {place} shows a real buy edge for a scouted hold."
    elif opp >= 58:
        verdict = f"Worth opening — {acres_note} in {place} is solid enough to shortlist."
    elif opp >= 45:
        verdict = f"Only a maybe — keep {acres_note} if the use fits; otherwise keep scanning."
    else:
        verdict = f"Weak edge on {acres_note} in {place} — better files are likely ahead."

    # --- Risk: what could bite you ---
    risk_bullets: list[str] = []
    if flood is not None and flood >= 25:
        risk_bullets.append(
            f"Flood map covers about {flood:.0f}% of this pin — that slows the long path and adds carry."
        )
    elif flood is not None and flood >= 10:
        risk_bullets.append(f"Some flood overlap (~{flood:.0f}%) — check before you bid hard.")
    elif flood is not None:
        risk_bullets.append("Flood overlap looks light on the map for this pin.")

    if wet is not None and wet >= 20:
        risk_bullets.append(
            f"Wetlands (~{wet:.0f}%) may cut usable acres — exit and rent screens already bake that in."
        )
    elif wet is not None and wet < 10:
        risk_bullets.append("Wetland screen looks limited on this shape.")

    if access is not None and access < 45:
        risk_bullets.append("Legal road access is not clear yet — confirm before you spend.")
    elif access is not None and access >= 70:
        risk_bullets.append("Access screen looks workable for this parcel.")

    if provider in ("public_tax_sale", "blm_lpad", "public_surplus"):
        risk_bullets.append(
            "Public process channel — title/clearing friction can step value down even when the map looks fine."
        )

    if not risk_bullets:
        risk_bullets.append(f"Map checks for this {size}property in {place} are still thin — verify on the ground.")

    if risk <= 35:
        risk_verdict = "Lower worry on the map — still confirm title and access."
    elif risk <= 55:
        risk_verdict = "Some yellow flags — fixable with homework, not a walk-away by itself."
    else:
        risk_verdict = "Higher worry — only pursue if you can live with the constraints."

    # --- Completeness: can you trust the file ---
    conf_bullets: list[str] = []
    have = []
    miss = []
    if prime is not None:
        have.append("soil")
    else:
        miss.append("soil")
    if flood is not None:
        have.append("flood")
    else:
        miss.append("flood")
    if wet is not None:
        have.append("wetlands")
    else:
        miss.append("wetlands")
    if est is not None:
        have.append("value")
    else:
        miss.append("value")
    if have:
        conf_bullets.append("We already have: " + ", ".join(have) + ".")
    if miss:
        conf_bullets.append("Still missing: " + ", ".join(miss) + " — don’t treat the score as final.")
    conf_bullets.append(
        "A lower completeness number means thinner data, not worse land."
    )

    if conf >= 65:
        conf_verdict = "File is full enough for a first go / no-go."
    elif conf >= 40:
        conf_verdict = "Partly filled in — open the checks below before you bid."
    else:
        conf_verdict = "Thin file — use this as a tip, then verify with the county."

    return {
        "opportunity": {"verdict": verdict, "bullets": opp_bullets[:4]},
        "risk": {"verdict": risk_verdict, "bullets": risk_bullets[:4]},
        "confidence": {"verdict": conf_verdict, "bullets": conf_bullets[:3]},
        "buy_lens": {
            "headline": verdict,
            "next_step": (
                "Call the office, confirm the parcel ID, then decide go / no-go."
                if opp >= 58
                else "Keep this on a short watch list while you open stronger files."
            ),
        },
    }
