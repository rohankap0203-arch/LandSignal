"""Hyper-specific call / website talk tracks for reaching the office."""

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


def _norm(enrichment, attr: str) -> dict:
    if not enrichment:
        return {}
    prov = getattr(enrichment, attr, None)
    if not prov:
        return {}
    return prov.normalized or prov.value or {}


def _step(kicker: str, body: str, fulfills: str) -> dict[str, str]:
    return {"kicker": kicker, "body": body, "fulfills": fulfills}


def build_outreach_playbook(
    *,
    parcel,
    listing,
    score,
    enrichment,
    sourcing: dict[str, Any] | None,
    entry_usd: float | None = None,
    mark_usd: float | None = None,
) -> dict[str, Any]:
    """Compact, conversational next steps for Call + Office page cards."""
    sourcing = sourcing or {}
    county = getattr(parcel, "county", None) or "the county"
    state = (getattr(parcel, "state", None) or "").upper() or "this state"
    place = f"{county}, {state}"
    acres = _f(getattr(parcel, "acreage", None))
    apn = getattr(parcel, "apn", None)
    provider = getattr(listing, "provider_id", None) if listing else None
    office = sourcing.get("office") or f"{county} land / tax office"
    phone = sourcing.get("phone")
    how = sourcing.get("how_to_buy") or sourcing.get("how")

    soil = _norm(enrichment, "soil")
    flood = _norm(enrichment, "flood")
    wet = _norm(enrichment, "wetlands")
    access = _norm(enrichment, "access")
    prime = _f(soil.get("prime_farmland_pct"))
    flood_pct = _f(flood.get("flood_zone_pct"))
    wet_pct = _f(wet.get("wetland_pct"))
    access_score = _f(access.get("legal_access_confidence"))

    strat = getattr(score, "best_strategy", None) if score else None
    strat_s = (
        strat.value.replace("_", " ").title()
        if strat and hasattr(strat, "value")
        else (str(strat).replace("_", " ").title() if strat else "hold / farm")
    )
    disc = _f(getattr(score, "asking_discount_pct", None) if score else None)
    est = mark_usd or _f(getattr(score, "estimated_value_usd", None) if score else None)
    buy = entry_usd
    if buy is None and est is not None and disc is not None:
        buy = est * (1 + disc / 100.0)
    if buy is None and est is not None and provider in (
        "public_tax_sale",
        "public_surplus",
        "blm_lpad",
        "public_vacant_gis",
    ):
        buy = est * (0.85 if provider == "public_vacant_gis" else 0.62)

    acres_s = f"{acres:,.2f} acres" if acres is not None else "this tract"
    pin = f"parcel ID {apn}" if apn else "this map pin"
    pin_short = str(apn) if apn else "this pin"
    addr = getattr(parcel, "address", None)

    channel_noun = {
        "public_tax_sale": "tax-sale / delinquent",
        "public_surplus": "surplus",
        "blm_lpad": "BLM disposal",
        "public_vacant_gis": "vacant map-screen",
    }.get(provider or "", "public-land")

    # Channel-specific opener / status asks
    if provider == "public_tax_sale":
        channel_line = (
            f"I'm looking at a {acres_s} tax-sale / delinquent inventory file in {place}."
        )
        ask_status = "Is this pin on the next tax sale, already struck off, or still just delinquent?"
        ask_status_why = (
            f"For {acres_s} in {county}: proves {pin_short} is still on a live tax-sale path — "
            f"not a closed delinquency you’re researching for nothing."
        )
        site_look = "Confirm sale date, deposit, and whether deed/title clears through the county or a trustee."
        site_look_why = (
            f"Those three numbers are your real {county} buy checklist — date, cash-due, and who clears title "
            f"on {pin_short}."
        )
    elif provider == "blm_lpad":
        channel_line = f"I'm reviewing a BLM disposal parcel — {acres_s} near {place}."
        ask_status = "Is this still in the active LPAD / sale notice window?"
        ask_status_why = (
            f"BLM notices die quietly — this confirms {acres_s} near {place} is still in an open window "
            f"before you build a {strat_s} file on it."
        )
        site_look = "Find the case/serial number, sale type, and any mineral or access reservations."
        site_look_why = (
            f"Case ID + reservations decide whether {acres_s} is actually usable for {strat_s}, "
            f"or locked under minerals/access you can’t live with."
        )
    elif provider == "public_surplus":
        channel_line = f"I'm interested in county/agency surplus land — {acres_s} in {place}."
        ask_status = "Is this still offered, and do you take sealed bids or direct offer?"
        ask_status_why = (
            f"Surplus in {county} dies when the resolution closes — this locks offer format "
            f"before you write the wrong package for {pin_short}."
        )
        site_look = "Look for surplus resolution, minimum bid, and closing timeline."
        site_look_why = (
            f"Min bid + close date are the only retail that matters on {acres_s} surplus in {place}."
        )
    elif provider == "public_vacant_gis":
        channel_line = (
            f"I pulled {acres_s} of vacant land in {place} from the public parcel map — "
            f"not an MLS listing."
        )
        ask_status = (
            "Can you confirm owner type (private vs metro/county) and whether there’s any "
            "tax sale, surplus, or redemption path — or if I should approach the owner of record?"
        )
        ask_status_why = (
            f"{acres_s} on the {county} map isn’t a listing yet — this finds who can sell {pin_short} "
            f"(owner vs metro vs sale calendar) before you burn a week."
        )
        site_look = (
            "On PAD / assessor: owner name, land use, last sale, and any tax status flags — "
            "don’t assume it’s for sale until the office says so."
        )
        site_look_why = (
            f"Owner + tax flags on {pin_short} separate ‘vacant on GIS’ from ‘you can actually buy "
            f"{acres_s} in {place}.’"
        )
    else:
        channel_line = f"I'm reviewing {acres_s} in {place}."
        ask_status = "What’s the cleanest way to make an offer or get on the sale list?"
        ask_status_why = (
            f"Gets {office}’s real intake for {pin_short} instead of guessing a path that won’t clear."
        )
        site_look = "Confirm the live posting, price, and contact for offers."
        site_look_why = (
            f"Confirms {acres_s} in {place} is still live and who at {office} takes the offer."
        )

    call_steps: list[dict[str, str]] = [
        _step(
            "Say this first",
            f"Hi — {channel_line}",
            (
                f"Why this opener: {office} hears you as a buyer screening {acres_s} of "
                f"{channel_noun} land in {place} — not a tourist asking for general info."
            ),
        ),
        _step(
            "Then say",
            f"I'm calling about {pin}"
            + (f" near {addr or 'the mapped location'}" if addr else "")
            + ".",
            (
                f"Why the ID: clerks pull the wrong tract constantly — {pin_short}"
                + (f" near {addr}" if addr else f" in {place}")
                + f" keeps the whole call on your {acres_s} file."
            ),
        ),
        _step("Then say", ask_status, ask_status_why),
    ]
    if buy is not None and est is not None:
        call_steps.append(
            _step(
                "Then say",
                (
                    f"We're screening a buy near {_money(buy)} against a desktop mark around {_money(est)} "
                    f"for a {strat_s} hold — not a retail flip ask."
                ),
                (
                    f"Why the numbers: anchors {pin_short} to process money (~{_money(buy)}) vs our "
                    f"~{_money(est)} mark for a {strat_s} hold in {place} — so they don’t pivot you to "
                    f"retail list-price talk."
                ),
            )
        )
    else:
        call_steps.append(
            _step(
                "Then say",
                f"Best use we’re screening: {strat_s}.",
                (
                    f"Why say the use: frames {acres_s} in {place} as a {strat_s} underwrite — "
                    f"they stop treating you like a tire-kicker."
                ),
            )
        )

    ask_next_steps: list[dict[str, str]] = [
        _step(
            "Ask next",
            "Who handles buyer questions for this exact parcel ID?",
            (
                f"Why ask: {office} transfers wander — you need the person who can speak to "
                f"{pin_short} ({acres_s}) without a second hold."
            ),
        ),
        _step(
            "Ask next",
            "What paperwork or deposit do you need before I spend on a survey/title?",
            (
                f"Why ask: stops you paying survey/title on {acres_s} in {county} before "
                f"{office} will even accept you as a buyer on {pin_short}."
            ),
        ),
    ]
    if access_score is not None and access_score < 50:
        ask_next_steps.insert(
            0,
            _step(
                "Ask next",
                "Is there recorded legal road access, or only an easement / leftover flag?",
                (
                    f"Why ask: desktop access on this pin is only {access_score:.0f}/100 — "
                    f"if {acres_s} in {place} has no recorded road, a {strat_s} hold can strand."
                ),
            ),
        )
    if flood_pct is not None and flood_pct >= 20:
        ask_next_steps.insert(
            0,
            _step(
                "Ask next",
                f"Flood map shows ~{flood_pct:.0f}% overlap — any local gotchas buyers miss?",
                (
                    f"Why ask: ~{flood_pct:.0f}% of {acres_s} at {pin_short} sits in flood screen — "
                    f"{county} staff know the insurance/fill gotchas the map won’t spell out."
                ),
            ),
        )
    if wet_pct is not None and wet_pct >= 15:
        ask_next_steps.insert(
            0,
            _step(
                "Ask next",
                f"Wetlands look ~{wet_pct:.0f}% — does the county treat that as unusable for your sale?",
                (
                    f"Why ask: ~{wet_pct:.0f}% wetlands on {acres_s} can cut usable acres for {strat_s} — "
                    f"confirm how {county} treats that before you bid."
                ),
            ),
        )
    if prime is not None and prime >= 50:
        ask_next_steps.append(
            _step(
                "Ask next",
                f"Soil screen shows ~{prime:.0f}% prime — any farm lease history on file?",
                (
                    f"Why ask: ~{prime:.0f}% prime on {acres_s} supports a farm/rent read — "
                    f"lease history at {office} is free proof the thesis isn’t only desktop soil."
                ),
            )
        )

    call_steps.extend(ask_next_steps[:4])

    watch_outs: list[dict[str, str]] = []
    if provider == "public_vacant_gis":
        watch_outs.append(
            _step(
                "Watch out",
                "This started as a vacant GIS screen — verify it’s actually obtainable before you bid time.",
                (
                    f"Why it matters: {acres_s} in {place} entered as a map screen, not a sale — "
                    f"don’t calendar diligence on {pin_short} until someone confirms a buy path."
                ),
            )
        )
    if flood_pct is not None and flood_pct >= 25:
        watch_outs.append(
            _step(
                "Watch out",
                f"Price insurance / fill for ~{flood_pct:.0f}% flood overlap.",
                (
                    f"Why it matters: ~{flood_pct:.0f}% flood on {pin_short} changes carry — "
                    f"bake insurance/fill into the bid so a win on {acres_s} doesn’t become a cost shock."
                ),
            )
        )
    if access_score is not None and access_score < 45:
        watch_outs.append(
            _step(
                "Watch out",
                "Access isn’t clear yet — don’t wire money until a title person maps the easement.",
                (
                    f"Why it matters: access reads {access_score:.0f}/100 on this pin — "
                    f"wiring on {acres_s} in {county} before a title map can buy you a stranded deed."
                ),
            )
        )
    if not watch_outs:
        watch_outs.append(
            _step(
                "Watch out",
                f"Ask what kills deals on {acres_s} files in {county} — they’ll tell you the local trap.",
                (
                    f"Why it matters: {county} staff know the deal-killers on {acres_s}-class files "
                    f"(title quirks, access, redemption) that never show on a desktop map of {pin_short}."
                ),
            )
        )
    call_steps.append(watch_outs[0])
    call_steps.append(
        _step(
            "Close with",
            f"Thanks — I’ll confirm {pin} on your site and call back if the status is live.",
            (
                f"Why close this way: you leave {office} with a clear next step on {pin_short} — "
                f"and a reason to call again once the {place} status is in your notes."
            ),
        )
    )

    web_steps: list[dict[str, str]] = [
        _step(
            "Start here",
            f"On {office}'s site, hunt the live status for this pin — not a pretty brochure.",
            (
                f"Why first: status on {office}’s site decides if {acres_s} ({pin_short}) in {place} "
                f"is even obtainable — brochure copy won’t."
            ),
        ),
        _step("Look for", site_look, site_look_why),
        _step(
            "Look for",
            f"Search the site for {pin}" + (f" or address crumbs from {place}" if place else "") + ".",
            (
                f"Why search the ID: one hit on {pin_short} beats wandering {county} pages — "
                f"your What to say open needs that exact record."
            ),
        ),
        _step(
            "Look for",
            "Screenshot the status line (for sale / delinquent / surplus / owner) before you call.",
            (
                f"Why screenshot: you need the exact status words for {pin_short} in the first "
                f"20 seconds with {office} — memory won’t cut it."
            ),
        ),
    ]
    if how:
        web_steps.insert(
            1,
            _step(
                "Look for",
                str(how),
                (
                    f"Why follow this: it’s {office}’s own buy path for {place} — "
                    f"use it for {pin_short} before inventing a process."
                ),
            ),
        )
    if provider == "public_vacant_gis":
        web_steps.append(
            _step(
                "Look for",
                (
                    "If it’s privately owned vacant land, the ‘seller’ is the owner of record — "
                    "the office page is for ID + tax status, not a buy-it-now button."
                ),
                (
                    f"Why this check: {acres_s} in {place} may be private — {office} won’t sell it; "
                    f"owner of record on {pin_short} is the path."
                ),
            )
        )
    elif provider == "public_tax_sale":
        web_steps.append(
            _step(
                "Look for",
                "Ignore retail comps on Zillow for bid math — deposit, redemption, and clear title rules matter more.",
                (
                    f"Why ignore Zillow: {channel_noun} bids on {acres_s} in {county} clear on deposit/"
                    f"redemption/title rules — not retail comps near {pin_short}."
                ),
            )
        )

    web_steps.extend(
        [
            _step(
                "Do next",
                "Copy the exact parcel ID into their search.",
                (
                    f"Why copy {pin_short}: one ID → one {county} record — wrong-pin digs waste the "
                    f"call you still need to make on {acres_s}."
                ),
            ),
            _step(
                "Do next",
                "Note sale date / min bid / owner type in one screenshot.",
                (
                    f"Why these three: sale date, min bid, and owner type are the facts "
                    f"{office} expects when you open What to say on {pin_short}."
                ),
            ),
            _step(
                "Do next",
                "Then open What to say and use those facts in the first 20 seconds.",
                (
                    f"Why switch now: the site dig only pays off if {place} facts hit the phone "
                    f"open for {acres_s} — don’t call cold."
                ),
            ),
        ]
    )
    if watch_outs:
        web_steps.append(watch_outs[0])

    call_out = call_steps[:9]
    web_out = web_steps[:9]

    return {
        "office": office,
        "place": place,
        "parcel_ref": apn or "map pin",
        "channel": provider,
        "call": {
            "title": "What to say",
            "subtitle": f"Dial {phone}" if phone else f"Call {office} when ready",
            "steps": call_out,
            "opener": call_out[0]["body"] if call_out else None,
            "lines": [s["body"] for s in call_out if s["kicker"] == "Then say"],
            "ask_next": [s["body"] for s in call_out if s["kicker"] == "Ask next"],
            "watch_outs": [s["body"] for s in call_out if s["kicker"] == "Watch out"],
            "closing": next((s["body"] for s in call_out if s["kicker"] == "Close with"), None),
        },
        "website": {
            "title": "What to look for",
            "subtitle": "Open the office page with this checklist",
            "steps": web_out,
            "opener": web_out[0]["body"] if web_out else None,
            "lines": [s["body"] for s in web_out if s["kicker"] == "Look for"],
            "ask_next": [s["body"] for s in web_out if s["kicker"] == "Do next"],
            "watch_outs": [s["body"] for s in web_out if s["kicker"] == "Watch out"],
        },
        "one_liner": (
            f"Mission: confirm you can actually buy {acres_s} in {place}, at a process price, "
            f"with access/title that won’t strand the hold."
        ),
    }
