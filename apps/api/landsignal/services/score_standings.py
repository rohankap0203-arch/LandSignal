"""Sitewide opportunity standings — how this score stacks up for real."""

from __future__ import annotations

from typing import Any

from landsignal.services.humanize import CATEGORY_HELP


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def collect_live_opportunity_scores(store) -> list[float]:
    """Non-demo, scored parcels currently in inventory."""
    out: list[float] = []
    for pid, parcel in store.parcels.items():
        if getattr(parcel, "is_demo", False):
            continue
        score = store.latest_score(pid)
        if not score:
            continue
        listing = store.listing_for_parcel(pid)
        if not listing:
            continue
        opp = _f(getattr(score, "opportunity", None))
        if opp is None:
            continue
        out.append(max(0.0, min(100.0, opp)))
    return out


def _percentile_rank(sorted_vals: list[float], value: float) -> float:
    """% of scores strictly below this value (0–100)."""
    if not sorted_vals:
        return 0.0
    below = sum(1 for v in sorted_vals if v < value)
    return 100.0 * below / len(sorted_vals)


def _quantile(sorted_vals: list[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def build_histogram(scores: list[float], *, buckets: int = 10) -> list[dict[str, Any]]:
    """Equal-width 0–100 histogram."""
    width = 100.0 / buckets
    counts = [0] * buckets
    for s in scores:
        idx = min(buckets - 1, int(s // width))
        counts[idx] += 1
    peak = max(counts) if counts else 1
    out = []
    for i, n in enumerate(counts):
        lo = int(i * width)
        hi = int((i + 1) * width)
        out.append(
            {
                "lo": lo,
                "hi": hi,
                "label": f"{lo}–{hi}",
                "count": n,
                "share": round(n / len(scores), 4) if scores else 0.0,
                "bar": round(n / peak, 4) if peak else 0.0,
            }
        )
    return out


def build_factor_contributions(score) -> list[dict[str, Any]]:
    """Weighted category contributions — what pushed / held the opportunity score."""
    rows: list[dict[str, Any]] = []
    for c in (getattr(score, "components", None) or []):
        key = str(c.get("category") or c.get("label") or "")
        if not key:
            continue
        val = _f(c.get("value")) or 0.0
        weight = _f(c.get("weight")) or 0.0
        help_row = CATEGORY_HELP.get(key, {})
        contribution = val * weight
        gap_to_perfect = max(0.0, (100.0 - val) * weight)
        rows.append(
            {
                "key": key,
                "label": help_row.get("title") or key.replace("_", " ").title(),
                "simple": help_row.get("simple") or "",
                "score": round(val, 1),
                "weight_pct": round(weight * 100),
                "contribution": round(contribution, 1),
                "gap": round(gap_to_perfect, 1),
                "direction": "up" if val >= 62 else "mid" if val >= 45 else "down",
            }
        )
    rows.sort(key=lambda r: r["contribution"], reverse=True)
    return rows


def build_opportunity_standings(
    *,
    store,
    score,
    place: str = "this area",
) -> dict[str, Any]:
    """Compact, personal sitewide context for this opportunity score."""
    opp = _f(getattr(score, "opportunity", None)) or 0.0
    opp = max(0.0, min(100.0, opp))
    live = collect_live_opportunity_scores(store)
    live_sorted = sorted(live)
    n = len(live_sorted)
    median = _quantile(live_sorted, 0.5)
    p75 = _quantile(live_sorted, 0.75)
    p90 = _quantile(live_sorted, 0.90)
    p95 = _quantile(live_sorted, 0.95)
    top = live_sorted[-1] if live_sorted else None
    percentile = _percentile_rank(live_sorted, opp)
    beats_pct = round(percentile, 0)
    factors = build_factor_contributions(score)
    lifts = [f for f in factors if f["direction"] == "up"][:2]
    drags = sorted(factors, key=lambda r: r["gap"], reverse=True)[:2]
    shown = round(opp)
    risk = _f(getattr(score, "risk", None))

    # One personal lead line — what THIS number means for the buyer
    if top is not None and shown >= round(top) and beats_pct >= 90:
        rank_plain = (
            f"Your {shown} is as high as anything live right now "
            f"(beats ~{beats_pct:.0f}% of {n:,} files)."
        )
    elif beats_pct >= 90:
        rank_plain = (
            f"Your {shown} is elite — ahead of ~{beats_pct:.0f}% of live files "
            f"(site high ≈ {top:.0f})."
        )
    elif beats_pct >= 70:
        rank_plain = (
            f"Your {shown} is a strong scout pick — ahead of ~{beats_pct:.0f}% "
            f"(median ~{median:.0f})."
        )
    elif beats_pct >= 50:
        rank_plain = (
            f"Your {shown} sits above the middle of the pack (median ~{median:.0f})."
        )
    else:
        rank_plain = (
            f"Your {shown} is below the site median (~{median:.0f}) — "
            f"open stronger files first."
        )

    # Single short "why not 90" — personal + dynamic
    why_not: list[str] = []
    if top is not None and shown < 90:
        if round(top) < 90:
            why_bits = [f"Nothing live clears 90 — top on site is {top:.0f}"]
        else:
            why_bits = [f"90 is rare; you’re at {shown}"]
        if drags and drags[0]["gap"] >= 2:
            why_bits.append(
                f"{drags[0]['label'].lower()} is the main drag "
                f"({drags[0]['score']:.0f}/100)"
            )
        elif risk is not None and risk >= 40:
            why_bits.append(f"risk screen is still {risk:.0f}")
        why_not.append(" · ".join(why_bits) + ".")
    elif drags and drags[0]["gap"] >= 2:
        why_not.append(
            f"Room left mostly in {drags[0]['label'].lower()} "
            f"({drags[0]['score']:.0f}/100)."
        )
    if not why_not:
        why_not.append(
            "It’s a weighted buy-edge screen — price, land, growth, access, risk — "
            "not a dirt beauty grade."
        )

    # Short punch for what the number conveys
    if beats_pct >= 90:
        meaning = (
            f"In {place}, {shown} means this file is already near the ceiling of "
            f"what LandSignal is indexing."
        )
    elif beats_pct >= 60:
        meaning = (
            f"In {place}, {shown} means a real scoutable edge vs typical live inventory."
        )
    else:
        meaning = (
            f"In {place}, {shown} means a middling edge — useful context, not a rush."
        )

    return {
        "score": round(opp, 1),
        "sample_n": n,
        "beats_pct": beats_pct,
        "percentile": round(percentile, 1),
        "median": round(median, 1) if median is not None else None,
        "p75": round(p75, 1) if p75 is not None else None,
        "p90": round(p90, 1) if p90 is not None else None,
        "p95": round(p95, 1) if p95 is not None else None,
        "max": round(top, 1) if top is not None else None,
        "histogram": build_histogram(live),
        "factors": factors[:3],
        "lifts": lifts,
        "drags": drags,
        "why_not_higher": why_not[:1],
        "rank_plain": rank_plain,
        "ceiling_plain": meaning,
        "method_plain": None,
    }
