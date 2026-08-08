from __future__ import annotations

from typing import Any


def why_still_unsold(ctx: dict[str, Any]) -> dict[str, Any]:
    """Generate evidence-backed hypotheses for why an opportunity remains available."""
    hypotheses: list[dict[str, Any]] = []
    dom = ctx.get("days_on_market")
    wetland = ctx.get("wetland_pct")
    flood = ctx.get("flood_zone_pct")
    access = ctx.get("legal_access_confidence")
    discount = ctx.get("asking_discount_pct")
    liq = ctx.get("liquidity_score")
    ask = ctx.get("asking_price_usd")
    provider = ctx.get("provider_id")

    if provider == "blm_lpad":
        hypotheses.append(
            {
                "reason": "Federal disposal process / not conventional retail listing",
                "evidence": ["Source is BLM LPAD — acquisition follows FLPMA disposal rules, not MLS offer cycles"],
                "likelihood": 0.85,
            }
        )
    if ask is None:
        hypotheses.append(
            {
                "reason": "No published asking price",
                "evidence": ["Market cannot clear on price discovery without a quote"],
                "likelihood": 0.7,
            }
        )
    if wetland is not None and wetland > 35:
        hypotheses.append(
            {
                "reason": "Material wetlands constrain developable / tillable area",
                "evidence": [f"Wetland screening ~{wetland}% of parcel"],
                "likelihood": 0.65,
            }
        )
    if flood is not None and flood > 30:
        hypotheses.append(
            {
                "reason": "Flood exposure reduces buyer pool / financing",
                "evidence": [f"Flood screening ~{flood}%"],
                "likelihood": 0.6,
            }
        )
    if access is not None and access < 45:
        hypotheses.append(
            {
                "reason": "Access uncertainty (legal access not verified)",
                "evidence": [f"Legal access confidence {access} — not deed-verified"],
                "likelihood": 0.7,
            }
        )
    if discount is not None and discount > 15:
        hypotheses.append(
            {
                "reason": "Historically overpriced vs model",
                "evidence": [f"Ask premium {discount:.1f}% vs model base"],
                "likelihood": 0.55,
            }
        )
    if liq is not None and liq < 40:
        hypotheses.append(
            {
                "reason": "Local market illiquidity / thin buyer pool",
                "evidence": [f"Liquidity score {liq}"],
                "likelihood": 0.5,
            }
        )
    if dom is not None and dom > 180 and discount is not None and discount < -10:
        hypotheses.append(
            {
                "reason": "Recently became attractive after economics changed",
                "evidence": [f"DOM {dom} with model discount {discount:.1f}%"],
                "likelihood": 0.45,
            }
        )

    hypotheses.sort(key=lambda h: -h["likelihood"])
    top = hypotheses[0] if hypotheses else {
        "reason": "Insufficient evidence to explain availability",
        "evidence": ["Missing listing psychology and/or constraint layers"],
        "likelihood": 0.3,
    }
    return {"most_likely": top, "hypotheses": hypotheses[:6]}


def hidden_value_score(ctx: dict[str, Any]) -> dict[str, Any]:
    score = 40.0
    evidence: list[str] = []
    if ctx.get("provider_id") == "blm_lpad":
        score += 15
        evidence.append("Federal disposal inventory often under-marketed to private capital")
    if (ctx.get("asking_discount_pct") or 0) < -15:
        score += 20
        evidence.append("Wide ask vs model gap")
    if (ctx.get("path_of_growth_score") or 0) >= 70 and (ctx.get("zoning_development_friendly") or 0) < 40:
        score += 10
        evidence.append("Growth signal without marketed development narrative")
    if (ctx.get("nearest_transmission_m") or 1e12) < 5000 and (ctx.get("solar_irradiance_score") or 0) >= 60:
        score += 12
        evidence.append("Energy optionality not necessarily in listing thesis")
    if (ctx.get("prime_farmland_pct") or 0) >= 70 and (ctx.get("asking_price_usd") is None):
        score += 8
        evidence.append("Strong ag quality without retail pricing noise")
    score = max(0, min(100, score))
    return {"hidden_value_score": round(score, 1), "evidence": evidence}
