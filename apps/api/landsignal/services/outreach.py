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
    website = sourcing.get("website") or sourcing.get("posting_url")
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

    # Channel-specific opener
    if provider == "public_tax_sale":
        channel_line = (
            f"I'm looking at a {acres_s} tax-sale / delinquent inventory file in {place}."
        )
        ask_status = "Is this pin on the next tax sale, already struck off, or still just delinquent?"
        site_look = "Confirm sale date, deposit, and whether deed/title clears through the county or a trustee."
    elif provider == "blm_lpad":
        channel_line = f"I'm reviewing a BLM disposal parcel — {acres_s} near {place}."
        ask_status = "Is this still in the active LPAD / sale notice window?"
        site_look = "Find the case/serial number, sale type, and any mineral or access reservations."
    elif provider == "public_surplus":
        channel_line = f"I'm interested in county/agency surplus land — {acres_s} in {place}."
        ask_status = "Is this still offered, and do you take sealed bids or direct offer?"
        site_look = "Look for surplus resolution, minimum bid, and closing timeline."
    elif provider == "public_vacant_gis":
        channel_line = (
            f"I pulled {acres_s} of vacant land in {place} from the public parcel map — "
            f"not an MLS listing."
        )
        ask_status = (
            "Can you confirm owner type (private vs metro/county) and whether there’s any "
            "tax sale, surplus, or redemption path — or if I should approach the owner of record?"
        )
        site_look = (
            "On PAD / assessor: owner name, land use, last sale, and any tax status flags — "
            "don’t assume it’s for sale until the office says so."
        )
    else:
        channel_line = f"I'm reviewing {acres_s} in {place}."
        ask_status = "What’s the cleanest way to make an offer or get on the sale list?"
        site_look = "Confirm the live posting, price, and contact for offers."

    say_bits = [
        f"Hi — {channel_line}",
        f"I'm calling about {pin}" + (f" near {getattr(parcel, 'address', None) or 'the mapped location'}" if getattr(parcel, "address", None) else "") + ".",
        ask_status,
    ]
    if buy is not None and est is not None:
        say_bits.append(
            f"We're screening a buy near {_money(buy)} against a desktop mark around {_money(est)} "
            f"for a {strat_s} hold — not a retail flip ask."
        )
    else:
        say_bits.append(f"Best use we’re screening: {strat_s}.")

    ask_next = [
        "Who handles buyer questions for this exact parcel ID?",
        "What paperwork or deposit do you need before I spend on a survey/title?",
    ]
    if access_score is not None and access_score < 50:
        ask_next.insert(0, "Is there recorded legal road access, or only an easement / leftover flag?")
    if flood_pct is not None and flood_pct >= 20:
        ask_next.insert(0, f"Flood map shows ~{flood_pct:.0f}% overlap — any local gotchas buyers miss?")
    if wet_pct is not None and wet_pct >= 15:
        ask_next.insert(0, f"Wetlands look ~{wet_pct:.0f}% — does the county treat that as unusable for your sale?")
    if prime is not None and prime >= 50:
        ask_next.append(f"Soil screen shows ~{prime:.0f}% prime — any farm lease history on file?")

    web_steps = [
        site_look,
        f"Search the site for {pin}" + (f" or address crumbs from {place}" if place else "") + ".",
        "Screenshot the status line (for sale / delinquent / surplus / owner) before you call.",
    ]
    if how:
        web_steps.insert(0, str(how))
    if provider == "public_vacant_gis":
        web_steps.append(
            "If it’s privately owned vacant land, the ‘seller’ is the owner of record — "
            "the office page is for ID + tax status, not a buy-it-now button."
        )
    elif provider == "public_tax_sale":
        web_steps.append(
            "Ignore retail comps on Zillow for bid math — deposit, redemption, and clear title rules matter more."
        )

    watch_outs = []
    if provider == "public_vacant_gis":
        watch_outs.append("This started as a vacant GIS screen — verify it’s actually obtainable before you bid time.")
    if flood_pct is not None and flood_pct >= 25:
        watch_outs.append(f"Price insurance / fill for ~{flood_pct:.0f}% flood overlap.")
    if access_score is not None and access_score < 45:
        watch_outs.append("Access isn’t clear yet — don’t wire money until a title person maps the easement.")
    if not watch_outs:
        watch_outs.append(f"Ask what kills deals on {acres_s} files in {county} — they’ll tell you the local trap.")

    call_script = {
        "title": "What to say",
        "subtitle": f"Flip back to dial {phone}" if phone else f"Flip back when you’re ready to call {office}",
        "opener": say_bits[0],
        "lines": say_bits[1:],
        "ask_next": ask_next[:4],
        "watch_outs": watch_outs[:3],
        "closing": (
            f"Thanks — I’ll confirm {pin} on your site and call back if the status is live."
        ),
    }
    web_script = {
        "title": "What to look for",
        "subtitle": "Flip back to open the office page",
        "opener": f"On {office}'s site, hunt the live status for this pin — not a pretty brochure.",
        "lines": web_steps[:5],
        "ask_next": [
            "Copy the exact parcel ID into their search.",
            "Note sale date / min bid / owner type in one screenshot.",
            "Then flip to Call and use those facts in the first 20 seconds.",
        ],
        "watch_outs": watch_outs[:3],
        "closing": "If the page is a general department home, use parcel lookup — don’t wander the whole site.",
    }

    return {
        "office": office,
        "place": place,
        "parcel_ref": apn or "map pin",
        "channel": provider,
        "call": call_script,
        "website": web_script,
        "one_liner": (
            f"Mission: confirm you can actually buy {acres_s} in {place}, at a process price, "
            f"with access/title that won’t strand the hold."
        ),
    }
