"""Clarifying self-check: feeling question + Because… that lights up the land."""

from __future__ import annotations

import hashlib
from typing import Any


def _n(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _money(v: float | None) -> str | None:
    if v is None:
        return None
    return f"${v:,.0f}"


def _norm(enrichment, attr: str) -> dict:
    if not enrichment:
        return {}
    prov = getattr(enrichment, attr, None)
    if not prov:
        return {}
    return prov.normalized or prov.value or {}


def _pick(seed: str, options: list[tuple[int, str, str]]) -> tuple[str, str]:
    """Prefer richer parcel-specific pairs; hash only within the top tier."""
    if not options:
        return "", ""
    best = max(w for w, _, _ in options)
    floor = max(2, best - 1) if best >= 2 else best
    pool = [(q, b) for w, q, b in options if w >= floor] or [(q, b) for _, q, b in options]
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return pool[int(digest[:12], 16) % len(pool)]


def _ppa(price: float | None, acres: float | None) -> str | None:
    if price is None or acres is None or acres <= 0:
        return None
    return f"${price / acres:,.0f}/ac"


def _join(parts: list[str | None], sep: str = "; ") -> str:
    return sep.join(p for p in parts if p)


def _access_plain(access: float | None) -> str | None:
    if access is None:
        return None
    if access < 45:
        return "the way in still isn’t clear on paper"
    if access < 70:
        return "legal access still feels unsettled"
    return "access looks reasonably supported on the public read"


def _growth_plain(growth: float | None) -> str | None:
    if growth is None:
        return None
    if growth < 40:
        return "growth here looks like a long, quiet wait"
    if growth < 65:
        return "growth here looks like a multi-year clock"
    return "growth here has some forward pull"


def build_ask_yourself(
    *,
    parcel,
    listing,
    score,
    land_readouts: dict | None = None,
    enrichment=None,
) -> dict[str, str]:
    """
    Question keeps a calm emotional fork; Because… checkmates gently by naming
    the land’s full shape and the thought pattern it invites — no score jargon.
    """
    acres = _n(getattr(parcel, "acreage", None))
    state = (getattr(parcel, "state", None) or "US").upper()
    county = getattr(parcel, "county", None) or "this county"
    place = f"{county}, {state}"
    apn = getattr(parcel, "apn", None) or ""

    provider = (listing.provider_id if listing else None) or "unknown"
    ask = listing.asking_price_usd if listing else None
    if ask is not None and ask <= 0:
        ask = None

    strategy = (
        score.best_strategy.value
        if score and getattr(score, "best_strategy", None)
        else "UNDETERMINED"
    )
    strat_label = strategy.replace("_", " ").title()
    niche = {
        "FARMLAND": "working dirt — lease, crop, or hold for ag value",
        "DEVELOPMENT": "entitlement upside and a future exit to someone who builds",
        "LAND_BANK": "patience — owning time on the map more than a quick flip",
        "RECREATIONAL": "use and quiet — weekends, privacy, a place you actually visit",
        "ENERGY": "position near power and the option that might create",
        "TIMBER": "stand value and a harvest clock measured in years",
    }.get(strategy, "the kind of land you usually chase")

    opp = _n(getattr(score, "opportunity", None), 0) or 0
    risk = _n(getattr(score, "risk", None), 0) or 0
    conf = _n(getattr(score, "confidence", None), 0) or 0
    disc = _n(getattr(score, "asking_discount_pct", None))
    est = _n(getattr(score, "estimated_value_usd", None))

    soil_n = _norm(enrichment, "soil")
    flood_n = _norm(enrichment, "flood")
    wet_n = _norm(enrichment, "wetlands")
    infra_n = _norm(enrichment, "infrastructure")
    comps_n = _norm(enrichment, "comps")
    terr_n = _norm(enrichment, "terrain")
    access_n = _norm(enrichment, "access")
    growth_n = _norm(enrichment, "growth")

    flood_pct = _n(flood_n.get("flood_zone_pct"))
    flood_zone = flood_n.get("zone") or flood_n.get("flood_zone")
    wet_pct = _n(wet_n.get("wetland_pct"))
    prime = _n(soil_n.get("prime_farmland_pct"))
    farm_class = soil_n.get("farmland_classification")
    tx_m = _n(infra_n.get("nearest_transmission_m"))
    slope = _n(terr_n.get("avg_slope_pct"))
    access = (
        _n(access_n.get("legal_access_confidence"))
        or _n(comps_n.get("legal_access_confidence"))
        or _n(terr_n.get("legal_access_confidence"))
    )
    growth = _n(growth_n.get("path_of_growth_score")) or _n(comps_n.get("path_of_growth_score"))

    auction = comps_n.get("auction_path") if isinstance(comps_n.get("auction_path"), dict) else None
    if auction is None and enrichment and getattr(enrichment, "comps", None):
        raw_ap = (enrichment.comps.normalized or {}).get("auction_path")
        auction = raw_ap if isinstance(raw_ap, dict) else None
    settle = _n(auction.get("expected_settle_usd")) if auction else None
    opener = _n(auction.get("opening_bid_usd")) if auction else None
    infl = _n(auction.get("bid_inflation_mult_base")) if auction else None

    buy = settle if settle is not None else ask
    acres_s = f"{acres:,.1f} acres" if acres is not None else "this tract"
    buy_m = _money(buy)
    est_m = _money(est)
    opener_m = _money(opener or ask)
    settle_m = _money(settle)
    buy_ppa = _ppa(buy, acres)
    est_ppa = _ppa(est, acres)

    channel = {
        "public_tax_sale": "a county tax sale",
        "public_surplus": "a government surplus sale",
        "blm_lpad": "a federal BLM disposal",
        "public_vacant_gis": "a vacant map screen (not a tidy listing)",
    }.get(provider, "a public land path")

    flood_bit = None
    if flood_pct is not None:
        flood_bit = f"about {flood_pct:.0f}% of the checked ground touches flood" + (
            f" (zone {flood_zone})" if flood_zone else ""
        )
    wet_bit = f"about {wet_pct:.0f}% reads as wetlands" if wet_pct is not None else None
    access_plain = _access_plain(access)
    access_bit = access_plain
    growth_plain = _growth_plain(growth)
    soil_bit = None
    if prime is not None:
        soil_bit = f"{prime:.0f}% prime-farmland signal"
        if farm_class:
            soil_bit += f" (“{farm_class}”)"
    elif farm_class:
        soil_bit = f"soil marked “{farm_class}”"

    file_feel = (
        "the buy path still has open questions"
        if conf < 45
        else "the file is only partly filled in"
        if conf < 65
        else "the public file looks fairly filled in"
    )
    risk_feel = (
        "this pin asks for more homework before it feels simple"
        if risk >= 55
        else "the risk picture is more middling than scary"
        if risk >= 40
        else "the risk picture looks relatively settled"
    )
    opp_feel = (
        "the opportunity screens look encouraging"
        if opp >= 70
        else "the opportunity screens are mixed"
        if opp >= 50
        else "the opportunity screens are modest"
    )

    reality_core = _join(
        [
            f"{acres_s} in {place}",
            channel.replace("a ", "", 1) if channel.startswith("a ") else channel,
            f"leaning {strat_label.lower()}",
            f"money path near {buy_m}" if buy_m else None,
            f"our mark near {est_m}" if est_m else None,
            f"about {abs(disc):.0f}% {'under' if (disc or 0) < 0 else 'over'} that mark"
            if disc is not None and est_m
            else None,
            f"{buy_ppa} versus {est_ppa}" if buy_ppa and est_ppa else None,
            flood_bit,
            wet_bit,
            soil_bit,
            access_bit,
            f"average slope around {slope:.1f}%" if slope is not None else None,
            file_feel,
        ]
    )

    options: list[tuple[int, str, str]] = []

    def add(weight: int, question: str, because: str) -> None:
        q = " ".join(question.split())
        b = " ".join(because.split())
        if not b.lower().startswith("because"):
            b = f"Because {b[0].lower() + b[1:]}" if b else b
        if q and b:
            options.append((weight, q, b))

    if prime is not None and acres is not None:
        rest = max(0.0, 100.0 - prime)
        add(
            5,
            f"The soil read says {prime:.0f}% prime-farmland signal on {acres_s} in {place}. "
            f"Does that dirt match the farmland story you came looking for — "
            f"or are you noticing you’d rather admire good soil than operate it?",
            f"Because {prime:.0f}% prime also means roughly {rest:.0f}% of that signal isn’t carrying that grade, "
            f"so the warm feeling of ‘good dirt’ can outrun what you’d actually work day to day"
            + (f" at about {buy_ppa}" if buy_ppa else "")
            + (f" against our {est_ppa} mark" if est_ppa and buy_ppa else "")
            + (f", while {flood_bit}" if flood_bit else "")
            + (f", and {access_plain}" if access is not None and access < 70 else "")
            + f". A true yes for you needs the whole acreage story, not only the flattering slice.",
        )

    if auction and settle_m and opener_m and est_m:
        add(
            5,
            f"Picture yourself owning {acres_s} in {place} after {channel} — not at the {opener_m} opener, "
            f"but near the more likely {settle_m} finish (our mark is {est_m}). "
            f"Does that version still feel like your kind of land, or does naming the real number "
            f"let the excitement settle into something quieter and clearer?",
            f"Because the opener is how the story starts, not what you should emotionally bond to"
            + (f" — finishes like this often run near {infl:.1f}× the start" if infl else "")
            + f". Your gut may fall in love with {opener_m} while the file more honestly clears around {settle_m}"
            + (
                f", about {abs(disc):.0f}% {'under' if disc < 0 else 'over'} our {est_m}"
                if disc is not None
                else f" versus our {est_m}"
            )
            + (f", and {flood_bit}" if flood_bit else "")
            + (f", plus {wet_bit}" if wet_bit else "")
            + ". Comfort comes from deciding at the finish, not the teaser.",
        )

    if disc is not None and est_m and buy_m and (flood_bit or wet_bit):
        water = _join([flood_bit, wet_bit], " and ")
        add(
            5,
            f"This pin sits roughly {abs(disc):.0f}% "
            f"{'under' if disc < 0 else 'over'} our {est_m} mark, and {water}. "
            f"When you hold both truths at once — the price story and the water story — "
            f"does your body lean toward ‘I can live with this,’ "
            f"or toward relief that you noticed before you chased it?",
            f"Because a {abs(disc):.0f}% gap only helps if the constrained ground still does the job you need. "
            f"On {acres_s}, that water reshapes what you can use, insure, and someday hand to someone else"
            + (f" — and {access_plain}" if access is not None and access < 70 else "")
            + ". The discount is real; so is the haircut your plan has to absorb.",
        )

    if flood_pct is not None and flood_pct >= 15:
        add(
            4,
            f"Roughly {flood_pct:.0f}% of the checked ground on this {acres_s} in {place} touches flood"
            + (f" (zone {flood_zone})" if flood_zone else "")
            + ". "
            f"If your name were on it tomorrow, would that water be something you already know how to live with — "
            f"or the detail that lets you breathe and pass without regret?",
            f"Because flood on that share of the check isn’t a small print line — it changes where buildings, "
            f"crops, and peace of mind can sit on your {acres_s}"
            + (f", next to a money path near {buy_m}" if buy_m else "")
            + (f" and our mark of {est_m}" if est_m else "")
            + (f", plus {wet_bit}" if wet_bit else "")
            + ". Naming that early is how you stay comfortable either way.",
        )

    if wet_pct is not None and wet_pct >= 12:
        add(
            4,
            f"About {wet_pct:.0f}% wetlands show up on {acres_s} in {place}. "
            f"Does ‘usable for what I actually do’ still feel honest after that — "
            f"or is this the moment the map gives you permission to want a drier pin?",
            f"Because wetlands at {wet_pct:.0f}% quietly redefine the acres you can count on — "
            f"the map can still look wide while the workable piece shrinks"
            + (f", especially when {flood_bit}" if flood_bit else "")
            + ". Clarity here is kindness to the you who would have to live with it.",
        )

    if access is not None and access < 70:
        add(
            4,
            f"On this {place} file, {access_plain}. "
            f"Can you picture yourself calm owning the land while that question is still open — "
            f"or does comfort for you start only after the road and deed path feel settled?",
            f"Because unsettled access means a pin can be beautiful and still hard to reach, prove, or resell — "
            f"on {acres_s}"
            + (f" with a money path near {buy_m}" if buy_m else "")
            + (f", while {flood_bit}" if flood_bit else "")
            + f". Wanting that settled before you feel at ease isn’t hesitation; it’s how ownership stays quiet in your chest.",
        )

    if slope is not None and slope >= 8:
        add(
            3,
            f"Average slope reads about {slope:.1f}% across {acres_s} in {place}. "
            f"In your mind’s eye, is that rolling land you want to walk and hold — "
            f"or steeper than the {strat_label.lower()} use you quietly assumed?",
            f"Because that kind of grade changes equipment, build pads, water flow, and what ‘easy land’ means on an ordinary Tuesday"
            + (f", alongside the fact that {flood_bit}" if flood_bit else "")
            + (f", and {wet_bit}" if wet_bit else "")
            + ". The feeling of ‘pretty hills’ and the work you’d actually do are not always the same purchase.",
        )

    if tx_m is not None and (strategy == "ENERGY" or tx_m < 2500):
        add(
            4,
            f"Transmission sits roughly {tx_m:,.0f} meters from this pin on {acres_s} in {place}. "
            f"Does that proximity feel like optional upside you truly understand — "
            f"or like a story that isn’t really why you’d sleep well owning this ground?",
            f"Because distance to a line is not a deal by itself — interconnect is process, timing, and capital — "
            f"while you would still be living with "
            + _join(
                [
                    f"a {strat_label.lower()} lean",
                    f"a money path near {buy_m}" if buy_m else None,
                    flood_bit,
                    access_plain if access is not None and access < 70 else None,
                ],
                ", ",
            )
            + ". If power isn’t your real reason, let the land win or lose on the land.",
        )

    if growth is not None and strategy in ("DEVELOPMENT", "LAND_BANK") and growth_plain:
        add(
            3,
            f"For {acres_s} in {place}, {growth_plain}. "
            f"Are you someone who feels steady waiting on that kind of clock — "
            f"or does saying it out loud remind you that patience isn’t where you are right now?",
            f"Because that growth read is a years-long bet, not a weekend win — "
            f"your comfort depends on whether {place} time matches the patience you actually have"
            + (f", at roughly {buy_m} in versus our {est_m} mark" if buy_m and est_m else "")
            + (f", with {flood_bit}" if flood_bit else "")
            + ". A clean no on timing is as helpful as a calm yes.",
        )

    if provider == "public_vacant_gis":
        add(
            4,
            f"This is {acres_s} on a vacant map in {place} — not a clean priced listing"
            + (f", with our desktop mark near {est_m}" if est_m else "")
            + ". "
            f"Does the work of confirming a real buy path feel like your kind of hunt — "
            f"or does comfort for you mean waiting for a file that’s already clearer?",
            f"Because a map pin can feel like discovery while buyability is still unproven — "
            f"{file_feel}"
            + (f", {flood_bit}" if flood_bit else "")
            + (f", and {access_plain}" if access is not None and access < 70 else "")
            + (f", our mark {est_m} with no firm ask" if est_m else "")
            + ". Relief is knowing whether you enjoy that fog or need a clearer door.",
        )

    if provider in ("public_tax_sale", "public_surplus") and buy_m:
        add(
            4,
            f"You’re looking at {channel} for {acres_s} in {place}, with a realistic money path near {buy_m}"
            + (f" against our {est_m}" if est_m else "")
            + ". "
            f"When the process stress and the land itself are both in the frame, "
            f"does this still feel like a property you’d be glad to explain to someone you love — "
            f"or is the helpful answer that it’s interesting, but not yours?",
            f"Because process buys recruit you with urgency while the land still has a body"
            + (
                f" — {_join([flood_bit, wet_bit, access_bit if access is not None and access < 70 else None, soil_bit], ', ')}"
                if _join([flood_bit, wet_bit, access_bit if access is not None and access < 70 else None, soil_bit], ", ")
                else ""
            )
            + f". {risk_feel.capitalize()}. "
            f"Holding process and parcel together keeps you from confusing winning the sale with wanting the ground.",
        )

    if risk >= 55:
        bits = _join(
            [
                flood_bit,
                wet_bit,
                access_plain if access is not None and access < 70 else None,
            ],
            ", ",
        )
        add(
            4,
            f"On {acres_s} in {place}, {risk_feel}"
            + (f" — {bits}" if bits else "")
            + ". "
            f"Does naming that make you feel more oriented toward a deliberate yes, "
            f"or gently steered toward something that would sit easier in your life?",
            f"Because the heavier homework isn’t an insult to the land — it’s the map asking you to be honest: "
            + (f"{bits}. " if bits else "")
            + f"On this pin"
            + (f" near {buy_m}" if buy_m else "")
            + ", orientation beats optimism. You get to choose comfort with your eyes open.",
        )

    if opp >= 70 and conf >= 50 and risk < 50:
        add(
            4,
            f"This one reads calmer than most: {opp_feel}, {risk_feel}, {file_feel}, "
            f"leaning {strat_label.lower()} on {acres_s} in {place}"
            + (f", money path near {buy_m}" if buy_m else "")
            + ". "
            f"If you let yourself trust that quieter read for a moment — does this feel like land "
            f"you’d be comfortable owning, or still not quite what you came for?",
            f"Because a calmer file can still be the wrong land for you — ease doesn’t invent "
            f"{niche} if that isn’t what you want to wake up owning. "
            f"Use the calm as permission to tell the truth, not pressure to say yes.",
        )

    add(
        2,
        f"Forget the charts for a breath. You’re looking at {acres_s} in {place}, via {channel}, "
        f"leaning {strat_label.lower()} — {niche}. "
        f"When you imagine your name on it, do you feel a quiet yes, or a quiet thank-you for looking closely enough to walk away?",
        f"Because the full light on this pin is: {reality_core}. "
        f"Either feeling — yes or not this one — means you understood the land instead of negotiating with hope.",
    )

    if buy_m and est_m:
        add(
            3,
            f"Buy screen near {buy_m}, our value near {est_m}"
            + (f" ({buy_ppa} vs {est_ppa})" if buy_ppa and est_ppa else "")
            + f", on {acres_s} in {place}. "
            f"Does that math leave you feeling grounded enough to keep going — "
            f"or relieved that the numbers talked you out of forcing a fit?",
            f"Because price only comforts you after it survives the land you would actually live with"
            + (
                f" — {_join([flood_bit, wet_bit, access_plain if access is not None and access < 70 else None, soil_bit], ', ')}"
                if _join([flood_bit, wet_bit, access_plain if access is not None and access < 70 else None, soil_bit], ", ")
                else ""
            )
            + (
                f". A gap of about {abs(disc):.0f}% versus our mark only helps if the ground still matches how you use and hold land."
                if disc is not None
                else ". That spread only helps if the ground still matches how you use and hold land."
            ),
        )

    seed = "|".join(
        [
            apn,
            place,
            provider,
            strategy,
            f"{acres:.2f}" if acres is not None else "na",
            f"{disc:.1f}" if disc is not None else "nd",
            f"{flood_pct:.0f}" if flood_pct is not None else "nf",
            f"{wet_pct:.0f}" if wet_pct is not None else "nw",
            f"{access:.0f}" if access is not None else "nacc",
            f"{opp:.0f}",
            f"{risk:.0f}",
        ]
    )
    question, because = _pick(seed, options)

    return {
        "label": "Ask yourself",
        "question": question,
        "because": because,
        "aftertaste": because,
    }
