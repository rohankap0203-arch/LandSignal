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
    the land’s full shape and the thought pattern it invites.
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
        flood_bit = f"{flood_pct:.0f}% flood overlap" + (
            f" (zone {flood_zone})" if flood_zone else ""
        )
    wet_bit = f"{wet_pct:.0f}% wetlands" if wet_pct is not None else None
    access_bit = f"access confidence {access:.0f}/100" if access is not None else None
    soil_bit = None
    if prime is not None:
        soil_bit = f"{prime:.0f}% prime-farmland signal"
        if farm_class:
            soil_bit += f" (“{farm_class}”)"
    elif farm_class:
        soil_bit = f"soil class “{farm_class}”"

    # Shared reality line used to ground Because… paragraphs
    reality_core = _join(
        [
            f"{acres_s} in {place}",
            channel.replace("a ", "", 1) if channel.startswith("a ") else channel,
            f"best-use lean {strat_label}",
            f"{buy_m} buy path" if buy_m else None,
            f"our mark {est_m}" if est_m else None,
            f"{disc:+.0f}% vs value" if disc is not None and est_m else None,
            f"{buy_ppa} vs {est_ppa}" if buy_ppa and est_ppa else None,
            flood_bit,
            wet_bit,
            soil_bit,
            access_bit,
            f"avg slope {slope:.1f}%" if slope is not None else None,
            f"opportunity {opp:.0f} · risk {risk:.0f} · file {conf:.0f}" ,
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
            f"Because {prime:.0f}% prime also means roughly {rest:.0f}% of the signal isn’t carrying that grade, "
            f"so the warm feeling of ‘good dirt’ can outrun the usable picture"
            + (f" at about {buy_ppa}" if buy_ppa else "")
            + (f" against our {est_ppa} mark" if est_ppa and buy_ppa else "")
            + (f", with {flood_bit} still on the map" if flood_bit else "")
            + (f" and {access_bit}" if access_bit else "")
            + f". A true {strat_label.lower()} yes needs the whole acreage story, not only the flattering slice.",
        )

    if auction and settle_m and opener_m and est_m:
        add(
            5,
            f"Picture owning {acres_s} in {place} after {channel} — not at the {opener_m} opener, "
            f"but near the more likely {settle_m} finish (our mark is {est_m}). "
            f"Does that version still feel like {niche} for you, or does naming the real number "
            f"let the excitement settle into something quieter and clearer?",
            f"Because the opener is a doorway, not the deed price"
            + (f" — finishes like this often run near {infl:.1f}× the start" if infl else "")
            + f", and your nervous system will try to bond with {opener_m} while the file actually clears around {settle_m}"
            + (f" ({disc:+.0f}% vs our {est_m})" if disc is not None else f" versus our {est_m}")
            + (f", with {flood_bit}" if flood_bit else "")
            + (f" and {wet_bit}" if wet_bit else "")
            + ". Comfort comes from deciding at the finish, not the teaser.",
        )

    if disc is not None and est_m and buy_m and (flood_bit or wet_bit):
        water = _join([flood_bit, wet_bit], " and ")
        add(
            5,
            f"This pin screens roughly {abs(disc):.0f}% "
            f"{'under' if disc < 0 else 'over'} our {est_m} mark, with {water} on the map. "
            f"When you hold both truths at once — the price story and the water story — "
            f"does your body lean toward ‘this is my kind of {strat_label.lower()} risk,’ "
            f"or toward relief that you noticed before you chased it?",
            f"Because a {abs(disc):.0f}% gap only helps if the constrained ground still does the job you need — "
            f"on {acres_s}, {water} reshapes what you can use, insure, and exit"
            + (f", while {access_bit} still sits open" if access_bit else "")
            + f". The discount is real; so is the haircut your plan has to absorb.",
        )

    if flood_pct is not None and flood_pct >= 15:
        add(
            4,
            f"Roughly {flood_pct:.0f}% of the checked ground on this {acres_s} in {place} touches flood"
            + (f" (zone {flood_zone})" if flood_zone else "")
            + ". "
            f"If you bought tomorrow, would that water be a constraint you already know how to live with "
            f"in a {strat_label.lower()} plan — or the detail that lets you breathe and pass without regret?",
            f"Because flood on {flood_pct:.0f}% of the check is not a footnote — it changes where buildings, "
            f"crops, and peace of mind can sit on {acres_s}"
            + (f", next to a money path near {buy_m}" if buy_m else "")
            + (f" and our mark of {est_m}" if est_m else "")
            + (f", plus {wet_bit}" if wet_bit else "")
            + ". Naming that early is how you stay comfortable either way.",
        )

    if wet_pct is not None and wet_pct >= 12:
        add(
            4,
            f"About {wet_pct:.0f}% wetlands show up on {acres_s} in {place}. "
            f"Does ‘usable for what I actually do’ still feel honest after that number — "
            f"or is this the moment the map gives you permission to want a drier pin?",
            f"Because wetlands at {wet_pct:.0f}% quietly redefine the acreage you can count on — "
            f"the map can still look wide while the workable piece shrinks"
            + (f", especially with {flood_bit}" if flood_bit else "")
            + (f" and a {strat_label.lower()} lean that needs dry, usable ground" if strategy in ("FARMLAND", "DEVELOPMENT", "RECREATIONAL") else "")
            + ". Clarity here is kindness to your future self.",
        )

    if access is not None and access < 70:
        add(
            4,
            f"Legal-access confidence sits around {access:.0f}/100 on this {place} file. "
            f"Can you picture yourself calm owning land while that question is still open — "
            f"or does comfort for you start only after the road and deed path feel settled?",
            f"Because access at {access:.0f}/100 means the pin can be beautiful and still hard to reach, prove, or resell — "
            f"on {acres_s}"
            + (f" with a buy path near {buy_m}" if buy_m else "")
            + (f", {flood_bit}" if flood_bit else "")
            + f", risk {risk:.0f}/100. Wanting that settled before you feel at ease isn’t hesitation; it’s how ownership stays quiet in your chest.",
        )

    if slope is not None and slope >= 8:
        add(
            3,
            f"Average slope reads about {slope:.1f}% across {acres_s} in {place}. "
            f"In your mind’s eye, is that rolling land you want to walk and hold — "
            f"or steeper than the {strat_label.lower()} use you quietly assumed?",
            f"Because {slope:.1f}% average grade changes equipment, build pads, water flow, and what ‘easy land’ means day to day"
            + (f", alongside {flood_bit}" if flood_bit else "")
            + (f" and {wet_bit}" if wet_bit else "")
            + f". The feeling of ‘pretty hills’ and the work of {strat_label.lower()} are not always the same purchase.",
        )

    if tx_m is not None and (strategy == "ENERGY" or tx_m < 2500):
        add(
            4,
            f"Transmission sits roughly {tx_m:,.0f} meters from this pin on {acres_s} in {place}. "
            f"Does that proximity feel like optional upside you understand — "
            f"or like a story that isn’t really why you’d sleep well owning this ground?",
            f"Because {tx_m:,.0f} m to the line is a distance, not a deal — interconnect is process, timing, and capital, "
            f"while this file still carries "
            + _join(
                [
                    f"a {strat_label} lean",
                    f"buy path {buy_m}" if buy_m else None,
                    flood_bit,
                    access_bit,
                ],
                ", ",
            )
            + ". If power isn’t your real reason, let the land win or lose on the land.",
        )

    if growth is not None and strategy in ("DEVELOPMENT", "LAND_BANK"):
        add(
            3,
            f"Path-of-growth screens around {growth:.0f}/100 for {acres_s} in {place}. "
            f"Are you someone who feels steady waiting on that kind of clock — "
            f"or does saying it out loud remind you that patience isn’t the niche you’re in right now?",
            f"Because a {growth:.0f}/100 growth read is a years-long bet, not a weekend win — "
            f"your comfort depends on whether {place} time matches your capital’s patience"
            + (f", at roughly {buy_m} in versus {est_m} mark" if buy_m and est_m else "")
            + (f", with {flood_bit} still in the physical picture" if flood_bit else "")
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
            f"Because a GIS pin can feel like discovery while buyability is still unproven — "
            f"completeness is {conf:.0f}/100"
            + (f", {flood_bit}" if flood_bit else "")
            + (f", {access_bit}" if access_bit else "")
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
            f"does this still feel like a property you’d be glad to explain to a partner — "
            f"or is the helpful answer that it’s interesting, but not yours?",
            f"Because process buys recruit you with urgency while the land still has a body"
            + (
                f" — {_join([flood_bit, wet_bit, access_bit, soil_bit], ', ')}"
                if _join([flood_bit, wet_bit, access_bit, soil_bit], ", ")
                else ""
            )
            + f"; opportunity {opp:.0f}, risk {risk:.0f}. "
            f"Holding process and parcel together keeps you from confusing winning the sale with wanting the ground.",
        )

    if risk >= 55:
        bits = _join([flood_bit, wet_bit, access_bit], ", ")
        add(
            4,
            f"Risk on this pin reads {risk:.0f}/100"
            + (f", with {bits} in the mix" if bits else "")
            + ". "
            f"That’s not a verdict — it’s a mirror. Does knowing that make you feel more oriented "
            f"toward a deliberate {strat_label.lower()} yes, or gently steered toward something simpler?",
            f"Because {risk:.0f}/100 risk is the scoreboard catching up to the map: "
            + (f"{bits}. " if bits else "")
            + f"On {acres_s} in {place}"
            + (f" near {buy_m}" if buy_m else "")
            + ", orientation beats optimism — you get to choose comfort with eyes open.",
        )

    if opp >= 70 and conf >= 50 and risk < 50:
        add(
            4,
            f"The screens are relatively friendly here: opportunity {opp:.0f}, risk {risk:.0f}, "
            f"file completeness {conf:.0f}, best-use leaning {strat_label} on {acres_s} in {place}"
            + (f", money path near {buy_m}" if buy_m else "")
            + ". "
            f"If you let yourself trust a calmer read for a moment — does this feel like land "
            f"you’d be comfortable owning, or still not quite the niche you came for?",
            f"Because a calmer file can still be the wrong niche — friendly scores don’t invent "
            f"{niche} if that isn’t what you want to wake up owning. "
            f"Use the ease as permission to tell the truth, not pressure to say yes.",
        )

    add(
        2,
        f"Forget the scoreboard for a breath. You’re looking at {acres_s} in {place}, via {channel}, "
        f"reading best as {strat_label} — {niche}. "
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
            f"Because price only comforts you after it survives the land"
            + (
                f" — {_join([flood_bit, wet_bit, access_bit, soil_bit], ', ')}"
                if _join([flood_bit, wet_bit, access_bit, soil_bit], ", ")
                else ""
            )
            + (
                f". A {abs(disc):.0f}% gap vs our mark is meaningful only if the ground still matches how you actually use and hold land."
                if disc is not None
                else ". That spread is meaningful only if the ground still matches how you actually use and hold land."
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
