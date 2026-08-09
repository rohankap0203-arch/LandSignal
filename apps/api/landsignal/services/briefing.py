"""Parcel-specific, plain-English intelligence briefs — no filler."""

from __future__ import annotations

from landsignal.services.voice import place_phrase, strip_apn_mentions, this_property

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
    apn = parcel.apn or ""
    prop = this_property(parcel, listing, with_place=True, with_acres=True)
    prop_short = this_property(parcel, listing)
    from landsignal.services.voice import display_title as _display_title
    title = _display_title(parcel, listing)
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
                    f"Starting bid {_money(ask)} · likely finish ~{_money(settle_v)} · "
                    f"our value {_money(est)}"
                ),
                "detail": (
                    f"On {prop}, the {_money(ask)} number is only the opening bid — "
                    f"not what you should expect to pay. Similar auctions usually climb about "
                    f"{auction.get('bid_inflation_mult_base', 0):.1f}× "
                    f"(rough range {auction.get('bid_inflation_mult_low', 0):.1f}×–"
                    f"{auction.get('bid_inflation_mult_high', 0):.1f}×), so a realistic finish is near "
                    f"{_money(settle_v)}. Compared with our estimated value {_money(est)}, that is about "
                    f"{_money(abs(gap))} "
                    f"({abs(disc):.0f}% {'cheaper' if (disc or 0) < 0 else 'more expensive'}). "
                    f"The opener looked {abs(auction.get('opener_discount_pct') or 0):.0f}% under our value — "
                    f"that teaser is normal for auctions, not a guaranteed bargain."
                ),
            }
        )
    elif disc is not None and ask is not None and est is not None:
        gap = est - ask
        why.append(
            {
                "headline": (
                    f"Listed at {_money(ask)} · we think it’s worth {_money(est)} "
                    f"({abs(disc):.0f}% {'cheaper' if disc < 0 else 'pricier'} than our estimate)"
                ),
                "detail": (
                    f"On {prop}, the public price is {_money(ask)}"
                    + (f" ({_money(ppa)} per acre)" if ppa else "")
                    + f". Our estimate for this land is {_money(est)}"
                    + (f" ({_money(model_ppa)} per acre)" if model_ppa else "")
                    + f" — a gap of about {_money(abs(gap))}. "
                    + (
                        "That price difference is the main reason this listing ranks high — still confirm with a local broker, title search, and a site walk."
                        if disc < -8
                        else "The price gap is small, so treat price as one factor among several before you bid."
                    )
                ),
            }
        )
    elif ask is None:
        size_bit = f"{acres:,.2f} acres" if acres is not None else "this parcel"
        why.append(
            {
                "headline": f"No public sale price yet · {provider_label.replace('_', ' ')}",
                "detail": (
                    f"{title[:90]} is on a {provider_label.replace('_', ' ')} feed with no consumer-style asking price. "
                    f"We estimate about {_money(est)} for {size_bit} at map pin {pin}. "
                    f"Your advantage is knowing how to buy through the agency / auction / surplus process — "
                    f"not racing a retail listing crowd."
                ),
            }
        )
    if acres is not None:
        if acres >= 80:
            why.append(
                {
                    "headline": f"Large tract: {acres:,.1f} acres",
                    "detail": (
                        f"At {acres:,.1f} acres in {county}, {state}, this is big enough for farming, holding, "
                        f"or energy-style uses without buying neighboring lots."
                    ),
                }
            )
        elif acres >= 10:
            why.append(
                {
                    "headline": f"Mid-size rural tract: {acres:,.1f} acres",
                    "detail": (
                        f"{acres:,.1f} acres in {county} is enough to rent to a farmer, lease for recreation, "
                        f"or hold. Bigger than a city lot, small enough that road access and usable acres still matter a lot."
                    ),
                }
            )
        elif acres < 2:
            why.append(
                {
                    "headline": f"Small lot ({acres:,.2f} acres) — city / tax-sale style",
                    "detail": (
                        f"This size usually fits assembling with a neighbor, flipping, or holding — not growing crops. "
                        f"Our value estimate uses small-lot logic, not farm-per-acre pricing. Keep the county parcel ID handy for the assessor lookup."
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
                "headline": f"Best use we see: {strategy.replace('_', ' ').title()}",
                "detail": (
                    f"For this parcel’s {size_clause}location ({county}, {state}), "
                    f"the strongest fit is {strategy.replace('_', ' ').title()}"
                    f"{second_clause}. "
                    f"Open the score breakdown below for the full mix — a second use can still help when you sell later."
                ),
            }
        )
    if provider == "public_tax_sale":
        why.append(
            {
                "headline": "County tax sale / land-bank listing",
                "detail": (
                    f"This came from a public tax sale, foreclosure, or land-bank list in {county}. "
                    f"These often sell below normal asking prices because of title questions, unknown occupants, "
                    f"and auction paperwork — so check those carefully before you bid."
                ),
            }
        )
    elif provider == "blm_lpad":
        why.append(
            {
                "headline": "Federal BLM land (not a normal MLS listing)",
                "detail": (
                    f"Buying follows the BLM government process at map pin {pin}. Expect longer timelines, "
                    f"an appraisal step, and possible use rules. Fewer private buyers watch this channel — "
                    f"that can help if you can wait."
                ),
            }
        )
    elif provider == "public_surplus":
        why.append(
            {
                "headline": "City or county surplus land",
                "detail": (
                    f"This is surplus-style public land in {county}, {state}. "
                    f"Government sale rules and calendars matter more than browsing sites like Zillow."
                ),
            }
        )
    if prime is not None and prime >= 40 and acres and acres >= 10:
        why.append(
            {
                "headline": f"About {prime:.0f}% of the soil looks like prime farmland",
                "detail": (
                    f"USDA soil data for this shape: class {farm_class or 'not listed'}, about {prime:.0f}% prime. "
                    f"On {acres:,.1f} acres that helps cash rent and selling later to a farmer — "
                    f"still order a soil test before counting on crop yield."
                ),
            }
        )
    if tx_m is not None and tx_m < 8000 and (strategy == "ENERGY" or (acres or 0) >= 20):
        why.append(
            {
                "headline": f"Power line about {tx_m/1609:.1f} miles away",
                "detail": (
                    f"The nearest mapped transmission line is about {tx_m:,.0f} meters from this pin. "
                    f"That is only a first clue for energy uses — it does not mean you can connect, "
                    f"or that a substation has spare capacity."
                ),
            }
        )
    if conf < 45:
        why.append(
            {
                "headline": f"File is still incomplete ({conf:.0f}/100 how-complete)",
                "detail": (
                    f"Opportunity score {opp:.0f}/100 is a first look, not proof this is a great buy. "
                    f"Missing maps or listing facts lower the completeness score on purpose. "
                    f"Use the checklist below before bidding on this property."
                ),
            }
        )
    if not why:
        why.append(
            {
                "headline": "Passes the first automated checks",
                "detail": (
                    f"At least one use still looks possible for {prop} "
                    f"after the first automated gates."
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
        detail = evid or f"Buyer friction on this property."
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
                "headline": "Low starting bid draws browsers; real finish price weeds them out",
                "detail": (
                    f"The published {_money(ask)} looks cheap next to our {_money(est)} estimate — "
                    f"until you plan on a likely finish near {_money(settle)}. "
                    f"Experienced buyers already bake that climb into their max bid; casual bidders often don’t. "
                    f"That mismatch is one reason parcels can sit through a whole auction cycle."
                ),
            },
        )
    if flood_pct is not None and flood_pct >= 20:
        still.append(
            {
                "headline": f"About {flood_pct:.0f}% flood overlap on the map (zone {flood_zone or 'not listed'})",
                "detail": (
                    f"FEMA data at pin {pin} shows meaningful flood overlap. Banks and cash-flow buyers often pass, "
                    f"which can leave room for someone who prices insurance, fill, and elevation correctly."
                ),
            }
        )
    if wet_pct is not None and wet_pct >= 15:
        deed_bit = (
            f"Usable acres may be well below the deeded {acres:,.2f} acres. "
            if acres is not None
            else ""
        )
        still.append(
            {
                "headline": f"About {wet_pct:.0f}% of the parcel looks like wetlands",
                "detail": (
                    f"{deed_bit}Quick flip / subdivision buyers often skip these. "
                    f"A farmer or recreation buyer may still want it after a wetland survey in {county}."
                ),
            }
        )
    if ask is None:
        still.append(
            {
                "headline": "Harder for casual buyers to find or price",
                "detail": (
                    f"Without a normal asking price, most shoppers never see this property. "
                    f"“Still available” often means the government / auction process is unfinished — "
                    f"not that the land is automatically bad."
                ),
            }
        )
    if risk >= 55:
        still.append(
            {
                "headline": f"Higher risk on this file ({risk:.0f}/100)",
                "detail": (
                    f"Risk {risk:.0f}/100 usually means flood, wetlands, access issues, or missing data. "
                    f"That scares fast buyers — and can create negotiating room if you do the homework."
                ),
            }
        )
    if provider in ("public_tax_sale", "public_surplus") and readiness < 55:
        still.append(
            {
                "headline": f"Not ready to bid yet ({readiness:.0f}/100 ready-to-pursue)",
                "detail": (
                    f"Title, road access, and whether anyone is on the land are not confirmed yet for this "
                    f"{provider_label.replace('_', ' ')} parcel. Many bigger buyers won’t bid until those are clean — "
                    f"which is why it can still be sitting."
                ),
            }
        )
    if not still:
        still.append(
            {
                "headline": "No single clear red flag in the public file",
                "detail": (
                    f"Public maps on this property don’t show an obvious deal-breaker at pin {pin}. "
                    f"It may be early in marketing, hard to find online, or waiting on an agency / auction date."
                ),
            }
        )

    # ---- Land card addenda (parcel-specific) ----
    soil_extra = [
        f"{prop_short} · {county}, {state} · {acres:,.2f} ac" if acres else f"{prop_short} · {county}, {state}",
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
        f"If your plan needs grading in {county}, budget a delineation before you lock a close date on this property.",
        f"Deeded acres {acres:,.2f} ≠ tillable/buildable acres when wetlands bite." if acres else "Confirm usable acres on site.",
    ]
    tx_extra = [
        f"Nearest mapped transmission: {tx_m:,.0f} m ({tx_m/1609:.1f} mi)" if tx_m is not None else "Transmission distance not confirmed yet",
        "Energy use only: being near a line does not mean you can connect or that the substation has spare capacity.",
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
                f"{case}: yearly farm-return math is a weak fit for a {acres:,.2f}-acre city/tax-sale lot. "
                f"Treat these numbers as a rough check only — think assemble, flip, or lease instead."
            )
        elif irr is not None and ask:
            summary = (
                f"{case} for {acres:,.1f} acres in {county}: if you bought near {_money(ask)} and "
                f"local cash rents hold, a simple return screen shows about {float(irr)*100:.1f}% per year. "
                f"Confirm with local rent comps before you trust it."
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
                    f"Yearly return screens need local rent and yield numbers. For {prop}, "
                    f"pull local cash-rent comps before trusting a percent-per-year figure."
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
            f"On {prop}"
            + (f", {acres:.2f} ac" if acres else "")
            + f", at {pin}: {why_m}"
        )
        if "title" in label.lower() and provider in ("public_tax_sale", "blm_lpad"):
            how = (
                f"{how} For this {provider_label} file, start with the county treasurer / clerk "
                f"or BLM field office and ask specifically about this property (bring the county parcel ID)."
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

    # ---- Institutional return case (acquisition desk style) ----
    entry = settle if settle and settle > 0 else (ask if ask and ask > 0 else None)
    if entry is None and est:
        # Unpriced public inventory: underwrite a process entry below screening mark
        entry = est * (0.62 if provider in ("public_tax_sale", "public_surplus") else 0.85)
    gap_usd = (est - entry) if est and entry else None
    gap_pct = ((gap_usd / entry) * 100.0) if gap_usd is not None and entry else None
    irr_best = None
    for s in scenarios_human[:4]:
        try:
            irr_v = s.get("irr")
            if irr_v is not None:
                irr_best = max(irr_best or -999, float(irr_v))
        except Exception:
            pass
    conviction = (
        "HIGH"
        if opp >= 68 and risk <= 42 and conf >= 40 and (gap_pct is None or gap_pct >= 12)
        else "MEDIUM"
        if opp >= 52 and risk <= 58
        else "WATCH"
    )
    thesis_bullets: list[str] = []
    if entry and est:
        thesis_bullets.append(
            f"Plan to buy near {_money(entry)}. We think this land is worth about {_money(est)}"
            + (f" ({gap_pct:+.0f}% difference)" if gap_pct is not None else "")
            + "."
        )
    if auction and settle:
        thesis_bullets.append(
            f"Ignore the {_money(ask)} starting bid as the real price — auctions like this "
            f"usually finish near {_money(settle)} (about {auction.get('bid_inflation_mult_base', 0):.1f}× the opener)."
        )
    if strategy != "UNDETERMINED":
        strat = strategy.replace("_", " ").title()
        sec = f"; next-best use {secondary.replace('_', ' ').title()}" if secondary else ""
        size = f" on {acres:,.1f} acres in {county}, {state}" if acres is not None else f" in {county}, {state}"
        thesis_bullets.append(f"Best use we see for this listing: {strat}{sec}{size}.")
    if irr_best is not None and irr_best > -900:
        thesis_bullets.append(
            f"If you hold it and local rents hold up, a simple return screen shows about "
            f"{irr_best * 100:.1f}% per year — confirm with local rent comps before trusting it."
        )
    if prime is not None and prime >= 35 and acres and acres >= 10:
        thesis_bullets.append(
            f"Soil check shows about {prime:.0f}% prime farmland — helpful for cash rent or selling to a farmer later."
        )
    if flood_pct is not None and flood_pct >= 25:
        thesis_bullets.append(
            f"About {flood_pct:.0f}% flood overlap on the map — budget insurance/fill; many buyers will skip it."
        )
    if not thesis_bullets:
        thesis_bullets.append(
            f"{prop_short.capitalize()} in {county}, {state} passes the first automated checks for a closer look."
        )
    return_case = {
        "conviction": conviction,
        "headline": (
            f"{'Strong interest' if conviction == 'HIGH' else 'Moderate interest' if conviction == 'MEDIUM' else 'Worth watching'}"
            f" · buy near {_money(entry)} · our value {_money(est)}"
            if entry and est
            else (
                f"{'Strong interest' if conviction == 'HIGH' else 'Moderate interest' if conviction == 'MEDIUM' else 'Worth watching'}"
                f" · best use {strategy.replace('_', ' ').title()}"
            )
        ),
        "entry_usd": entry,
        "mark_usd": est,
        "equity_gap_usd": gap_usd,
        "equity_gap_pct": gap_pct,
        "strategy": strategy,
        "irr_screen": irr_best if irr_best is not None and irr_best > -900 else None,
        "bullets": thesis_bullets[:5],
        "desk_note": (
            f"For {prop_short}: opportunity {opp:.0f}/100, risk {risk:.0f}/100, "
            f"how complete the file is {conf:.0f}/100, ready-to-pursue {readiness:.0f}/100. "
            f"This is a first look — not a buy order."
        ),
    }

    def _scrub(obj):
        if isinstance(obj, str):
            return strip_apn_mentions(obj)
        if isinstance(obj, list):
            return [_scrub(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _scrub(v) for k, v in obj.items()}
        return obj

    return _scrub({
        "why_opportunity": why,
        "why_still_available": still,
        "return_case": return_case,
        "soil_addendum": soil_extra,
        "flood_addendum": flood_extra,
        "wetlands_addendum": wet_extra,
        "transmission_addendum": tx_extra,
        "scenario_cards": scen_notes,
        "dd_focus": dd_focus,
        "score_story": {
            "landsignal": (
                f"{prop} ranks here because "
                + (
                    f"the realistic buy price sits {abs(disc):.0f}% "
                    f"{'under' if (disc or 0) < 0 else 'over'} our estimated value {_money(est)}, "
                    f"and the best use we see is {strategy.replace('_', ' ').title()}"
                    if disc is not None and est is not None
                    else f"the best use we see is {strategy.replace('_', ' ').title()} and the main checks still pass"
                )
                + f". Ready-to-pursue for this file: {readiness:.0f}/100."
            ),
            "risk": (
                f"At map pin {pin}, "
                + (
                    f"about {flood_pct:.0f}% of the checked area looks flood-exposed"
                    if flood_pct is not None
                    else "flood data is not confirmed yet"
                )
                + (
                    f", and about {wet_pct:.0f}% looks like wetlands"
                    if wet_pct is not None
                    else ", and wetlands are not confirmed yet"
                )
                + f". That’s why this property needs extra homework before a bid."
            ),
            "confidence": (
                f"Tracks soils, flood, value, and map data at {pin} for this property. "
                f"Missing pieces lower this number on purpose — it is not a quality grade."
            ),
        },
        "primary_cta": primary_cta,
        "watch_hint": (
            "Track opportunity, risk, how-complete, price, and status here. "
            "Set your email under My criteria → Watchlist email sync to get change notices."
        ),
    })
