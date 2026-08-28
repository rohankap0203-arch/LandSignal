"""Data confidence (evidence quality) — separate from Opportunity Score."""

from __future__ import annotations

from typing import Any, Mapping


def compute_data_confidence(row: Mapping[str, Any]) -> dict[str, Any]:
    """0–100 evidence score. Never blended into opportunity."""
    score = 35.0
    reasons: list[str] = []

    sources = row.get("sources") or []
    if isinstance(sources, list):
        n = len({str(s) for s in sources if s})
        score += min(20, n * 8)
        if n:
            reasons.append(f"{n} source(s)")

    def present(key: str) -> bool:
        v = row.get(key)
        if isinstance(v, dict):
            return v.get("value") is not None
        return v is not None and v != ""

    for key, pts, label in (
        ("acreage", 10, "acreage"),
        ("latitude", 8, "coordinates"),
        ("asking_price_usd", 10, "asking price"),
        ("ask", 10, "asking price"),
        ("apn", 8, "APN"),
        ("attomId", 12, "ATTOM id"),
        ("attom_id", 12, "ATTOM id"),
        ("address", 6, "address"),
    ):
        if present(key):
            score += pts
            reasons.append(label)

    verification = str(row.get("listingVerification") or row.get("listing_verification") or "unverified").lower()
    if verification == "verified":
        score += 12
        reasons.append("verified listing")
    elif verification == "probable":
        score += 5

    market = str(row.get("marketStatus") or row.get("market_status") or "unknown").lower()
    if market == "active_listing":
        score += 6
    elif market == "off_market":
        score -= 2

    # Missing critical fields
    if not present("acreage") and not present("acres"):
        score -= 8
        reasons.append("missing acres")
    if not present("state"):
        score -= 15

    # Conflicts
    conflicts = row.get("data_conflicts") or row.get("conflicts") or []
    if conflicts:
        score -= min(20, 5 * len(conflicts))
        reasons.append("field conflicts")

    score = max(0.0, min(100.0, score))
    return {
        "data_confidence": round(score, 1),
        "data_confidence_display": f"{round(score):.0f}%",
        "data_confidence_reasons": reasons[:8],
    }
