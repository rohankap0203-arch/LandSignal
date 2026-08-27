"""Live filter coverage — only offer dropdown values that have ≥1 real hit.

The State / price / acre / channel catalogs used to list the full US even when
inventory only covered ~17 states, so Show Matches returned empty for TX, WY,
etc. Filter options must be derived from scored live inventory so any offered
combination can return at least one result that actually adheres.
"""

from __future__ import annotations

from typing import Any

from landsignal.geo_meta import US_STATES, search_meta_payload
from landsignal.store import MemoryStore

_STATE_NAME = {s["code"]: s["name"] for s in US_STATES}


def _budget_usd(listing, score, store) -> float | None:
    ask = listing.asking_price_usd
    if ask is not None and ask > 0:
        return float(ask)
    try:
        from landsignal.services.assessed_price import extract_assessed_land_usd

        assessed = extract_assessed_land_usd(listing.raw)
        if assessed is not None and assessed > 0:
            return float(assessed)
    except Exception:
        pass
    est = getattr(score, "estimated_value_usd", None)
    if est is not None and est > 0:
        # Unpriced process parcels: use model mark only for "has inventory in band"
        # coverage of open-ended presets — never as a fake ask on the card.
        return float(est)
    return None


def _preset_hit_price(budget: float | None, preset: dict[str, Any], *, unpriced_ok: bool) -> bool:
    if budget is None:
        return bool(unpriced_ok and preset.get("min") is None and preset.get("max") is None)
    lo = preset.get("min")
    hi = preset.get("max")
    if lo is not None and budget < float(lo):
        return False
    if hi is not None and budget > float(hi):
        return False
    return True


def _preset_hit_acres(acres: float | None, preset: dict[str, Any]) -> bool:
    if acres is None:
        return preset.get("min") is None and preset.get("max") is None
    lo = preset.get("min")
    hi = preset.get("max")
    if lo is not None and acres < float(lo):
        return False
    if hi is not None and acres > float(hi):
        return False
    return True


def build_live_filter_catalog(store: MemoryStore) -> dict[str, Any]:
    """Prune the canonical catalog to values that exist in scored live inventory."""
    base = search_meta_payload()
    price_presets = list(base["price_presets"])
    acre_presets = list(base["acre_presets"])
    channel_defs = list(base.get("market_channels") or [])
    risk_opts = [x for x in (base.get("max_risk") or []) if x != "Any"]
    conf_opts = [x for x in (base.get("min_confidence") or []) if x != "Any"]

    by_state_counts: dict[str, int] = {}
    # coverage[state_or_Any] -> sets of viable option keys
    cov: dict[str, dict[str, set]] = {}

    def bucket(key: str) -> dict[str, set]:
        if key not in cov:
            cov[key] = {
                "price": set(),
                "acres": set(),
                "channels": set(),
                "regions": set(),
                "max_risk": set(),
                "min_confidence": set(),
                "unpriced": set(),
            }
        return cov[key]

    scored_n = 0
    for parcel in store.parcels.values():
        if parcel.is_demo or not parcel.state:
            continue
        listing = store.listing_for_parcel(parcel.id)
        score = store.latest_score(parcel.id)
        if not listing or not score:
            continue
        scored_n += 1
        st = parcel.state.upper()
        by_state_counts[st] = by_state_counts.get(st, 0) + 1
        budget = _budget_usd(listing, score, store)
        acres = parcel.acreage
        priced = budget is not None and (listing.asking_price_usd or 0) > 0
        channel = listing.provider_id or "manual"
        region = f"{parcel.county}, {parcel.state}" if parcel.county else None
        risk = float(score.risk or 0)
        conf = float(score.confidence or 0)

        for scope in ("Any", st):
            b = bucket(scope)
            if region:
                b["regions"].add(region)
            b["channels"].add(channel)
            if priced:
                b["channels"].add("priced_only")
                b["unpriced"].add("priced")
                b["unpriced"].add("include")
            else:
                b["unpriced"].add("unpriced_only")
                b["unpriced"].add("include")
            for p in price_presets:
                label = p.get("label")
                if not label or label in ("Any", "Custom…"):
                    continue
                if _preset_hit_price(budget, p, unpriced_ok=not priced):
                    # Open-ended "Up to" presets need a real budget to adhere.
                    if p.get("max") is not None and budget is None:
                        continue
                    if p.get("min") is not None and budget is None:
                        continue
                    b["price"].add(label)
            for a in acre_presets:
                label = a.get("label")
                if not label or label in ("Any", "Custom range…"):
                    continue
                if _preset_hit_acres(acres, a):
                    b["acres"].add(label)
            for r in risk_opts:
                try:
                    if risk <= float(r):
                        b["max_risk"].add(r)
                except (TypeError, ValueError):
                    continue
            for c in conf_opts:
                try:
                    if conf >= float(c):
                        b["min_confidence"].add(c)
                except (TypeError, ValueError):
                    continue

    live_states = sorted(by_state_counts.keys())
    state_labels = ["Any", *[f"{c} — {_STATE_NAME.get(c, c)}" for c in live_states]]

    def serialize_scope(scope: str) -> dict[str, Any]:
        b = cov.get(scope) or {
            "price": set(),
            "acres": set(),
            "channels": set(),
            "regions": set(),
            "max_risk": set(),
            "min_confidence": set(),
            "unpriced": set(),
        }
        price_out = [p for p in price_presets if p["label"] == "Any" or p["label"] == "Custom…" or p["label"] in b["price"]]
        # Keep Custom always; drop empty closed presets
        acre_out = [a for a in acre_presets if a["label"] == "Any" or a["label"] == "Custom range…" or a["label"] in b["acres"]]
        channels_out = [
            ch
            for ch in channel_defs
            if ch["value"] == "Any" or ch["value"] in b["channels"]
        ]
        unpriced_out = [
            u
            for u in (base.get("unpriced_options") or [])
            if u["value"] in b["unpriced"] or u["value"] == "include"
        ]
        if not unpriced_out:
            unpriced_out = list(base.get("unpriced_options") or [])
        risk_out = ["Any", *sorted(b["max_risk"], key=lambda x: float(x))]
        conf_out = ["Any", *sorted(b["min_confidence"], key=lambda x: float(x))]
        regions_out = ["Any", *sorted(b["regions"])[:400]]
        return {
            "price_presets": price_out,
            "acre_presets": acre_out,
            "market_channels": channels_out,
            "unpriced_options": unpriced_out,
            "max_risk": risk_out,
            "min_confidence": conf_out,
            "regions": regions_out,
        }

    coverage_by_state = {st: serialize_scope(st) for st in ["Any", *live_states]}

    # National defaults = Any scope
    national = coverage_by_state.get("Any") or serialize_scope("Any")

    return {
        "states": state_labels,
        "state_codes": ["Any", *live_states],
        "regions": national["regions"],
        "regions_by_state": {
            "Any": national["regions"],
            **{
                st: coverage_by_state[st]["regions"]
                for st in live_states
            },
        },
        "price_presets": national["price_presets"],
        "acre_presets": national["acre_presets"],
        "market_channels": national["market_channels"],
        "unpriced_options": national["unpriced_options"],
        "max_risk": national["max_risk"],
        "min_confidence": national["min_confidence"],
        "strategies": base["strategies"],
        "hold_years": base["hold_years"],
        "sort_options": base["sort_options"],
        "tooltips": base["tooltips"],
        "allows_custom": base["allows_custom"],
        "coverage_by_state": coverage_by_state,
        "inventory_by_state": dict(sorted(by_state_counts.items())),
        "inventory_states": live_states,
        "inventory_count_scored": scored_n,
        "filters_live_backed": True,
        "filters_note": (
            "Dropdowns only list values with at least one scored live parcel, "
            "so Show Matches can return a result that actually adheres. "
            "Custom price/acre boxes can still miss — use presets for guaranteed hits."
        ),
    }
