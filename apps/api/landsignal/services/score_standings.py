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
        # Contribution to 0–100 opportunity (pre-lift) ≈ value * weight
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
    """Compact, true sitewide context for this opportunity score."""
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
    lifts = [f for f in factors if f["direction"] == "up"][:3]
    drags = sorted(factors, key=lambda r: r["gap"], reverse=True)[:3]

    # Why not 90? — honest ceiling for process/public land screens
    why_not: list[str] = []
    if top is not None and opp < 90:
        if top < 90:
            why_not.append(
                f"Across {n:,} live files, the top score right now is {top:.0f} — "
                f"90 is above anything currently indexed."
            )
        else:
            why_not.append(
                f"Only the rarest files clear 90. This one sits at {opp:.0f}."
            )
    if drags:
        top_drag = drags[0]
        if top_drag["gap"] >= 2:
            why_not.append(
                f"Biggest hold-back: {top_drag['label']} at {top_drag['score']:.0f}/100 "
                f"(~{top_drag['gap']:.0f} pts left on the table)."
            )
    risk = _f(getattr(score, "risk", None))
    if risk is not None and risk >= 40:
        why_not.append(
            f"Risk screen is {risk:.0f}/100 — the engine won’t hand out elite scores while that stays elevated."
        )
    if not why_not:
        why_not.append(
            "Scores are a weighted blend of price edge, land quality, growth, access, and risk — "
            "not a grade for ‘how good the dirt looks’ alone."
        )

    shown = round(opp)
    if top is not None and shown >= round(top) and beats_pct >= 90:
        rank_plain = (
            f"{shown} is at the top of the live board "
            f"(beats ~{beats_pct:.0f}% of {n:,} scored files; site high ≈ {top:.0f})."
        )
    elif beats_pct >= 95:
        rank_plain = f"{shown} is elite here — beats about {beats_pct:.0f}% of live inventory."
    elif beats_pct >= 80:
        rank_plain = f"{shown} is a strong scout file — beats about {beats_pct:.0f}% of live inventory."
    elif beats_pct >= 50:
        rank_plain = f"{shown} is above the middle of the pack (median ~{median:.0f})."
    else:
        rank_plain = f"{shown} sits below the site median (~{median:.0f}) — open stronger files first."

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
        "factors": factors[:8],
        "lifts": lifts,
        "drags": drags,
        "why_not_higher": why_not[:3],
        "rank_plain": rank_plain,
        "ceiling_plain": (
            f"On LandSignal, public-process files rarely clear ~{p95:.0f}–{top:.0f}. "
            f"A {opp:.0f} in {place} is already near the top of what’s live."
            if top is not None and p95 is not None and opp >= (p75 or 0)
            else f"Live inventory median is ~{median:.0f}; top files reach ~{top:.0f}."
            if median is not None and top is not None
            else "Standings refresh as live inventory scores."
        ),
        "method_plain": (
            "Opportunity is a 0–100 blend: price vs our estimate, land quality, use options, "
            "area growth, roads/power, resale ease, scarcity, seller/channel pressure, and risk. "
            "Chart = every scored live parcel on the site right now."
        ),
    }
