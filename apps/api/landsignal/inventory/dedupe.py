"""Deterministic + fuzzy listing deduplication across providers.

Canonical property = one Land Signal parcel; provider records retained underneath
via listing.raw / external_id provenance.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


def _norm_apn(apn: str | None) -> str | None:
    if not apn:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(apn).upper())
    return cleaned or None


def _norm_addr(address: str | None) -> str | None:
    if not address:
        return None
    s = re.sub(r"\s+", " ", str(address).lower().strip())
    s = re.sub(r"\b(road|rd|street|st|avenue|ave|drive|dr|lane|ln|boulevard|blvd)\b", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return s.strip() or None


def _round_coord(v: float | None, places: int = 4) -> float | None:
    if v is None:
        return None
    return round(float(v), places)


@dataclass(frozen=True)
class DedupeKey:
    """Strong identity key — identical keys merge into one canonical property."""

    kind: str
    value: str


def strong_keys(row: dict[str, Any]) -> list[DedupeKey]:
    keys: list[DedupeKey] = []
    state = (row.get("state") or "").upper()
    apn = _norm_apn(row.get("apn") or row.get("parcel_number"))
    if state and apn:
        keys.append(DedupeKey("apn", f"{state}:{apn}"))
    provider = row.get("provider_id") or row.get("source")
    external = row.get("external_id") or row.get("source_listing_id")
    if provider and external:
        keys.append(DedupeKey("external", f"{provider}:{external}"))
    lat = _round_coord(row.get("latitude"))
    lon = _round_coord(row.get("longitude"))
    acres = row.get("acreage")
    if lat is not None and lon is not None and acres:
        keys.append(DedupeKey("geo_acres", f"{lat}:{lon}:{round(float(acres), 2)}"))
    return keys


def fuzzy_similar(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Conservative fuzzy match — same state + near coords + similar acres/price/address."""
    if (a.get("state") or "").upper() != (b.get("state") or "").upper():
        return False
    lat_a, lon_a = a.get("latitude"), a.get("longitude")
    lat_b, lon_b = b.get("latitude"), b.get("longitude")
    if None in (lat_a, lon_a, lat_b, lon_b):
        return False
    # ~110m per 0.001 deg latitude
    if abs(float(lat_a) - float(lat_b)) > 0.002 or abs(float(lon_a) - float(lon_b)) > 0.002:
        return False
    ac_a, ac_b = a.get("acreage"), b.get("acreage")
    if ac_a and ac_b:
        ratio = min(float(ac_a), float(ac_b)) / max(float(ac_a), float(ac_b))
        if ratio < 0.85:
            return False
    price_a = a.get("asking_price_usd") or a.get("price")
    price_b = b.get("asking_price_usd") or b.get("price")
    if price_a and price_b and min(float(price_a), float(price_b)) > 0:
        pr = min(float(price_a), float(price_b)) / max(float(price_a), float(price_b))
        if pr < 0.8:
            return False
    addr_a = _norm_addr(a.get("address"))
    addr_b = _norm_addr(b.get("address"))
    if addr_a and addr_b and addr_a == addr_b:
        return True
    # Geo+acres proximity alone is enough when both coords present
    return bool(ac_a and ac_b)


def prefer_record(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Prefer freshest + most complete provider row."""

    def completeness(r: dict[str, Any]) -> tuple:
        fields = (
            "asking_price_usd",
            "price",
            "acreage",
            "address",
            "source_url",
            "description",
            "latitude",
            "longitude",
            "polygon",
        )
        filled = sum(1 for f in fields if r.get(f) not in (None, "", [], {}))
        seen = r.get("last_seen_at") or r.get("last_updated") or r.get("source_updated_at") or ""
        return (filled, str(seen))

    return a if completeness(a) >= completeness(b) else b


def merge_duplicates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Collapse duplicate provider rows. Returns (canonical_rows, merge_count)."""
    by_strong: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    merges = 0
    for row in rows:
        keys = strong_keys(row)
        hit_id = None
        for k in keys:
            token = f"{k.kind}:{k.value}"
            if token in by_strong:
                hit_id = token
                break
        if hit_id:
            winner = prefer_record(by_strong[hit_id], row)
            # Keep provider provenance under the winner
            prev = by_strong[hit_id]
            meta = list(winner.get("provider_records") or prev.get("provider_records") or [])
            meta.append(
                {
                    "provider_id": row.get("provider_id") or row.get("source"),
                    "external_id": row.get("external_id") or row.get("source_listing_id"),
                }
            )
            winner = {**winner, "provider_records": meta}
            by_strong[hit_id] = winner
            merges += 1
            continue
        token = f"row:{len(order)}"
        if keys:
            token = f"{keys[0].kind}:{keys[0].value}"
        by_strong[token] = row
        order.append(token)

    # Second pass: fuzzy merge remaining singletons (O(n^2) capped)
    items = [(tid, by_strong[tid]) for tid in order if tid in by_strong]
    drop: set[str] = set()
    for i, (id_a, a) in enumerate(items):
        if id_a in drop:
            continue
        for id_b, b in items[i + 1 :]:
            if id_b in drop:
                continue
            if fuzzy_similar(a, b):
                winner = prefer_record(a, b)
                by_strong[id_a] = winner
                drop.add(id_b)
                merges += 1
    canonical = [by_strong[tid] for tid in order if tid not in drop and tid in by_strong]
    return canonical, merges


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
