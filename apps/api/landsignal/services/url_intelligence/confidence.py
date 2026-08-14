"""Confidence engine for URL-ingested properties — no random scores."""

from __future__ import annotations

from typing import Any

from landsignal.services.url_intelligence.provenance import unwrap


def _avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def compute_url_confidence(
    *,
    fields: dict[str, Any],
    identity: dict[str, Any],
    conflicts: list[dict[str, Any]],
    fetch_status: str,
    semantic: dict[str, Any],
    enrichment_present: bool = False,
) -> dict[str, Any]:
    listing_confs: list[float] = []
    for key in ("askingPrice", "acreage", "title", "address", "state"):
        f = fields.get(key)
        if isinstance(f, dict) and f.get("confidence") is not None:
            listing_confs.append(float(f["confidence"]) * 100)

    listing_data = _avg(listing_confs) if listing_confs else 35.0
    if fetch_status in {"blocked", "thin_or_app_shell", "http_error", "network_error"}:
        listing_data = min(listing_data, 55.0)

    parcel_identity = float(identity.get("propertyIdentityConfidence") or 0)

    zoning = 40.0
    if fields.get("zoning") and unwrap(fields.get("zoning")):
        z = fields["zoning"]
        zoning = float(z.get("confidence", 0.6)) * 100 if isinstance(z, dict) else 60.0

    environmental = 45.0
    if semantic.get("environment") or semantic.get("hazards"):
        environmental = 70.0
    if enrichment_present:
        environmental = max(environmental, 80.0)

    market = 50.0
    if unwrap(fields.get("askingPrice")) and unwrap(fields.get("acreage")):
        market = 72.0
    if enrichment_present:
        market = max(market, 78.0)

    valuation = 48.0
    if unwrap(fields.get("askingPrice")) and unwrap(fields.get("acreage")) and parcel_identity >= 50:
        valuation = 70.0
    if enrichment_present:
        valuation = max(valuation, 82.0)

    # Conflict penalty
    penalty = min(25.0, 6.0 * len(conflicts))
    # Missing material fields
    missing_penalty = 0.0
    for key in ("acreage", "state", "latitude"):
        if unwrap(fields.get(key if key != "latitude" else "latitude")) is None and (
            key != "latitude" or unwrap(fields.get("longitude")) is None
        ):
            if key == "latitude":
                if unwrap(fields.get("latitude")) is None or unwrap(fields.get("longitude")) is None:
                    missing_penalty += 8
            else:
                missing_penalty += 8

    categories = {
        "Parcel Identity": round(parcel_identity, 1),
        "Listing Data": round(max(0, listing_data - penalty * 0.3), 1),
        "Zoning": round(zoning, 1),
        "Environmental": round(max(0, environmental - penalty * 0.2), 1),
        "Market Data": round(max(0, market - penalty * 0.2), 1),
        "Valuation Inputs": round(max(0, valuation - penalty * 0.4 - missing_penalty), 1),
    }
    overall = _avg(list(categories.values()))
    overall = max(0.0, min(100.0, overall - penalty * 0.5))

    return {
        "overall": round(overall, 1),
        "categories": categories,
        "conflictPenalty": round(penalty, 1),
        "missingPenalty": round(missing_penalty, 1),
    }
