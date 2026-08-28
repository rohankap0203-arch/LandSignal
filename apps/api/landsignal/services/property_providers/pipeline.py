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


_ATTOM_SNAPSHOT_PATH = "/tmp/landsignal_attom_enrichment.json"


def snapshot_attom_enrichment(
    *,
    parcel_key: str,
    fields: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> None:
    """Persist ATTOM enrichment for test replay after key removal (local /tmp only)."""
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    if not parcel_key or not fields:
        return
    path = Path(_ATTOM_SNAPSHOT_PATH)
    try:
        data: dict[str, Any] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("by_parcel") if isinstance(data.get("by_parcel"), dict) else {}
        entries[str(parcel_key)] = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "fields": fields,
            "meta": meta or {},
        }
        # Cap snapshot size for cloud VMs
        if len(entries) > 5000:
            # drop oldest by saved_at
            ordered = sorted(entries.items(), key=lambda kv: str((kv[1] or {}).get("saved_at") or ""))
            entries = dict(ordered[-4000:])
        payload = {
            "note": (
                "ATTOM enrichment snapshot for tests — not for-sale inventory. "
                "Public GIS/BLM remain the Show Matches candidate source."
            ),
            "count": len(entries),
            "by_parcel": entries,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("attom_snapshot_failed", error=str(exc)[:160])


def load_attom_snapshot(parcel_key: str) -> dict[str, Any] | None:
    """Load a previously snapshotted ATTOM enrichment (works even if API key is gone)."""
    import json
    from pathlib import Path

    path = Path(_ATTOM_SNAPSHOT_PATH)
    if not path.exists() or not parcel_key:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = (data.get("by_parcel") or {}).get(str(parcel_key))
        if isinstance(entry, dict) and entry.get("fields"):
            return entry
    except Exception:
        return None
    return None
