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
    addr = getattr(parcel, "address", None)

    # Channel-specific opener / status asks
    if provider == "public_tax_sale":
        channel_line = (
            f"I'm looking at a {acres_s} tax-sale / delinquent inventory file in {place}."
        )
        ask_status = "Is this pin on the next tax sale, already struck off, or still just delinquent?"
        ask_status_why = "Confirms you can still buy it through the county process — not chasing a closed file."
        site_look = "Confirm sale date, deposit, and whether deed/title clears through the county or a trustee."
        site_look_why = "Locks the real buy path and cash you’ll need on sale day."
    elif provider == "blm_lpad":
        channel_line = f"I'm reviewing a BLM disposal parcel — {acres_s} near {place}."
        ask_status = "Is this still in the active LPAD / sale notice window?"
        ask_status_why = "Federal disposals expire — this stops you working a dead notice."
        site_look = "Find the case/serial number, sale type, and any mineral or access reservations."
        site_look_why = "Case ID + reservations decide if the hold is even usable."
    elif provider == "public_surplus":
        channel_line = f"I'm interested in county/agency surplus land — {acres_s} in {place}."
        ask_status = "Is this still offered, and do you take sealed bids or direct offer?"
        ask_status_why = "Tells you the offer format before you write a wrong kind of bid."
        site_look = "Look for surplus resolution, minimum bid, and closing timeline."
        site_look_why = "Agency sales live or die on min bid + close date, not MLS vibes."
    elif provider == "public_vacant_gis":
        channel_line = (
            f"I pulled {acres_s} of vacant land in {place} from the public parcel map — "
            f"not an MLS listing."
        )
        ask_status = (
            "Can you confirm owner type (private vs metro/county) and whether there’s any "
            "tax sale, surplus, or redemption path — or if I should approach the owner of record?"
        )
        ask_status_why = "Map screens aren’t listings — this finds who can actually sell it."
        site_look = (
            "On PAD / assessor: owner name, land use, last sale, and any tax status flags — "
            "don’t assume it’s for sale until the office says so."
        )
        site_look_why = "Separates ‘on the map’ from ‘obtainable’ before you spend hours."
    else:
        channel_line = f"I'm reviewing {acres_s} in {place}."
        ask_status = "What’s the cleanest way to make an offer or get on the sale list?"
        ask_status_why = "Gets the real intake path instead of guessing."
        site_look = "Confirm the live posting, price, and contact for offers."
        site_look_why = "Verifies the file is live and who takes the offer."

    call_steps: list[dict[str, str]] = [
        _step(
            "Say this first",
            f"Hi — {channel_line}",
            f"Opens as a serious {place} land buyer, not a random info call.",
        ),
        _step(
            "Then say",
            f"I'm calling about {pin}"
            + (f" near {addr or 'the mapped location'}" if addr else "")
            + ".",
            "Pins the exact file so they don’t pull the wrong tract.",
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
                f"Signals process pricing + {strat_s} use so they don’t quote retail MLS math.",
            )
        )
    else:
        call_steps.append(
            _step(
                "Then say",
                f"Best use we’re screening: {strat_s}.",
                f"Frames the call around a real {strat_s} thesis, not tire-kicking.",
            )
        )

    ask_next_steps: list[dict[str, str]] = [
        _step(
            "Ask next",
            "Who handles buyer questions for this exact parcel ID?",
            "Gets you the right desk — not a transfer loop.",
        ),
        _step(
            "Ask next",
            "What paperwork or deposit do you need before I spend on a survey/title?",
            "Stops you paying for diligence before the county will even take you.",
        ),
    ]
    if access_score is not None and access_score < 50:
        ask_next_steps.insert(
            0,
            _step(
                "Ask next",
                "Is there recorded legal road access, or only an easement / leftover flag?",
                f"Access screen is soft ({access_score:.0f}/100) — this kills stranded-land risk early.",
            ),
        )
    if flood_pct is not None and flood_pct >= 20:
        ask_next_steps.insert(
            0,
            _step(
                "Ask next",
                f"Flood map shows ~{flood_pct:.0f}% overlap — any local gotchas buyers miss?",
                "Turns a map flag into local carry cost / insurability truth.",
            ),
        )
    if wet_pct is not None and wet_pct >= 15:
        ask_next_steps.insert(
            0,
            _step(
                "Ask next",
                f"Wetlands look ~{wet_pct:.0f}% — does the county treat that as unusable for your sale?",
                "Checks whether deeded acres shrink when you try to use or resell.",
            ),
        )
    if prime is not None and prime >= 50:
        ask_next_steps.append(
            _step(
                "Ask next",
                f"Soil screen shows ~{prime:.0f}% prime — any farm lease history on file?",
                "Tests if the farm/rent thesis has any county-side trail.",
            )
        )

    call_steps.extend(ask_next_steps[:4])

    watch_outs: list[dict[str, str]] = []
    if provider == "public_vacant_gis":
        watch_outs.append(
            _step(
                "Watch out",
                "This started as a vacant GIS screen — verify it’s actually obtainable before you bid time.",
                "Protects your week from a pretty map pin that isn’t for sale.",
            )
        )
    if flood_pct is not None and flood_pct >= 25:
        watch_outs.append(
            _step(
                "Watch out",
                f"Price insurance / fill for ~{flood_pct:.0f}% flood overlap.",
                "Keeps flood carry in the bid math, not as a surprise after you win.",
            )
        )
    if access_score is not None and access_score < 45:
        watch_outs.append(
            _step(
                "Watch out",
                "Access isn’t clear yet — don’t wire money until a title person maps the easement.",
                "Blocks a stranded purchase if the road isn’t truly legal.",
            )
        )
    if not watch_outs:
        watch_outs.append(
            _step(
                "Watch out",
                f"Ask what kills deals on {acres_s} files in {county} — they’ll tell you the local trap.",
                "Surfaces the county’s real deal-killers you can’t see on a desktop map.",
            )
        )
    call_steps.append(watch_outs[0])
    call_steps.append(
        _step(
            "Close with",
            f"Thanks — I’ll confirm {pin} on your site and call back if the status is live.",
            "Leaves a clean next step and a reason to call again with facts.",
        )
    )

    web_steps: list[dict[str, str]] = [
        _step(
            "Start here",
            f"On {office}'s site, hunt the live status for this pin — not a pretty brochure.",
            "Status beats marketing copy for whether you can buy at all.",
        ),
        _step("Look for", site_look, site_look_why),
        _step(
            "Look for",
            f"Search the site for {pin}" + (f" or address crumbs from {place}" if place else "") + ".",
            "Finds the exact record so Call can open with the right ID.",
        ),
        _step(
            "Look for",
            "Screenshot the status line (for sale / delinquent / surplus / owner) before you call.",
            "Gives you proof-words for the first 20 seconds on the phone.",
        ),
    ]
    if how:
        web_steps.insert(
            1,
            _step(
                "Look for",
                str(how),
                f"County’s own buy path for {place} — follow this before inventing one.",
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
                "Stops you waiting on a sale button that will never appear.",
            )
        )
    elif provider == "public_tax_sale":
        web_steps.append(
            _step(
                "Look for",
                "Ignore retail comps on Zillow for bid math — deposit, redemption, and clear title rules matter more.",
                "Keeps bid math on process rules, not retail land porn.",
            )
        )

    web_steps.extend(
        [
            _step(
                "Do next",
                "Copy the exact parcel ID into their search.",
                "One ID → one record; no wrong-pin rabbit holes.",
            ),
            _step(
                "Do next",
                "Note sale date / min bid / owner type in one screenshot.",
                "Packs the three facts Call needs to sound ready.",
            ),
            _step(
                "Do next",
                "Then open Talk track and use those facts in the first 20 seconds.",
                "Turns the website dig into a sharp phone open.",
            ),
        ]
    )
    if watch_outs:
        web_steps.append(watch_outs[0])

    # Cap length but keep specificity
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
            # legacy flat fields (older UI)
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
