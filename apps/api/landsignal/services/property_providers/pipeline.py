"""Staged enrichment helpers for Show Matches / parcel reports."""

from __future__ import annotations

from typing import Any

import structlog

from landsignal.services.property_providers.attom import AttomPropertyProvider
from landsignal.services.property_providers.confidence import compute_data_confidence
from landsignal.services.property_providers.ranking import classify_improved
from landsignal.settings import Settings, get_settings

log = structlog.get_logger()


async def enrich_with_attom(
    parcel_blob: dict[str, Any],
    *,
    deep: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Best-effort ATTOM enrichment. Never raises; never invents listings."""
    settings = settings or get_settings()
    provider = AttomPropertyProvider(settings=settings)
    try:
        result = await provider.enrich_parcel(parcel_blob, deep=deep)
    except Exception as exc:  # noqa: BLE001
        log.warning("attom_enrich_failed", error_type=type(exc).__name__)
        return {
            "ok": False,
            "state": "UNAVAILABLE",
            "fields": {},
            "error": "ATTOM enrichment unavailable",
        }

    fields = result.get("fields") or {}
    improved = classify_improved(fields)
    conf = compute_data_confidence({**parcel_blob, **fields, "sources": list({*(parcel_blob.get("sources") or []), "ATTOM"} if result.get("ok") else (parcel_blob.get("sources") or []))})
    return {
        **result,
        "improved": improved,
        "data_confidence": conf,
    }


def attom_fields_to_enrichment_patch(fields: dict[str, Any]) -> dict[str, Any]:
    """Map normalized ATTOM fields into analyze_parcel / EnrichmentBundle-friendly values."""

    def val(key: str) -> Any:
        item = fields.get(key)
        if isinstance(item, dict) and "value" in item:
            return item.get("value")
        return item

    patch: dict[str, Any] = {}
    acres = val("acreage")
    if acres is not None:
        patch["attom_acreage"] = acres
    avm = None
    valuation = fields.get("valuation") or {}
    if isinstance(valuation, dict):
        avm_item = valuation.get("avmValue")
        if isinstance(avm_item, dict):
            avm = avm_item.get("value")
    if avm is not None:
        patch["attom_avm"] = avm
    assessed = None
    assessment = fields.get("assessment") or {}
    if isinstance(assessment, dict):
        a = assessment.get("assessedValue") or assessment.get("marketValue")
        if isinstance(a, dict):
            assessed = a.get("value")
    if assessed is not None:
        patch["attom_assessed_value"] = assessed
    if fields.get("attomId") is not None:
        patch["attom_id"] = fields.get("attomId")
    if fields.get("hasStructure") is not None:
        patch["has_structure"] = bool(fields.get("hasStructure"))
    for k in ("buildingSqFt", "yearBuilt", "bedrooms", "bathrooms"):
        v = val(k)
        if v is not None:
            patch[k] = v
    owner = fields.get("ownership") or {}
    if isinstance(owner, dict):
        on = owner.get("ownerName")
        if isinstance(on, dict) and on.get("value"):
            patch["owner_name"] = on["value"]
    # Never map sale history amount into asking price
    patch["market_status"] = fields.get("marketStatus") or "off_market"
    patch["availability_status"] = fields.get("availabilityStatus") or "OFF-MARKET PROPERTY"
    return patch
