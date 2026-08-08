"""Parcel-specific, plain-English intelligence briefs — no filler."""

from __future__ import annotations

from typing import Any


def _n(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _money(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"${v:,.0f}"


def build_intelligence_brief(
    *,
    parcel,
    listing,
    score,
    enrichment,
    price: dict,
    land_readouts: dict,
    scenarios_human: list,
    dd_guided: list,
) -> dict[str, Any]:
    acres = _n(parcel.acreage)
    ask = listing.asking_price_usd if listing else None
    state = (parcel.state or "US").upper()
    county = parcel.county or "this county"
    apn = parcel.apn or "no APN on file"
    title = (listing.title if listing else None) or parcel.apn or "This parcel"
    provider = (listing.provider_id if listing else None) or "unknown"
    provider_label = provider.replace("_", " ")
    opp = _n(getattr(score, "opportunity", None), 0) or 0
    risk = _n(getattr(score, "risk", None), 0) or 0
    conf = _n(getattr(score, "confidence", None), 0) or 0
    disc = _n(getattr(score, "asking_discount_pct", None))
    strategy = score.best_strategy.value if score and score.best_strategy else "UNDETERMINED"
    secondary = (
        score.secondary_strategy.value if score and score.secondary_strategy else None
    )
    est = _n(getattr(score, "estimated_value_usd", None))
    readiness = _n(getattr(score, "deal_readiness", None), 0) or 0
    lat = parcel.latitude
    lon = parcel.longitude
    pin = f"{lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else "coordinates incomplete"

    soil = land_readouts.get("soil") or {}
    flood = land_readouts.get("flood") or {}
    wet = land_readouts.get("wetlands") or {}
    tx = land_readouts.get("transmission") or {}

    soil_n = {}
    flood_n = {}
    wet_n = {}
    infra_n = {}
    if enrichment:
        if enrichment.soil:
            soil_n = enrichment.soil.normalized or enrichment.soil.value or {}
        if enrichment.flood:
            flood_n = enrichment.flood.normalized or enrichment.flood.value or {}
        if enrichment.wetlands:
            wet_n = enrichment.wetlands.normalized or enrichment.wetlands.value or {}
        if enrichment.infrastructure:
            infra_n = enrichment.infrastructure.normalized or enrichment.infrastructure.value or {}

    prime = _n(soil_n.get("prime_farmland_pct"))
    farm_class = soil_n.get("farmland_classification")
    flood_pct = _n(flood_n.get("flood_zone_pct"))
    flood_zone = flood_n.get("zone")
    wet_pct = _n(wet_n.get("wetland_pct"))
    tx_m = _n(infra_n.get("nearest_transmission_m"))

    auction = None
    if enrichment and enrichment.comps:
        auction = (enrichment.comps.normalized or {}).get("auction_path")
    if not isinstance(auction, dict):
        auction = None

    ppa = (ask / acres) if ask and acres and acres > 0 else None
    model_ppa = (est / acres) if est and acres and acres > 0 else None
    settle = _n(auction.get("expected_settle_usd")) if auction else None

    # ---- Why this opportunity ----
    why: list[dict[str, str]] = []
    if auction and ask is not None and est is not None:
        settle_v = settle or ask
        gap = est - settle_v
        why.append(
            {
                "headline": (
                    f"Auction math: {_money(ask)} opener → ~{_money(settle_v)} settle "
                    f"vs {_money(est)} model"
                ),
                "detail": (
                    f"On {apn} in {county}, {state}, do not treat {_money(ask)} as the buy price — "
                    f"tax/auction openers are floors. Screening applies ~{auction.get('bid_inflation_mult_base', 0):.1f}× "
                    f"typical bid-up (band {auction.get('bid_inflation_mult_low', 0):.1f}×–"
                    f"{auction.get('bid_inflation_mult_high', 0):.1f}×) → likely clear near {_money(settle_v)}. "
                    f"Settle-adjusted gap vs model ≈ {_money(abs(gap))} "
                    f"({abs(disc):.0f}% {'under' if (disc or 0) < 0 else 'over'}). "
                    f"Teaser opener looked {abs(auction.get('opener_discount_pct') or 0):.0f}% under model — that was anchoring, not edge."
                ),
            }
        )
    elif disc is not None and ask is not None and est is not None:
        gap = est - ask
        why.append(
            {
                "headline": (
                    f"Model gap: ask {_money(ask)} vs screen {_money(est)} "
                    f"({abs(disc):.0f}% {'under' if disc < 0 else 'over'})"
                ),
                "detail": (
                    f"On {apn} in {county}, {state}, the public ask is {_money(ask)}"
                    + (f" ({_money(ppa)}/ac)" if ppa else "")
                    + f" while the screening base is {_money(est)}"
                    + (f" ({_money(model_ppa)}/ac)" if model_ppa else "")
                    + f". Dollar gap ≈ {_money(abs(gap))}. "
                    + (
                        "That is the economic hook — still verify with a local broker, title, and a site walk before you treat it as equity."
                        if disc < -8
                        else "Gap is modest; treat price as one input, not the thesis."
                    )
                ),
            }
        )
    elif ask is None:
        size_bit = f"{acres:,.2f} acres" if acres is not None else "this parcel"
        why.append(
            {
                "headline": f"No retail ask — {provider_label} process pricing",
                "detail": (
                    f"{title[:90]} comes from {provider_label} with no Zillow-style list price. "
                    f"Screening value sits near {_money(est)} for {size_bit} at {pin}. "
                    f"Your edge is process access (agency, auction calendar, surplus office), "
                    f"not outbidding a retail crowd."
                ),
            }
        )
    if acres is not None:
        if acres >= 80:
            why.append(
                {
                    "headline": f"Institutional-scale tract: {acres:,.1f} acres",
                    "detail": (
                        f"At {acres:,.1f} ac in {county}, {state}, this clears most farmland / land-bank / "
                        f"energy minimums. One parcel can carry a multi-year hold without assembling neighbors."
                    ),
                }
            )
        elif acres >= 10:
            why.append(
                {
                    "headline": f"Workable rural scale: {acres:,.1f} acres",
                    "detail": (
                        f"{acres:,.1f} acres is enough for cash-rent, recreation lease, or a land-bank pad "
                        f"in {county}. Too big for a leftover city lot thesis; too small to ignore access and tillable %."
                    ),
                }
            )
        elif acres < 2:
            why.append(
                {
                    "headline": f"Small lot ({acres:,.2f} ac) — urban / tax-sale style play",
                    "detail": (
                        f"Size points to assemble, side-lot, flip, or hold — not row-crop. "
                        f"Model value uses urban residual logic, not ag $/acre priors. "
                        f"APN {apn}."
                    ),
                }
            )
    if strategy != "UNDETERMINED":
        size_clause = f"size ({acres:,.2f} ac), " if acres is not None else ""
        second_clause = (
            f", with {secondary.replace('_', ' ').title()} second" if secondary else ""
        )
        why.append(
            {
                "headline": f"Best screen: {strategy.replace('_', ' ').title()}",
                "detail": (
                    f"Strategy matrix picks {strategy.replace('_', ' ').title()} first"
                    f"{second_clause} for this parcel’s {size_clause}"
                    f"location ({county}, {state}), and constraint screens. "
                    f"Open the rating breakdown for the scored mix — secondary uses can still matter on exit."
                ),
            }
        )
    if provider == "public_tax_sale":
        why.append(
            {
                "headline": "Distressed / tax-sale / land-bank channel",
                "detail": (
                    f"Inventory is from a public tax-sale, foreclosure, or land-bank layer in {county}. "
                    f"These often clear below retail because of title risk, occupancy unknowns, and auction friction — "
                    f"which is also why diligence must be heavier than an MLS farm listing."
                ),
            }
        )
    elif provider == "blm_lpad":
        why.append(
            {
                "headline": "Federal BLM disposal tract (not MLS)",
                "detail": (
                    f"Sale/exchange follows BLM / FLPMA process at {pin}. Timelines, appraisals, and possible "
                    f"use conditions apply. Fewer private buyers track LPAD — that can be the edge if you can wait."
                ),
            }
        )
    elif provider == "public_surplus":
        why.append(
            {
                "headline": "Government surplus / public disposal inventory",
                "detail": (
                    f"This is a municipal or county surplus-style parcel in {county}, {state}. "
                    f"Procurement rules and surplus calendars matter more than Redfin traffic."
                ),
            }
        )
    if prime is not None and prime >= 40 and acres and acres >= 10:
        why.append(
            {
                "headline": f"Soil screen shows ~{prime:.0f}% prime farmland",
                "detail": (
                    f"USDA SSURGO mark at this geometry: {farm_class or 'class n/a'}, ~{prime:.0f}% prime. "
                    f"For a {acres:,.1f}-ac position that supports cash-rent and resale to ag buyers — "
                    f"still pull a soil test before you underwrite yield."
                ),
            }
        )
    if tx_m is not None and tx_m < 8000 and (strategy == "ENERGY" or (acres or 0) >= 20):
        why.append(
            {
                "headline": f"Transmission screen ~{tx_m/1609:.1f} mi away",
                "detail": (
                    f"HIFLD mark puts nearest mapped line about {tx_m:,.0f} m from the pin. "
                    f"That is a screening hint for energy optionality — not queue position, "
                    f"interconnection rights, or substation capacity."
                ),
            }
        )
    if conf < 45:
        why.append(
            {
                "headline": f"Evidence file still thin (confidence {conf:.0f}/100)",
                "detail": (
                    f"LandSignal {opp:.0f}/100 is a screen, not a proven gem. "
                    f"Missing map layers or listing facts lower confidence on purpose. "
                    f"Use the due-diligence checklist before any bid on {apn}."
                ),
            }
        )
    if not why:
        why.append(
            {
                "headline": "Passes stage-1 screens",
                "detail": (
                    f"At least one investment strategy remains open after automated gates for {apn} "
                    f"in {county}, {state}."
                ),
            }
        )

    # ---- Why still available (multi-hypothesis + buyer psychology) ----
    still: list[dict[str, str]] = []
    narratives = (enrichment.narratives if enrichment else None) or {}
    unsold = (narratives.get("why_unsold") if isinstance(narratives, dict) else None) or {}
    hyps = (unsold.get("hypotheses") if isinstance(unsold, dict) else None) or []
    if not hyps and isinstance(unsold, dict) and unsold.get("most_likely"):
        hyps = [unsold["most_likely"]]
    for h in hyps[:5]:
        evid = "; ".join(str(e) for e in (h.get("evidence") or [])[:3])
        psych = h.get("psychology")
        detail = evid or f"Buyer friction on {apn}."
        if psych:
            detail = f"{detail} Buyer psychology: {psych}"
        still.append(
            {
                "headline": str(h.get("reason") or "Likely friction for other buyers"),
                "detail": detail,
            }
        )
    if auction and ask is not None:
        still.insert(
            0,
            {
                "headline": "Teaser opener attracts browsers; settle price filters capital",
                "detail": (
                    f"Published {_money(ask)} looks like a steal next to {_money(est)} model value — "
                    f"until you price ~{_money(settle)} expected clear. "
                    f"Pros underwrite bid-up; novices get anchored. That gap in sophistication is why "
                    f"the parcel can sit through a full auction calendar."
                ),
            },
        )
    if flood_pct is not None and flood_pct >= 20:
        still.append(
            {
                "headline": f"Flood screen ~{flood_pct:.0f}% (zone {flood_zone or 'n/a'})",
                "detail": (
                    f"FEMA overlap at {pin} looks material. Cash-flow and bank buyers often step back, "
                    f"which can leave room for a patient buyer who prices insurance, fill, and elevation correctly."
                ),
            }
        )
    if wet_pct is not None and wet_pct >= 15:
        deed_bit = (
            f"Buildable/tillable acres may be well below deeded {acres:,.2f} ac. "
            if acres is not None
            else ""
        )
        still.append(
            {
                "headline": f"Wetlands screen ~{wet_pct:.0f}% of the parcel",
                "detail": (
                    f"{deed_bit}Speculative subdividers often pass; ag or recreation buyers may still "
                    f"underwrite it after a delineation in {county}."
                ),
            }
        )
    if ask is None:
        still.append(
            {
                "headline": "Harder for retail shoppers to find / price",
                "detail": (
                    f"Without a consumer ask, casual buyers never see {apn}. "
                    f"“Available” often means process not finished — not automatically bad land."
                ),
            }
        )
    if risk >= 55:
        still.append(
            {
                "headline": f"Screened risk elevated ({risk:.0f}/100)",
                "detail": (
                    f"Risk {risk:.0f} usually means flood/wetland/access/data gaps on this file. "
                    f"That scares fast money and is exactly what a careful underwriter can turn into a negotiated price."
                ),
            }
        )
    if provider in ("public_tax_sale", "public_surplus") and readiness < 55:
        still.append(
            {
                "headline": f"Deal readiness only {readiness:.0f}/100 — homework unfinished",
                "detail": (
                    f"Title, access, and occupancy are not desktop-certified for this {provider_label} parcel. "
                    f"Many institutions won’t bid until those are clean — which is why it can still be sitting."
                ),
            }
        )
    if not still:
        still.append(
            {
                "headline": "No single smoking-gun reason in the public file",
                "detail": (
                    f"Public layers on {apn} don’t show a clear poison pill at {pin}. "
                    f"It may be early in marketing, poorly syndicated, or waiting on an agency/auction calendar."
                ),
            }
        )

    # ---- Land card addenda (parcel-specific) ----
    soil_extra = [
        f"Parcel {apn} · {county}, {state} · {acres:,.2f} ac" if acres else f"Parcel {apn} · {county}, {state}",
        f"Pin {pin}",
    ]
    if farm_class:
        soil_extra.append(f"USDA class mark: {farm_class}")
    if prime is not None:
        soil_extra.append(f"Prime farmland screen: {prime:.0f}% of sampled area")
    else:
        soil_extra.append(
            "Prime share not confirmed yet — open this page after enrichment or order SSURGO/soil test."
        )
    if acres and acres >= 20:
        soil_extra.append(
            f"At {acres:,.0f} acres, soil class drives rent and resale more than curb appeal in {state}."
        )

    flood_extra = [
        f"Pin {pin}",
        f"FEMA overlap screen: {flood_pct:.0f}%" if flood_pct is not None else "FEMA overlap not confirmed at this pin yet",
        f"Zone mark: {flood_zone}" if flood_zone else "Zone letter not returned on point sample",
        "Not an elevation certificate — lender may still require one.",
    ]
    wet_extra = [
        f"Wetland share screen: {wet_pct:.0f}%" if wet_pct is not None else "NWI wetland share not confirmed yet",
        f"If your plan needs grading in {county}, budget a delineation before you lock a close date on {apn}.",
        f"Deeded acres {acres:,.2f} ≠ tillable/buildable acres when wetlands bite." if acres else "Confirm usable acres on site.",
    ]
    tx_extra = [
        f"Nearest mapped transmission: {tx_m:,.0f} m ({tx_m/1609:.1f} mi)" if tx_m is not None else "Transmission distance not confirmed yet",
        "Energy thesis only: proximity ≠ interconnection rights, queue position, or substation capacity.",
        f"Strategy screen currently emphasizes {strategy.replace('_', ' ').title()}.",
    ]

    # ---- Scenarios ----
    scen_notes = []
    for s in scenarios_human[:3]:
        case = s.get("case_label") or s.get("case_type")
        irr = s.get("irr")
        summary = s.get("plain_english")
        if acres and acres < 5:
            summary = (
                f"{case}: farmland IRR math is a weak fit for a {acres:,.2f}-ac urban/tax-sale lot. "
                f"Treat these numbers as a sanity check only — underwrite assemble/flip or lease instead."
            )
        elif irr is not None and ask:
            summary = (
                f"{case} for {acres:,.1f} ac in {county}: if you bought near {_money(ask)} and "
                f"cash-rent assumptions hold, screen IRR ≈ {float(irr)*100:.1f}%/yr. "
                f"Pull local rent comps before you believe it."
            )
        scen_notes.append(
            {
                "case": case,
                "summary": summary,
                "numbers": {
                    "noi": s.get("noi_display"),
                    "irr": s.get("irr_display"),
                    "npv": s.get("npv_display"),
                    "breakeven": s.get("breakeven_display"),
                },
            }
        )
    if not scen_notes:
        scen_notes.append(
            {
                "case": "Not modeled yet",
                "summary": (
                    f"Farmland IRR screens need rent/yield assumptions. For this {state} parcel ({apn}), "
                    f"open manual diligence and pull local cash-rent comps before trusting an IRR."
                ),
                "numbers": {},
            }
        )

    # ---- DD ----
    dd_focus = []
    for item in dd_guided[:8]:
        label = str(item.get("label") or "Diligence item")
        why_m = str(item.get("why_it_matters") or "")
        how = str(item.get("how_to_start") or "")
        parcel_note = (
            f"On {title[:70]} ({apn}) in {county}, {state}"
            + (f", {acres:.2f} ac" if acres else "")
            + f", at {pin}: {why_m}"
        )
        if "title" in label.lower() and provider in ("public_tax_sale", "blm_lpad"):
            how = (
                f"{how} For this {provider_label} file, start with the county treasurer / clerk "
                f"or BLM field office and ask specifically about {apn}."
            )
        if "flood" in label.lower() and flood_pct is not None:
            parcel_note += f" Desktop flood screen already shows ~{flood_pct:.0f}% overlap."
        dd_focus.append({**item, "parcel_note": parcel_note, "how_to_start": how})

    primary_cta = None
    if listing and listing.source_url:
        primary_cta = {
            "label": "Open official listing / agency page",
            "url": listing.source_url,
        }
    elif provider == "blm_lpad":
        primary_cta = {
            "label": "BLM land tenure / how to acquire",
            "url": "https://www.blm.gov/programs/lands-and-realty/land-tenure",
        }
    elif provider == "public_tax_sale" and state:
        primary_cta = {
            "label": f"Search {county} {state} treasurer / tax sale",
            "url": f"https://www.google.com/search?q={county}+{state}+tax+sale+treasurer+{apn}".replace(" ", "+"),
        }

    return {
        "why_opportunity": why,
        "why_still_available": still,
        "soil_addendum": soil_extra,
        "flood_addendum": flood_extra,
        "wetlands_addendum": wet_extra,
        "transmission_addendum": tx_extra,
        "scenario_cards": scen_notes,
        "dd_focus": dd_focus,
        "score_story": {
            "landsignal": (
                f"LandSignal {opp:.0f}/100 is the weighted screen of price, land quality, options, "
                f"growth, and risk for {apn} in {county}, {state}. "
                + (
                    f"Price-vs-value is doing heavy lifting ({disc:.0f}% vs model)."
                    if disc is not None and disc < -10
                    else "No single category should be read alone — open each rating bar."
                )
            ),
            "risk": (
                f"Risk {risk:.0f}/100 is the desktop trouble score (flood, wetlands, thin data, access) "
                f"at {pin}. "
                + ("Lower is calmer." if risk < 40 else "Budget more diligence before you bid.")
            ),
            "confidence": (
                f"Confidence {conf:.0f}/100 is how complete the evidence file is — not how “good” the land is. "
                f"Missing layers lower confidence instead of inventing green checks."
            ),
        },
        "primary_cta": primary_cta,
        "watch_hint": (
            "Add to watchlist to track LandSignal, risk, confidence, price, and status. "
            "Set your email under My criteria → Watchlist email sync to receive change notices."
        ),
    }
