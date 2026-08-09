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
    terr = _norm(enrichment, "terrain")
    growth_n = _norm(enrichment, "growth")
    comps = _norm(enrichment, "comps")

    prime = _f(soil.get("prime_farmland_pct"))
    flood_pct = _f(flood.get("flood_zone_pct"))
    wet_pct = _f(wet.get("wetland_pct"))
    access_score = _f(access.get("legal_access_confidence"))
    if access_score is None:
        access_score = _f(comps.get("legal_access_confidence"))
    slope = _f(terr.get("avg_slope_pct"))
    growth = _f(growth_n.get("path_of_growth_score")) or _f(comps.get("path_of_growth_score"))
    liq = _f(comps.get("liquidity_score"))
    scar = _f(comps.get("scarcity_score"))
    seller = _f(comps.get("seller_pressure_score"))

    risk = _f(getattr(score, "risk", None) if score else None)
    conf = _f(getattr(score, "confidence", None) if score else None)
    opp = _f(getattr(score, "opportunity", None) if score else None)

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

    # Usable-acre nuance from wetlands
    usable_hint = None
    if acres is not None and wet_pct is not None and wet_pct >= 10:
        usable = max(0.0, acres * (1.0 - min(0.85, wet_pct / 100.0 * 0.55)))
        usable_hint = f"~{usable:,.1f} usable ac after ~{wet_pct:.0f}% wetland drag"

    size_band = (
        "micro lot"
        if acres is not None and acres < 2
        else "small tract"
        if acres is not None and acres < 20
        else "mid tract"
        if acres is not None and acres < 80
        else "large tract"
        if acres is not None
        else "tract"
    )

    screen_bits: list[str] = []
    if flood_pct is not None and flood_pct >= 15:
        screen_bits.append(f"flood ~{flood_pct:.0f}%")
    if wet_pct is not None and wet_pct >= 10:
        screen_bits.append(f"wet ~{wet_pct:.0f}%")
    if access_score is not None and access_score < 55:
        screen_bits.append(f"access {access_score:.0f}/100")
    if slope is not None and slope >= 12:
        screen_bits.append(f"slope ~{slope:.0f}%")
    if prime is not None and prime >= 45:
        screen_bits.append(f"prime soil ~{prime:.0f}%")
    screens = ", ".join(screen_bits) if screen_bits else "thin desktop screens so far"

    risk_bit = (
        f"risk {risk:.0f}/100"
        if risk is not None
        else "risk still forming"
    )
    conf_bit = (
        f"file complete {conf:.0f}/100"
        if conf is not None
        else "completeness still thin"
    )
    growth_bit = (
        f"growth {growth:.0f}/100 around {county}"
        if growth is not None
        else f"no strong growth read yet for {county}"
    )
    liq_bit = (
        f"resale ease {liq:.0f}/100"
        if liq is not None
        else "resale ease unrated"
    )

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
            f"{size_band.title()} {acres_s} at {pin_short} only works if {county} still has it on a "
            f"live sale/delinquent calendar — struck-off or redeemed files waste a {strat_s} underwrite "
            f"({risk_bit}; {screens})."
        )
        site_look = "Confirm sale date, deposit, and whether deed/title clears through the county or a trustee."
        site_look_why = (
            f"For {pin_short} in {place}, sale date + deposit set cash timing, and trustee vs county "
            f"deed tells you when title is clean enough to fund survey — before you lean on {strat_s} "
            f"and {growth_bit}."
        )
    elif provider == "blm_lpad":
        channel_line = f"I'm reviewing a BLM disposal parcel — {acres_s} near {place}."
        ask_status = "Is this still in the active LPAD / sale notice window?"
        ask_status_why = (
            f"LPAD windows close; {acres_s} near {place} ({pin_short}) is only worth a {strat_s} file "
            f"if the notice is still open — federal dust-collectors don’t care that {conf_bit}."
        )
        site_look = "Find the case/serial number, sale type, and any mineral or access reservations."
        site_look_why = (
            f"Case/serial + mineral/access reservations decide if {acres_s} can actually support "
            f"{strat_s} given {screens} and {liq_bit} on exit."
        )
    elif provider == "public_surplus":
        channel_line = f"I'm interested in county/agency surplus land — {acres_s} in {place}."
        ask_status = "Is this still offered, and do you take sealed bids or direct offer?"
        ask_status_why = (
            f"Surplus resolutions end; {pin_short} ({acres_s}) needs a live offer format from {office} "
            f"or your sealed packet / direct offer is dead paper — especially with {risk_bit}."
        )
        site_look = "Look for surplus resolution, minimum bid, and closing timeline."
        site_look_why = (
            f"Min bid + close date are the only price truth on {acres_s} surplus in {place}; "
            f"pair them with {screens} before you treat {_money(est) if est else 'our mark'} as the ceiling."
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
            f"{size_band.title()} {acres_s} at {pin_short} is a {county} map screen, not a sale sheet — "
            f"owner type + tax/surplus/redemption path is the only way to know if a {strat_s} hold is "
            f"even reachable ({conf_bit}; {screens})."
        )
        site_look = (
            "On PAD / assessor: owner name, land use, last sale, and any tax status flags — "
            "don’t assume it’s for sale until the office says so."
        )
        seller_lane = (
            "seller pressure is soft — this isn’t a forced-sale lane"
            if seller is not None and seller < 50
            else "you’re not in a forced-sale lane"
        )
        site_look_why = (
            f"Owner name, land use, last sale, and tax flags on {pin_short} separate vacant-on-GIS from "
            f"buyable {acres_s} in {place}. {seller_lane.capitalize()}; with {screens} and {growth_bit}, "
            f"don’t spend on {strat_s} diligence until that record says someone can sell"
            + (f" ({usable_hint})" if usable_hint else "")
            + "."
        )
    else:
        channel_line = f"I'm reviewing {acres_s} in {place}."
        ask_status = "What’s the cleanest way to make an offer or get on the sale list?"
        ask_status_why = (
            f"{office}’s real intake for {pin_short} ({acres_s}) beats guessing — wrong door burns "
            f"days while {risk_bit} and {screens} still need answers."
        )
        site_look = "Confirm the live posting, price, and contact for offers."
        site_look_why = (
            f"Live posting + offer contact for {acres_s} in {place} tells you whether {_money(buy) if buy else 'a process entry'} "
            f"is even possible before you underwrite {strat_s}."
        )

    edge_bit = ""
    if buy is not None and est is not None and est > 0:
        gap = (est - buy) / est * 100
        edge_bit = f"~{gap:.0f}% under our mark" if gap > 0 else "near our mark"

    call_steps: list[dict[str, str]] = [
        _step(
            "Say this first",
            f"Hi — {channel_line}",
            (
                f"{office} should hear a buyer screening {acres_s} of {channel_noun} land in {place} "
                f"for {strat_s} — not a general {county} info call. Opportunity screen "
                f"{opp:.0f}/100 · {conf_bit}."
                if opp is not None
                else (
                    f"{office} should hear a buyer screening {acres_s} of {channel_noun} land in {place} "
                    f"for {strat_s} — not a general {county} info call ({conf_bit})."
                )
            ),
        ),
        _step(
            "Then say",
            f"I'm calling about {pin}"
            + (f" near {addr or 'the mapped location'}" if addr else "")
            + ".",
            (
                f"Clerks mis-pull tracts; {pin_short}"
                + (f" near {addr}" if addr else f" in {place}")
                + f" keeps the call on your {size_band} ({acres_s})"
                + (f"; {usable_hint}" if usable_hint else "")
                + f" while you still need clarity on {screens}."
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
                    f"Anchors {pin_short} to process money {_money(buy)} vs desktop mark {_money(est)} "
                    f"({edge_bit}) for {strat_s} on {acres_s} in {place}. Stops retail list-price talk "
                    f"when {liq_bit} and {growth_bit} already say this isn’t a Zillow flip."
                ),
            )
        )
    else:
        call_steps.append(
            _step(
                "Then say",
                f"Best use we’re screening: {strat_s}.",
                (
                    f"Frames {acres_s} in {place} as a {strat_s} underwrite — with {screens} and "
                    f"{risk_bit}, they stop treating you like a tire-kicker."
                ),
            )
        )

    ask_next_steps: list[dict[str, str]] = [
        _step(
            "Ask next",
            "Who handles buyer questions for this exact parcel ID?",
            (
                f"{office} transfer loops waste the window on {pin_short}. You need the desk that can "
                f"speak to this {size_band} ({acres_s}) — deposit, status, and title path — while "
                f"{conf_bit}."
            ),
        ),
        _step(
            "Ask next",
            "What paperwork or deposit do you need before I spend on a survey/title?",
            (
                f"Survey/title on {acres_s} in {county} is real money. {office} must accept you on "
                f"{pin_short} first — especially with {risk_bit} and {screens} still open."
                + (f" Also mind {usable_hint}." if usable_hint else "")
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
                    f"Desktop access is {access_score:.0f}/100 on {pin_short}. For a {strat_s} hold on "
                    f"{acres_s} in {place}, unrecorded/easement-only access can strand the deed — "
                    f"and {liq_bit} already says exits are thin."
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
                    f"~{flood_pct:.0f}% of {acres_s} at {pin_short} hits flood screen. {county} staff "
                    f"know insurance, fill, and culvert gotchas that change carry on a {strat_s} hold — "
                    f"map % alone won’t price that ({risk_bit})."
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
                    f"~{wet_pct:.0f}% wetlands on deeded {acres_s}"
                    + (f" → {usable_hint}" if usable_hint else "")
                    + f". Confirm how {county} treats that for sale/use so your {strat_s} exit math "
                    f"isn’t on phantom acres ({liq_bit})."
                ),
            ),
        )
    if prime is not None and prime >= 50:
        ask_next_steps.append(
            _step(
                "Ask next",
                f"Soil screen shows ~{prime:.0f}% prime — any farm lease history on file?",
                (
                    f"~{prime:.0f}% prime on {acres_s} supports farm/rent for {strat_s}. Lease history "
                    f"at {office} is free proof for {pin_short} — better than soil % alone when "
                    f"{growth_bit}."
                ),
            )
        )
    if slope is not None and slope >= 12 and len(ask_next_steps) < 4:
        ask_next_steps.append(
            _step(
                "Ask next",
                f"Average slope looks ~{slope:.0f}% on our terrain screen — any build/farm limits you see locally?",
                (
                    f"~{slope:.0f}% avg slope on {pin_short} can kill pads or tillable rows on {acres_s}. "
                    f"{county} nuance here protects a {strat_s} plan before you bid."
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
                    f"{acres_s} in {place} ({pin_short}) entered as GIS vacant, not a sale. With "
                    f"{conf_bit} and {screens}, don’t calendar survey/title until a human confirms "
                    f"a buy path for {strat_s}."
                ),
            )
        )
    if flood_pct is not None and flood_pct >= 25:
        watch_outs.append(
            _step(
                "Watch out",
                f"Price insurance / fill for ~{flood_pct:.0f}% flood overlap.",
                (
                    f"~{flood_pct:.0f}% flood on {pin_short} changes annual carry on {acres_s}. Bake "
                    f"insurance/fill into {_money(buy) if buy else 'your entry'} so a win doesn’t "
                    f"blow up the {strat_s} IRR ({risk_bit})."
                ),
            )
        )
    if access_score is not None and access_score < 45:
        watch_outs.append(
            _step(
                "Watch out",
                "Access isn’t clear yet — don’t wire money until a title person maps the easement.",
                (
                    f"Access {access_score:.0f}/100 on {pin_short} + {liq_bit} is a stranded-deed recipe "
                    f"on {acres_s} in {county}. Title map before wire — especially for {strat_s}."
                ),
            )
        )
    if scar is not None and scar >= 70 and not watch_outs:
        watch_outs.append(
            _step(
                "Watch out",
                f"Scarcity screen is high (~{scar:.0f}/100) — ask what substitutes usually trade nearby.",
                (
                    f"Scarcity {scar:.0f}/100 on {acres_s} in {place} can support exit — or hide a "
                    f"one-off pin nobody else will buy. Ask {office} what actually substitutes for "
                    f"{pin_short}."
                ),
            )
        )
    if not watch_outs:
        watch_outs.append(
            _step(
                "Watch out",
                f"Ask what kills deals on {acres_s} files in {county} — they’ll tell you the local trap.",
                (
                    f"{county} staff know title/access/redemption traps on {size_band} files like "
                    f"{pin_short} that never show in {screens}. One sentence here can save the "
                    f"{strat_s} hold ({risk_bit})."
                ),
            )
        )
    call_steps.append(watch_outs[0])
    call_steps.append(
        _step(
            "Close with",
            f"Thanks — I’ll confirm {pin} on your site and call back if the status is live.",
            (
                f"Leaves {office} a clean next step on {pin_short}: you’ll verify status for "
                f"{acres_s} in {place}, then return with deposit/title questions — not another cold loop."
            ),
        )
    )

    web_steps: list[dict[str, str]] = [
        _step(
            "Start here",
            f"On {office}'s site, hunt the live status for this pin — not a pretty brochure.",
            (
                f"Status on {office} decides if {acres_s} ({pin_short}) in {place} is obtainable. "
                f"Brochure copy won’t fix {screens} or {conf_bit}."
            ),
        ),
        _step("Look for", site_look, site_look_why),
        _step(
            "Look for",
            f"Search the site for {pin}" + (f" or address crumbs from {place}" if place else "") + ".",
            (
                f"One hit on {pin_short} beats wandering {county} pages. What to say needs that exact "
                f"record for your {size_band} ({acres_s}) before you dial"
                + (f" {phone}" if phone else "")
                + "."
            ),
        ),
        _step(
            "Look for",
            "Screenshot the status line (for sale / delinquent / surplus / owner) before you call.",
            (
                f"Exact status words for {pin_short} belong in the first 20 seconds with {office}. "
                f"Memory fails when {risk_bit} and {screens} are already in play."
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
                    f"{office}’s published path for {place} — follow it for {pin_short} ({acres_s}) "
                    f"before inventing a process that won’t clear {channel_noun} rules."
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
                    f"{acres_s} in {place} may be private. {office} won’t sell {pin_short}; owner of "
                    f"record is the path — don’t wait on a buy button while {growth_bit}."
                ),
            )
        )
    elif provider == "public_tax_sale":
        web_steps.append(
            _step(
                "Look for",
                "Ignore retail comps on Zillow for bid math — deposit, redemption, and clear title rules matter more.",
                (
                    f"{channel_noun} clearing on {acres_s} in {county} runs on deposit, redemption, and "
                    f"title — not retail comps near {pin_short}. Pair rules with {_money(buy) if buy else 'process entry'} "
                    f"vs {_money(est) if est else 'mark'} and {liq_bit}."
                ),
            )
        )

    web_steps.extend(
        [
            _step(
                "Do next",
                "Copy the exact parcel ID into their search.",
                (
                    f"{pin_short} → one {county} record. Wrong-pin digs waste the call you still need "
                    f"on {acres_s} while {screens} stay unresolved."
                ),
            ),
            _step(
                "Do next",
                "Note sale date / min bid / owner type in one screenshot.",
                (
                    f"Sale date, min bid, and owner type are what {office} expects when you open "
                    f"What to say on {pin_short} — the three facts that unlock a {strat_s} go/no-go "
                    f"with {edge_bit or 'your entry'} in mind."
                    if edge_bit
                    else (
                        f"Sale date, min bid, and owner type are what {office} expects when you open "
                        f"What to say on {pin_short} — three facts for a {strat_s} go/no-go on {acres_s}."
                    )
                ),
            ),
            _step(
                "Do next",
                "Then open What to say and use those facts in the first 20 seconds.",
                (
                    f"Site dig only pays if {place} facts hit the phone open for {acres_s} "
                    f"({pin_short}). Cold calls bounce when {conf_bit}."
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
