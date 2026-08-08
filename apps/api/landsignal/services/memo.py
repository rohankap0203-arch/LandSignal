from __future__ import annotations

from uuid import UUID

from landsignal.store import MemoryStore


def verdict_from_score(opportunity: float, risk: float, confidence: float, deal_readiness: float) -> str:
    if opportunity < 40 or risk > 80:
        return "REJECT"
    if opportunity >= 90 and confidence >= 75 and risk <= 35:
        return "INVESTIGATE IMMEDIATELY" if deal_readiness < 60 else "HIGH PRIORITY"
    if opportunity >= 75:
        return "WATCH" if confidence < 55 else "INVESTIGATE IMMEDIATELY"
    return "PASS"


def generate_memo(store: MemoryStore, parcel_id: UUID) -> str:
    parcel = store.parcels[parcel_id]
    listing = store.listing_for_parcel(parcel_id)
    score = store.latest_score(parcel_id)
    if score is None:
        return "# Investment Memo\n\nNo score available. Run analysis first.\n"

    verdict = verdict_from_score(
        score.opportunity, score.risk, score.confidence, score.deal_readiness
    )
    title = listing.title if listing else (parcel.apn or str(parcel.id))
    def bullets(items: list[str], empty: str) -> list[str]:
        return [f"- {x}" for x in items] if items else [empty]

    lines = [
        f"# LandSignal Investment Memo — {title}",
        "",
        f"**Verdict:** {verdict}",
        "",
        "## Executive Summary",
        f"- LandSignal Score: {score.opportunity}/100",
        f"- Risk: {score.risk}/100",
        f"- Confidence: {score.confidence}%",
        f"- Asymmetry: {score.asymmetry}/100",
        f"- Deal Readiness: {score.deal_readiness}/100",
        f"- Best Strategy: {score.best_strategy.value if score.best_strategy else None}",
        f"- Secondary Strategy: {score.secondary_strategy.value if score.secondary_strategy else None}",
        f"- Ask: {listing.asking_price_usd if listing else 'N/A'}",
        f"- Model Value: {score.estimated_value_usd}",
        f"- Discount/Premium: {score.asking_discount_pct}",
        "",
        "## Investment Thesis",
        *bullets(score.why_interesting, "- Insufficient thesis signals"),
        "",
        "## Property Overview",
        f"- Location: {parcel.county}, {parcel.state}",
        f"- APN: {parcel.apn}",
        f"- Acreage: {parcel.acreage}",
        f"- Geometry confidence: {parcel.geometry_confidence}",
        "",
        "## Valuation",
        f"- Asking discount/premium to model base: {score.asking_discount_pct}%",
        *bullets(score.why_mispriced, "- No mispricing narrative"),
        "",
        "## Highest & Best Use",
        f"- Screens: {score.strategy_screens}",
        f"- Strategy scores: {score.strategy_scores}",
        "",
        "## Risks",
        *bullets(score.what_could_kill, "- See risk score"),
        "",
        "## Why It May Still Be Available",
        *bullets(score.why_still_available, "- Unknown"),
        "",
        "## Due Diligence Items",
        *[f"- [ ] {x}" for x in score.manual_verification],
        "",
        "## Recommendation",
        f"{verdict}. This system does not execute purchases. A human investor must decide.",
        "",
        f"_Algorithm {score.algorithm_version} / weights {score.weight_version} / hash {score.input_hash}_",
        "",
        "> Screening only — not an appraisal, title opinion, survey, or offer authorization.",
    ]
    return "\n".join(lines)
