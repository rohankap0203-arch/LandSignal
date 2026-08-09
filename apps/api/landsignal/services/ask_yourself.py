"""One clarifying self-check for the intelligence page — data + feeling, not a grilling."""

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
    """Prefer richer, parcel-specific lines; hash only within the top tier."""
    if not options:
        return ""
    best = max(w for w, _ in options)
    floor = max(2, best - 1) if best >= 2 else best
    pool = [q for w, q in options if w >= floor] or [q for _, q in options]
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return pool[int(digest[:12], 16) % len(pool)]


def _ppa(price: float | None, acres: float | None) -> str | None:
    if price is None or acres is None or acres <= 0:
        return None
    return f"${price / acres:,.0f}/ac"


def build_ask_yourself(
    *,
    parcel,
    listing,
    score,
    land_readouts: dict | None = None,
    enrichment=None,
) -> dict[str, str]:
    """
    A single question that helps the buyer exhale — either into a clearer yes
    or a clean no — using this pin’s real shape, without shaming them.
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

    options: list[tuple[int, str]] = []

    def add(weight: int, q: str) -> None:
        q = " ".join(q.split())
        if q:
            options.append((weight, q))

    # --- Calm, specific middle-ground questions ---

    if auction and settle_m and opener_m and est_m:
        add(
            5,
            f"Picture yourself owning {acres_s} in {place} after {channel} — not at the "
            f"{opener_m} opener, but near the more likely {settle_m} finish (our mark is {est_m}). "
            f"Does that version of the deal still feel like {niche} for you, or does naming the "
            f"real number make the excitement settle into something quieter and clearer?",
        )

    if disc is not None and est_m and buy_m and (flood_pct is not None or wet_pct is not None):
        water = []
        if flood_pct is not None:
            water.append(
                f"about {flood_pct:.0f}% flood overlap"
                + (f" (zone {flood_zone})" if flood_zone else "")
            )
        if wet_pct is not None:
            water.append(f"about {wet_pct:.0f}% wetlands")
        water_s = " and ".join(water)
        add(
            5,
            f"This pin screens roughly {abs(disc):.0f}% "
            f"{'under' if disc < 0 else 'over'} our {est_m} mark, with {water_s} on the map. "
            f"When you hold both truths at once — the price story and the water story — "
            f"does your body lean toward ‘this is my kind of {strat_label.lower()} risk,’ "
            f"or toward relief that you noticed before you chased it?",
        )

    if flood_pct is not None and flood_pct >= 15:
        add(
            4,
            f"Roughly {flood_pct:.0f}% of the checked ground on this {acres_s} in {place} "
            f"touches flood"
            + (f" (zone {flood_zone})" if flood_zone else "")
            + ". "
            f"If you bought tomorrow, would that water be a constraint you already know how to live with "
            f"in a {strat_label.lower()} plan — or the detail that lets you breathe and pass without regret?",
        )

    if wet_pct is not None and wet_pct >= 12:
        add(
            4,
            f"About {wet_pct:.0f}% wetlands show up on {acres_s} in {place}. "
            f"Does ‘usable for what I actually do’ still feel honest after that number — "
            f"or is this the moment the map gives you permission to want a drier pin?",
        )

    if access is not None and access < 70:
        add(
            4,
            f"Legal-access confidence sits around {access:.0f}/100 on this {place} file. "
            f"Can you picture yourself calm owning land while that question is still open — "
            f"or does comfort for you start only after the road and deed path feel settled?",
        )

    if soil_bit := (
        f"{prime:.0f}% prime-farmland signal"
        if prime is not None
        else (f"soil marked “{farm_class}”" if farm_class else None)
    ):
        if strategy == "FARMLAND" or (prime is not None and prime >= 35):
            add(
                4,
                f"The soil read says {soil_bit} on {acres_s} in {place}"
                + (f", around {buy_ppa}" if buy_ppa else "")
                + (f" versus our {est_ppa} mark" if est_ppa and buy_ppa else "")
                + ". "
                f"Does that dirt match the farmland story you came looking for — "
                f"or are you noticing you’d rather admire good soil than operate it?",
            )

    if slope is not None and slope >= 8:
        add(
            3,
            f"Average slope reads about {slope:.1f}% across {acres_s} in {place}. "
            f"In your mind’s eye, is that rolling land you want to walk and hold — "
            f"or steeper than the {strat_label.lower()} use you quietly assumed?",
        )

    if tx_m is not None and (strategy == "ENERGY" or tx_m < 2500):
        add(
            4,
            f"Transmission sits roughly {tx_m:,.0f} meters from this pin on {acres_s} in {place}. "
            f"Does that proximity feel like optional upside you understand — "
            f"or like a story that isn’t really why you’d sleep well owning this ground?",
        )

    if growth is not None and strategy in ("DEVELOPMENT", "LAND_BANK"):
        add(
            3,
            f"Path-of-growth screens around {growth:.0f}/100 for {acres_s} in {place}. "
            f"Are you someone who feels steady waiting on that kind of clock — "
            f"or does saying it out loud remind you that patience isn’t the niche you’re in right now?",
        )

    if provider == "public_vacant_gis":
        add(
            4,
            f"This is {acres_s} on a vacant map in {place} — not a clean priced listing"
            + (f", with our desktop mark near {est_m}" if est_m else "")
            + ". "
            f"Does the work of confirming a real buy path feel like your kind of hunt — "
            f"or does comfort for you mean waiting for a file that’s already clearer?",
        )

    if provider in ("public_tax_sale", "public_surplus") and buy_m:
        add(
            4,
            f"You’re looking at {channel} for {acres_s} in {place}, with a realistic money path "
            f"near {buy_m}"
            + (f" against our {est_m}" if est_m else "")
            + ". "
            f"When the process stress and the land itself are both in the frame, "
            f"does this still feel like a property you’d be glad to explain to a partner — "
            f"or is the helpful answer that it’s interesting, but not yours?",
        )

    if risk >= 55:
        bits = []
        if flood_pct is not None and flood_pct >= 15:
            bits.append(f"{flood_pct:.0f}% flood")
        if wet_pct is not None and wet_pct >= 12:
            bits.append(f"{wet_pct:.0f}% wetlands")
        if access is not None and access < 70:
            bits.append(f"access {access:.0f}/100")
        driver = (", ".join(bits) + " in the mix") if bits else "a few open questions still in the file"
        add(
            4,
            f"Risk on this pin reads {risk:.0f}/100, with {driver}. "
            f"That’s not a verdict — it’s a mirror. Does knowing that make you feel more oriented "
            f"toward a deliberate {strat_label.lower()} yes, or gently steered toward something simpler?",
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
        )

    # Soft universal anchors (still parcel-specific)
    add(
        2,
        f"Forget the scoreboard for a breath. You’re looking at {acres_s} in {place}, via {channel}, "
        f"reading best as {strat_label} — {niche}. "
        f"When you imagine your name on it, do you feel a quiet yes, or a quiet thank-you for looking closely enough to walk away?",
    )

    if buy_m and est_m:
        add(
            3,
            f"Buy screen near {buy_m}, our value near {est_m}"
            + (f" ({buy_ppa} vs {est_ppa})" if buy_ppa and est_ppa else "")
            + f", on {acres_s} in {place}. "
            f"Does that math leave you feeling grounded enough to keep going — "
            f"or relieved that the numbers talked you out of forcing a fit?",
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
    question = _pick(seed, options)

    stings: list[tuple[int, str]] = []
    if auction and settle_m and opener_m and settle and opener and settle > opener * 1.15:
        stings.append(
            (3, f"It’s okay to decide at {settle_m}. The opener ({opener_m}) is just how the story starts.")
        )
    if flood_pct is not None and flood_pct >= 20:
        stings.append(
            (3, f"Water on {flood_pct:.0f}% of the check isn’t a scare tactic — it’s clarity you can use.")
        )
    if wet_pct is not None and wet_pct >= 15:
        stings.append((3, f"Wetlands at {wet_pct:.0f}% simply redefine what ‘usable’ means for you."))
    if access is not None and access < 65:
        stings.append(
            (3, "Needing a clearer access path before you feel at ease is a solid instinct, not hesitation.")
        )
    if disc is not None and disc < -10:
        stings.append(
            (
                2,
                f"A ~{abs(disc):.0f}% gap under our mark only helps if the land’s constraints still fit your life.",
            )
        )
    if opp >= 70 and risk < 50:
        stings.append(
            (2, "A calmer file can be permission to proceed — or permission to admit it still isn’t your niche.")
        )
    stings.append(
        (1, "Either answer is a win: a clearer yes, or a clean no before the wrong land costs you sleep.")
    )
    aftertaste = _pick(seed + "|sting", stings)

    return {
        "label": "Ask yourself",
        "question": question,
        "aftertaste": aftertaste,
    }
