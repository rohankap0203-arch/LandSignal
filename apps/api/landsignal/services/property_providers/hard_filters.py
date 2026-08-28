"""Centralized HARD filter gate — absolute constraints only.

Strategy and hold period are ranking signals and must NEVER call this function
as an exclusion rule.
"""

from __future__ import annotations

from typing import Any, Mapping


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None  # NaN guard


def _norm_state(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip().upper()
    if not s or s in {"ANY", "ALL", "*"}:
        return None
    # Accept "FL — Florida" style labels
    if "—" in s:
        s = s.split("—", 1)[0].strip()
    if "-" in s and len(s) > 2:
        s = s.split("-", 1)[0].strip()
    return s[:2] if len(s) >= 2 else s


def _states_from_filters(filters: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("state", "states"):
        raw = filters.get(key)
        if raw is None:
            continue
        if isinstance(raw, (list, tuple, set)):
            parts = list(raw)
        else:
            parts = str(raw).replace(";", ",").split(",")
        for p in parts:
            st = _norm_state(p)
            if st:
                out.add(st)
    return out


def _in_band(value: float | None, lo: float | None, hi: float | None, *, allow_unknown: bool) -> bool:
    if lo is None and hi is None:
        return True
    if value is None:
        return allow_unknown
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def passes_hard_filters(
    property_row: Mapping[str, Any],
    filters: Mapping[str, Any],
    *,
    allow_unknown_price: bool | None = None,
    allow_unknown_acres: bool | None = None,
    region_matcher: Any | None = None,
) -> bool:
    """Return True only when the property satisfies all known hard constraints.

    Hard filters: state, region/county/locality, price min/max, acreage min/max,
    optional property_type when explicitly selected.
    """
    wanted_states = _states_from_filters(filters)
    prop_state = _norm_state(property_row.get("state") or property_row.get("State"))
    if wanted_states:
        if not prop_state or prop_state not in wanted_states:
            return False

    region = filters.get("region")
    if region and str(region).strip() and str(region).strip().upper() not in {"ANY", "ALL"}:
        if region_matcher is not None:
            if not region_matcher(property_row, region):
                return False
        else:
            # Conservative fallback: county / city / region string must match (case-insensitive contains)
            needle = str(region).strip().lower()
            hay = " ".join(
                str(property_row.get(k) or "")
                for k in ("region", "county", "city", "locality", "metro", "location")
            ).lower()
            if needle not in hay:
                return False

    min_price = _f(filters.get("min_price"))
    max_price = _f(filters.get("max_price"))
    # Asking price only — never treat ATTOM historical sale as ask
    ask = _f(
        property_row.get("asking_price_usd")
        if property_row.get("asking_price_usd") is not None
        else property_row.get("ask")
        if property_row.get("ask") is not None
        else property_row.get("asking_price")
    )
    unpriced_ok = allow_unknown_price
    if unpriced_ok is None:
        mode = str(filters.get("unpriced_mode") or "").lower()
        unpriced_ok = mode in {"", "include", "any", "unpriced_only"} and mode != "priced"
        if mode == "priced":
            unpriced_ok = False
        if mode == "unpriced_only":
            return ask is None and _in_band(None, min_price, max_price, allow_unknown=True)
    if not _in_band(ask, min_price, max_price, allow_unknown=bool(unpriced_ok)):
        return False

    min_acres = _f(filters.get("min_acres"))
    max_acres = _f(filters.get("max_acres"))
    acres = _f(property_row.get("acreage") if property_row.get("acreage") is not None else property_row.get("acres"))
    acres_unknown_ok = True if allow_unknown_acres is None else bool(allow_unknown_acres)
    if not _in_band(acres, min_acres, max_acres, allow_unknown=acres_unknown_ok):
        return False

    prop_type = filters.get("property_type") or filters.get("propertyType")
    if prop_type and str(prop_type).strip().upper() not in {"ANY", "ALL", ""}:
        got = str(
            property_row.get("property_type")
            or property_row.get("propertyType")
            or property_row.get("propclass")
            or ""
        ).strip().lower()
        want = str(prop_type).strip().lower()
        if want not in got and got not in want:
            return False

    return True


def hard_filter_failures(property_row: Mapping[str, Any], filters: Mapping[str, Any]) -> list[str]:
    """Debug helper: which hard constraints failed."""
    failures: list[str] = []
    # Re-check component-wise for diagnostics
    wanted = _states_from_filters(filters)
    prop_state = _norm_state(property_row.get("state"))
    if wanted and (not prop_state or prop_state not in wanted):
        failures.append("state")
    ask = _f(property_row.get("asking_price_usd") or property_row.get("ask"))
    if not _in_band(ask, _f(filters.get("min_price")), _f(filters.get("max_price")), allow_unknown=True):
        failures.append("price")
    acres = _f(property_row.get("acreage") or property_row.get("acres"))
    if not _in_band(acres, _f(filters.get("min_acres")), _f(filters.get("max_acres")), allow_unknown=False):
        failures.append("acres")
    return failures
