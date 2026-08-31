"""Staged enrichment helpers for Show Matches / parcel reports.

ATTOM intelligence is retained in a durable on-disk reserve so LandSignal keeps
serving every field the API key once presented — even after the key expires.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from landsignal.services.property_providers.attom import AttomPropertyProvider
from landsignal.services.property_providers.confidence import compute_data_confidence
from landsignal.services.property_providers.ranking import classify_improved
from landsignal.settings import Settings, get_settings

log = structlog.get_logger()

_ATTOM_SNAPSHOT_PATH = os.environ.get(
    "LANDSIGNAL_ATTOM_MEMORY_PATH",
    "/tmp/landsignal_attom_enrichment.json",
)
# Hard reserve cap — keep what the key presented; trim only pathological growth.
_ATTOM_MEMORY_SOFT_CAP = int(os.environ.get("LANDSIGNAL_ATTOM_MEMORY_CAP") or 25_000)
_ATTOM_MEMORY_TRIM_TO = int(os.environ.get("LANDSIGNAL_ATTOM_MEMORY_TRIM") or 20_000)


async def enrich_with_attom(
    parcel_blob: dict[str, Any],
    *,
    deep: bool = False,
    settings: Settings | None = None,
    parcel_key: str | None = None,
) -> dict[str, Any]:
    """Best-effort ATTOM enrichment. Never raises; never invents listings.

    When live ATTOM fails (expired key, auth, circuit), returns last-known
    reserved fields for this parcel if we have them — UI/data stay unchanged.
    """
    settings = settings or get_settings()
    provider = AttomPropertyProvider(settings=settings)
    live: dict[str, Any]
    try:
        result = await provider.enrich_parcel(parcel_blob, deep=deep)
        fields = result.get("fields") or {}
        improved = classify_improved(fields)
        conf = compute_data_confidence(
            {
                **parcel_blob,
                **fields,
                "sources": list(
                    {
                        *(parcel_blob.get("sources") or []),
                        "ATTOM",
                    }
                    if result.get("ok")
                    else (parcel_blob.get("sources") or [])
                ),
            }
        )
        live = {
            **result,
            "improved": improved,
            "data_confidence": conf,
            "from_memory": False,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("attom_enrich_failed", error_type=type(exc).__name__)
        live = {
            "ok": False,
            "state": "UNAVAILABLE",
            "fields": {},
            "error": "ATTOM enrichment unavailable",
            "from_memory": False,
        }

    if live.get("ok") and live.get("fields"):
        return live

    # Live miss — serve durable reserve so expiration never erases presented IQ.
    key = parcel_key or _memory_lookup_key(parcel_blob)
    reserved = load_attom_snapshot(key) if key else None
    if reserved and isinstance(reserved.get("fields"), dict) and reserved["fields"]:
        fields = reserved["fields"]
        improved = classify_improved(fields)
        conf = compute_data_confidence(
            {
                **parcel_blob,
                **fields,
                "sources": list({*(parcel_blob.get("sources") or []), "ATTOM", "ATTOM:MEMORY"}),
            }
        )
        log.info(
            "attom_served_from_memory",
            parcel_key=key,
            live_state=live.get("state"),
            saved_at=reserved.get("saved_at"),
        )
        return {
            "ok": True,
            "state": "RESERVED_MEMORY",
            "fields": fields,
            "improved": improved,
            "data_confidence": conf,
            "from_memory": True,
            "saved_at": reserved.get("saved_at"),
            "live_state": live.get("state"),
            "live_error": live.get("error"),
            "persistencePolicy": "RESERVED_LAST_KNOWN",
        }
    return live


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


def _memory_lookup_key(parcel_blob: dict[str, Any]) -> str | None:
    for k in ("parcel_id", "id"):
        v = parcel_blob.get(k)
        if v:
            return str(v)
    apn = parcel_blob.get("apn")
    state = parcel_blob.get("state")
    if apn and state:
        return f"{str(state).upper()}:{str(apn).strip()}"
    return None


def _read_memory_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"by_parcel": {}, "count": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"by_parcel": {}, "count": 0}
        entries = data.get("by_parcel") if isinstance(data.get("by_parcel"), dict) else {}
        return {**data, "by_parcel": entries, "count": len(entries)}
    except Exception:
        return {"by_parcel": {}, "count": 0}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="attom_mem_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def snapshot_attom_enrichment(
    *,
    parcel_key: str,
    fields: dict[str, Any],
    meta: dict[str, Any] | None = None,
) -> None:
    """Durably reserve ATTOM fields the live key presented (survives key expiry + restarts)."""
    if not parcel_key or not fields:
        return
    path = Path(_ATTOM_SNAPSHOT_PATH)
    try:
        data = _read_memory_file(path)
        entries: dict[str, Any] = dict(data.get("by_parcel") or {})
        now = datetime.now(timezone.utc).isoformat()
        prior = entries.get(str(parcel_key)) if isinstance(entries.get(str(parcel_key)), dict) else {}
        # Never shrink a known good payload — merge field keys, prefer newest values.
        prior_fields = prior.get("fields") if isinstance(prior.get("fields"), dict) else {}
        merged_fields = {**prior_fields, **fields}
        entries[str(parcel_key)] = {
            "saved_at": now,
            "first_saved_at": prior.get("first_saved_at") or prior.get("saved_at") or now,
            "fields": merged_fields,
            "meta": {**(prior.get("meta") or {}), **(meta or {})},
            "persistencePolicy": "RESERVED_LAST_KNOWN",
        }
        if len(entries) > _ATTOM_MEMORY_SOFT_CAP:
            ordered = sorted(entries.items(), key=lambda kv: str((kv[1] or {}).get("saved_at") or ""))
            entries = dict(ordered[-_ATTOM_MEMORY_TRIM_TO:])
            log.warning(
                "attom_memory_trimmed",
                kept=len(entries),
                soft_cap=_ATTOM_MEMORY_SOFT_CAP,
            )
        payload = {
            "note": (
                "LandSignal ATTOM intelligence reserve — every field a live key presented. "
                "Served unchanged after key expiry / NOT_CONFIGURED. "
                "Not for-sale inventory; public GIS/BLM remain Show Matches sources."
            ),
            "count": len(entries),
            "updated_at": now,
            "by_parcel": entries,
        }
        _atomic_write_json(path, payload)
    except Exception as exc:  # noqa: BLE001
        log.warning("attom_snapshot_failed", error=str(exc)[:160])


def load_attom_snapshot(parcel_key: str) -> dict[str, Any] | None:
    """Load a previously reserved ATTOM enrichment (works even if API key is gone)."""
    path = Path(_ATTOM_SNAPSHOT_PATH)
    if not path.exists() or not parcel_key:
        return None
    try:
        data = _read_memory_file(path)
        entry = (data.get("by_parcel") or {}).get(str(parcel_key))
        if isinstance(entry, dict) and entry.get("fields"):
            return entry
        # Secondary key: meta apn/state lookup when UUID key miss
    except Exception:
        return None
    return None


def load_all_attom_snapshots() -> dict[str, dict[str, Any]]:
    data = _read_memory_file(Path(_ATTOM_SNAPSHOT_PATH))
    out: dict[str, dict[str, Any]] = {}
    for k, v in (data.get("by_parcel") or {}).items():
        if isinstance(v, dict) and v.get("fields"):
            out[str(k)] = v
    return out


def prior_attom_ok(enrichment_other: Any) -> dict[str, Any] | None:
    """Extract a previously successful ATTOM payload from enrichment.other."""
    if enrichment_other is None:
        return None
    value = getattr(enrichment_other, "value", None)
    if not isinstance(value, dict):
        return None
    attom = value.get("attom")
    if not isinstance(attom, dict):
        return None
    if attom.get("ok") and isinstance(attom.get("fields"), dict) and attom["fields"]:
        return attom
    return None


def hydrate_attom_memory_into_store(store: Any) -> int:
    """Boot-time: reattach reserved ATTOM IQ onto enrichments (key may already be gone)."""
    from landsignal.models import EnrichmentBundle, KnowledgeState, Provenanced

    entries = load_all_attom_snapshots()
    if not entries:
        return 0
    n = 0
    for pid_s, entry in entries.items():
        try:
            pid = UUID(str(pid_s))
        except Exception:
            continue
        if pid not in getattr(store, "parcels", {}):
            continue
        fields = entry.get("fields")
        if not isinstance(fields, dict) or not fields:
            continue
        existing = store.enrichments.get(pid) or EnrichmentBundle()
        if prior_attom_ok(existing.other):
            # Already have successful IQ in RAM — leave it.
            continue
        existing.other = Provenanced(
            value={
                "attom": {
                    "ok": True,
                    "state": "RESERVED_MEMORY",
                    "fields": fields,
                    "from_memory": True,
                    "saved_at": entry.get("saved_at"),
                    "first_saved_at": entry.get("first_saved_at"),
                    "data_confidence": (entry.get("meta") or {}).get("data_confidence"),
                    "persistencePolicy": "RESERVED_LAST_KNOWN",
                }
            },
            knowledge_state=KnowledgeState.KNOWN,
            confidence=0.8,
            source="ATTOM:MEMORY",
            retrieved_at=datetime.now(timezone.utc),
        )
        store.enrichments[pid] = existing
        n += 1
    if n:
        log.info("attom_memory_hydrated", parcels=n, reserve_size=len(entries))
    return n
