"""Appreciation / depreciation history for every parcel.

We rarely get a full closed-sale tape on public GIS feeds. When we don't, we
build a transparent TREND_PROXY path from:
  - state land-value growth regimes (farmland / metro-fringe style priors)
  - channel type (tax-sale, BLM, surplus, retail-like)
  - acreage class, soil/flood/wetland screens, census growth when present
  - any observed ask / assessed / sale marks in listing.raw

Every series is anchored to this parcel's current screening mark (or ask),
so the chart is always parcel-specific — never a blank generic chart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# Annualized land-value regime priors (%/yr), screening only — not appraisals.
# Tuned to long-run farmland / fringe land patterns by state cluster.
STATE_ANNUAL_APPRECIATION = {
    # Strong growth / constrained supply
    "CA": 0.055,
    "WA": 0.048,
    "OR": 0.042,
    "CO": 0.045,
    "UT": 0.050,
    "ID": 0.048,
    "AZ": 0.052,
    "FL": 0.050,
    "TX": 0.045,
    "NV": 0.040,
    "TN": 0.042,
    "NC": 0.040,
    "GA": 0.038,
    "SC": 0.036,
    # Midwest farmland belt (steadier, often lower %)
    "IA": 0.032,
    "IL": 0.030,
    "IN": 0.028,
    "OH": 0.027,
    "MN": 0.030,
    "WI": 0.028,
    "MI": 0.026,
    "MO": 0.025,
    "NE": 0.028,
    "KS": 0.022,
    "SD": 0.024,
    "ND": 0.022,
    # South / plains
    "AL": 0.030,
    "MS": 0.026,
    "AR": 0.028,
    "LA": 0.027,
    "OK": 0.024,
    "KY": 0.028,
    "VA": 0.034,
    "MD": 0.032,
    "PA": 0.026,
    "NY": 0.028,
    "NJ": 0.030,
    "NM": 0.030,
    "MT": 0.034,
    "WY": 0.028,
    "AK": 0.020,
    "HI": 0.040,
    "DC": 0.035,
}

CHANNEL_MULT = {
    "public_tax_sale": 0.72,  # distressed path — lags retail land indexes
    "public_surplus": 0.80,
    "blm_lpad": 0.55,  # federal disposal — thin, slow, process-bound
    "manual": 1.0,
    "csv": 1.0,
}

# Soft drawdowns / spikes by year offset (relative to today) for realism —
# 2020–21 land boom, 2022–23 rate-shock cooling, then re-acceleration in Sun Belt.
CYCLE_SHAPERS = {
    -10: 0.96,
    -9: 0.97,
    -8: 0.98,
    -7: 0.99,
    -6: 1.00,
    -5: 1.01,
    -4: 1.04,  # late-2010s / early pandemic bid
    -3: 1.08,  # 2021-ish land strength
    -2: 0.97,  # rate shock
    -1: 0.99,
    0: 1.00,
    1: 1.01,
    2: 1.02,
    3: 1.03,
}


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _money(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"${v:,.0f}"


def _extract_observed_marks(raw: dict | None, ask: float | None) -> list[dict[str, Any]]:
    """Pull any year/value pairs that look like assessments or prior sales."""
    raw = raw or {}
    marks: list[dict[str, Any]] = []
    pairs = [
        ("sale_year", "sale_price", "Prior sale"),
        ("SaleYear", "SalePrice", "Prior sale"),
        ("SALE_YEAR", "SALE_PRICE", "Prior sale"),
        ("year_built", None, None),  # ignore
        ("assessed_year", "assessed_value", "Assessed"),
        ("ASSESSYR", "TOTASSESS", "Assessed"),
        ("tax_year", "market_value", "Tax roll mark"),
        ("TAXYEAR", "MARKET_VALUE", "Tax roll mark"),
        ("AppraisalYear", "MarketValue", "Appraisal"),
    ]
    for yk, vk, label in pairs:
        if not vk:
            continue
        y, v = raw.get(yk), _f(raw.get(vk))
        try:
            yi = int(float(y)) if y is not None else None
        except Exception:
            yi = None
        if yi and v and v > 0 and 1980 <= yi <= datetime.now(timezone.utc).year + 1:
            marks.append({"year": yi, "value_usd": v, "label": label, "source": "listing_raw"})
    # Flat assessed / market without year → pin to last year
    for key, label in (
        ("assessed_value", "Assessed"),
        ("market_value", "Market / tax roll"),
        ("MARKET_VALUE", "Market / tax roll"),
        ("TOTASSESS", "Assessed"),
        ("appraised_value", "Appraised"),
    ):
        v = _f(raw.get(key))
        if v and v > 0 and not any(m["label"] == label for m in marks):
            marks.append(
                {
                    "year": datetime.now(timezone.utc).year - 1,
                    "value_usd": v,
                    "label": label,
                    "source": "listing_raw",
                }
            )
    if ask and ask > 0:
        marks.append(
            {
                "year": datetime.now(timezone.utc).year,
                "value_usd": ask,
                "label": "Published ask / opener",
                "source": "listing",
            }
        )
    # Dedupe by year keeping highest label priority
    by_year: dict[int, dict] = {}
    for m in sorted(marks, key=lambda x: x["year"]):
        by_year[m["year"]] = m
    return [by_year[y] for y in sorted(by_year)]


def _base_annual_rate(
    *,
    state: str | None,
    provider_id: str | None,
    acres: float | None,
    growth_score: float | None,
    prime_pct: float | None,
    flood_pct: float | None,
    wet_pct: float | None,
) -> tuple[float, list[str]]:
    st = (state or "").upper()
    base = STATE_ANNUAL_APPRECIATION.get(st, 0.028)
    notes = [f"State land regime prior for {st or 'US'}: {base*100:.1f}%/yr"]
    ch = CHANNEL_MULT.get(provider_id or "", 0.9)
    if ch != 1.0:
        notes.append(
            f"Channel {provider_id} multiplies trend by {ch:.2f} "
            f"(distressed/federal paths lag retail indexes)"
        )
    rate = base * ch

    if growth_score is not None:
        # growth 50 → no change; 80 → +1.2pp; 20 → -1.2pp
        adj = (growth_score - 50) / 50 * 0.012
        rate += adj
        notes.append(f"Census/path-of-growth {growth_score:.0f} adjusts annual rate by {adj*100:+.1f} pp")

    if acres is not None:
        if acres < 2:
            rate *= 0.85
            notes.append("Sub-2 ac urban/tax-sale class: softer, lumpier path (−15% rate)")
        elif acres >= 80:
            rate *= 1.05
            notes.append("Institutional scale (≥80 ac): slightly stronger farmland/fringe path (+5%)")

    if prime_pct is not None and prime_pct >= 50 and (acres or 0) >= 10:
        rate += 0.004
        notes.append(f"Prime farmland screen {prime_pct:.0f}% adds +0.4 pp")
    if flood_pct is not None and flood_pct >= 30:
        rate -= 0.006
        notes.append(f"Flood overlap {flood_pct:.0f}% subtracts −0.6 pp")
    if wet_pct is not None and wet_pct >= 25:
        rate -= 0.004
        notes.append(f"Wetlands {wet_pct:.0f}% subtracts −0.4 pp")

    # Clamp to sane land ranges
    rate = max(-0.04, min(0.12, rate))
    return rate, notes


def build_market_trajectory(
    *,
    parcel,
    listing=None,
    score=None,
    enrichment=None,
    years_back: int = 10,
    years_forward: int = 3,
) -> dict[str, Any]:
    """Always returns a parcel-bound appreciation/depreciation series."""
    state = getattr(parcel, "state", None)
    county = getattr(parcel, "county", None)
    apn = getattr(parcel, "apn", None) or "parcel"
    acres = _f(getattr(parcel, "acreage", None))
    provider = getattr(listing, "provider_id", None) if listing else None
    ask = _f(getattr(listing, "asking_price_usd", None) if listing else None)
    if ask is not None and ask <= 0:
        ask = None
    est = _f(getattr(score, "estimated_value_usd", None) if score else None)

    growth_n = {}
    soil_n = {}
    flood_n = {}
    wet_n = {}
    comps_n = {}
    if enrichment:
        if enrichment.growth:
            growth_n = enrichment.growth.normalized or enrichment.growth.value or {}
        if enrichment.soil:
            soil_n = enrichment.soil.normalized or enrichment.soil.value or {}
        if enrichment.flood:
            flood_n = enrichment.flood.normalized or enrichment.flood.value or {}
        if enrichment.wetlands:
            wet_n = enrichment.wetlands.normalized or enrichment.wetlands.value or {}
        if enrichment.comps:
            comps_n = enrichment.comps.normalized or enrichment.comps.value or {}

    growth_score = _f(growth_n.get("path_of_growth_score"))
    if growth_score is None:
        growth_score = _f(comps_n.get("path_of_growth_score"))
    prime = _f(soil_n.get("prime_farmland_pct"))
    flood = _f(flood_n.get("flood_zone_pct"))
    wet = _f(wet_n.get("wetland_pct"))

    annual, method_notes = _base_annual_rate(
        state=state,
        provider_id=provider,
        acres=acres,
        growth_score=growth_score,
        prime_pct=prime,
        flood_pct=flood,
        wet_pct=wet,
    )

    # Anchor: screening mark preferred; else ask; else synthetic prior
    anchor = est or ask
    if anchor is None:
        from landsignal.services.analyze import STATE_PPA_PRIOR

        ppa = STATE_PPA_PRIOR.get((state or "").upper(), 3000)
        anchor = ppa * (acres or 1.0)
        method_notes.append(f"No mark/ask — anchored to state PPA prior ${_money(ppa)}/ac × acres")

    raw = (listing.raw if listing else None) or {}
    observed = _extract_observed_marks(raw, ask=None)  # don't double-count ask as history
    observed_years = {m["year"] for m in observed}
    has_observed = len(observed) >= 2

    now_y = datetime.now(timezone.utc).year
    points: list[dict[str, Any]] = []

    # Walk backward then forward from today using compounded annual + cycle shaper
    # Value_t = anchor / Π(1+r_eff) for past years
    # Calibrate so year 0 = anchor
    past_vals: dict[int, float] = {0: float(anchor)}
    for k in range(1, years_back + 1):
        shaper = CYCLE_SHAPERS.get(-k, 1.0)
        # effective one-year factor looking back
        factor = (1.0 + annual) * shaper
        past_vals[-k] = past_vals[-k + 1] / max(factor, 0.85)

    future_vals: dict[int, float] = {0: float(anchor)}
    for k in range(1, years_forward + 1):
        shaper = CYCLE_SHAPERS.get(k, 1.0)
        factor = (1.0 + annual) * shaper
        # Forward slightly conservative vs history
        future_vals[k] = future_vals[k - 1] * (1.0 + annual * 0.9) * (0.98 + 0.02 * shaper)

    for offset in range(-years_back, years_forward + 1):
        year = now_y + offset
        if offset <= 0:
            val = past_vals[offset]
            kind = "history"
        else:
            val = future_vals[offset]
            kind = "outlook"
        # Blend observed marks when present in that year
        obs = next((m for m in observed if m["year"] == year), None)
        if obs:
            # Pull series toward observed mark (70% observed / 30% trend)
            val = 0.7 * obs["value_usd"] + 0.3 * val
            point_src = "blended_observed"
            note = f"{obs['label']} mark blended into trend"
        else:
            point_src = "trend_proxy"
            note = "Regime trend for this state/channel/parcel class"
        points.append(
            {
                "year": year,
                "offset": offset,
                "value_usd": round(val, 0),
                "kind": kind,
                "source": point_src,
                "note": note,
            }
        )

    # Stats
    y0 = next(p for p in points if p["offset"] == 0)
    y_5 = next((p for p in points if p["offset"] == -5), None)
    y_10 = next((p for p in points if p["offset"] == -years_back), None)
    y_fwd = next((p for p in points if p["offset"] == years_forward), None)

    def _cagr(start: dict | None, end: dict | None) -> float | None:
        if not start or not end or start["value_usd"] <= 0:
            return None
        yrs = max(1, end["year"] - start["year"])
        return (end["value_usd"] / start["value_usd"]) ** (1 / yrs) - 1

    cagr_5 = _cagr(y_5, y0)
    cagr_10 = _cagr(y_10, y0)
    cagr_fwd = _cagr(y0, y_fwd)

    # Peak / trough in history window
    hist = [p for p in points if p["kind"] == "history"]
    peak = max(hist, key=lambda p: p["value_usd"]) if hist else y0
    trough = min(hist, key=lambda p: p["value_usd"]) if hist else y0
    from_peak = (y0["value_usd"] - peak["value_usd"]) / peak["value_usd"] if peak["value_usd"] else 0
    from_trough = (y0["value_usd"] - trough["value_usd"]) / trough["value_usd"] if trough["value_usd"] else 0

    if from_peak < -0.03:
        regime = "DEPRECIATING_FROM_PEAK"
        regime_label = f"Down {abs(from_peak)*100:.0f}% from the {peak['year']} high"
    elif cagr_5 is not None and cagr_5 >= 0.03:
        regime = "APPRECIATING"
        regime_label = f"Rising about {cagr_5*100:.1f}% per year over 5 years"
    elif cagr_5 is not None and cagr_5 <= 0:
        regime = "FLAT_TO_DOWN"
        regime_label = f"Flat to soft · about {cagr_5*100:.1f}% per year over 5 years"
    else:
        regime = "MODEST_GROWTH"
        regime_label = f"Slow rise · about {(cagr_5 or 0)*100:.1f}% per year over 5 years"

    knowledge = "BLENDED" if has_observed else "TREND_PROXY"
    knowledge_label = (
        "Mixed: tax-roll marks + local trend"
        if has_observed
        else "Estimate from similar land in this area"
    )
    confidence = 55 if has_observed else 38
    if growth_score is not None:
        confidence += 8
    if prime is not None or flood is not None:
        confidence += 5
    confidence = min(78, confidence)

    identity = f"{apn} · {county or 'County'}, {(state or 'US').upper()}"
    if acres is not None:
        identity += f" · {acres:,.2f} acres"

    headline = (
        f"For {identity}: {regime_label}. "
        f"Today’s path value ~{_money(y0['value_usd'])}"
        + (f". Ten years ago on this path: {_money(y_10['value_usd'])}" if y_10 else "")
        + (
            f". In about {years_forward} years (outlook): {_money(y_fwd['value_usd'])}"
            if y_fwd
            else ""
        )
        + "."
    )

    summary_bullets = [
        f"Typical yearly change we use for this listing: {annual*100:.1f}% ({knowledge_label}).",
        (
            f"Last 5 years on this path: about {cagr_5*100:+.1f}% per year"
            if cagr_5 is not None
            else "5-year path not available"
        ),
        (
            f"Last 10 years on this path: about {cagr_10*100:+.1f}% per year"
            if cagr_10 is not None
            else "10-year path not available"
        ),
        (
            f"Next {years_forward} years (cautious outlook): about {cagr_fwd*100:+.1f}% per year"
            if cagr_fwd is not None
            else "Forward outlook not modeled"
        ),
        (
            f"Highest point in the window: {_money(peak['value_usd'])} in {peak['year']}. "
            f"Lowest: {_money(trough['value_usd'])} in {trough['year']}."
        ),
    ]
    if has_observed:
        summary_bullets.append(
            f"We folded in {len(observed)} tax-roll / sale figure(s) from this listing’s source feed."
        )
    else:
        summary_bullets.append(
            "This public feed has no multi-year sale history for this parcel, "
            "so the chart follows similar land in this state and listing type — not recorded deeds."
        )

    spark = [p["value_usd"] for p in points if p["kind"] == "history"]

    return {
        "identity": identity,
        "headline": headline,
        "regime": regime,
        "regime_label": regime_label,
        "knowledge_state": knowledge,
        "knowledge_label": knowledge_label,
        "confidence": confidence,
        "annual_rate": annual,
        "annual_rate_display": f"{annual*100:.1f}%/yr",
        "cagr_5y": cagr_5,
        "cagr_10y": cagr_10,
        "cagr_forward": cagr_fwd,
        "cagr_5y_display": f"{cagr_5*100:+.1f}%/yr" if cagr_5 is not None else "n/a",
        "cagr_10y_display": f"{cagr_10*100:+.1f}%/yr" if cagr_10 is not None else "n/a",
        "cagr_forward_display": f"{cagr_fwd*100:+.1f}%/yr" if cagr_fwd is not None else "n/a",
        "anchor_usd": round(float(anchor), 0),
        "now_usd": y0["value_usd"],
        "peak": {"year": peak["year"], "value_usd": peak["value_usd"]},
        "trough": {"year": trough["year"], "value_usd": trough["value_usd"]},
        "from_peak_pct": from_peak,
        "from_trough_pct": from_trough,
        "points": points,
        "sparkline": spark,
        "observed_marks": observed,
        "method_notes": method_notes,
        "summary_bullets": summary_bullets,
        "disclaimer": (
            "First-look value path for this listing. When deed history is missing, we estimate "
            "from similar land in this state and listing type. Not an appraisal or guarantee."
        ),
    }
