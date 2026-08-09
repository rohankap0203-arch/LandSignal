"""One hard, parcel-specific self-interrogation for the intelligence page."""

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


def _money(v: float | None) -> str:
    if v is None:
        return "an unpriced entry"
    return f"${v:,.0f}"


def _pick(seed: str, options: list[str]) -> str:
    if not options:
        return ""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    idx = int(digest[:12], 16) % len(options)
    return options[idx]


def build_ask_yourself(
    *,
    parcel,
    listing,
    score,
    land_readouts: dict | None = None,
    enrichment=None,
) -> dict[str, str]:
    """Return a single sniper question tailored to this pin's tensions."""
    acres = _n(getattr(parcel, "acreage", None))
    state = (getattr(parcel, "state", None) or "US").upper()
    county = getattr(parcel, "county", None) or "this county"
    place = f"{county}, {state}"
    apn = getattr(parcel, "apn", None) or ""
    lat = getattr(parcel, "latitude", None)
    lon = getattr(parcel, "longitude", None)
    pin = f"{lat:.4f},{lon:.4f}" if lat is not None and lon is not None else "pin"

    provider = (listing.provider_id if listing else None) or "unknown"
    ask = listing.asking_price_usd if listing else None
    strategy = (
        score.best_strategy.value
        if score and getattr(score, "best_strategy", None)
        else "UNDETERMINED"
    )
    opp = _n(getattr(score, "opportunity", None), 0) or 0
    risk = _n(getattr(score, "risk", None), 0) or 0
    conf = _n(getattr(score, "confidence", None), 0) or 0
    disc = _n(getattr(score, "asking_discount_pct", None))
    est = _n(getattr(score, "estimated_value_usd", None))
    readiness = _n(getattr(score, "deal_readiness", None), 0) or 0

    soil_n: dict = {}
    flood_n: dict = {}
    wet_n: dict = {}
    infra_n: dict = {}
    if enrichment:
        if enrichment.soil:
            soil_n = enrichment.soil.normalized or enrichment.soil.value or {}
        if enrichment.flood:
            flood_n = enrichment.flood.normalized or enrichment.flood.value or {}
        if enrichment.wetlands:
            wet_n = enrichment.wetlands.normalized or enrichment.wetlands.value or {}
        if enrichment.infrastructure:
            infra_n = enrichment.infrastructure.normalized or enrichment.infrastructure.value or {}

    land_readouts = land_readouts or {}
    flood_pct = _n(flood_n.get("flood_zone_pct"))
    wet_pct = _n(wet_n.get("wetland_pct"))
    prime = _n(soil_n.get("prime_farmland_pct"))
    tx_m = _n(infra_n.get("nearest_transmission_m"))

    auction = None
    if enrichment and enrichment.comps:
        auction = (enrichment.comps.normalized or {}).get("auction_path")
    if not isinstance(auction, dict):
        auction = None
    settle = _n(auction.get("expected_settle_usd")) if auction else None
    opener = _n(auction.get("opening_bid_usd")) if auction else None

    acres_s = f"{acres:,.1f}-acre" if acres is not None else "this"
    size_feel = (
        "postage-stamp"
        if acres is not None and acres < 5
        else "mid-size working"
        if acres is not None and acres < 40
        else "serious acreage"
        if acres is not None and acres < 160
        else "empire-scale"
        if acres is not None
        else "unmeasured"
    )
    niche = {
        "FARMLAND": "tillable dirt and cash-rent math",
        "DEVELOPMENT": "entitlement risk and exit to a builder",
        "LAND_BANK": "patient capital and a long clock",
        "RECREATIONAL": "recreation, privacy, and weekends that actually get used",
        "ENERGY": "grid adjacency and power-of-position",
        "TIMBER": "stand value and harvest timing",
    }.get(strategy, "whatever niche you claim as your edge")

    channel = {
        "public_tax_sale": "a tax-sale process",
        "public_surplus": "a surplus/disposal process",
        "blm_lpad": "a federal disposal path",
        "public_vacant_gis": "a vacant map screen with no clean retail listing",
    }.get(provider, "a public land channel")

    candidates: list[str] = []

    # --- Strategy / niche fit ---
    candidates.append(
        f"If your real edge is {niche}, does this {acres_s} pin in {place} belong in that book—"
        f"or are you about to stretch your thesis because the screen looked clever?"
    )
    candidates.append(
        f"Be honest: when you picture your next five wins, is a {strategy.replace('_', ' ').lower()} "
        f"play in {county} the pattern—or is this the shiny outlier your ego wants to justify?"
    )
    candidates.append(
        f"Would you still want this {acres_s} tract in {place} if a friend bought the identical file "
        f"tomorrow and asked you to underwrite it cold—with no FOMO attached?"
    )

    # --- Channel psychology ---
    if provider in ("public_tax_sale", "public_surplus"):
        candidates.append(
            f"Are you hunting {niche} in {county}, or hunting the dopamine of {channel}—"
            f"where the opener looks kind and the finish rarely is?"
        )
        candidates.append(
            f"If this tax/process file in {place} blows past your number, will you walk—"
            f"or will ‘I’ve already researched it’ become the reason you overpay?"
        )
    if provider == "public_vacant_gis":
        candidates.append(
            f"This is a map screen in {place}, not a clean ask. Is chasing owner-path uncertainty "
            f"actually your niche—or are you confusing ‘visible on GIS’ with ‘buyable this quarter’?"
        )
    if provider == "blm_lpad":
        candidates.append(
            f"Federal disposal land in {place} moves on process, not vibes. Does that tempo match "
            f"how you actually deploy capital—or only how you like to browse?"
        )

    # --- Auction / price gap ---
    if auction and settle is not None:
        candidates.append(
            f"The opener may whisper {_money(opener or ask)}, but the likely finish is near {_money(settle)}. "
            f"Is your niche buying the whisper—or can you still love this pin at the louder number?"
        )
    if disc is not None and disc < -12 and est is not None:
        candidates.append(
            f"‘About {abs(disc):.0f}% under our value’ feels like destiny. Is the discount recruiting you "
            f"into a file whose risk ({risk:.0f}/100) you would never accept at full price?"
        )
    if disc is not None and disc > 8 and est is not None:
        candidates.append(
            f"You’re staring at a pin that screens roughly {disc:.0f}% over our mark of {_money(est)}. "
            f"Is paying up part of your niche—or are you negotiating with hope?"
        )
    if ask is None and provider == "public_vacant_gis":
        candidates.append(
            f"No public price. Opportunity {opp:.0f}/100. Does your niche include buying optionality "
            f"in {county} with a thin file—or do you need a number before your pulse counts?"
        )

    # --- Land hazards as emotional traps ---
    if flood_pct is not None and flood_pct >= 20:
        candidates.append(
            f"Roughly {flood_pct:.0f}% of this checked area in {place} looks flood-touched. "
            f"Is water risk inside your niche—or are you about to romanticize cheap acres you’ll never insure cleanly?"
        )
    if wet_pct is not None and wet_pct >= 15:
        candidates.append(
            f"About {wet_pct:.0f}% wetlands on the read. Can you say out loud that constrained ground "
            f"is what you buy on purpose—not what you’re tolerating because the pin is pretty?"
        )
    if prime is not None and prime >= 40 and strategy == "FARMLAND":
        candidates.append(
            f"Prime farmland signals look real (~{prime:.0f}%). That’s flattering. "
            f"Do you actually farm or lease dirt in {state}—or are you collecting a soil grade like a trophy?"
        )
    if tx_m is not None and tx_m < 2500 and strategy == "ENERGY":
        candidates.append(
            f"Transmission sits roughly {tx_m:,.0f} m away. Cool map energy. "
            f"Is interconnect optionality truly your niche in {county}, or a story you like telling yourself?"
        )

    # --- Size / hold psychology ---
    if acres is not None:
        candidates.append(
            f"This is {size_feel} ground ({acres:,.1f} ac) in {place}. "
            f"Does that scale match the deals you finish—or the deals you fantasize about at 1 a.m.?"
        )
    if strategy in ("LAND_BANK", "TIMBER", "DEVELOPMENT"):
        candidates.append(
            f"The best-use screen points to {strategy.replace('_', ' ').title()}—a long clock. "
            f"Can your capital, attention, and identity sit in {county} for years without needing a win next month?"
        )

    # --- Confidence / readiness gut checks ---
    if conf < 45:
        candidates.append(
            f"The file is thin (completeness {conf:.0f}/100) at {pin}. "
            f"Is underwriting fog your niche—or are you mistaking incomplete data for hidden alpha?"
        )
    if readiness < 50:
        candidates.append(
            f"Basics on file sit at {readiness:.0f}/100. Before you fall in love with {acres_s} acres in {place}, "
            f"ask: do you buy incomplete stories in your niche, or do you wait until the map stops lying by omission?"
        )
    if risk >= 55:
        candidates.append(
            f"Risk reads {risk:.0f}/100 on this pin. In your real niche—not your browsing niche—"
            f"is that the kind of heat you get paid for, or the kind you apologize for later?"
        )
    if opp >= 75:
        candidates.append(
            f"Opportunity {opp:.0f}/100 will try to close the sale in your head. "
            f"Ignore the score for ten seconds: is a {strategy.replace('_', ' ').lower()} file in {county} "
            f"still the land you want your name on?"
        )

    # --- Always-on niche closer ---
    candidates.append(
        f"Strip the charts. Is this {acres_s} property in {place} actually inside the niche you claim—"
        f"{niche}—or did the interface just make you feel like a sharper buyer than you are today?"
    )
    candidates.append(
        f"If you could only own one more land file this year, would it be this one in {county}—"
        f"or are you collecting tabs because walking away feels like losing?"
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
            f"{opp:.0f}",
            f"{risk:.0f}",
            pin,
        ]
    )
    question = _pick(seed, candidates)

    aftertastes = [
        f"If the answer hesitates, the niche already voted no.",
        f"A clean yes feels quiet. A maybe usually means you’re shopping for a feeling.",
        f"Your edge is repetition. One-off romance is expensive.",
        f"Niche fit is a filter, not a vibe. Use it.",
    ]
    aftertaste = _pick(seed + "|sting", aftertastes)

    return {
        "label": "Ask yourself",
        "question": question,
        "aftertaste": aftertaste,
    }
