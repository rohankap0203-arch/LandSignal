"""Multi-factor land return paths — not a flat compound line.

Builds year-by-year land value + rent cashflows from this property’s own
screens: soil, flood, wetlands, growth, channel, acreage, strategy fit,
risk, liquidity, scarcity, access/power, and cycle shape.

Every path is parcel-bound. Bear / typical / optimistic cases share the
same factor ledger but stress different assumptions.
"""

from __future__ import annotations

import math
from typing import Any

from landsignal.scoring.financial import irr as irr_solve
from landsignal.services.inflation import (
    DEFAULT_CPI_ANNUAL,
    enrich_endpoint_inflation,
    inflation_meta,
)
from landsignal.services.market_trajectory import STATE_ANNUAL_APPRECIATION, CHANNEL_MULT, _cycle_shaper
from landsignal.services.voice import place_phrase, this_property

HOLD_WINDOWS = [1, 3, 5, 10, 15, 25, 40, 60, 80, 100]


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


def _norm(enrichment, attr: str) -> dict:
    if not enrichment:
        return {}
    prov = getattr(enrichment, attr, None)
    if not prov:
        return {}
    return prov.normalized or prov.value or {}


def _factor(
    key: str,
    label: str,
    bps: float,
    plain: str,
    *,
    kind: str = "appreciation",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "bps": round(bps, 1),
        "pct_points": round(bps / 100.0, 2),
        "direction": "up" if bps > 0 else "down" if bps < 0 else "neutral",
        "kind": kind,
        "plain": plain,
    }


def build_factor_model(
    *,
    parcel,
    listing,
    score,
    enrichment,
    base_annual: float | None = None,
    channel_already_applied: bool = False,
) -> dict[str, Any]:
    """Assemble the nuance ledger that bends the path away from a straight line."""
    state = (getattr(parcel, "state", None) or "US").upper()
    county = getattr(parcel, "county", None) or "this county"
    acres = _f(getattr(parcel, "acreage", None))
    provider = getattr(listing, "provider_id", None) if listing else None
    place = place_phrase(parcel)
    prop = this_property(parcel, listing)

    soil_n = _norm(enrichment, "soil")
    flood_n = _norm(enrichment, "flood")
    wet_n = _norm(enrichment, "wetlands")
    growth_n = _norm(enrichment, "growth")
    infra_n = _norm(enrichment, "infrastructure")
    comps_n = _norm(enrichment, "comps")
    terr_n = _norm(enrichment, "terrain")

    prime = _f(soil_n.get("prime_farmland_pct"))
    flood = _f(flood_n.get("flood_zone_pct"))
    wet = _f(wet_n.get("wetland_pct"))
    growth = _f(growth_n.get("path_of_growth_score")) or _f(comps_n.get("path_of_growth_score"))
    tx_m = _f(infra_n.get("nearest_transmission_m"))
    access = _f(comps_n.get("legal_access_confidence")) or _f(
        (getattr(enrichment, "access", None).normalized if enrichment and getattr(enrichment, "access", None) else {})
        or {}
    )
    if access is None:
        access = _f((terr_n or {}).get("legal_access_confidence"))

    risk = _f(getattr(score, "risk", None)) if score else None
    conf = _f(getattr(score, "confidence", None)) if score else None
    opp = _f(getattr(score, "opportunity", None)) if score else None
    liq = _f(comps_n.get("liquidity_score"))
    scar = _f(comps_n.get("scarcity_score"))
    seller = _f(comps_n.get("seller_pressure_score"))
    strategy = (
        score.best_strategy.value
        if score and getattr(score, "best_strategy", None)
        else None
    )
    strat_scores = getattr(score, "strategy_scores", None) or {}

    # Channel cheapens the BUY (opportunity / entry). Once owned, land tracks area pace.
    from_trajectory = base_annual is not None
    base = base_annual if base_annual is not None else STATE_ANNUAL_APPRECIATION.get(state, 0.028)
    ch = CHANNEL_MULT.get(provider or "", 0.9)
    factors: list[dict[str, Any]] = []

    rate = base
    factors.append(
        _factor(
            "state_prior",
            "Area land pace",
            base * 10000,
            (
                f"Starting pace from the land-value path for {state}: about {base*100:.1f}%/yr."
                if from_trajectory
                else f"Typical long-run land pace in {state}: about {base*100:.1f}%/yr before this property’s own screens."
            ),
        )
    )

    # Document channel as entry edge — do not cut lifelong appreciation (that made
    # After inflation always fall below CPI for tax-sale files).
    if ch < 1.0:
        channel_name = {
            "public_tax_sale": "county tax-sale channel",
            "public_vacant_gis": "vacant public-map screen",
            "public_surplus": "government surplus channel",
            "blm_lpad": "federal BLM channel",
        }.get(provider or "", "this listing channel")
        factors.append(
            _factor(
                "channel",
                "How it is sold",
                0.0,
                f"{channel_name.title()} usually clears cheaper than retail — that shows up in "
                f"your buy vs our value for {prop}, not by permanently slowing the land once you own it.",
                kind="entry",
            )
        )

    # Flood/wetland still drive carry + usable acres even when pace comes from trajectory.
    flood_carry = 0.0
    if flood is not None:
        flood_carry = (flood / 100) * 0.004
    usable_frac = 1.0
    if wet is not None:
        usable_frac = max(0.35, 1.0 - (wet / 100) * 0.55)

    if from_trajectory:
        # Land-value path already layered growth/soil/flood/size/access/etc.
        # Re-applying them here double-cut every listing and shoved hold pace ≤ CPI.
        factors.append(
            _factor(
                "path_sync",
                "Same pace as land-value path",
                base * 10000,
                f"Hold return uses the same ~{base*100:.1f}%/yr owned-land pace as the land-value "
                f"path for {prop} — screens are not applied twice.",
            )
        )
    else:
        # Growth
        if growth is not None:
            adj = (growth - 50) / 50 * 0.012
            rate += adj
            factors.append(
                _factor(
                    "growth",
                    "Local growth",
                    adj * 10000,
                    f"Growth signal {growth:.0f}/100 in {county} moves the yearly pace by {adj*100:+.1f} pts.",
                )
            )

        # Soil / prime
        if prime is not None and acres and acres >= 5:
            adj = (prime - 40) / 100 * 0.008
            rate += adj
            factors.append(
                _factor(
                    "soil",
                    "Soil quality",
                    adj * 10000,
                    f"About {prime:.0f}% prime farmland on the map — {'helps' if adj >= 0 else 'softens'} cash-rent and resale to ag buyers.",
                )
            )
        elif acres is not None and acres < 2:
            adj = -0.004
            rate += adj
            factors.append(
                _factor(
                    "lot_class",
                    "Small-lot class",
                    adj * 10000,
                    "Under 2 acres: path is lumpier and less farm-index driven than big rural tracts.",
                )
            )
        elif acres is not None and acres >= 80:
            adj = 0.003
            rate += adj
            factors.append(
                _factor(
                    "scale",
                    "Large-tract scale",
                    adj * 10000,
                    f"{acres:,.0f} acres: institutional-scale tracts often track farm/fringe indexes a bit more tightly.",
                )
            )

        # Flood
        if flood is not None:
            adj = -min(0.018, (flood / 100) * 0.02)
            rate += adj
            factors.append(
                _factor(
                    "flood",
                    "Flood exposure",
                    adj * 10000,
                    f"About {flood:.0f}% flood overlap — slows appreciation and adds carrying cost (insurance/fill reserve).",
                )
            )

        # Wetlands
        if wet is not None:
            adj = -min(0.012, (wet / 100) * 0.015)
            rate += adj
            factors.append(
                _factor(
                    "wetlands",
                    "Wetlands",
                    adj * 10000,
                    f"About {wet:.0f}% wetlands — usable acres may be ~{usable_frac*100:.0f}% of deeded size, which weighs on exit.",
                )
            )

        # Access
        if access is not None and access < 45:
            adj = -0.005
            rate += adj
            factors.append(
                _factor(
                    "access",
                    "Road access",
                    adj * 10000,
                    f"Access confidence looks soft ({access:.0f}/100) — fewer buyers, slower resale.",
                )
            )
        elif access is not None and access >= 70:
            adj = 0.002
            rate += adj
            factors.append(
                _factor(
                    "access",
                    "Road access",
                    adj * 10000,
                    f"Access looks workable ({access:.0f}/100) — helps resale and any build/farm use.",
                )
            )

        # Transmission / energy optionality
        if tx_m is not None and tx_m < 8000 and (strategy == "ENERGY" or (acres or 0) >= 20):
            adj = 0.0025
            rate += adj
            factors.append(
                _factor(
                    "power",
                    "Nearby power line",
                    adj * 10000,
                    f"Mapped transmission ~{tx_m/1609:.1f} mi away — a small energy-optionality lift, not a grid connection right.",
                )
            )

        # Liquidity / scarcity
        if liq is not None:
            adj = (liq - 50) / 50 * 0.004
            rate += adj
            factors.append(
                _factor(
                    "liquidity",
                    "Ease of resale",
                    adj * 10000,
                    f"Resale ease {liq:.0f}/100 for this channel/size in {place}.",
                )
            )
        if scar is not None and scar >= 60:
            adj = 0.002
            rate += adj
            factors.append(
                _factor(
                    "scarcity",
                    "How rare it is",
                    adj * 10000,
                    f"Scarcity screen {scar:.0f}/100 — fewer substitutes nearby can support exit price.",
                )
            )

        # Risk cushion
        if risk is not None and risk >= 55:
            adj = -((risk - 50) / 100) * 0.01
            rate += adj
            factors.append(
                _factor(
                    "risk",
                    "Map risk",
                    adj * 10000,
                    f"Risk {risk:.0f}/100 — we slow the path until flood/wetland/access homework is cleaner.",
                )
            )
        elif risk is not None and risk <= 30:
            adj = 0.0015
            rate += adj
            factors.append(
                _factor(
                    "risk",
                    "Map risk",
                    adj * 10000,
                    f"Risk {risk:.0f}/100 — cleaner desktop map checks support a steadier path.",
                )
            )

        # Strategy fit
        if strategy and isinstance(strat_scores, dict):
            best = _f(strat_scores.get(strategy))
            if best is not None:
                adj = (best - 55) / 100 * 0.006
                rate += adj
                factors.append(
                    _factor(
                        "strategy",
                        "Best-use fit",
                        adj * 10000,
                        f"Best use {strategy.replace('_', ' ').title()} scores {best:.0f}/100 on this file — "
                        f"{'supports' if adj >= 0 else 'softens'} the hold case.",
                    )
                )

    # Thin file → wider uncertainty band (case spread), not a second pace haircut
    # when we already synced to the land-value path.
    uncertainty = 0.35
    if conf is not None:
        uncertainty = max(0.18, min(0.55, 0.55 - (conf / 100) * 0.35))
        if conf < 45 and not from_trajectory:
            adj = -0.002
            rate += adj
            factors.append(
                _factor(
                    "completeness",
                    "How complete the file is",
                    adj * 10000,
                    f"File complete {conf:.0f}/100 — we stay a bit conservative until more layers confirm.",
                )
            )

    # Seller pressure can improve entry, not long-run appreciation — track as entry note
    entry_edge_bps = 0.0
    if seller is not None and seller >= 65:
        entry_edge_bps = (seller - 60) * 2  # informational
        factors.append(
            _factor(
                "seller",
                "Seller / channel pressure",
                entry_edge_bps,
                f"Seller pressure {seller:.0f}/100 — more room on entry price than on long-run land pace.",
                kind="entry",
            )
        )

    rate = max(-0.04, min(0.12, rate))

    # Sort factors by absolute impact for UI
    factors_sorted = sorted(factors, key=lambda x: abs(x["bps"]), reverse=True)

    return {
        "base_annual": base,
        "effective_annual": rate,
        "channel_mult": ch,
        "usable_frac": usable_frac,
        "flood_carry_frac": flood_carry,
        "uncertainty": uncertainty,
        "prime_pct": prime,
        "flood_pct": flood,
        "wet_pct": wet,
        "growth_score": growth,
        "strategy": strategy,
        "acres": acres,
        "state": state,
        "county": county,
        "place": place,
        "provider": provider,
        "factors": factors_sorted,
        "factor_count": len(factors_sorted),
    }


def _case_scalars(case: str, uncertainty: float) -> dict[str, float]:
    """Stress multipliers for rent, appreciation, exit haircut, carry."""
    c = (case or "BASE").upper()
    if c in ("BEAR", "DOWNSIDE", "STRESS"):
        return {
            "rent_mult": 0.72,
            "appr_mult": max(0.35, 1.0 - uncertainty * 1.1),
            "exit_haircut": 0.08 + uncertainty * 0.12,
            "carry_mult": 1.25,
            "cycle_amp": 1.35,
        }
    if c in ("BULL", "UPSIDE"):
        return {
            "rent_mult": 1.25,
            "appr_mult": 1.0 + uncertainty * 0.85,
            "exit_haircut": max(0.0, 0.02 - uncertainty * 0.04),
            "carry_mult": 0.9,
            "cycle_amp": 0.85,
        }
    return {
        "rent_mult": 1.0,
        "appr_mult": 1.0,
        "exit_haircut": 0.03 + uncertainty * 0.05,
        "carry_mult": 1.0,
        "cycle_amp": 1.0,
    }


def _base_rent_per_acre(model: dict[str, Any], strategy: str | None) -> float:
    """Rough cash-rent / hold-income prior by strategy + soil."""
    st = model["state"]
    prime = model.get("prime_pct") or 35.0
    # Farm belt priors vs sunbelt recreational
    farm_belt = {"IA", "IL", "IN", "OH", "MN", "WI", "NE", "SD", "ND", "MO", "KS"}
    base = 220.0 if st in farm_belt else 140.0 if st in {"TX", "OK", "KS"} else 160.0
    base *= 0.75 + (prime / 100) * 0.55
    if strategy == "RECREATIONAL":
        base = max(40.0, base * 0.35)  # hunt/lease style
    elif strategy == "ENERGY":
        base = max(60.0, base * 0.45)  # option/lease placeholder
    elif strategy == "LAND_BANK":
        base = max(20.0, base * 0.15)
    elif strategy == "DEVELOPMENT":
        base = max(30.0, base * 0.2)
    usable = model.get("usable_frac") or 1.0
    return base * usable


def build_case_path(
    *,
    purchase: float,
    model: dict[str, Any],
    case: str,
    hold_years: int,
    mark_usd: float | None = None,
) -> dict[str, Any]:
    """Year-by-year land + rent path for one case and hold length.

    Land mark starts at our value (when above buy), not at the distressed entry.
    Cash IRR still uses purchase as the outflow — that is the opportunity edge.
    """
    hold_years = max(1, min(100, int(hold_years)))
    scalars = _case_scalars(case, float(model["uncertainty"]))
    acres = float(model.get("acres") or 1.0)
    appr0 = float(model["effective_annual"]) * scalars["appr_mult"]
    appr0 = max(-0.05, min(0.14, appr0))
    rent0 = _base_rent_per_acre(model, model.get("strategy")) * acres * scalars["rent_mult"]
    # Vacancy / opex / taxes / insurance as fractions of rent or value
    vacancy = 0.08 if case.upper() in ("BEAR", "DOWNSIDE", "STRESS") else 0.05
    opex_frac = 0.18 * scalars["carry_mult"]
    # Property-tax screen — full 1.1% of mark on a 0.8ac vacant lot with tiny rent
    # made every hold look like a CPI death spiral. Soften on small / non-income uses.
    tax_frac = 0.009 * scalars["carry_mult"]
    if acres < 2:
        tax_frac *= 0.55
    if (model.get("strategy") or "") in ("LAND_BANK", "DEVELOPMENT"):
        tax_frac *= 0.7
    insure_frac = (0.002 + float(model.get("flood_carry_frac") or 0)) * scalars["carry_mult"]
    mgmt_frac = 0.06  # of EGI

    path: list[dict[str, Any]] = []
    # Day-one mark: what the dirt is worth vs what you pay. Growing from purchase
    # at a suppressed rate made After inflation look like a permanent loss.
    mark0 = float(mark_usd) if mark_usd and mark_usd > 0 else float(purchase)
    if mark0 < purchase:
        mark0 = float(purchase)
    land = mark0
    cum_rent = 0.0
    cum_noi = 0.0
    cum_carry = 0.0
    flows = [-purchase]
    rent_series = []

    case_u = case.upper()
    for y in range(1, hold_years + 1):
        # Mild cycle (dampened) — full ±3% swings made After inflation bounce.
        raw_shaper = _cycle_shaper(y, forward=True)
        amp = scalars["cycle_amp"] * 0.35
        shaped = 1.0 + (raw_shaper - 1.0) * amp
        # Long-hold fatigue mirrors land-value path fade — uncertainty, not a CPI hack.
        fatigue = 1.0
        if y > 15:
            fatigue = max(0.88, 1.0 - (y - 15) * 0.006)
        if y > 35:
            fatigue = max(0.80, fatigue - (y - 35) * 0.003)
        if y > 60:
            fatigue = max(0.74, fatigue - (y - 60) * 0.0015)
        # Flood/wetland “realization” years — occasional step downs in bear/base
        shock = 1.0
        if y in (7, 14, 28, 42, 55) and case_u in ("BEAR", "BASE", "DOWNSIDE", "STRESS"):
            if (model.get("flood_pct") or 0) >= 25:
                shock *= 0.985 if case_u == "BASE" else 0.97
            if (model.get("wet_pct") or 0) >= 20:
                shock *= 0.992
        # Access / thin-channel friction years
        if y in (5, 22, 48) and model.get("provider") in ("public_tax_sale", "blm_lpad", "public_surplus"):
            shock *= 0.994 if case_u == "BASE" else (0.99 if case_u in ("BEAR", "DOWNSIDE", "STRESS") else 0.997)

        year_appr = appr0 * fatigue
        land = land * (1.0 + year_appr) * shaped * shock

        # Rent drifts with land quality + mild inflation, with usable-acre drag;
        # far years: rents don't compound as fast as a stock model
        rent_cap = 0.022 if y <= 30 else 0.014 if y <= 60 else 0.009
        rent_drift = 1.0 + max(-0.01, min(rent_cap, year_appr * 0.42))
        if y > 1:
            rent0 *= rent_drift
        egi = rent0 * (1.0 - vacancy)
        opex = egi * opex_frac
        # Tax/insurance creep slightly with time (reassessments, climate)
        tax_creep = 1.0 + min(0.25, max(0.0, (y - 10) * 0.002))
        taxes = land * tax_frac * tax_creep
        insure = land * insure_frac * (1.0 + (0.15 if y > 40 else 0.0))
        mgmt = egi * mgmt_frac
        noi = egi - opex - taxes - insure - mgmt
        # Very small lots / land-bank: NOI can be near zero or slightly negative carry
        if (model.get("strategy") or "") in ("LAND_BANK", "DEVELOPMENT") and noi < 0:
            noi = min(noi, -land * 0.004)

        cum_noi += noi
        cum_rent += max(0.0, noi)
        cum_carry += max(0.0, taxes + insure)
        rent_series.append(noi)

        exit_haircut = scalars["exit_haircut"]
        # Thin-channel exit friction — light on short holds, fades with time
        if model.get("provider") in ("public_tax_sale", "blm_lpad", "public_surplus"):
            exit_haircut += max(0.0, 0.035 - y * 0.0012)
        # Ultra-long exits: buyer pool / estate friction haircut
        if y >= 75:
            exit_haircut += 0.025 if case_u in ("BEAR", "DOWNSIDE", "STRESS") else 0.012

        mark_exit = land * (1.0 - exit_haircut)
        # Net cash back = exit + all NOI (including negative tax years). Old code
        # only banked positive rent, so tiny lots looked profitable while IRR died.
        total_back = mark_exit + cum_noi
        path.append(
            {
                "year_offset": y,
                "land_usd": round(land, 0),
                "exit_usd": round(mark_exit, 0),
                "noi_usd": round(noi, 0),
                "cumulative_rent_usd": round(cum_rent, 0),
                "cumulative_noi_usd": round(cum_noi, 0),
                "cumulative_carry_usd": round(cum_carry, 0),
                "total_back_usd": round(total_back, 0),
                "gain_usd": round(total_back - purchase, 0),
                "year_appreciation": year_appr,
                "fatigue": round(fatigue, 3),
                "starting_mark_usd": round(mark0, 0),
                "purchase_usd": round(purchase, 0),
            }
        )
        flows.append(noi)

    # Terminal exit on last flow
    if path:
        flows[-1] = rent_series[-1] + path[-1]["exit_usd"]

    irr_v = irr_solve(flows)
    last = path[-1] if path else None

    return {
        "case": case.upper(),
        "case_label": {
            "BEAR": "Cautious",
            "DOWNSIDE": "Cautious",
            "STRESS": "Cautious",
            "BULL": "Optimistic",
            "UPSIDE": "Optimistic",
            "BASE": "Typical",
        }.get(case.upper(), case.title()),
        "hold_years": hold_years,
        "purchase_usd": round(purchase, 0),
        "starting_mark_usd": round(mark0, 0),
        "irr": irr_v,
        "irr_display": f"{irr_v*100:.1f}%/yr" if irr_v is not None else "n/a",
        "exit_usd": last["exit_usd"] if last else None,
        "land_mark_usd": last["land_usd"] if last else None,
        "cumulative_rent_usd": last["cumulative_rent_usd"] if last else 0,
        "total_back_usd": last["total_back_usd"] if last else None,
        "gain_usd": last["gain_usd"] if last else None,
        "path": path,
        "effective_annual_used": appr0,
        "starting_noi": round(rent_series[0], 0) if rent_series else 0,
        "scalars": scalars,
    }


def _endpoint_from_path(
    full: dict[str, Any],
    hold_years: int,
) -> dict[str, Any]:
    """Slice a long path to an exact hold length and recompute IRR for that exit."""
    hold_years = max(1, min(100, int(hold_years)))
    path = (full.get("path") or [])[:hold_years]
    purchase = float(full["purchase_usd"])
    if not path:
        return {
            "irr": None,
            "irr_display": "n/a",
            "exit_usd": None,
            "land_mark_usd": None,
            "cumulative_rent_usd": 0,
            "total_back_usd": None,
            "gain_usd": None,
            "path": [],
            "starting_noi": full.get("starting_noi"),
            "effective_annual_used": full.get("effective_annual_used"),
            "case_label": full.get("case_label"),
            "purchase_usd": purchase,
            "hold_years": hold_years,
        }
    last = path[-1]
    flows = [-purchase]
    for i, pt in enumerate(path):
        noi = float(pt.get("noi_usd") or 0)
        if i == len(path) - 1:
            flows.append(noi + float(pt["exit_usd"]))
        else:
            flows.append(noi)
    irr_v = irr_solve(flows)
    return {
        "irr": irr_v,
        "irr_display": f"{irr_v*100:.1f}%/yr" if irr_v is not None else "n/a",
        "exit_usd": last["exit_usd"],
        "land_mark_usd": last["land_usd"],
        "cumulative_rent_usd": last["cumulative_rent_usd"],
        "total_back_usd": last["total_back_usd"],
        "gain_usd": last["gain_usd"],
        "path": path,
        "starting_noi": full.get("starting_noi"),
        "effective_annual_used": full.get("effective_annual_used"),
        "case_label": full.get("case_label"),
        "purchase_usd": purchase,
        "hold_years": hold_years,
    }


def build_return_intelligence(
    *,
    parcel,
    listing,
    score,
    enrichment,
    entry_usd: float | None,
    mark_usd: float | None = None,
    hold_years: int = 10,
    trajectory_annual: float | None = None,
) -> dict[str, Any]:
    """Full interactive return package for the detail page."""
    model = build_factor_model(
        parcel=parcel,
        listing=listing,
        score=score,
        enrichment=enrichment,
        base_annual=trajectory_annual,
        channel_already_applied=trajectory_annual is not None,
    )
    purchase = entry_usd or mark_usd
    if purchase is None or purchase <= 0:
        return {
            "available": False,
            "reason": "Need a buy price or value estimate before a return path can be built.",
            "factors": model["factors"],
            "all_factors": model["factors"],
            "windows": HOLD_WINDOWS,
            "inflation": inflation_meta(),
            "model": {
                "effective_annual": model["effective_annual"],
                "effective_annual_display": f"{model['effective_annual']*100:.1f}%/yr",
                "uncertainty": model["uncertainty"],
                "usable_frac": model["usable_frac"],
                "factor_count": model["factor_count"],
                "place": model["place"],
                "strategy": model.get("strategy"),
            },
            "method": (
                "Year-by-year path bends with soil, flood, wetlands, growth, access, channel, "
                "strategy, risk, liquidity, scarcity, power, cycles, and carry — not a flat line."
            ),
        }

    # Prefer underwriting entry; if only mark, assume process discount by channel
    if entry_usd is None and mark_usd:
        ch = model["channel_mult"]
        purchase = mark_usd * (0.62 if ch <= 0.75 else 0.85 if ch < 1 else 1.0)

    # One 100-year path per case, then exact window slices (keeps curves + IRR consistent)
    full_paths: dict[str, Any] = {}
    for case in ("BEAR", "BASE", "BULL"):
        full_paths[case] = build_case_path(
            purchase=float(purchase),
            model=model,
            case=case,
            hold_years=100,
            mark_usd=float(mark_usd) if mark_usd else None,
        )

    cpi = DEFAULT_CPI_ANNUAL
    infl = inflation_meta(cpi)
    endpoints: dict[str, Any] = {}
    for w in HOLD_WINDOWS:
        endpoints[str(w)] = {
            case: enrich_endpoint_inflation(_endpoint_from_path(full_paths[case], w), cpi=cpi)
            for case in ("BEAR", "BASE", "BULL")
        }

    default_hold = hold_years if hold_years in HOLD_WINDOWS else 10
    cases = {
        case: {
            **endpoints[str(default_hold)][case],
            "case": case,
        }
        for case in ("BEAR", "BASE", "BULL")
    }

    top_factors = model["factors"][:8]
    base_case = cases["BASE"]
    base_100 = endpoints["100"]["BASE"]
    bull_100 = endpoints["100"]["BULL"]
    mult_100 = (
        (base_100["total_back_usd"] / purchase) if purchase and base_100.get("total_back_usd") else None
    )
    summary = (
        f"For {this_property(parcel, listing, with_place=True, with_acres=True)}: "
        f"{model['factor_count']} screens bend the path (not a flat line). "
        f"Typical {default_hold}-yr hold screens about "
        f"{base_case['irr_display'] if base_case.get('irr') is not None else 'n/a'} "
        f"before inflation ({base_case.get('irr_real_display') or 'n/a'} in today’s $), "
        f"with exit near {_money(base_case.get('exit_usd'))} "
        f"(~{_money(base_case.get('exit_usd_today'))} in today’s $)."
    )
    horizon_notes = {
        "10": (
            f"Decade holds mostly track this file’s near-term screens. "
            f"Compare After inflation vs Before inflation (~{infl['cpi_display']} CPI). "
            f"Opportunity score is the buy edge — not this hold path."
        ),
        "30": (
            "By 30 years, path fatigue slows the climb. After inflation shows purchasing power; "
            "Before inflation shows the raw future sticker."
        ),
        "50": (
            "Half-century: Before inflation can look large; After inflation is the CPI-honest read. "
            "Judge the deal on entry discount + mid holds, not century marks alone."
        ),
        "75": (
            "75–100 year screens are illustrative. After inflation applies the CPI haircut; "
            "far-year fatigue still applies so terminals don’t rocket unrealistically."
        ),
        "100": (
            f"At 100 years, typical total-back is about {mult_100:.1f}× buy before inflation "
            f"(~{_money(base_100.get('total_back_usd'))} · ~{_money(base_100.get('total_back_usd_today'))} "
            f"after inflation); optimistic tops near {_money(bull_100.get('total_back_usd'))}."
            if mult_100 is not None
            else "Century marks are a screen — compare Before vs After inflation."
        ),
    }

    return {
        "available": True,
        "purchase_usd": round(float(purchase), 0),
        "mark_usd": round(float(mark_usd), 0) if mark_usd else None,
        "hold_years": default_hold,
        "windows": HOLD_WINDOWS,
        "inflation": infl,
        "model": {
            "effective_annual": model["effective_annual"],
            "effective_annual_display": f"{model['effective_annual']*100:.1f}%/yr",
            "uncertainty": model["uncertainty"],
            "usable_frac": model["usable_frac"],
            "factor_count": model["factor_count"],
            "place": model["place"],
            "strategy": model.get("strategy"),
        },
        "factors": top_factors,
        "all_factors": model["factors"],
        "cases": cases,
        "paths_100": {
            case: {
                "path": full_paths[case]["path"],
                "case_label": full_paths[case]["case_label"],
                "purchase_usd": full_paths[case]["purchase_usd"],
                "starting_noi": full_paths[case]["starting_noi"],
                "effective_annual_used": full_paths[case]["effective_annual_used"],
            }
            for case in ("BEAR", "BASE", "BULL")
        },
        "endpoints": endpoints,
        "horizon_notes": horizon_notes,
        "summary": summary,
        "method": (
            "Owned-land pace matches the land-value path (state prior + parcel screens once). "
            "Auction/tax-sale channel cheapens the buy, not lifelong appreciation. Land mark "
            "starts at our value; IRR still uses what you pay. Carry, exit haircut, and light "
            "long-hold fade apply. Before inflation = raw future $; After inflation = ÷ "
            f"(1+CPI)^years at {infl['cpi_display']}. Screen — not an appraisal."
        ),
    }
