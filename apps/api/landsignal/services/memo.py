"""Plain-English investment memo for a single property."""

from __future__ import annotations

from uuid import UUID

from landsignal.services.voice import display_title, place_phrase, this_property
from landsignal.store import MemoryStore


def verdict_from_score(opportunity: float, risk: float, confidence: float, deal_readiness: float) -> str:
    if opportunity < 40 or risk > 80:
        return "PASS FOR NOW"
    if opportunity >= 90 and confidence >= 75 and risk <= 35:
        return "LOOK CLOSELY NOW" if deal_readiness < 60 else "HIGH PRIORITY"
    if opportunity >= 75:
        return "WORTH WATCHING" if confidence < 55 else "LOOK CLOSELY NOW"
    return "KEEP ON THE LIST"


def _money(v) -> str:
    try:
        if v is None:
            return "not published"
        return f"${float(v):,.0f}"
    except Exception:
        return "not published"


def generate_memo(store: MemoryStore, parcel_id: UUID) -> str:
    parcel = store.parcels[parcel_id]
    listing = store.listing_for_parcel(parcel_id)
    score = store.latest_score(parcel_id)
    if score is None:
        return (
            "# Quick memo\n\n"
            "We don’t have a score for this property yet. Open the full details page once "
            "analysis finishes, then try again.\n"
        )

    verdict = verdict_from_score(
        score.opportunity, score.risk, score.confidence, score.deal_readiness
    )
    title = display_title(parcel, listing)
    place = place_phrase(parcel)
    prop = this_property(parcel, listing, with_place=True, with_acres=True)
    ask = listing.asking_price_usd if listing else None
    if ask is not None and ask <= 0:
        ask = None
    strat = score.best_strategy.value.replace("_", " ").title() if score.best_strategy else "Undetermined"
    secondary = (
        score.secondary_strategy.value.replace("_", " ").title()
        if score.secondary_strategy
        else None
    )
    disc = score.asking_discount_pct
    gap_line = (
        f"Buy price looks about {abs(disc):.0f}% {'under' if disc < 0 else 'over'} our "
        f"{_money(score.estimated_value_usd)} estimate."
        if disc is not None and score.estimated_value_usd
        else f"Our estimated value is {_money(score.estimated_value_usd)} (no public ask on this feed)."
    )

    def bullets(items: list[str], empty: str) -> list[str]:
        cleaned = [f"- {x}" for x in (items or []) if x]
        return cleaned if cleaned else [f"- {empty}"]

    lines = [
        f"# Quick memo — {title}",
        "",
        f"**Bottom line:** {verdict}",
        "",
        f"This one-page note summarizes {prop}. It is a first look for humans — "
        f"not an appraisal, title opinion, or buy order.",
        "",
        "## Snapshot",
        f"- Opportunity score: {score.opportunity:.0f}/100",
        f"- Risk: {score.risk:.0f}/100 (lower is calmer)",
        f"- How complete the file is: {score.confidence:.0f}/100",
        f"- Ready to pursue: {score.deal_readiness:.0f}/100",
        f"- Best use we see: {strat}"
        + (f" (next: {secondary})" if secondary else ""),
        f"- Published price: {_money(ask)}",
        f"- Our estimate: {_money(score.estimated_value_usd)}",
        f"- {gap_line}",
        "",
        "## Why it stands out",
        *bullets(score.why_interesting, "No strong standout signal beyond the scores above."),
        "",
        "## Price read",
        *bullets(score.why_mispriced, "Price case is thin — confirm with the selling office."),
        "",
        "## What could go wrong",
        *bullets(score.what_could_kill, "See the risk score and map layers on the details page."),
        "",
        "## Why it might still be available",
        *bullets(score.why_still_available, "No single clear reason in the public file."),
        "",
        "## Homework before any bid",
    ]
    hw = [f"- [ ] {x}" for x in (score.manual_verification or [])]
    if not hw:
        hw = ["- [ ] Confirm title, access, and flood/wetlands with local professionals."]
    lines.extend(hw)
    lines.extend(
        [
            "",
            "## Recommendation",
            (
                f"**{verdict}.** Use the official posting / county office to verify price and process. "
                f"LandSignal ranks public opportunities — it never buys land for you."
            ),
            "",
            f"_Place: {place}. Screening model {score.algorithm_version}._",
        ]
    )
    return "\n".join(lines)
