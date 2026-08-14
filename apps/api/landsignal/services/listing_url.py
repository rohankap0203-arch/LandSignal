"""User-initiated listing URL → draft fields for Land Signal intelligence.

Backward-compatible facade over the Universal Listing URL Intelligence Engine.
This is NOT bulk marketplace scraping.
"""

from __future__ import annotations

from typing import Any

from landsignal.services.url_intelligence.adapters.generic import (
    extract_raw as extract_listing_draft_from_html,
    host_label as _host_label,
)
from landsignal.services.url_intelligence.pipeline import (
    extract_listing_intelligence,
    geocode_address,
    missing_required,
)


async def fetch_listing_url(url: str) -> dict[str, Any]:
    """Fetch one user-pasted URL and return a draft + status (legacy shape + extras)."""
    result = await extract_listing_intelligence(url)
    # Preserve legacy keys expected by /ingest page and older clients
    return {
        "ok": result.get("ok", False),
        "error": result.get("error"),
        "draft": result.get("draft") or {},
        "missing": result.get("missing") or [],
        "fetch_status": result.get("fetch_status"),
        "note": result.get("note"),
        "source_host": result.get("source_host"),
        # Extended intelligence envelope
        "fields": result.get("fields"),
        "identity": result.get("identity"),
        "confidence": result.get("confidence"),
        "conflicts": result.get("conflicts"),
        "facts": result.get("facts"),
        "stages": result.get("stages"),
        "missing_material": result.get("missing_material"),
        "needs_confirmation": result.get("needs_confirmation"),
        "fallback": result.get("fallback"),
        "imported_listing": result.get("imported_listing"),
        "canonical_url": result.get("canonical_url"),
        "adapter_id": result.get("adapter_id"),
    }


__all__ = [
    "extract_listing_draft_from_html",
    "missing_required",
    "geocode_address",
    "fetch_listing_url",
    "_host_label",
]
