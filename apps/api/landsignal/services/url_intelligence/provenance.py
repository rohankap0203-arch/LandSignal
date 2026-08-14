"""Field-level provenance helpers for URL intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def provenanced(
    value: Any,
    *,
    source: str,
    confidence: float,
    extraction_method: str,
    source_url: str | None = None,
    source_text: str | None = None,
    unit: str | None = None,
    knowledge_state: str = "CONFIRMED",
) -> dict[str, Any]:
    """Build a field envelope. Never invent values — caller supplies value or skips."""
    out: dict[str, Any] = {
        "value": value,
        "source": source,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 3),
        "extractionMethod": extraction_method,
        "knowledgeState": knowledge_state,
    }
    if unit is not None:
        out["unit"] = unit
    if source_url:
        out["sourceUrl"] = source_url
    if source_text:
        out["sourceText"] = source_text[:400]
    out["retrievedAt"] = datetime.now(timezone.utc).isoformat()
    return out


def unwrap(field: Any) -> Any:
    if isinstance(field, dict) and "value" in field:
        return field.get("value")
    return field


def draft_from_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Flatten provenanced fields into ManualIngestRequest-shaped draft."""
    key_map = {
        "title": "title",
        "askingPrice": "asking_price_usd",
        "acreage": "acreage",
        "state": "state",
        "county": "county",
        "address": "address",
        "latitude": "latitude",
        "longitude": "longitude",
        "apn": "apn",
        "description": "description",
        "sourceUrl": "source_url",
        "zoning": "zoning",
        "propertyType": "property_type",
    }
    draft: dict[str, Any] = {}
    for src, dest in key_map.items():
        if src in fields:
            draft[dest] = unwrap(fields[src])
    # Nested utilities / environment stay under structured keys
    for nest in ("utilities", "access", "environment", "hazards", "rights"):
        if nest in fields:
            draft[nest] = fields[nest]
    return draft
