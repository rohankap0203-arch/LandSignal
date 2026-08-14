"""Canonical property identity + multi-source dedupe."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Mapping


def _norm_apn(apn: str | None) -> str | None:
    if not apn:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(apn)).upper()
    return cleaned or None


def _norm_addr(addr: str | None) -> str | None:
    if not addr:
        return None
    s = re.sub(r"\s+", " ", str(addr).strip().upper())
    s = s.replace(",", "")
    return s or None


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        if isinstance(v, dict):
            v = v.get("value")
        n = float(v)
        return n if n == n else None
    except (TypeError, ValueError):
        return None


def canonical_property_id(row: Mapping[str, Any]) -> str:
    """Stable id preference: ATTOM → FIPS+APN → address → geo+acres → fingerprint."""
    attom = row.get("attomId") or row.get("attom_id")
    if attom:
        return f"attom:{attom}"
    fips = str(row.get("fips") or "").strip()
    apn = _norm_apn(row.get("apn") or row.get("parcel_id"))
    if fips and apn:
        return f"fipsapn:{fips}:{apn}"
    addr = _norm_addr(row.get("address") or row.get("oneLine"))
    st = str(row.get("state") or "").upper()[:2]
    if addr and st:
        return f"addr:{st}:{addr}"
    lat, lon = _f(row.get("latitude")), _f(row.get("longitude"))
    acres = _f(row.get("acreage") if row.get("acreage") is not None else row.get("acres"))
    if lat is not None and lon is not None:
        # ~11m grid
        return f"geo:{lat:.4f}:{lon:.4f}:a{round(acres or 0, 2)}"
    blob = "|".join(str(row.get(k) or "") for k in ("title", "county", "state", "external_id", "provider_id"))
    return "fp:" + hashlib.sha1(blob.encode()).hexdigest()[:16]


def _geo_close(a: Mapping[str, Any], b: Mapping[str, Any], *, meters: float = 40.0) -> bool:
    lat1, lon1 = _f(a.get("latitude")), _f(a.get("longitude"))
    lat2, lon2 = _f(b.get("latitude")), _f(b.get("longitude"))
    if None in (lat1, lon1, lat2, lon2):
        return False
    # Equirectangular approx
    dy = (lat1 - lat2) * 111_320
    dx = (lon1 - lon2) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy) <= meters


def merge_property_records(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    """Merge sources; prefer non-null values with provenance lists."""
    out = dict(primary)
    sources = list(out.get("sources") or [])
    for s in secondary.get("sources") or []:
        if s not in sources:
            sources.append(s)
    out["sources"] = sources
    for k, v in secondary.items():
        if k in {"sources", "field_provenance"}:
            continue
        if out.get(k) in (None, "", [], {}):
            out[k] = v
    prov = dict(out.get("field_provenance") or {})
    for k, v in secondary.items():
        if v in (None, "", [], {}):
            continue
        if k not in prov:
            src = (secondary.get("sources") or ["unknown"])[0]
            prov[k] = src
    out["field_provenance"] = prov
    out["canonicalPropertyId"] = canonical_property_id(out)
    return out


def dedupe_candidates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Dedupe by canonical id + geo proximity. Returns (unique_rows, duplicates_removed)."""
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    removed = 0
    for row in rows:
        cid = canonical_property_id(row)
        row = {**row, "canonicalPropertyId": cid}
        if cid in by_id:
            by_id[cid] = merge_property_records(by_id[cid], row)
            removed += 1
            continue
        # Secondary geo match against recent
        matched = None
        lat = _f(row.get("latitude"))
        if lat is not None:
            for existing_id in order[-50:]:
                if _geo_close(by_id[existing_id], row):
                    acres_a = _f(by_id[existing_id].get("acreage") or by_id[existing_id].get("acres"))
                    acres_b = _f(row.get("acreage") or row.get("acres"))
                    if acres_a is None or acres_b is None or abs(acres_a - acres_b) <= max(0.15, 0.05 * max(acres_a, acres_b)):
                        matched = existing_id
                        break
        if matched:
            by_id[matched] = merge_property_records(by_id[matched], row)
            removed += 1
            continue
        by_id[cid] = row
        order.append(cid)
    return [by_id[i] for i in order], removed
