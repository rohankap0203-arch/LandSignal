from __future__ import annotations

from typing import Any


def why_still_unsold(ctx: dict[str, Any]) -> dict[str, Any]:
    """Evidence-backed + buyer-psychology hypotheses for why a parcel remains available."""
    hypotheses: list[dict[str, Any]] = []
    dom = ctx.get("days_on_market")
    wetland = ctx.get("wetland_pct")
    flood = ctx.get("flood_zone_pct")
    access = ctx.get("legal_access_confidence")
    discount = ctx.get("asking_discount_pct")
    liq = ctx.get("liquidity_score")
    ask = ctx.get("asking_price_usd")
    provider = ctx.get("provider_id")
    auction = ctx.get("auction_path") if isinstance(ctx.get("auction_path"), dict) else None
    acres = ctx.get("acreage")
    conf = ctx.get("confidence")
    risk = ctx.get("risk")
    readiness = ctx.get("deal_readiness")
    county = ctx.get("county") or "this county"
    state = (ctx.get("state") or "US").upper()
    strategy = ctx.get("best_strategy")

    if provider == "blm_lpad":
        hypotheses.append(
            {
                "reason": "Federal disposal process — not a retail listing cycle",
                "evidence": [
                    "BLM LPAD / FLPMA path filters out MLS shoppers and most retail investors",
                    "Timelines and appraisal rules scare buyers who want a 30-day close",
                ],
                "likelihood": 0.88,
                "psychology": "Status-quo buyers ignore anything that isn’t on Zillow.",
            }
        )
    if provider == "public_tax_sale":
        hypotheses.append(
            {
                "reason": "Tax-sale / distress channel filters casual capital",
                "evidence": [
                    f"Public tax-sale or land-bank inventory in {county}, {state}",
                    "Title, occupancy, and auction rules push retail and many banks aside",
                ],
                "likelihood": 0.8,
                "psychology": "Fear of “what am I actually buying?” keeps non-specialists out.",
            }
        )
    if auction and ask is not None:
        opener = auction.get("opening_bid_usd")
        settle = auction.get("expected_settle_usd")
        hypotheses.append(
            {
                "reason": "Opening bid looks cheap — serious buyers price the settle, not the teaser",
                "evidence": [
                    f"Published opener ${opener:,.0f}; screening settle ~${settle:,.0f}",
                    auction.get("note", "Bid-up typical on contested tax sales")[:180],
                ],
                "likelihood": 0.78,
                "psychology": "Anchoring bias: novices chase the opener; pros underwrite clearing price.",
            }
        )
    if ask is None:
        hypotheses.append(
            {
                "reason": "No published asking price — price discovery is work",
                "evidence": [
                    "Market cannot clear on a Zillow-style quote",
                    "Buyers must engage an agency, auctioneer, or surplus office",
                ],
                "likelihood": 0.72,
                "psychology": "Ambiguity aversion: people skip assets they can’t price in 10 seconds.",
            }
        )
    if wetland is not None and wetland > 20:
        hypotheses.append(
            {
                "reason": f"Wetlands screen (~{wetland:.0f}%) shrinks usable acres",
                "evidence": [
                    f"NWI wetland share ~{wetland:.0f}% — deeded acres ≠ tillable/buildable",
                    "Subdividers and many lenders step back until delineation",
                ],
                "likelihood": 0.66 if wetland > 35 else 0.52,
                "psychology": "Loss framing: buyers overweight the unusable slice.",
            }
        )
    if flood is not None and flood > 15:
        hypotheses.append(
            {
                "reason": f"Flood screen (~{flood:.0f}%) cuts the financed buyer pool",
                "evidence": [
                    f"FEMA overlap ~{flood:.0f}% at the pin",
                    "Insurance and bank underwriting get picky — cash buyers remain",
                ],
                "likelihood": 0.62 if flood > 30 else 0.48,
                "psychology": "Insurance anxiety feels larger than the actuarial cost for many buyers.",
            }
        )
    if access is not None and access < 55:
        hypotheses.append(
            {
                "reason": "Legal access not desktop-certified",
                "evidence": [
                    f"Access confidence {access:.0f}/100 — not deed/easement verified",
                    "Institutions often won’t bid until a surveyor or title desk clears the path",
                ],
                "likelihood": 0.74 if access < 40 else 0.55,
                "psychology": "Landlocked fear is a hard stop even when access is probably fine.",
            }
        )
    if discount is not None and discount > 12:
        hypotheses.append(
            {
                "reason": "Still looks expensive vs the screening model",
                "evidence": [f"Comparison price sits {discount:.1f}% above model base"],
                "likelihood": 0.58,
                "psychology": "Nobody wants to be the person who overpays in public.",
            }
        )
    if discount is not None and discount < -25 and auction:
        hypotheses.append(
            {
                "reason": "Even after bid-up, edge remains — but diligence load is high",
                "evidence": [
                    f"Settle-adjusted discount ~{discount:.1f}% vs model",
                    f"Deal readiness {readiness:.0f}/100" if readiness is not None else "Readiness incomplete",
                ],
                "likelihood": 0.5,
                "psychology": "Pros wait for cleaner files; patience is the filter.",
            }
        )
    if liq is not None and liq < 45:
        hypotheses.append(
            {
                "reason": "Thin local buyer pool / low liquidity",
                "evidence": [f"Liquidity screen {liq:.0f}/100 in {county}, {state}"],
                "likelihood": 0.55,
                "psychology": "Exit-risk salience: “Can I sell this later?” kills bids today.",
            }
        )
    if conf is not None and conf < 45:
        hypotheses.append(
            {
                "reason": "Thin public evidence file — uncertainty tax",
                "evidence": [
                    f"Confidence {conf:.0f}/100 means missing layers or listing facts",
                    "Underwriters discount hard when soils/flood/title are incomplete",
                ],
                "likelihood": 0.6,
                "psychology": "Uncertainty feels like risk; incomplete files look “haunted.”",
            }
        )
    if risk is not None and risk >= 55:
        hypotheses.append(
            {
                "reason": f"Elevated desktop risk ({risk:.0f}/100) scares fast money",
                "evidence": ["Flood, wetlands, access, or data gaps inflate the trouble score"],
                "likelihood": 0.57,
                "psychology": "Negativity bias: one red flag outweighs three green ones.",
            }
        )
    if acres is not None and acres < 1.0 and provider == "public_tax_sale":
        hypotheses.append(
            {
                "reason": "Tiny lot — only assemble / side-lot buyers care",
                "evidence": [
                    f"{acres:.2f} acres is below most farmland or energy screens",
                    "Retail land tourists skip micro lots even when the math works for neighbors",
                ],
                "likelihood": 0.63,
                "psychology": "Category mismatch: shoppers looking for ‘land’ ignore city scraps.",
            }
        )
    if acres is not None and acres >= 200 and provider == "blm_lpad":
        hypotheses.append(
            {
                "reason": "Scale intimidates small capital; process intimidates big capital",
                "evidence": [
                    f"{acres:,.0f} acres needs real equity and patience",
                    "Federal process + large ticket = narrow intersection of capable buyers",
                ],
                "likelihood": 0.7,
                "psychology": "Capability gap: most browsers can’t underwrite or fund it.",
            }
        )
    if strategy == "ENERGY":
        hypotheses.append(
            {
                "reason": "Energy thesis is optional — most buyers don’t underwrite interconnection",
                "evidence": [
                    "Solar/transmission screens need specialist diligence",
                    "Retail land buyers won’t pay for a queue they don’t understand",
                ],
                "likelihood": 0.48,
                "psychology": "Expertise barrier: if you can’t explain ISO queue, you don’t bid.",
            }
        )
    if dom is not None and dom > 180 and discount is not None and discount < -10:
        hypotheses.append(
            {
                "reason": "Long marketing / process time — stigma or reset economics",
                "evidence": [f"DOM {dom} with settle-adjusted model gap {discount:.1f}%"],
                "likelihood": 0.45,
                "psychology": "Stale listing stigma: ‘If it were good, someone would have taken it.’",
            }
        )

    hypotheses.sort(key=lambda h: -h["likelihood"])
    top = (
        hypotheses[0]
        if hypotheses
        else {
            "reason": "No single smoking-gun reason in the public file",
            "evidence": ["May be early in process, poorly syndicated, or waiting on a calendar"],
            "likelihood": 0.35,
            "psychology": "Silence isn’t a defect — sometimes it’s just distribution.",
        }
    )
    return {"most_likely": top, "hypotheses": hypotheses[:8]}


def hidden_value_score(ctx: dict[str, Any]) -> dict[str, Any]:
    score = 40.0
    evidence: list[str] = []
    if ctx.get("provider_id") == "blm_lpad":
        score += 15
        evidence.append("Federal disposal inventory often under-marketed to private capital")
    auction = ctx.get("auction_path") if isinstance(ctx.get("auction_path"), dict) else None
    disc = ctx.get("asking_discount_pct") or 0
    if auction and disc < -12:
        score += 12
        evidence.append("Settle-adjusted gap still favors buyer after typical bid-up")
    elif disc < -15:
        score += 20
        evidence.append("Wide comparison price vs model gap")
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
