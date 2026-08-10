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
    # Never prefix with "Why ask/…" — the UI already labels Why ·
    clean = fulfills.strip()
    for prefix in (
        "Why ask:",
        "Why ask ·",
        "Why this opener:",
        "Why the ID:",
        "Why the numbers:",
        "Why say the use:",
        "Why close this way:",
        "Why it matters:",
        "Why first:",
        "Why search the ID:",
        "Why screenshot:",
        "Why follow this:",
        "Why this check:",
        "Why copy:",
        "Why these three:",
        "Why switch now:",
        "Why say this:",
        "Why next:",
    ):
        if clean.lower().startswith(prefix.lower()):
            clean = clean[len(prefix) :].lstrip(" :·—-")
            break
    return {"kicker": kicker, "body": body, "fulfills": clean}


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
    """Compact next steps for Call + Office page — Why lines stay short and plain."""
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
    terr = _norm(enrichment, "terrain")
    comps = _norm(enrichment, "comps")

    prime = _f(soil.get("prime_farmland_pct"))
    flood_pct = _f(flood.get("flood_zone_pct"))
    wet_pct = _f(wet.get("wetland_pct"))
    access_score = _f(access.get("legal_access_confidence"))
    if access_score is None:
        access_score = _f(comps.get("legal_access_confidence"))
    slope = _f(terr.get("avg_slope_pct"))
    scar = _f(comps.get("scarcity_score"))

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

    acres_s = f"{acres:,.2f} acres" if acres is not None else "this land"
    pin = f"parcel ID {apn}" if apn else "this map pin"
    pin_short = str(apn) if apn else "this pin"
    addr = getattr(parcel, "address", None)

    # Channel-specific opener / status asks — Why stays one plain sentence.
    if provider == "public_tax_sale":
        channel_line = (
            f"I'm looking at a {acres_s} tax-sale / delinquent inventory file in {place}."
        )
        ask_status = "Is this pin on the next tax sale, already struck off, or still just delinquent?"
        ask_status_why = "If it’s already sold or redeemed, stop — you can’t buy it."
        site_look = "Confirm sale date, deposit, and whether deed/title clears through the county or a trustee."
        site_look_why = "Those three facts tell you when you pay and when you own it."
    elif provider == "blm_lpad":
        channel_line = f"I'm reviewing a BLM disposal parcel — {acres_s} near {place}."
        ask_status = "Is this still in the active LPAD / sale notice window?"
        ask_status_why = "If the sale window closed, this land is off the table."
        site_look = "Find the case/serial number, sale type, and any mineral or access reservations."
        site_look_why = "Those details say what you actually get — and what you don’t."
    elif provider == "public_surplus":
        channel_line = f"I'm interested in county/agency surplus land — {acres_s} in {place}."
        ask_status = "Is this still offered, and do you take sealed bids or direct offer?"
        ask_status_why = "You need the real way to offer — or your paperwork goes nowhere."
        site_look = "Look for surplus resolution, minimum bid, and closing timeline."
        site_look_why = "Min bid and close date are the real price rules for this land."
    elif provider == "public_vacant_gis":
        channel_line = (
            f"I pulled {acres_s} of vacant land in {place} from the public parcel map — "
            f"not an MLS listing."
        )
        ask_status = (
            "Can you confirm owner type (private vs metro/county) and whether there’s any "
            "tax sale, surplus, or redemption path — or if I should approach the owner of record?"
        )
        ask_status_why = "A map pin isn’t a sale — you need who can actually sell it."
        site_look = (
            "On PAD / assessor: owner name, land use, last sale, and any tax status flags — "
            "don’t assume it’s for sale until the office says so."
        )
        site_look_why = "Owner + tax flags tell you if this land is even for sale."
    else:
        channel_line = f"I'm reviewing {acres_s} in {place}."
        ask_status = "What’s the cleanest way to make an offer or get on the sale list?"
        ask_status_why = "Wrong door wastes days — ask the desk that can sell this pin."
        site_look = "Confirm the live posting, price, and contact for offers."
        site_look_why = "Live posting + contact = can you buy it or not."

    call_steps: list[dict[str, str]] = [
        _step(
            "Say this first",
            f"Hi — {channel_line}",
            "So they know you’re a buyer on this land — not a random info call.",
        ),
        _step(
            "Then say",
            f"I'm calling about {pin}"
            + (f" near {addr or 'the mapped location'}" if addr else "")
            + ".",
            "So they pull the right parcel — not a neighbor’s.",
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
                "So they hear your real budget — not a retail list-price chat.",
            )
        )
    else:
        call_steps.append(
            _step(
                "Then say",
                f"Best use we’re screening: {strat_s}.",
                "So they know how you’d use the land — not that you’re browsing.",
            )
        )

    ask_next_steps: list[dict[str, str]] = [
        _step(
            "Ask next",
            "Who handles buyer questions for this exact parcel ID?",
            "So you talk to the person who can answer — not get bounced around.",
        ),
        _step(
            "Ask next",
            "What paperwork or deposit do you need before I spend on a survey/title?",
            "So you don’t spend money before they even accept you as a buyer.",
        ),
    ]
    if access_score is not None and access_score < 50:
        ask_next_steps.insert(
            0,
            _step(
                "Ask next",
                "Is there recorded legal road access, or only an easement / leftover flag?",
                "No road in = land you may not be able to use or sell.",
            ),
        )
    if flood_pct is not None and flood_pct >= 20:
        ask_next_steps.insert(
            0,
            _step(
                "Ask next",
                f"Flood map shows ~{flood_pct:.0f}% overlap — any local gotchas buyers miss?",
                "Flood can mean higher insurance and surprise costs every year.",
            ),
        )
    if wet_pct is not None and wet_pct >= 15:
        ask_next_steps.insert(
            0,
            _step(
                "Ask next",
                f"Wetlands look ~{wet_pct:.0f}% — does the county treat that as unusable for your sale?",
                "Wet acres often don’t count as land you can farm or build on.",
            ),
        )
    if prime is not None and prime >= 50:
        ask_next_steps.append(
            _step(
                "Ask next",
                f"Soil screen shows ~{prime:.0f}% prime — any farm lease history on file?",
                "Lease history is free proof the land can earn rent.",
            )
        )
    if slope is not None and slope >= 12 and len(ask_next_steps) < 4:
        ask_next_steps.append(
            _step(
                "Ask next",
                f"Average slope looks ~{slope:.0f}% on our terrain screen — any build/farm limits you see locally?",
                "Steep ground can block building or farming — ask before you bid.",
            )
        )

    call_steps.extend(ask_next_steps[:4])

    watch_outs: list[dict[str, str]] = []
    if provider == "public_vacant_gis":
        watch_outs.append(
            _step(
                "Watch out",
                "This started as a vacant GIS screen — verify it’s actually obtainable before you bid time.",
                "On a map ≠ for sale. Confirm you can buy it first.",
            )
        )
    if flood_pct is not None and flood_pct >= 25:
        watch_outs.append(
            _step(
                "Watch out",
                f"Price insurance / fill for ~{flood_pct:.0f}% flood overlap.",
                "Flood costs can wipe out a “cheap” buy.",
            )
        )
    if access_score is not None and access_score < 45:
        watch_outs.append(
            _step(
                "Watch out",
                "Access isn’t clear yet — don’t wire money until a title person maps the easement.",
                "No clear road = don’t send money yet.",
            )
        )
    if scar is not None and scar >= 70 and not watch_outs:
        watch_outs.append(
            _step(
                "Watch out",
                f"Scarcity screen is high (~{scar:.0f}/100) — ask what substitutes usually trade nearby.",
                "Rare on paper can still be hard to resell — ask what else trades nearby.",
            )
        )
    if not watch_outs:
        watch_outs.append(
            _step(
                "Watch out",
                f"Ask what kills deals on {acres_s} files in {county} — they’ll tell you the local trap.",
                "They know the local trap that sinks deals like this.",
            )
        )
    call_steps.append(watch_outs[0])
    call_steps.append(
        _step(
            "Close with",
            f"Thanks — I’ll confirm {pin} on your site and call back if the status is live.",
            "Ends clean: you’ll check status, then call back with real questions.",
        )
    )

    web_steps: list[dict[str, str]] = [
        _step(
            "Start here",
            f"On {office}'s site, hunt the live status for this pin — not a pretty brochure.",
            "Status first: can you buy this pin, or not?",
        ),
        _step("Look for", site_look, site_look_why),
        _step(
            "Look for",
            f"Search the site for {pin}" + (f" or address crumbs from {place}" if place else "") + ".",
            "Find this exact pin — not a lookalike nearby.",
        ),
        _step(
            "Look for",
            "Screenshot the status line (for sale / delinquent / surplus / owner) before you call.",
            "Write it down so you say the right status on the phone.",
        ),
    ]
    if how:
        web_steps.insert(
            1,
            _step(
                "Look for",
                str(how),
                "Follow their published buy steps — don’t invent your own.",
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
                "The county page won’t sell private land — you need the owner.",
            )
        )
    elif provider == "public_tax_sale":
        web_steps.append(
            _step(
                "Look for",
                "Ignore retail comps on Zillow for bid math — deposit, redemption, and clear title rules matter more.",
                "Tax sales follow their rules — not Zillow prices.",
            )
        )

    web_steps.extend(
        [
            _step(
                "Do next",
                "Copy the exact parcel ID into their search.",
                "Wrong ID = wrong land.",
            ),
            _step(
                "Do next",
                "Note sale date / min bid / owner type in one screenshot.",
                "Those three facts are what you need before you call.",
            ),
            _step(
                "Do next",
                "Then open What to say and use those facts in the first 20 seconds.",
                "Use what you found — don’t call cold.",
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
        "one_liner": f"Goal: confirm you can buy {acres_s} in {place} — at a real process price, with a road and clean title.",
    }
