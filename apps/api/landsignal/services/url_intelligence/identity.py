"""Property identity resolution + duplicate detection against the Land Signal store."""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from landsignal.services.url_intelligence.provenance import unwrap


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _norm_apn(apn: str | None) -> str | None:
    if not apn:
        return None
    cleaned = "".join(c for c in str(apn).upper() if c.isalnum())
    return cleaned or None


def resolve_identity(fields: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """Score how confidently we can identify a physical parcel from listing fields."""
    score = 0
    reasons: list[str] = []
    apn = unwrap(fields.get("apn")) or draft.get("apn")
    lat = unwrap(fields.get("latitude")) or draft.get("latitude")
    lon = unwrap(fields.get("longitude")) or draft.get("longitude")
    address = unwrap(fields.get("address")) or draft.get("address")
    state = unwrap(fields.get("state")) or draft.get("state")
    county = unwrap(fields.get("county")) or draft.get("county")
    acres = unwrap(fields.get("acreage")) or draft.get("acreage")

    if _norm_apn(apn) and state:
        score += 45
        reasons.append("APN + state present")
    elif _norm_apn(apn):
        score += 30
        reasons.append("APN present")

    if lat is not None and lon is not None:
        try:
            float(lat)
            float(lon)
            score += 35
            reasons.append("Coordinates present")
        except (TypeError, ValueError):
            pass

    if address and state:
        score += 15
        reasons.append("Address + state")
    elif address:
        score += 8
        reasons.append("Address only")

    if county and state:
        score += 5
        reasons.append("County + state")

    if acres is not None:
        score += 5
        reasons.append("Acreage present")

    score = max(0, min(100, score))
    if score >= 85:
        state_label = "VERIFIED"
    elif score >= 70:
        state_label = "HIGH_CONFIDENCE"
    elif score >= 50:
        state_label = "PROBABLE"
    elif score >= 25:
        state_label = "AMBIGUOUS"
    else:
        state_label = "UNRESOLVED"

    return {
        "propertyIdentityConfidence": score,
        "state": state_label,
        "reasons": reasons,
        "sufficientForEnrichment": score >= 50 and lat is not None and lon is not None,
        "apn": apn,
        "coordinates": {"latitude": lat, "longitude": lon} if lat is not None and lon is not None else None,
    }


def find_duplicate_parcel(store: Any, draft: dict[str, Any]) -> dict[str, Any] | None:
    """Return existing parcel match if URLs/APN/coords point to the same land."""
    source_url = (draft.get("source_url") or "").strip().rstrip("/")
    apn_n = _norm_apn(draft.get("apn"))
    state = (draft.get("state") or "").upper()[:2]
    lat = draft.get("latitude")
    lon = draft.get("longitude")
    acres = draft.get("acreage")

    best: tuple[float, Any, str] | None = None  # score, parcel, reason

    for listing in getattr(store, "listings", {}).values():
        parcel = store.parcels.get(listing.parcel_id)
        if not parcel:
            continue
        # Same canonical URL
        existing_url = (listing.source_url or "").strip().rstrip("/")
        if source_url and existing_url and source_url.lower() == existing_url.lower():
            return {
                "parcel_id": str(parcel.id),
                "reason": "Same listing URL already imported",
                "matchStrength": 100,
                "message": "This property is already in Land Signal.",
            }

        score = 0
        reason = ""
        p_apn = _norm_apn(parcel.apn)
        if apn_n and p_apn and apn_n == p_apn and (not state or (parcel.state or "").upper() == state):
            score = 95
            reason = "Matching APN"
        elif lat is not None and lon is not None and parcel.latitude is not None and parcel.longitude is not None:
            try:
                dist = _haversine_m(float(lat), float(lon), float(parcel.latitude), float(parcel.longitude))
            except (TypeError, ValueError):
                dist = 1e9
            if dist <= 60:
                score = 80
                reason = f"Coordinates within {int(dist)}m"
                if acres is not None and parcel.acreage is not None:
                    try:
                        ratio = max(float(acres), 0.01) / max(float(parcel.acreage), 0.01)
                        if 0.7 <= ratio <= 1.3:
                            score = 90
                            reason += " with similar acreage"
                        elif ratio < 0.4 or ratio > 2.5:
                            score = 40
                            reason += " but acreage diverges"
                    except (TypeError, ValueError):
                        pass

        if score >= 80 and (best is None or score > best[0]):
            best = (score, parcel, reason)

    if best:
        return {
            "parcel_id": str(best[1].id),
            "reason": best[2],
            "matchStrength": best[0],
            "message": "This property is already in Land Signal.",
        }
    return None


def apply_user_corrections(draft: dict[str, Any], corrections: dict[str, Any] | None) -> dict[str, Any]:
    if not corrections:
        return draft
    out = dict(draft)
    mapping = {
        "title": "title",
        "state": "state",
        "county": "county",
        "apn": "apn",
        "address": "address",
        "acreage": "acreage",
        "asking_price_usd": "asking_price_usd",
        "askingPrice": "asking_price_usd",
        "latitude": "latitude",
        "longitude": "longitude",
        "description": "description",
    }
    for k, dest in mapping.items():
        if k in corrections and corrections[k] not in (None, ""):
            val = corrections[k]
            if dest in ("acreage", "asking_price_usd", "latitude", "longitude"):
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    continue
            if dest == "state":
                val = str(val).upper()[:2]
            out[dest] = val
            out.setdefault("_user_confirmed_fields", [])
            if dest not in out["_user_confirmed_fields"]:
                out["_user_confirmed_fields"].append(dest)
    return out
