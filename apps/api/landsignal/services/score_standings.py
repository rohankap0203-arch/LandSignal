"""Sitewide score standings — how opportunity / risk / completeness stack up."""

from __future__ import annotations

from typing import Any, Literal

from landsignal.services.humanize import CATEGORY_HELP

MetricKind = Literal["opportunity", "risk", "confidence"]


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def collect_live_metric_scores(store, attr: str) -> list[float]:
    """Non-demo, scored parcels currently in inventory for one metric."""
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
        val = _f(getattr(score, attr, None))
        if val is None:
            continue
        out.append(max(0.0, min(100.0, val)))
    return out


def collect_live_opportunity_scores(store) -> list[float]:
    return collect_live_metric_scores(store, "opportunity")


def _percentile_rank(sorted_vals: list[float], value: float) -> float:
    """Average-rank / midrank percentile (0–100).

    Strictly-below ranks blow up when inventory clusters on one score (e.g. almost
    every fast-scored file at risk≈45 → “safer than 100%”). Midrank gives ties the
    middle of their band so a typical file reads ~50%, not 100%.
    """
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    below = sum(1 for v in sorted_vals if v < value)
    equal = sum(1 for v in sorted_vals if v == value)
    if equal <= 0:
        # Value not in sample — still report share strictly below.
        return 100.0 * below / n
    return 100.0 * (below + 0.5 * equal) / n


def _tie_share(sorted_vals: list[float], value: float) -> float:
    """Fraction of the live sample tied at this exact score (0–1)."""
    if not sorted_vals:
        return 0.0
    return sum(1 for v in sorted_vals if v == value) / len(sorted_vals)


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


def _enrichment_maps(enrichment) -> tuple[dict, dict, dict, dict]:
    soil_n = flood_n = wet_n = access_n = {}
    if enrichment:
        if enrichment.soil:
            soil_n = enrichment.soil.normalized or enrichment.soil.value or {}
        if enrichment.flood:
            flood_n = enrichment.flood.normalized or enrichment.flood.value or {}
        if enrichment.wetlands:
            wet_n = enrichment.wetlands.normalized or enrichment.wetlands.value or {}
        if enrichment.access:
            access_n = enrichment.access.normalized or enrichment.access.value or {}
    return soil_n, flood_n, wet_n, access_n


def build_risk_factors(*, enrichment=None, listing=None, risk: float) -> list[dict[str, Any]]:
    """Compact drivers that push the risk number (higher = more worry)."""
    soil_n, flood_n, wet_n, access_n = _enrichment_maps(enrichment)
    flood = _f(flood_n.get("flood_zone_pct"))
    wet = _f(wet_n.get("wetland_pct"))
    access = _f(access_n.get("legal_access_confidence"))
    provider = getattr(listing, "provider_id", None) if listing else None
    rows: list[dict[str, Any]] = []

    if flood is not None:
        rows.append(
            {
                "key": "flood",
                "label": "Flood overlap",
                "simple": "Share of the pin in a mapped flood zone.",
                "score": round(min(100.0, flood * 1.1), 1),
                "weight_pct": 28,
                "contribution": round(min(100.0, flood * 1.1) * 0.28, 1),
                "gap": round(max(0.0, flood - 10.0), 1),
                "direction": "up" if flood >= 25 else "mid" if flood >= 10 else "down",
            }
        )
    if wet is not None:
        rows.append(
            {
                "key": "wetlands",
                "label": "Wetlands",
                "simple": "Mapped wetland share that can cut usable acres.",
                "score": round(wet, 1),
                "weight_pct": 24,
                "contribution": round(wet * 0.24, 1),
                "gap": round(max(0.0, wet - 8.0), 1),
                "direction": "up" if wet >= 20 else "mid" if wet >= 10 else "down",
            }
        )
    if access is not None:
        access_risk = max(0.0, min(100.0, 100.0 - access))
        rows.append(
            {
                "key": "access",
                "label": "Access clarity",
                "simple": "How unclear legal road access looks on desktop.",
                "score": round(access_risk, 1),
                "weight_pct": 22,
                "contribution": round(access_risk * 0.22, 1),
                "gap": round(access_risk, 1),
                "direction": "up" if access < 45 else "mid" if access < 70 else "down",
            }
        )
    if provider in ("public_tax_sale", "blm_lpad", "public_surplus"):
        rows.append(
            {
                "key": "process",
                "label": "Public process",
                "simple": "Title / clearing friction on auction-style channels.",
                "score": 55.0,
                "weight_pct": 18,
                "contribution": 9.9,
                "gap": 20.0,
                "direction": "mid",
            }
        )
    if not rows:
        rows.append(
            {
                "key": "thin",
                "label": "Thin risk file",
                "simple": "Not enough map inputs — risk held near neutral.",
                "score": round(risk, 1),
                "weight_pct": 100,
                "contribution": round(risk, 1),
                "gap": round(abs(risk - 35.0), 1),
                "direction": "mid",
            }
        )
    rows.sort(key=lambda r: r["contribution"], reverse=True)
    return rows


def build_confidence_factors(*, enrichment=None, score=None, conf: float) -> list[dict[str, Any]]:
    """Five drivers for how complete the file is (higher = fuller)."""
    soil_n, flood_n, wet_n, access_n = _enrichment_maps(enrichment)
    comps_n: dict = {}
    growth_n: dict = {}
    if enrichment:
        if getattr(enrichment, "comps", None):
            comps_n = enrichment.comps.normalized or enrichment.comps.value or {}
        if getattr(enrichment, "growth", None):
            growth_n = enrichment.growth.normalized or enrichment.growth.value or {}
    prime = _f(soil_n.get("prime_farmland_pct"))
    flood = _f(flood_n.get("flood_zone_pct"))
    wet = _f(wet_n.get("wetland_pct"))
    access = _f(access_n.get("legal_access_confidence"))
    growth = _f(growth_n.get("path_of_growth_score")) or _f(comps_n.get("path_of_growth_score"))
    liquidity = _f(comps_n.get("liquidity_score"))
    est = _f(getattr(score, "estimated_value_usd", None)) if score else None
    market_present = growth is not None or liquidity is not None
    market_score = growth if growth is not None else liquidity
    rows: list[dict[str, Any]] = []

    def _row(key: str, label: str, present: bool, score_v: float | None = None) -> dict[str, Any]:
        s = 78.0 if present else 18.0
        if present and score_v is not None:
            s = max(55.0, min(92.0, 60.0 + score_v * 0.2))
        w = 20.0
        return {
            "key": key,
            "label": label,
            "simple": "On file" if present else "Still missing",
            "score": round(s, 1),
            "weight_pct": 20,
            "contribution": round(s * (w / 100.0), 1),
            "gap": round(0.0 if present else w, 1),
            "direction": "up" if present else "down",
        }

    rows.append(_row("soil", "Soil screen", prime is not None, prime))
    rows.append(_row("flood", "Flood screen", flood is not None, flood))
    rows.append(_row("wetlands", "Wetland screen", wet is not None, wet))
    rows.append(_row("value", "Value mark", est is not None, None))
    rows.append(_row("access", "Access screen", access is not None, access))
    # Prefer access; if missing, still surface a fifth market-context factor.
    if access is None:
        rows[-1] = _row("market", "Market context", market_present, market_score)
    # Sort: missing first for "gap", then by contribution
    rows.sort(key=lambda r: (0 if r["direction"] == "down" else 1, -r["contribution"]))
    # Keep a sense of completeness level in the list order for display
    if conf >= 65:
        rows.sort(key=lambda r: r["contribution"], reverse=True)
    return rows[:5]


def _base_stats(live: list[float], value: float) -> dict[str, Any]:
    live_sorted = sorted(live)
    n = len(live_sorted)
    median = _quantile(live_sorted, 0.5)
    p75 = _quantile(live_sorted, 0.75)
    p90 = _quantile(live_sorted, 0.90)
    p95 = _quantile(live_sorted, 0.95)
    top = live_sorted[-1] if live_sorted else None
    low = live_sorted[0] if live_sorted else None
    percentile = _percentile_rank(live_sorted, value)
    return {
        "live_sorted": live_sorted,
        "n": n,
        "median": median,
        "p75": p75,
        "p90": p90,
        "p95": p95,
        "top": top,
        "low": low,
        "percentile": percentile,
        "beats_pct": round(percentile, 0),
        "tie_share": round(_tie_share(live_sorted, value), 4),
    }


def build_opportunity_standings(
    *,
    store,
    score,
    place: str = "this area",
) -> dict[str, Any]:
    """Compact, personal sitewide context for this opportunity score."""
    opp = _f(getattr(score, "opportunity", None)) or 0.0
    opp = max(0.0, min(100.0, opp))
    live = collect_live_metric_scores(store, "opportunity")
    stats = _base_stats(live, opp)
    n = stats["n"]
    median = stats["median"]
    top = stats["top"]
    beats_pct = stats["beats_pct"]
    if beats_pct >= 100:
        beats_pct = 99.0
    factors = build_factor_contributions(score)
    lifts = [f for f in factors if f["direction"] == "up"][:2]
    drags = sorted(factors, key=lambda r: r["gap"], reverse=True)[:2]
    shown = round(opp)
    tie_share = float(stats.get("tie_share") or 0.0)

    if n and tie_share >= 0.55:
        rank_plain = (
            f"Your {shown} sits in the common live-file band "
            f"(~{tie_share * 100:.0f}% of {n:,} share this score; median ~{median:.0f})."
        )
        beats_pct = 50.0
    elif top is not None and shown >= round(top) and beats_pct >= 90:
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

    # Keep only site-high + how this score compares (dynamic).
    why_not: list[str] = []
    if top is not None and median is not None:
        why_not.append(
            f"Top on the site right now is {top:.0f}. Yours is {shown} — "
            f"ahead of ~{beats_pct:.0f}% of live files (middle is ~{median:.0f})."
        )
    elif top is not None:
        why_not.append(
            f"Top on the site right now is {top:.0f}. Yours is {shown} — "
            f"ahead of ~{beats_pct:.0f}% of live files."
        )
    else:
        why_not.append(
            f"Yours is {shown} — ahead of ~{beats_pct:.0f}% of live files on the site."
        )

    if beats_pct >= 90:
        meaning = f"Compared with live listings, {shown} is near the top of the site."
    elif beats_pct >= 60:
        meaning = f"Compared with live listings, {shown} is above most files on the site."
    else:
        meaning = f"Compared with live listings, {shown} sits near or below the middle."

    return {
        "kind": "opportunity",
        "polarity": "higher_better",
        "score": round(opp, 1),
        "sample_n": n,
        "beats_pct": beats_pct,
        "tie_share": round(tie_share, 4),
        "percentile": round(stats["percentile"], 1),
        "median": round(median, 1) if median is not None else None,
        "p75": round(stats["p75"], 1) if stats["p75"] is not None else None,
        "p90": round(stats["p90"], 1) if stats["p90"] is not None else None,
        "p95": round(stats["p95"], 1) if stats["p95"] is not None else None,
        "max": round(top, 1) if top is not None else None,
        "min": round(stats["low"], 1) if stats["low"] is not None else None,
        "histogram": build_histogram(live),
        "factors": factors[:3],
        "lifts": lifts,
        "drags": drags,
        "why_not_higher": why_not[:1],
        "why_label": "Why not 90",
        "factors_label": f"What’s in your {shown}",
        "meta_best_label": "Site high",
        "rank_plain": rank_plain,
        "ceiling_plain": meaning,
        "method_plain": None,
    }


def build_risk_standings(
    *,
    store,
    score,
    enrichment=None,
    listing=None,
    place: str = "this area",
) -> dict[str, Any]:
    """Compact sitewide context for risk (lower is better)."""
    risk = _f(getattr(score, "risk", None)) or 0.0
    risk = max(0.0, min(100.0, risk))
    live = collect_live_metric_scores(store, "risk")
    stats = _base_stats(live, risk)
    n = stats["n"]
    median = stats["median"]
    top = stats["top"]
    low = stats["low"]
    # Safer than ≈ share with higher risk via midrank (ties → ~50%, not 100%).
    safer_pct = round(100.0 - stats["percentile"], 0) if n else 0.0
    # Never claim a literal 100% — midrank of a unique low still rounds there.
    if safer_pct >= 100:
        safer_pct = 99.0
    tie_share = float(stats.get("tie_share") or 0.0)
    shown = round(risk)
    factors = build_risk_factors(enrichment=enrichment, listing=listing, risk=risk)
    lifts = [f for f in factors if f["direction"] == "up"][:2]
    calm = [f for f in factors if f["direction"] == "down"][:2]

    # Degenerate cluster (most files share this score) — don't overclaim rank.
    if n and tie_share >= 0.55:
        rank_plain = (
            f"Your {shown} matches the common live-file band "
            f"(~{tie_share * 100:.0f}% of {n:,} sit here; median ~{median:.0f})."
        )
        safer_pct = 50.0
    elif n and shown <= round(low or shown) and safer_pct >= 90 and tie_share < 0.25:
        rank_plain = (
            f"Your {shown} is among the calmest live files "
            f"(safer than ~{safer_pct:.0f}% of {n:,})."
        )
    elif safer_pct >= 75:
        rank_plain = (
            f"Your {shown} is relatively calm — safer than ~{safer_pct:.0f}% "
            f"(median risk ~{median:.0f})."
        )
    elif safer_pct >= 45:
        rank_plain = (
            f"Your {shown} sits near typical risk on site (median ~{median:.0f})."
        )
    else:
        rank_plain = (
            f"Your {shown} is elevated vs the pack (median ~{median:.0f}) — "
            f"homework before you stretch."
        )

    why_not: list[str] = []
    if lifts and lifts[0]["score"] >= 20:
        why_not.append(
            f"{lifts[0]['label']} is the main push "
            f"({lifts[0]['score']:.0f}/100 on the risk screen)."
        )
    elif shown <= 35:
        why_not.append(
            "Map flags look light — title and access still need a human check."
        )
    else:
        why_not.append(
            "Desktop risk blends flood, wetlands, access, and process friction — "
            "not a title opinion."
        )

    if tie_share >= 0.55:
        meaning = (
            f"In {place}, {shown} is the usual desktop risk band — not a standout calm file."
        )
    elif safer_pct >= 75:
        meaning = f"In {place}, {shown} means fewer yellow flags than most live files."
    elif safer_pct >= 45:
        meaning = f"In {place}, {shown} means ordinary scout risk — fixable with homework."
    else:
        meaning = f"In {place}, {shown} means constraints are doing real work on this pin."

    return {
        "kind": "risk",
        "polarity": "lower_better",
        "score": round(risk, 1),
        "sample_n": n,
        "beats_pct": safer_pct,
        "tie_share": round(tie_share, 4),
        "percentile": round(stats["percentile"], 1),
        "median": round(median, 1) if median is not None else None,
        "p75": round(stats["p75"], 1) if stats["p75"] is not None else None,
        "p90": round(stats["p90"], 1) if stats["p90"] is not None else None,
        "p95": round(stats["p95"], 1) if stats["p95"] is not None else None,
        "max": round(top, 1) if top is not None else None,
        "min": round(low, 1) if low is not None else None,
        "histogram": build_histogram(live),
        "factors": factors[:3],
        "lifts": lifts,
        "drags": calm,
        "why_not_higher": why_not[:1],
        "why_label": "Why not lower",
        "factors_label": f"What’s in your {shown}",
        "meta_best_label": "Site low",
        "meta_best_value": round(low, 1) if low is not None else None,
        "rank_plain": rank_plain,
        "ceiling_plain": meaning,
        "method_plain": None,
    }


def build_confidence_standings(
    *,
    store,
    score,
    enrichment=None,
    place: str = "this area",
) -> dict[str, Any]:
    """Compact sitewide context for file completeness."""
    conf = _f(getattr(score, "confidence", None)) or 0.0
    conf = max(0.0, min(100.0, conf))
    live = collect_live_metric_scores(store, "confidence")
    stats = _base_stats(live, conf)
    n = stats["n"]
    median = stats["median"]
    top = stats["top"]
    beats_pct = stats["beats_pct"]
    if beats_pct >= 100:
        beats_pct = 99.0
    shown = round(conf)
    factors = build_confidence_factors(enrichment=enrichment, score=score, conf=conf)
    missing = [f for f in factors if f["direction"] == "down"]
    have = [f for f in factors if f["direction"] == "up"]
    tie_share = float(stats.get("tie_share") or 0.0)

    if n and tie_share >= 0.55:
        rank_plain = (
            f"Your {shown} matches the usual completeness band "
            f"(~{tie_share * 100:.0f}% of {n:,} sit here; median ~{median:.0f})."
        )
        beats_pct = 50.0
    elif top is not None and shown >= round(top) and beats_pct >= 90:
        rank_plain = (
            f"Your {shown} is as filled-in as anything live "
            f"(ahead of ~{beats_pct:.0f}% of {n:,} files)."
        )
    elif beats_pct >= 70:
        rank_plain = (
            f"Your {shown} is a fuller file than ~{beats_pct:.0f}% "
            f"(median ~{median:.0f})."
        )
    elif beats_pct >= 45:
        rank_plain = (
            f"Your {shown} is about average completeness (median ~{median:.0f})."
        )
    else:
        rank_plain = (
            f"Your {shown} is thinner than most live files (median ~{median:.0f}) — "
            f"treat scores as tips."
        )

    why_not: list[str] = []
    if missing:
        labels = ", ".join(f["label"].lower() for f in missing[:2])
        why_not.append(f"Still thin on {labels}.")
    elif shown < 90:
        why_not.append(
            f"90 means dense desktop coverage; you’re at {shown} with the screens we have."
        )
    else:
        why_not.append("Dense enough for a first go / no-go — still verify on the ground.")

    if beats_pct >= 70:
        meaning = f"In {place}, {shown} means enough layers for a first call."
    elif beats_pct >= 40:
        meaning = f"In {place}, {shown} means partly filled — open the checks before you bid."
    else:
        meaning = f"In {place}, {shown} means a tip sheet, not a finished diligence pack."

    # Always surface all five completeness factors (missing first when thin).
    shown_factors = (missing + have)[:5] if shown < 55 else (have + missing)[:5]

    return {
        "kind": "confidence",
        "polarity": "higher_better",
        "score": round(conf, 1),
        "sample_n": n,
        "beats_pct": beats_pct,
        "tie_share": round(tie_share, 4),
        "percentile": round(stats["percentile"], 1),
        "median": round(median, 1) if median is not None else None,
        "p75": round(stats["p75"], 1) if stats["p75"] is not None else None,
        "p90": round(stats["p90"], 1) if stats["p90"] is not None else None,
        "p95": round(stats["p95"], 1) if stats["p95"] is not None else None,
        "max": round(top, 1) if top is not None else None,
        "min": round(stats["low"], 1) if stats["low"] is not None else None,
        "histogram": build_histogram(live),
        "factors": shown_factors,
        "lifts": have[:2],
        "drags": missing[:2],
        "why_not_higher": why_not[:1],
        "why_label": "Why not 90",
        "factors_label": f"What’s in your {shown}",
        "meta_best_label": "Site high",
        "rank_plain": rank_plain,
        "ceiling_plain": meaning,
        "method_plain": None,
    }
