"""One hard, data-grounded self-interrogation for the intelligence page."""

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


def _pick(seed: str, options: list[tuple[int, str]]) -> str:
    """Prefer high technical density; hash only within the densest tier."""
    if not options:
        return ""
    best = max(w for w, _ in options)
    floor = max(3, best - 1) if best >= 3 else best
    pool = [q for w, q in options if w >= floor] or [q for _, q in options]
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return pool[int(digest[:12], 16) % len(pool)]


def _ppa(price: float | None, acres: float | None) -> str | None:
    if price is None or acres is None or acres <= 0:
        return None
    return f"${price / acres:,.0f}/ac"


def _clip_plain(text: str, max_len: int = 110) -> str | None:
    s = " ".join((text or "").split()).strip()
    if not s:
        return None
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s.rstrip(".")


def build_ask_yourself(
    *,
    parcel,
    listing,
    score,
    land_readouts: dict | None = None,
    enrichment=None,
) -> dict[str, str]:
    """Return one question that puts the user on the hot seat with this pin's numbers."""
    acres = _n(getattr(parcel, "acreage", None))
    state = (getattr(parcel, "state", None) or "US").upper()
    county = getattr(parcel, "county", None) or "this county"
    place = f"{county}, {state}"
    apn = getattr(parcel, "apn", None) or ""
    lat = getattr(parcel, "latitude", None)
    lon = getattr(parcel, "longitude", None)
    pin = f"{lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else None

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
    opp = _n(getattr(score, "opportunity", None), 0) or 0
    risk = _n(getattr(score, "risk", None), 0) or 0
    conf = _n(getattr(score, "confidence", None), 0) or 0
    disc = _n(getattr(score, "asking_discount_pct", None))
    est = _n(getattr(score, "estimated_value_usd", None))
    readiness = _n(getattr(score, "deal_readiness", None), 0) or 0
    strat_scores = getattr(score, "strategy_scores", None) or {} if score else {}
    strat_n = _n(strat_scores.get(strategy)) if isinstance(strat_scores, dict) else None

    soil_n = _norm(enrichment, "soil")
    flood_n = _norm(enrichment, "flood")
    wet_n = _norm(enrichment, "wetlands")
    infra_n = _norm(enrichment, "infrastructure")
    comps_n = _norm(enrichment, "comps")
    terr_n = _norm(enrichment, "terrain")
    growth_n = _norm(enrichment, "growth")
    access_n = _norm(enrichment, "access")

    flood_pct = _n(flood_n.get("flood_zone_pct"))
    flood_zone = flood_n.get("zone") or flood_n.get("flood_zone")
    wet_pct = _n(wet_n.get("wetland_pct"))
    prime = _n(soil_n.get("prime_farmland_pct"))
    farm_class = soil_n.get("farmland_classification")
    tx_m = _n(infra_n.get("nearest_transmission_m"))
    slope = _n(terr_n.get("avg_slope_pct"))
    max_slope = _n(terr_n.get("max_slope_pct"))
    access = (
        _n(access_n.get("legal_access_confidence"))
        or _n(comps_n.get("legal_access_confidence"))
        or _n(terr_n.get("legal_access_confidence"))
    )
    growth = _n(growth_n.get("path_of_growth_score")) or _n(comps_n.get("path_of_growth_score"))
    liq = _n(comps_n.get("liquidity_score"))
    zoning = _n(comps_n.get("zoning_development_friendly"))
    comps_count = comps_n.get("comps_count")
    try:
        comps_count = int(comps_count) if comps_count is not None else None
    except Exception:
        comps_count = None

    land_readouts = land_readouts or {}
    access_plain = _clip_plain(str((land_readouts.get("access") or {}).get("plain_english") or ""))
    soil_plain = _clip_plain(str((land_readouts.get("soil") or {}).get("plain_english") or ""))

    auction = comps_n.get("auction_path") if isinstance(comps_n.get("auction_path"), dict) else None
    if auction is None and enrichment and getattr(enrichment, "comps", None):
        raw_ap = (enrichment.comps.normalized or {}).get("auction_path")
        auction = raw_ap if isinstance(raw_ap, dict) else None
    settle = _n(auction.get("expected_settle_usd")) if auction else None
    opener = _n(auction.get("opening_bid_usd")) if auction else None
    settle_lo = _n(auction.get("settle_low_usd")) if auction else None
    settle_hi = _n(auction.get("settle_high_usd")) if auction else None
    infl = _n(auction.get("bid_inflation_mult_base")) if auction else None

    buy = settle if settle is not None else ask
    acres_s = f"{acres:,.2f} ac" if acres is not None else "acreage unpublished"
    buy_ppa = _ppa(buy, acres)
    est_ppa = _ppa(est, acres)
    ask_m = _money(ask)
    est_m = _money(est)
    settle_m = _money(settle)
    opener_m = _money(opener or ask)
    buy_m = _money(buy)

    flood_bit = (
        f"{flood_pct:.0f}% flood overlap" + (f" (zone {flood_zone})" if flood_zone else "")
        if flood_pct is not None
        else None
    )
    wet_bit = f"{wet_pct:.0f}% wetlands" if wet_pct is not None else None
    if prime is not None:
        soil_bit = f"{prime:.0f}% prime-farmland signal" + (
            f", class “{farm_class}”" if farm_class else ""
        )
    elif farm_class:
        soil_bit = f"soil class “{farm_class}”"
    else:
        soil_bit = None
    access_bit = f"legal-access confidence {access:.0f}/100" if access is not None else None
    slope_bit = None
    if slope is not None:
        slope_bit = f"avg slope {slope:.1f}%" + (
            f", max {max_slope:.1f}%" if max_slope is not None else ""
        )

    if auction and settle_m and est_m:
        price_bit = (
            f"likely auction finish {settle_m}"
            + (f" from opener {opener_m}" if opener_m else "")
            + f" against our {est_m}"
            + (f" ({disc:+.0f}%)" if disc is not None else "")
        )
    elif buy_m and est_m:
        price_bit = f"price screen {buy_m} vs our {est_m}" + (
            f" ({disc:+.0f}%)" if disc is not None else ""
        )
    elif est_m and buy_m is None:
        price_bit = f"no firm public ask; our desktop mark is {est_m}"
    elif buy_m:
        price_bit = f"process/public price {buy_m}"
    else:
        price_bit = None

    ppa_bit = (
        f"{buy_ppa} in vs {est_ppa} mark"
        if buy_ppa and est_ppa
        else (buy_ppa or est_ppa)
    )

    channel_bit = {
        "public_tax_sale": "county tax-sale",
        "public_surplus": "government surplus",
        "blm_lpad": "BLM federal disposal",
        "public_vacant_gis": "vacant GIS / no retail listing",
    }.get(provider, "public land channel")

    options: list[tuple[int, str]] = []

    def add(weight: int, q: str) -> None:
        q = " ".join(q.split())
        if q:
            options.append((weight, q))

    land_bits = ", ".join(b for b in (flood_bit, wet_bit, soil_bit, access_bit, slope_bit) if b)

    if price_bit and land_bits:
        add(
            6,
            f"On this {acres_s} {channel_bit} file in {place}: {price_bit}"
            + (f"; {ppa_bit}" if ppa_bit else "")
            + f". Land screen: {land_bits}. "
            f"Does a {strat_label} thesis still clear those exact constraints in your underwriting—"
            f"or does one number on this pin fail your niche filters?",
        )

    if auction and settle is not None and est is not None and acres is not None:
        add(
            6,
            f"Opener {opener_m or 'n/a'}, model finish {settle_m}"
            + (f" (band {_money(settle_lo)}–{_money(settle_hi)})" if settle_lo and settle_hi else "")
            + (f", ~{infl:.1f}× the start" if infl else "")
            + f", our value {est_m} on {acres_s} ({buy_ppa or 'n/a'} vs {est_ppa or 'n/a'}). "
            f"At the finish price—not the teaser—does this still fit the {strat_label} buys you fund in {county}?",
        )

    if disc is not None and est is not None and buy is not None and (flood_bit or wet_bit):
        constraint = flood_bit or wet_bit
        add(
            6,
            f"The gap reads {disc:+.0f}% ({buy_m} vs {est_m}) while {constraint} sits on the map "
            f"for {acres_s} in {place}. "
            f"Is that discount compensation for a constraint your {strat_label} niche already prices—"
            f"or a number that only works if you ignore the map layer?",
        )

    if flood_bit and wet_bit and acres is not None:
        hit = min(100.0, (flood_pct or 0) + (wet_pct or 0) * 0.5)
        use_bit = (
            f"For the {strat_label} use case ({strat_n:.0f}/100)"
            if strat_n is not None
            else f"For a {strat_label} use case"
        )
        add(
            5,
            f"{flood_bit}; {wet_bit} on {acres_s} at {place} "
            f"(combined water/wet stress read ~{hit:.0f}/100). {use_bit}, "
            f"can you underwrite usable ground and exit with those layers—"
            f"or does this pin fail your physical niche before price matters?",
        )

    if soil_bit and strategy == "FARMLAND" and (buy_ppa or est_ppa):
        add(
            5,
            f"Soil read: {soil_bit} on {acres_s} in {place}"
            + (f". {soil_plain}" if soil_plain else "")
            + f". Price screen {ppa_bit or buy_ppa or est_ppa}. "
            f"Does that dirt + $/ac stack match the farmland files you actually lease or farm—"
            f"or does yield math on this pin fail your niche even if the class label looks strong?",
        )

    if access_bit and access is not None and access < 70:
        add(
            5,
            f"{access_bit} on {acres_s} in {place}"
            + (f" — {access_plain}" if access_plain else "")
            + f". Best-use screen is {strat_label}"
            + (f" at {strat_n:.0f}/100" if strat_n is not None else "")
            + ". "
            f"Can your niche close and exit at that access confidence—"
            f"or is legal ingress the veto you require before capital moves?",
        )

    if slope_bit and strategy in ("DEVELOPMENT", "FARMLAND", "RECREATIONAL"):
        site_bits = (
            ", ".join(b for b in (flood_bit, wet_bit, access_bit) if b)
            or "limited other site metrics on file"
        )
        add(
            4,
            f"Terrain: {slope_bit} across {acres_s} in {place}, with {site_bits}. "
            f"Does that grade profile fit how you site {strat_label.lower()} deals—"
            f"or does slope alone knock this outside your niche?",
        )

    if tx_m is not None and (strategy == "ENERGY" or (tx_m < 2000 and opp >= 60)):
        add(
            5,
            f"Nearest transmission ~{tx_m:,.0f} m from the pin"
            + (f" ({pin})" if pin else "")
            + f" on {acres_s} in {place}"
            + (f"; {price_bit}" if price_bit else "")
            + f". Energy/use screen {strat_label}"
            + (f" {strat_n:.0f}/100" if strat_n is not None else "")
            + ". "
            f"Is that distance inside the interconnect envelope you underwrite—"
            f"or too far / too thin for your energy niche on this acreage?",
        )

    if growth is not None and strategy in ("DEVELOPMENT", "LAND_BANK"):
        add(
            4,
            f"Path-of-growth {growth:.0f}/100"
            + (f", zoning screen {zoning:.0f}/100" if zoning is not None else "")
            + f" on {acres_s} in {place}"
            + (f"; {price_bit}" if price_bit else "")
            + f". Risk {risk:.0f}/100, completeness {conf:.0f}/100. "
            f"Do those growth/zoning reads clear your {strat_label} hold thesis for {county}—"
            f"or is the land clock longer than your niche allows on this pin?",
        )

    if provider == "public_vacant_gis":
        add(
            5,
            f"Vacant GIS screen: {acres_s} in {place}, no clean retail ask"
            + (f", our mark {est_m}" if est_m else "")
            + (f", {flood_bit}" if flood_bit else "")
            + (f", {wet_bit}" if wet_bit else "")
            + (f", {access_bit}" if access_bit else "")
            + f", opportunity {opp:.0f}/100 · completeness {conf:.0f}/100. "
            f"Does your niche include owner-path / buyability work at this data density—"
            f"or do you require a priced, process-clear file before it qualifies?",
        )

    if provider in ("public_tax_sale", "public_surplus") and price_bit:
        add(
            5,
            f"{channel_bit.title()} in {place}: {price_bit} on {acres_s}"
            + (f"; {flood_bit}" if flood_bit else "")
            + (f"; {access_bit}" if access_bit else "")
            + f". Opportunity {opp:.0f}, risk {risk:.0f}. "
            f"At the process economics on this exact file, does it still pass your {strat_label} "
            f"niche rules—buy price, map constraints, and all—or only a cheap-paper screen?",
        )

    if comps_count is not None and comps_count < 3 and est_m:
        add(
            4,
            f"Only {comps_count} comps on file against our {est_m} mark for {acres_s} in {place}"
            + (f" ({ppa_bit})" if ppa_bit else "")
            + f". Completeness {conf:.0f}/100"
            + (f"; liquidity {liq:.0f}/100" if liq is not None else "")
            + ". "
            f"Is a thin-comp {strat_label} pin inside your niche—"
            f"or do you need a denser sales set before this county/size qualifies?",
        )

    if risk >= 55 and (flood_bit or wet_bit or access_bit):
        drivers = ", ".join(b for b in (flood_bit, wet_bit, access_bit, slope_bit) if b)
        add(
            5,
            f"Risk {risk:.0f}/100 on {acres_s} in {place}, with {drivers}"
            + (f"; {price_bit}" if price_bit else "")
            + ". "
            f"Which of those metrics does your {strat_label} book accept as normal on a buy—"
            f"and which one is a hard stop on this pin?",
        )

    dossier_parts = [acres_s, place]
    for bit in (flood_bit, wet_bit, soil_bit, access_bit, slope_bit, price_bit):
        if bit:
            dossier_parts.append(bit)
    dossier_parts.append(
        f"best-use {strat_label}" + (f" {strat_n:.0f}/100" if strat_n is not None else "")
    )
    dossier_parts.append(f"opportunity {opp:.0f} · risk {risk:.0f} · completeness {conf:.0f}")
    if readiness is not None:
        dossier_parts.append(f"basics on file {readiness:.0f}/100")

    if len(dossier_parts) >= 6:
        add(
            4,
            f"File dossier — {'; '.join(dossier_parts[:9])}. "
            f"Which reading is decisive for your niche, and does this {strat_label} pin in {county} still clear it?",
        )
    elif price_bit:
        add(
            3,
            f"{acres_s} in {place}: {price_bit}; best-use {strat_label}; "
            f"opportunity {opp:.0f}/100, risk {risk:.0f}/100, completeness {conf:.0f}/100. "
            f"Using only those figures, does this property fit the niche you underwrite—"
            f"or does a missing land screen mean it isn’t qualified yet?",
        )
    else:
        add(
            2,
            f"{acres_s} in {place} ({channel_bit}): best-use {strat_label}, "
            f"opportunity {opp:.0f}/100, risk {risk:.0f}/100, completeness {conf:.0f}/100"
            + (f", {access_bit}" if access_bit else "")
            + (f", {flood_bit}" if flood_bit else "")
            + ". "
            f"With the data actually on this pin, is it inside your niche filters—"
            f"or still unqualified until the thin fields fill in?",
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
            f"{settle:.0f}" if settle is not None else "ns",
            f"{opp:.0f}",
            f"{risk:.0f}",
        ]
    )
    question = _pick(seed, options)

    stings: list[tuple[int, str]] = []
    if flood_pct is not None and flood_pct >= 25:
        stings.append(
            (3, f"Lead with the flood figure ({flood_pct:.0f}%)—if that fails your niche, the discount is noise.")
        )
    if wet_pct is not None and wet_pct >= 20:
        stings.append((3, f"Wetlands at {wet_pct:.0f}% set the usable-acre math before strategy talk."))
    if access is not None and access < 65:
        stings.append((3, f"Access at {access:.0f}/100 is a gate metric on this pin."))
    if auction and settle is not None and opener is not None and settle > opener * 1.15:
        stings.append((3, f"Underwrite {settle_m}, not {opener_m}."))
    if disc is not None and disc < -10 and (flood_pct or 0) >= 20:
        stings.append(
            (
                3,
                f"A {abs(disc):.0f}% gap next to flood exposure is a tradeoff—"
                f"state which side of the trade your niche accepts.",
            )
        )
    if buy_ppa and est_ppa:
        stings.append(
            (2, f"Haircut {buy_ppa} for flood, wet, and access before you compare it to {est_ppa}.")
        )
    if ask_m and settle_m and ask_m != settle_m:
        stings.append((2, f"The operative number on this channel is {settle_m}, not {ask_m}."))
    stings.append((1, f"Decide from the pin’s metrics in {county}, not the opportunity score alone."))
    aftertaste = _pick(seed + "|sting", stings)

    return {
        "label": "Ask yourself",
        "question": question,
        "aftertaste": aftertaste,
    }
