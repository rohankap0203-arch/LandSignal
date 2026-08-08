from __future__ import annotations

from typing import Any


def _pct(v: Any) -> str | None:
    if v is None:
        return None
    try:
        return f"{float(v):.0f}%"
    except Exception:
        return None


def human_soil(prov: Any) -> dict[str, Any]:
    n = (getattr(prov, "normalized", None) or getattr(prov, "value", None) or {}) if prov else {}
    if isinstance(prov, dict):
        n = prov.get("normalized") or prov.get("value") or {}
    state = getattr(prov, "knowledge_state", None)
    state_s = state.value if hasattr(state, "value") else (prov.get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
    prime = n.get("prime_farmland_pct")
    farm = n.get("farmland_classification")
    bullets = []
    if farm:
        bullets.append(f"USDA farmland class: {farm}")
    if prime is not None:
        bullets.append(f"About {float(prime):.0f}% of the screened area looks like prime farmland (point/polygon screen).")
    else:
        bullets.append("Prime-farmland share is not confirmed yet from USDA for this parcel geometry.")
    bullets.append("This is a screening read from USDA SSURGO — order a soil test before farming decisions.")
    plain = (
        f"Soil look: {farm or 'classification not confirmed'}. "
        f"Prime farmland screen: {_pct(prime) or 'not confirmed'}."
    )
    return {
        "title": "Soil quality",
        "plain_english": plain,
        "bullets": bullets,
        "knowledge_state": state_s,
        "source": getattr(prov, "source", None) or (prov.get("source") if isinstance(prov, dict) else "ssurgo"),
        "confidence": getattr(prov, "confidence", None) if not isinstance(prov, dict) else prov.get("confidence"),
        "score_hint": int(prime) if prime is not None else None,
    }


def human_flood(prov: Any) -> dict[str, Any]:
    n = (getattr(prov, "normalized", None) or getattr(prov, "value", None) or {}) if prov else {}
    if isinstance(prov, dict):
        n = prov.get("normalized") or prov.get("value") or {}
    state = getattr(prov, "knowledge_state", None)
    state_s = state.value if hasattr(state, "value") else (prov.get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
    flood = n.get("flood_zone_pct")
    zone = n.get("zone")
    if flood is None:
        plain = "Flood exposure is not confirmed yet from FEMA for this location."
        level = "Unknown"
    elif float(flood) < 10:
        plain = "FEMA screen suggests low flood overlap at the checked location."
        level = "Lower"
    elif float(flood) < 35:
        plain = "FEMA screen suggests meaningful flood exposure — financing and insurance may be harder."
        level = "Moderate"
    else:
        plain = "FEMA screen suggests high flood exposure — treat as a major deal risk until surveyed."
        level = "Higher"
    bullets = [
        f"Flood overlap screen: {_pct(flood) or 'not confirmed'}",
        f"FEMA zone mark: {zone or 'not returned at point sample'}",
        "This is not a survey or elevation certificate. Verify with a flood specialist before buying.",
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
    state = getattr(prov, "knowledge_state", None)
    state_s = state.value if hasattr(state, "value") else (prov.get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
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
            "NWI is a screening layer, not a jurisdictional delineation.",
            "If wetlands matter to your plan, hire a qualified wetland scientist.",
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
    state = getattr(prov, "knowledge_state", None)
    state_s = state.value if hasattr(state, "value") else (prov.get("knowledge_state") if isinstance(prov, dict) else "UNKNOWN")
    meters = n.get("nearest_transmission_m")
    if meters is None:
        plain = "No nearby transmission line was confirmed in the search window."
        level = "Unknown / distant"
        miles = None
    else:
        miles = float(meters) / 1609.34
        if miles < 1:
            plain = f"A transmission line appears about {miles:.1f} miles away — useful for energy optionality screening only."
            level = "Nearby"
        elif miles < 5:
            plain = f"Nearest screened transmission line is about {miles:.1f} miles away."
            level = "Moderate distance"
        else:
            plain = f"Nearest screened transmission line is about {miles:.1f} miles away — interconnection may be harder."
            level = "Farther"
    return {
        "title": "Power line proximity",
        "plain_english": plain,
        "level": level,
        "bullets": [
            f"Distance screen: {miles:.1f} miles" if miles is not None else "Distance not confirmed",
            "Important: being near a line does NOT mean you can connect to the grid.",
            "Utility queue, capacity, and permits must be checked separately.",
        ],
        "knowledge_state": state_s,
        "source": getattr(prov, "source", None) or "hifld_transmission",
        "confidence": getattr(prov, "confidence", None) if not isinstance(prov, dict) else prov.get("confidence"),
        "score_hint": int(max(0, 100 - (miles or 20) * 8)) if miles is not None else None,
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
        "title": "Price vs value",
        "simple": "Does the asking/bid price look cheap or expensive versus our screening model?",
    },
    "intrinsic_land_quality": {
        "title": "Land quality",
        "simple": "How usable/productive does the land look from soils and slope screens?",
    },
    "hbu_optionality": {
        "title": "Future use options",
        "simple": "How many realistic ways could this land make money (farm, energy, homes, etc.)?",
    },
    "growth_appreciation": {
        "title": "Growth path",
        "simple": "Is activity and population pressure moving toward this area over time?",
    },
    "infrastructure": {
        "title": "Access & infrastructure",
        "simple": "Roads, power proximity, and basic infrastructure support.",
    },
    "liquidity": {
        "title": "Ease of resale",
        "simple": "If plans change, how hard might it be to sell this parcel later?",
    },
    "scarcity": {
        "title": "Scarcity",
        "simple": "How replaceable is a parcel like this nearby?",
    },
    "catalysts": {
        "title": "Nearby catalysts",
        "simple": "Known projects/events that could change value (highways, plants, etc.).",
    },
    "seller_dynamics": {
        "title": "Seller / listing pressure",
        "simple": "Listing behavior that may indicate negotiation room (from property facts only).",
    },
    "risk": {
        "title": "Risk cushion",
        "simple": "Higher here means lower screened risk contributing positively to opportunity.",
    },
}
