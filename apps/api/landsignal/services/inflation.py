"""Long-run inflation assumption for screening dollars.

Engine cashflows stay nominal (today’s money units compounded forward).
We also report purchasing-power (“today’s $”) by deflating future nominal
dollars with a single long-run CPI assumption — not a live CPI forecast.
"""

from __future__ import annotations

from typing import Any

# Long-run U.S. consumer-price screen (~Fed 2% target + small buffer).
DEFAULT_CPI_ANNUAL = 0.025


def inflation_meta(cpi: float = DEFAULT_CPI_ANNUAL) -> dict[str, Any]:
    return {
        "cpi_annual": cpi,
        "cpi_display": f"{cpi * 100:.1f}%/yr",
        "basis": "long_run_cpi_screen",
        "label_today": "After inflation",
        "label_nominal": "Before inflation",
        "plain": (
            f"We assume prices rise about {cpi * 100:.1f}%/yr. "
            "After inflation = future dollars with that CPI haircut applied. "
            "Before inflation = the raw future number with no CPI haircut."
        ),
    }


def deflate(nominal: float | None, years: float, cpi: float = DEFAULT_CPI_ANNUAL) -> float | None:
    """Convert a future nominal dollar amount into today’s purchasing power."""
    if nominal is None:
        return None
    try:
        n = float(nominal)
        y = float(years)
    except (TypeError, ValueError):
        return None
    if not (n == n) or y < 0:  # NaN guard
        return None
    return n / ((1.0 + cpi) ** y)


def real_rate(nominal_rate: float | None, cpi: float = DEFAULT_CPI_ANNUAL) -> float | None:
    """Fisher-style real rate from a nominal annualized rate."""
    if nominal_rate is None:
        return None
    try:
        r = float(nominal_rate)
    except (TypeError, ValueError):
        return None
    return (1.0 + r) / (1.0 + cpi) - 1.0


def enrich_endpoint_inflation(
    endpoint: dict[str, Any],
    *,
    cpi: float = DEFAULT_CPI_ANNUAL,
) -> dict[str, Any]:
    """Attach today’s-$ totals and a real IRR to a return-path endpoint."""
    from landsignal.scoring.financial import irr as irr_solve

    years = int(endpoint.get("hold_years") or 0)
    purchase = float(endpoint.get("purchase_usd") or 0)
    path = list(endpoint.get("path") or [])
    if years <= 0 or purchase <= 0 or not path:
        return {
            **endpoint,
            "exit_usd_today": deflate(endpoint.get("exit_usd"), max(years, 0), cpi),
            "cumulative_rent_usd_today": None,
            "total_back_usd_today": None,
            "gain_usd_today": None,
            "irr_real": None,
            "irr_real_display": "n/a",
        }

    rent_today = 0.0
    flows_real = [-purchase]
    for i, pt in enumerate(path):
        y = float(pt.get("year_offset") or (i + 1))
        noi = float(pt.get("noi_usd") or 0.0)
        # Match path accounting: cumulative rent only banks non-negative NOI.
        rent_today += max(0.0, noi) / ((1.0 + cpi) ** y)
        if i == len(path) - 1:
            cf = noi + float(pt.get("exit_usd") or pt.get("land_usd") or 0.0)
        else:
            cf = noi
        flows_real.append(cf / ((1.0 + cpi) ** y))

    exit_today = deflate(endpoint.get("exit_usd"), years, cpi)
    total_today = (exit_today or 0.0) + rent_today
    gain_today = total_today - purchase
    irr_real = irr_solve(flows_real)

    return {
        **endpoint,
        "exit_usd_today": round(exit_today, 0) if exit_today is not None else None,
        "cumulative_rent_usd_today": round(rent_today, 0),
        "total_back_usd_today": round(total_today, 0),
        "gain_usd_today": round(gain_today, 0),
        "irr_real": irr_real,
        "irr_real_display": f"{irr_real * 100:.1f}%/yr" if irr_real is not None else "n/a",
    }
