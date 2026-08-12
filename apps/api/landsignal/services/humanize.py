from __future__ import annotations

from typing import Any


def _pct(v: Any) -> str | None:
    if v is None:
        return None
    try:
        return f"{float(v):.0f}%"
    except Exception:
        return None


def human_soil(prov: Any, *, apn: str | None = None, county: str | None = None, state: str | None = None) -> dict[str, Any]:
    n = (getattr(prov, "normalized", None) or getattr(prov, "value", None) or {}) if prov else {}
    if isinstance(prov, dict):
        n = prov.get("normalized") or prov.get("value") or {}
    ks = getattr(prov, "knowledge_state", None)
    if hasattr(ks, "value"):
        state_s = str(ks.value)
    elif isinstance(prov, dict) and prov.get("knowledge_state") is not None:
        state_s = str(prov.get("knowledge_state"))
    else:
        state_s = "UNKNOWN"
    # Strip enum class prefixes if a raw enum leaked into storage
    state_s = state_s.replace("KnowledgeState.", "").strip()
    prime = n.get("prime_farmland_pct")
    farm = n.get("farmland_classification")
    place = f"{county}, {state}" if county and state else (county or state or "")
    where = f"This property in {place}" if place else "This property"
    bullets = []
    if farm:
        bullets.append(f"USDA farmland class: {farm}")
    if prime is not None:
        bullets.append(f"About {float(prime):.0f}% of the sampled area looks like prime farmland.")
    else:
        bullets.append("Prime farmland share not confirmed yet from USDA for this shape.")
    bullets.append("Map soil only — order a soil test before counting on farm income.")
    if farm or prime is not None:
        plain = (
            f"{where}: soil class {farm or 'not confirmed'}; "
            f"prime farmland {_pct(prime) or 'not confirmed'}."
        )
        level = "Known" if state_s.upper() == "KNOWN" else "Estimate"
    else:
        plain = f"{where}: soil class and prime farmland not confirmed yet."
        level = "Not confirmed"
    return {
        "title": "Soil quality",
        "plain_english": plain,
        "level": level,
        "bullets": bullets,
        "knowledge_state": state_s,
        "source": getattr(prov, "source", None) or (prov.get("source") if isinstance(prov, dict) else "ssurgo"),
        "confidence": getattr(prov, "confidence", None) if not isinstance(prov, dict) else prov.get("confidence"),
        "score_hint": int(prime) if prime is not None else None,
    }


def human_flood(prov: Any, *, apn: str | None = None) -> dict[str, Any]:
    n = (getattr(prov, "normalized", None) or getattr(prov, "value", None) or {}) if prov else {}
    if isinstance(prov, dict):
        n = prov.get("normalized") or prov.get("value") or {}
    ks = getattr(prov, "knowledge_state", None)
    state_s = (
        str(ks.value)
        if hasattr(ks, "value")
        else str(prov.get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
    ).replace("KnowledgeState.", "")
    flood = n.get("flood_zone_pct")
    zone = n.get("zone")
    if flood is None:
        plain = "Flood exposure not confirmed yet from FEMA."
        level = "Unknown"
    elif float(flood) < 10:
        plain = f"FEMA map shows low flood overlap ({float(flood):.0f}%)."
        level = "Lower"
    elif float(flood) < 35:
        plain = f"FEMA map shows {float(flood):.0f}% flood overlap — insurance and loans may be harder."
        level = "Moderate"
    else:
        plain = f"FEMA map shows high flood overlap ({float(flood):.0f}%) — plan for insurance and fill cost."
        level = "Higher"
    bullets = [
        f"Flood overlap {_pct(flood) or 'not confirmed'}"
        + (f" · zone {zone}" if zone else ""),
        "Not an elevation certificate — confirm before you bid.",
    ]
    return {
        "title": "Flood exposure",
        "plain_english": plain,
        "level": level,
        "bullets": bullets,
        "knowledge_state": state_s,
        "source": getattr(prov, "source", None) or "fema_nfhl",
        "confidence": getattr(prov, "confidence", None) if not isinstance(prov, dict) else prov.get("confidence"),
        "score_hint": max(0, 100 - int(float(flood))) if flood is not None else None,
    }


def human_wetlands(prov: Any) -> dict[str, Any]:
    n = (getattr(prov, "normalized", None) or getattr(prov, "value", None) or {}) if prov else {}
    if isinstance(prov, dict):
        n = prov.get("normalized") or prov.get("value") or {}
    ks = getattr(prov, "knowledge_state", None)
    state_s = (
        str(ks.value)
        if hasattr(ks, "value")
        else str(prov.get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
    ).replace("KnowledgeState.", "")
    wet = n.get("wetland_pct")
    if wet is None:
        plain = "Wetland share is not confirmed yet from the National Wetlands Inventory."
        level = "Unknown"
    elif float(wet) < 10:
        plain = "Wetland screen looks limited — still confirm before grading or subdividing."
        level = "Lower"
    elif float(wet) < 40:
        plain = "Wetlands may reduce buildable/farmable acres. Budget for delineation."
        level = "Moderate"
    else:
        plain = "Wetlands appear substantial and may block several development theses."
        level = "Higher"
    return {
        "title": "Wetlands",
        "plain_english": plain,
        "level": level,
        "bullets": [
            f"Wetland screen: {_pct(wet) or 'not confirmed'}",
            "NWI is a screen, not a jurisdictional delineation.",
        ],
        "knowledge_state": state_s,
        "source": getattr(prov, "source", None) or "nwi",
        "confidence": getattr(prov, "confidence", None) if not isinstance(prov, dict) else prov.get("confidence"),
        "score_hint": max(0, 100 - int(float(wet))) if wet is not None else None,
    }


def human_transmission(prov: Any) -> dict[str, Any]:
    n = (getattr(prov, "normalized", None) or getattr(prov, "value", None) or {}) if prov else {}
    if isinstance(prov, dict):
        n = prov.get("normalized") or prov.get("value") or {}
    ks = getattr(prov, "knowledge_state", None)
    state_s = (
        str(ks.value)
        if hasattr(ks, "value")
        else str(prov.get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
    ).replace("KnowledgeState.", "")
    meters = n.get("nearest_transmission_m")
    if meters is None:
        plain = "No nearby transmission line was confirmed in the search window."
        level = "Unknown"
        miles = None
    else:
        miles = float(meters) / 1609.34
        if miles < 1:
            plain = f"A transmission line appears about {miles:.1f} miles away — energy optionality screen only."
            level = "Nearby"
        elif miles < 5:
            plain = f"Nearest screened transmission line is about {miles:.1f} miles away."
            level = "Moderate"
        else:
            plain = f"Nearest screened line ~{miles:.1f} miles away — interconnection may be harder."
            level = "Farther"
    return {
        "title": "Power line proximity",
        "plain_english": plain,
        "level": level,
        "bullets": [
            f"Distance screen: {miles:.1f} miles" if miles is not None else "Distance not confirmed",
            "Near a line does not mean you can connect to the grid.",
        ],
        "knowledge_state": state_s,
        "source": getattr(prov, "source", None) or "hifld_transmission",
        "confidence": getattr(prov, "confidence", None) if not isinstance(prov, dict) else prov.get("confidence"),
        "score_hint": int(max(0, 100 - (miles or 20) * 8)) if miles is not None else None,
    }


def human_access(prov: Any) -> dict[str, Any]:
    n = (getattr(prov, "normalized", None) or getattr(prov, "value", None) or {}) if prov else {}
    if isinstance(prov, dict):
        n = prov.get("normalized") or prov.get("value") or {}
    ks = getattr(prov, "knowledge_state", None)
    state_s = (
        str(ks.value) if hasattr(ks, "value") else str(prov.get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
    ).replace("KnowledgeState.", "")
    access = n.get("legal_access_confidence")
    if access is None:
        plain = "Legal road access is not confirmed yet for this pin."
        level = "Not confirmed"
    elif float(access) >= 70:
        plain = f"Access screen looks workable ({float(access):.0f}/100) — still confirm on the deed."
        level = "Workable"
    elif float(access) >= 40:
        plain = f"Access is only partly clear ({float(access):.0f}/100) — check recorded easements."
        level = "Needs check"
    else:
        plain = f"Access looks weak ({float(access):.0f}/100) — do not assume you can drive in."
        level = "Weak"
    return {
        "title": "Road / legal access",
        "plain_english": plain,
        "level": level,
        "bullets": [
            f"Access confidence: {float(access):.0f}/100" if access is not None else "Access not scored yet",
            "Map adjacency ≠ a recorded right of way.",
        ],
        "knowledge_state": state_s,
        "source": getattr(prov, "source", None) or "access_model",
        "confidence": getattr(prov, "confidence", None) if not isinstance(prov, dict) else prov.get("confidence"),
        "score_hint": int(access) if access is not None else None,
    }


def human_slope(prov: Any) -> dict[str, Any]:
    n = (getattr(prov, "normalized", None) or getattr(prov, "value", None) or {}) if prov else {}
    if isinstance(prov, dict):
        n = prov.get("normalized") or prov.get("value") or {}
    ks = getattr(prov, "knowledge_state", None)
    state_s = (
        str(ks.value) if hasattr(ks, "value") else str(prov.get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
    ).replace("KnowledgeState.", "")
    avg = n.get("avg_slope_pct")
    mx = n.get("max_slope_pct")
    elev = n.get("elevation_m")
    if avg is None and mx is None:
        plain = "Slope / buildability is not confirmed yet for this shape."
        level = "Not confirmed"
    else:
        a = float(avg) if avg is not None else float(mx or 0)
        if a < 5:
            plain = f"Ground looks relatively flat (avg slope ~{a:.0f}%) — easier for build or farm use."
            level = "Gentle"
        elif a < 12:
            plain = f"Moderate slope (avg ~{a:.0f}%) — usable with some site work."
            level = "Moderate"
        else:
            plain = f"Steeper ground (avg ~{a:.0f}%) — can raise build/farm cost."
            level = "Steep"
    bullets = []
    if avg is not None:
        bullets.append(f"Average slope ~{float(avg):.0f}%")
    if mx is not None:
        bullets.append(f"Max slope screen ~{float(mx):.0f}%")
    if elev is not None:
        bullets.append(f"Elevation ~{float(elev):,.0f} m")
    if not bullets:
        bullets.append("Terrain layer thin for this pin.")
    return {
        "title": "Slope / buildability",
        "plain_english": plain,
        "level": level,
        "bullets": bullets[:3],
        "knowledge_state": state_s,
        "source": getattr(prov, "source", None) or "terrain",
        "confidence": getattr(prov, "confidence", None) if not isinstance(prov, dict) else prov.get("confidence"),
        "score_hint": int(max(0, 100 - float(avg or mx or 20) * 4)) if (avg is not None or mx is not None) else None,
    }


def human_growth(prov: Any, comps: Any = None) -> dict[str, Any]:
    n = (getattr(prov, "normalized", None) or getattr(prov, "value", None) or {}) if prov else {}
    if isinstance(prov, dict):
        n = prov.get("normalized") or prov.get("value") or {}
    if comps and not n.get("path_of_growth_score"):
        cn = getattr(comps, "normalized", None) or getattr(comps, "value", None) or {}
        if isinstance(comps, dict):
            cn = comps.get("normalized") or comps.get("value") or {}
        if cn.get("path_of_growth_score") is not None:
            n = {**n, "path_of_growth_score": cn.get("path_of_growth_score")}
    ks = getattr(prov, "knowledge_state", None) if prov else None
    state_s = (
        str(ks.value) if hasattr(ks, "value") else str((prov or {}).get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
    ).replace("KnowledgeState.", "")
    g = n.get("path_of_growth_score")
    county = n.get("county_name")
    if g is None:
        plain = "Area growth signal is not confirmed yet for this county."
        level = "Not confirmed"
    elif float(g) >= 70:
        plain = f"Growth screen is strong ({float(g):.0f}/100)" + (f" in {county}" if county else "") + " — demand may support exit."
        level = "Strong"
    elif float(g) >= 45:
        plain = f"Growth screen is mixed ({float(g):.0f}/100) — neither a magnet nor a dead zone."
        level = "Mixed"
    else:
        plain = f"Growth screen is soft ({float(g):.0f}/100) — plan a longer hold or a use that doesn’t need in-migration."
        level = "Soft"
    return {
        "title": "Area growth",
        "plain_english": plain,
        "level": level,
        "bullets": [
            f"Path-of-growth: {float(g):.0f}/100" if g is not None else "Growth not scored yet",
            "This is a county-level screen, not a guarantee of price.",
        ],
        "knowledge_state": state_s,
        "source": getattr(prov, "source", None) or "growth",
        "confidence": getattr(prov, "confidence", None) if prov and not isinstance(prov, dict) else None,
        "score_hint": int(g) if g is not None else None,
    }


def human_resale(comps: Any) -> dict[str, Any]:
    n = (getattr(comps, "normalized", None) or getattr(comps, "value", None) or {}) if comps else {}
    if isinstance(comps, dict):
        n = comps.get("normalized") or comps.get("value") or {}
    liq = n.get("liquidity_score")
    scar = n.get("scarcity_score")
    if liq is None and scar is None:
        plain = "Resale ease and scarcity are not confirmed yet for this file."
        level = "Not confirmed"
    else:
        parts = []
        if liq is not None:
            parts.append(f"resale ease {float(liq):.0f}/100")
        if scar is not None:
            parts.append(f"scarcity {float(scar):.0f}/100")
        plain = "For this channel/size: " + ", ".join(parts) + "."
        level = "Clearer" if (liq or 0) >= 55 or (scar or 0) >= 60 else "Tougher"
    return {
        "title": "Resale & scarcity",
        "plain_english": plain,
        "level": level,
        "bullets": [
            f"Liquidity screen: {float(liq):.0f}/100" if liq is not None else "Liquidity not scored",
            f"Scarcity screen: {float(scar):.0f}/100" if scar is not None else "Scarcity not scored",
        ],
        "knowledge_state": "ESTIMATED" if (liq is not None or scar is not None) else "UNKNOWN",
        "source": "comps",
        "confidence": getattr(comps, "confidence", None) if comps and not isinstance(comps, dict) else None,
        "score_hint": int(((liq or 50) + (scar or 50)) / 2) if (liq is not None or scar is not None) else None,
    }


def human_dd_items(items: list[dict], score: Any, enrichment: Any) -> list[dict[str, Any]]:
    """Turn checklist into guided next steps with why-it-matters."""
    why_map = {
        "Confirm title": "Proves who can legally sell and what exceptions exist.",
        "Order title commitment": "Shows liens, easements, and cure items before you spend more.",
        "Confirm legal access": "Road adjacency is not the same as recorded access rights.",
        "Survey": "Locks down acreage, boundaries, and encroachments.",
        "Verify easements": "Utility/access easements can shrink usable land.",
        "Verify zoning directly with county": "Online layers go stale; staff confirmation matters.",
        "Confirm water rights": "Critical for ag/irrigation value in the West.",
        "Wetlands delineation if necessary": "Needed if your plan needs grading or lots.",
        "Environmental assessment if necessary": "Looks for contamination beyond desktop screens.",
        "Soil testing": "Confirms farming or septic reality beyond USDA screens.",
        "Utility availability letters": "Will-serve letters beat map guesses.",
        "Confirm mineral rights": "Severed minerals can block or burden surface use.",
        "Review deed restrictions": "Private restrictions can ban your intended use.",
    }
    # Priority based on scores
    priority_boost = []
    if score and getattr(score, "risk", 50) >= 45:
        priority_boost.extend(["Confirm legal access", "Wetlands delineation if necessary", "Order title commitment"])
    wet = None
    if enrichment and getattr(enrichment, "wetlands", None) and enrichment.wetlands.normalized:
        wet = enrichment.wetlands.normalized.get("wetland_pct")
    if wet is not None and float(wet) >= 20:
        priority_boost.append("Wetlands delineation if necessary")

    out = []
    for i, item in enumerate(items or []):
        label = item.get("label") or ""
        priority = "Now" if label in priority_boost else ("Soon" if i < 6 else "Before closing")
        out.append(
            {
                "label": label,
                "completed": bool(item.get("completed")),
                "priority": priority,
                "why_it_matters": why_map.get(label, "Standard institutional diligence item for land."),
                "how_to_start": f"Ask a local title/survey/land-use professional to complete: {label.lower()}.",
            }
        )
    return out


CATEGORY_HELP = {
    "valuation_mispricing": {
        "title": "Price vs our estimate",
        "simple": "Compares what you’d likely pay today with what we think this land is worth. Higher = cheaper vs our estimate.",
    },
    "intrinsic_land_quality": {
        "title": "Land quality",
        "simple": "How usable this exact pin looks from soil and slope. Higher = more usable ground.",
    },
    "hbu_optionality": {
        "title": "Best-fit use",
        "simple": "How well farm, homes, energy, or hold uses fit this listing. Higher = a clearer fit.",
    },
    "growth_appreciation": {
        "title": "Area growth",
        "simple": "Whether people and jobs are moving toward this area. Higher = stronger local growth signal.",
    },
    "infrastructure": {
        "title": "Roads & power",
        "simple": "Road access and nearby power for this pin. Higher = easier to reach and serve.",
    },
    "liquidity": {
        "title": "Ease of resale",
        "simple": "How quickly similar land here usually finds a buyer. Higher = easier to sell later.",
    },
    "scarcity": {
        "title": "How rare it is",
        "simple": "How hard it is to find similar acreage nearby. Higher = rarer tract.",
    },
    "catalysts": {
        "title": "Nearby projects",
        "simple": "Known nearby projects that could lift value. Higher = clearer upside catalysts.",
    },
    "seller_dynamics": {
        "title": "Seller pressure",
        "simple": "Signs this seller or channel may accept a lower offer. Higher = more negotiating room.",
    },
    "risk": {
        "title": "Risk cushion",
        "simple": "Higher here means fewer flood/wetland/access red flags helping the opportunity score.",
    },
}
