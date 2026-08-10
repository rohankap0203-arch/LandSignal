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

import math
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
    "public_vacant_gis": 0.90,  # assessor vacant screen — closer to retail land pace
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
    access_score: float | None = None,
    slope_pct: float | None = None,
    liquidity: float | None = None,
    scarcity: float | None = None,
) -> tuple[float, list[str]]:
    st = (state or "").upper()
    base = STATE_ANNUAL_APPRECIATION.get(st, 0.028)
    notes = [
        f"Starting point: typical land in {(st or 'this state')} has risen about {base*100:.1f}% per year over long periods."
    ]
    ch = CHANNEL_MULT.get(provider_id or "", 0.9)
    channel_plain = {
        "public_tax_sale": "county tax-sale listings",
        "public_surplus": "government surplus listings",
        "blm_lpad": "federal BLM land",
        "public_vacant_gis": "vacant land on the public assessor map",
    }.get(provider_id or "", "this listing type")
    if ch != 1.0:
        notes.append(
            f"For {channel_plain}, we use {ch*100:.0f}% of that pace because these sales usually "
            f"move slower than normal retail land."
        )
    rate = base * ch

    if growth_score is not None:
        adj = (growth_score - 50) / 50 * 0.012
        rate += adj
        notes.append(
            f"Local growth signal ({growth_score:.0f}/100) changes the yearly pace by {adj*100:+.1f} percentage points."
        )

    if acres is not None:
        if acres < 2:
            rate *= 0.85
            notes.append("Under 2 acres: we use a softer path (−15%) because small lots jump around more year to year.")
        elif acres >= 80:
            rate *= 1.05
            notes.append("80+ acres: slightly stronger path (+5%) — bigger tracts often track farm/fringe land indexes.")

    if prime_pct is not None and prime_pct >= 50 and (acres or 0) >= 10:
        rate += 0.004
        notes.append(f"About {prime_pct:.0f}% prime farmland on the map adds +0.4 percentage points per year.")
    if flood_pct is not None and flood_pct >= 30:
        rate -= 0.006
        notes.append(f"About {flood_pct:.0f}% flood overlap on the map subtracts −0.6 percentage points per year.")
    if wet_pct is not None and wet_pct >= 25:
        rate -= 0.004
        notes.append(f"About {wet_pct:.0f}% wetlands on the map subtracts −0.4 percentage points per year.")
    if access_score is not None and access_score < 40:
        rate -= 0.005
        notes.append(f"Weak access screen ({access_score:.0f}/100) slows the path (−0.5 pts/yr).")
    elif access_score is not None and access_score >= 75:
        rate += 0.002
        notes.append(f"Clearer access ({access_score:.0f}/100) adds a small lift (+0.2 pts/yr).")
    if slope_pct is not None and slope_pct >= 15:
        rate -= 0.003
        notes.append(f"Steeper ground (avg slope ~{slope_pct:.0f}%) softens long-run pace (−0.3 pts/yr).")
    if liquidity is not None and liquidity < 40:
        rate -= 0.003
        notes.append(f"Thin resale ease ({liquidity:.0f}/100) trims the path (−0.3 pts/yr).")
    if scarcity is not None and scarcity >= 70:
        rate += 0.002
        notes.append(f"Higher scarcity ({scarcity:.0f}/100) adds a small support (+0.2 pts/yr).")

    # Clamp to sane land ranges — long-run land rarely compounds at stock-like rates
    rate = max(-0.04, min(0.08, rate))
    return rate, notes


def _cycle_shaper(offset: int) -> float:
    """Mild year-to-year wiggle so long paths are not a perfect straight compound."""
    if offset in CYCLE_SHAPERS:
        return CYCLE_SHAPERS[offset]
    # Longer history: soft multi-year cycle (±3%)
    return 1.0 + 0.03 * math.sin(offset * 0.55)


def _forward_fade(year_k: int) -> float:
    """Long holds mean-revert — 100y is not the same % forever.

    Near-term can track the parcel rate; after ~15y fade hard toward a slow
    long-run real land pace so terminals stay grounded (not generational rockets).
    """
    if year_k <= 8:
        return 1.0
    if year_k <= 20:
        return max(0.55, 1.0 - (year_k - 8) * 0.035)
    if year_k <= 40:
        return max(0.34, 0.55 - (year_k - 20) * 0.010)
    if year_k <= 70:
        return max(0.22, 0.34 - (year_k - 40) * 0.004)
    # Century mark: mostly real-land drift (~¼ of near-term pace)
    return max(0.16, 0.22 - (year_k - 70) * 0.002)


def _hitch_severity(
    hitch: str,
    *,
    flood: float | None,
    wet: float | None,
    access: float | None,
    growth: float | None,
    liquidity: float | None,
) -> float:
    """0.7–1.4 scale: how hard this hitch bites *this* pin."""
    if hitch == "rate_shock":
        thin = 1.0
        if liquidity is not None and liquidity < 45:
            thin += 0.25
        if access is not None and access < 50:
            thin += 0.1
        return min(1.35, thin)
    if hitch == "growth_surge":
        g = 1.0
        if growth is not None:
            g += max(-0.2, min(0.35, (growth - 50) / 100))
        return max(0.75, min(1.3, g))
    if hitch == "site_hitch":
        s = 1.0
        if flood is not None and flood >= 20:
            s += min(0.35, flood / 200)
        if wet is not None and wet >= 15:
            s += min(0.25, wet / 250)
        if access is not None and access < 50:
            s += 0.2
        return min(1.4, s)
    return 1.0


def _apply_hitch(
    offset: int,
    factor: float,
    hitch: str | None,
    *,
    severity: float = 1.0,
) -> float:
    """Future-only hitch — past years stay on the shared history path."""
    if not hitch or hitch == "base":
        return factor
    # Never rewrite history: hitches only bend outlook years
    if offset <= 0:
        return factor
    sev = max(0.7, min(1.4, severity))
    if hitch == "rate_shock":
        # Near-term bite; mild catch-up — not a permanent new floor
        if 1 <= offset <= 6:
            bite = 0.10 if offset <= 3 else 0.05
            return factor * (1.0 - bite * sev)
        if 7 <= offset <= 14:
            return factor * (1.0 + 0.008 * sev)
        return factor
    if hitch == "growth_surge":
        # Corridor boom window, then fade — capped so 100y isn't a lottery ticket
        if 4 <= offset <= 18:
            return factor * (1.0 + 0.028 * sev)
        if 19 <= offset <= 32:
            return factor * (1.0 - 0.006 * sev)
        if offset >= 33:
            return factor * (1.0 - 0.003 * sev)  # boom cools for far years
        return factor
    if hitch == "site_hitch":
        # Discrete realization years — then slightly slower climb, not a death spiral
        if offset in (3, 4, 12, 13, 28, 29):
            return factor * (1.0 - 0.05 * sev)
        if offset > 30:
            return factor * (1.0 - 0.002 * sev)
        return factor
    return factor


def _series_from_anchor(
    *,
    anchor: float,
    annual: float,
    years_back: int,
    years_forward: int,
    hitch: str | None = None,
    hitch_severity: float = 1.0,
) -> dict[int, float]:
    """Build offset→value with cycle + long-run fade + optional future hitch."""
    vals: dict[int, float] = {0: float(anchor)}
    # History is shared across hitch modes — only the forward path bends
    for k in range(1, years_back + 1):
        shaper = _cycle_shaper(-k)
        fade = _forward_fade(k)
        factor = (1.0 + annual * fade) * shaper
        vals[-k] = vals[-k + 1] / max(factor, 0.82)
    for k in range(1, years_forward + 1):
        shaper = _cycle_shaper(k)
        fade = _forward_fade(k)
        # Mild forward conservatism — old 0.78× + 0.988 drag made after-inflation
        # almost always fall, which overstated CPI damage vs a normal land hold.
        fwd = 0.96 if k <= 20 else 0.94 if k <= 45 else 0.90
        drag = 1.0 if k <= 30 else 0.998 if k <= 60 else 0.995
        factor = (1.0 + annual * fwd * fade) * (drag + (1.0 - drag) * shaper)
        factor = _apply_hitch(k, factor, hitch, severity=hitch_severity)
        vals[k] = vals[k - 1] * max(factor, 0.82)
    return vals


def build_market_trajectory(
    *,
    parcel,
    listing=None,
    score=None,
    enrichment=None,
    years_back: int = 100,
    years_forward: int = 100,
) -> dict[str, Any]:
    """Always returns a parcel-bound path (up to 100y history + 100y forward)."""
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
    access_n = {}
    terr_n = {}
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
        if enrichment.access:
            access_n = enrichment.access.normalized or enrichment.access.value or {}
        if enrichment.terrain:
            terr_n = enrichment.terrain.normalized or enrichment.terrain.value or {}

    growth_score = _f(growth_n.get("path_of_growth_score"))
    if growth_score is None:
        growth_score = _f(comps_n.get("path_of_growth_score"))
    prime = _f(soil_n.get("prime_farmland_pct"))
    flood = _f(flood_n.get("flood_zone_pct"))
    wet = _f(wet_n.get("wetland_pct"))
    access_score = _f(access_n.get("legal_access_confidence"))
    slope_pct = _f(terr_n.get("avg_slope_pct"))
    liquidity = _f(comps_n.get("liquidity_score"))
    scarcity = _f(comps_n.get("scarcity_score"))

    annual, method_notes = _base_annual_rate(
        state=state,
        provider_id=provider,
        acres=acres,
        growth_score=growth_score,
        prime_pct=prime,
        flood_pct=flood,
        wet_pct=wet,
        access_score=access_score,
        slope_pct=slope_pct,
        liquidity=liquidity,
        scarcity=scarcity,
    )
    method_notes.append(
        "Long horizons fade toward a slower real land pace — 100 years is not the near-term % forever."
    )

    # Anchor: screening mark preferred; else ask; else synthetic prior
    anchor = est or ask
    if anchor is None:
        from landsignal.services.analyze import STATE_PPA_PRIOR

        ppa = STATE_PPA_PRIOR.get((state or "").upper(), 3000)
        anchor = ppa * (acres or 1.0)
        st_u = (state or "US").upper()
        method_notes.append(
            f"No public price — started from typical {st_u} land at about {_money(ppa)} per acre × acres"
        )

    raw = (listing.raw if listing else None) or {}
    observed = _extract_observed_marks(raw, ask=None)  # don't double-count ask as history
    observed_years = {m["year"] for m in observed}
    has_observed = len(observed) >= 2

    now_y = datetime.now(timezone.utc).year

    def _points_for(hitch: str | None) -> list[dict[str, Any]]:
        sev = (
            _hitch_severity(
                hitch,
                flood=flood,
                wet=wet,
                access=access_score,
                growth=growth_score,
                liquidity=liquidity,
            )
            if hitch and hitch != "base"
            else 1.0
        )
        series = _series_from_anchor(
            anchor=float(anchor),
            annual=annual,
            years_back=years_back,
            years_forward=years_forward,
            hitch=hitch,
            hitch_severity=sev,
        )
        out: list[dict[str, Any]] = []
        for offset in range(-years_back, years_forward + 1):
            year = now_y + offset
            val = series[offset]
            kind = "history" if offset <= 0 else "outlook"
            obs = next((m for m in observed if m["year"] == year), None)
            if obs and hitch in (None, "base"):
                val = 0.7 * obs["value_usd"] + 0.3 * val
                point_src = "blended_observed"
                note = f"Includes a real {obs['label'].lower()} figure from the source, blended with the local trend"
            else:
                point_src = "trend_proxy" if hitch in (None, "base") else f"hitch_{hitch}"
                note = (
                    "Estimated from similar land in this state and listing type (no deed sale found for this year)"
                    if hitch in (None, "base")
                    else f"What-if path · {hitch.replace('_', ' ')} hitch on this pin (severity {sev:.2f}×)"
                )
            out.append(
                {
                    "year": year,
                    "offset": offset,
                    "value_usd": round(val, 0),
                    "kind": kind,
                    "source": point_src,
                    "note": note,
                }
            )
        return out

    points = _points_for("base")
    rate_sev = _hitch_severity(
        "rate_shock", flood=flood, wet=wet, access=access_score, growth=growth_score, liquidity=liquidity
    )
    growth_sev = _hitch_severity(
        "growth_surge", flood=flood, wet=wet, access=access_score, growth=growth_score, liquidity=liquidity
    )
    site_sev = _hitch_severity(
        "site_hitch", flood=flood, wet=wet, access=access_score, growth=growth_score, liquidity=liquidity
    )
    # Parcel-aware hitch labels — exactly three stress cases for the chart rail
    hitch_catalog = [
        {
            "id": "rate_shock",
            "label": "Rate bite",
            "short": "Rates",
            "plain": (
                f"From today forward: higher borrowing costs cool bids for a few years on this "
                f"{provider or 'listing'} channel"
                f"{' (thin resale)' if (liquidity or 100) < 45 else ''} — then a mild catch-up. "
                f"Past years stay put."
            ),
            "severity": round(rate_sev, 2),
            "points": _points_for("rate_shock"),
        },
        {
            "id": "growth_surge",
            "label": "Growth surge",
            "short": "Growth",
            "plain": (
                f"From today forward: stronger corridor demand around {county or 'this county'} "
                f"lifts the mid years, then fades. Past years stay on the shared history."
            ),
            "severity": round(growth_sev, 2),
            "points": _points_for("growth_surge"),
        },
        {
            "id": "site_hitch",
            "label": "Site hitch",
            "short": "Site",
            "plain": (
                (
                    f"From today forward: flood (~{flood:.0f}%), wetlands, or access surprise "
                    f"steps value down — then a slower climb. History unchanged."
                    if (flood or 0) >= 15
                    else "From today forward: a site/title/access surprise steps value down — "
                    "then a slower climb. History unchanged."
                )
            ),
            "severity": round(site_sev, 2),
            "points": _points_for("site_hitch"),
        },
    ]
    hitch_help = {
        "title": "What these hitch buttons do",
        "body": (
            "They only bend the future (dashed) side of the chart. The past stays the same so you can "
            "compare “what if” from today’s mark."
        ),
        "items": [
            {
                "id": "rate_shock",
                "label": "Rates",
                "plain": "What if borrowing costs cool buyers for a few years, then ease a bit?",
            },
            {
                "id": "growth_surge",
                "label": "Growth",
                "plain": f"What if {county or 'this county'} gets a mid-term demand surge — then it fades?",
            },
            {
                "id": "site_hitch",
                "label": "Site",
                "plain": "What if flood, access, or title news steps this pin down after you buy?",
            },
        ],
    }

    # Stats
    y0 = next(p for p in points if p["offset"] == 0)
    y_10 = next((p for p in points if p["offset"] == -10), None)
    y_fwd = next((p for p in points if p["offset"] == years_forward), None)

    def _cagr(start: dict | None, end: dict | None) -> float | None:
        if not start or not end or start["value_usd"] <= 0:
            return None
        yrs = max(1, end["year"] - start["year"])
        return (end["value_usd"] / start["value_usd"]) ** (1 / yrs) - 1

    # Value-over-time chart presets (hold-period 5-yr steps live on return paths).
    windows = [1, 3, 5, 10, 15, 30, 50, 75, 100]
    window_stats: dict[str, Any] = {}
    for w in windows:
        start = next((p for p in points if p["offset"] == -w), None)
        fut = next((p for p in points if p["offset"] == w), None)
        c_past = _cagr(start, y0)
        c_fwd = _cagr(y0, fut)
        window_stats[str(w)] = {
            "years": w,
            "start_year": start["year"] if start else None,
            "end_year": fut["year"] if fut else None,
            "start_usd": start["value_usd"] if start else None,
            "today_usd": y0["value_usd"],
            "end_usd": y0["value_usd"],
            "forward_usd": fut["value_usd"] if fut else None,
            "cagr": c_past,
            "cagr_display": f"{c_past*100:+.1f}%/yr" if c_past is not None else "n/a",
            "forward_cagr": c_fwd,
            "forward_cagr_display": f"{c_fwd*100:+.1f}%/yr" if c_fwd is not None else "n/a",
            "change_pct": (
                ((y0["value_usd"] - start["value_usd"]) / start["value_usd"]) * 100
                if start and start["value_usd"]
                else None
            ),
            "forward_change_pct": (
                ((fut["value_usd"] - y0["value_usd"]) / y0["value_usd"]) * 100
                if fut and y0["value_usd"]
                else None
            ),
        }

    cagr_5 = window_stats.get("5", {}).get("cagr")
    cagr_10 = window_stats.get("10", {}).get("cagr")
    cagr_fwd = _cagr(y0, y_fwd)

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
        regime_label = f"Up about {cagr_5*100:.1f}% per year over the last 5 years"
    elif cagr_5 is not None and cagr_5 <= 0:
        regime = "FLAT_TO_DOWN"
        regime_label = f"Flat to soft · about {cagr_5*100:.1f}% per year over the last 5 years"
    else:
        regime = "MODEST_GROWTH"
        regime_label = f"Slow rise · about {(cagr_5 or 0)*100:.1f}% per year over the last 5 years"

    knowledge = "BLENDED" if has_observed else "TREND_PROXY"
    knowledge_label = (
        "Uses tax-roll / sale figures plus the local trend"
        if has_observed
        else "Estimated from similar land nearby (no multi-year sale tape on this feed)"
    )
    confidence = 55 if has_observed else 38
    if growth_score is not None:
        confidence += 8
    if prime is not None or flood is not None:
        confidence += 5
    confidence = min(78, confidence)

    identity = f"{county or 'County'}, {(state or 'US').upper()}"
    if acres is not None:
        identity += f" · {acres:,.2f} acres"
    identity = f"This property · {identity}"

    fwd_mult = (y_fwd["value_usd"] / y0["value_usd"]) if y_fwd and y0["value_usd"] else None
    headline = (
        f"{regime_label}. Today ~{_money(y0['value_usd'])}"
        + (f" · 10 years ago ~{_money(y_10['value_usd'])}" if y_10 else "")
        + (
            f" · in {years_forward} years (faded outlook) ~{_money(y_fwd['value_usd'])}"
            if y_fwd
            else ""
        )
        + "."
    )

    summary_bullets = [
        f"Near-term pace for this listing: {annual*100:.1f}%/yr — after ~20 years the path fades hard.",
        f"Highest in the full history: {_money(peak['value_usd'])} ({peak['year']}); "
        f"lowest: {_money(trough['value_usd'])} ({trough['year']}).",
    ]
    from landsignal.services.inflation import DEFAULT_CPI_ANNUAL, deflate, inflation_meta, real_rate

    infl = inflation_meta(DEFAULT_CPI_ANNUAL)
    fwd_today = (
        deflate(y_fwd["value_usd"], years_forward, DEFAULT_CPI_ANNUAL) if y_fwd else None
    )
    if fwd_mult is not None and years_forward >= 50:
        summary_bullets.append(
            f"At {years_forward} years the faded path is about {fwd_mult:.1f}× today’s mark "
            f"(~{_money(y_fwd['value_usd'])} before inflation · ~{_money(fwd_today)} in today’s $) — "
            f"not a promise of generational wealth."
        )
    if has_observed:
        summary_bullets.append(
            f"Folded in {len(observed)} tax-roll / sale figure(s) from this listing’s source."
        )
    else:
        summary_bullets.append(
            "No multi-year sale history on this public feed for this parcel ID, "
            "so the line follows similar land in this state and listing type — not recorded deeds."
        )
    if (flood or 0) >= 20 or (wet or 0) >= 15 or (access_score is not None and access_score < 45):
        summary_bullets.append(
            "Site screens (flood / wetlands / access) already slow this pin’s base path — "
            "use the Site hitch to stress a sharper surprise."
        )

    # Card sparkline stays short (last ~10 years)
    hist_vals = [p["value_usd"] for p in points if p["kind"] == "history"]
    spark = hist_vals[-11:] if len(hist_vals) > 11 else hist_vals

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
        "cagr_forward_real": real_rate(cagr_fwd, DEFAULT_CPI_ANNUAL),
        "cagr_5y_display": f"{cagr_5*100:+.1f}%/yr" if cagr_5 is not None else "n/a",
        "cagr_10y_display": f"{cagr_10*100:+.1f}%/yr" if cagr_10 is not None else "n/a",
        "cagr_forward_display": f"{cagr_fwd*100:+.1f}%/yr" if cagr_fwd is not None else "n/a",
        "cagr_forward_real_display": (
            f"{real_rate(cagr_fwd, DEFAULT_CPI_ANNUAL)*100:+.1f}%/yr after inflation"
            if cagr_fwd is not None and real_rate(cagr_fwd, DEFAULT_CPI_ANNUAL) is not None
            else "n/a"
        ),
        "anchor_usd": round(float(anchor), 0),
        "now_usd": y0["value_usd"],
        "forward_usd_today": round(fwd_today, 0) if fwd_today is not None else None,
        "inflation": infl,
        "peak": {"year": peak["year"], "value_usd": peak["value_usd"]},
        "trough": {"year": trough["year"], "value_usd": trough["value_usd"]},
        "from_peak_pct": from_peak,
        "from_trough_pct": from_trough,
        "years_back": years_back,
        "years_forward": years_forward,
        "windows": windows,
        "window_stats": window_stats,
        "points": points,
        "hitches": hitch_catalog,
        "hitch_help": hitch_help,
        "sparkline": spark,
        "observed_marks": observed,
        "method_notes": method_notes,
        "summary_bullets": summary_bullets
        + [
            "Far-out years fade toward a slower real land pace — not a straight rocket to generational millions.",
            "Use the hitch buttons to stress rate bites, growth surges, or a site surprise on this same pin.",
        ],
        "interaction_hint": "Each button shows that many years back and the same span ahead. Drag to read any year.",
        "disclaimer": (
            "First look only. Long outlooks are faded on purpose. When deed history is missing, dollars "
            "follow similar land in this state and listing type. Not an appraisal or a promise of future prices."
        ),
    }
