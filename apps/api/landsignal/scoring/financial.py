from __future__ import annotations


def clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def price_per_acre(price_usd: float | None, acreage: float | None) -> float | None:
    if price_usd is None or acreage is None or acreage <= 0:
        return None
    return price_usd / acreage


def asking_discount_pct(asking: float | None, estimated: float | None) -> float | None:
    if asking is None or estimated is None or estimated <= 0 or asking < 0:
        return None
    return ((asking - estimated) / estimated) * 100.0


def margin_of_safety(purchase: float, base_value: float) -> float:
    if base_value <= 0:
        return 0.0
    return (base_value - purchase) / base_value


def noi_from_rent(
    gross_rent: float,
    vacancy_rate: float,
    opex: float,
    taxes: float,
    insurance: float,
    management: float,
) -> float:
    egi = gross_rent * (1 - vacancy_rate)
    return egi - opex - taxes - insurance - management


def cap_rate(noi: float, value: float) -> float | None:
    if value <= 0:
        return None
    return noi / value


def cash_on_cash(annual_cf: float, equity: float) -> float | None:
    if equity <= 0:
        return None
    return annual_cf / equity


def npv(rate: float, cash_flows: list[float]) -> float:
    total = 0.0
    for t, cf in enumerate(cash_flows):
        total += cf / ((1 + rate) ** t)
    return total


def irr(
    cash_flows: list[float],
    lo: float = -0.99,
    hi: float = 10.0,
    tol: float = 1e-6,
    max_iter: int = 200,
) -> float | None:
    if len(cash_flows) < 2:
        return None
    npv_lo = npv(lo, cash_flows)
    npv_hi = npv(hi, cash_flows)
    if npv_lo * npv_hi > 0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        npv_mid = npv(mid, cash_flows)
        if abs(npv_mid) < tol:
            return mid
        if npv_lo * npv_mid <= 0:
            hi = mid
            npv_hi = npv_mid
        else:
            lo = mid
            npv_lo = npv_mid
    return (lo + hi) / 2


def breakeven_land_value(noi: float, target_cap: float) -> float | None:
    if target_cap <= 0:
        return None
    return noi / target_cap


def farmland_scenario(
    cash_rent_per_acre: float,
    acres: float,
    vacancy_rate: float,
    opex_per_acre: float,
    taxes: float,
    insurance: float,
    management: float,
    purchase_price: float,
    hold_years: int,
    exit_cap_rate: float,
    annual_appreciation: float,
    discount_rate: float,
) -> dict:
    gross = cash_rent_per_acre * acres
    noi = noi_from_rent(
        gross,
        vacancy_rate,
        opex_per_acre * acres,
        taxes,
        insurance,
        management,
    )
    flows = [-purchase_price] + [noi] * hold_years
    exit_value = purchase_price * ((1 + annual_appreciation) ** hold_years)
    flows[-1] += exit_value
    return {
        "gross_rent": gross,
        "noi": noi,
        "cap_rate": cap_rate(noi, purchase_price),
        "cash_on_cash": cash_on_cash(noi, purchase_price),
        "irr": irr(flows),
        "npv": npv(discount_rate, flows),
        "breakeven_land_value": breakeven_land_value(noi, exit_cap_rate),
    }
