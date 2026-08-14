"""ListingSourceAdapter interface and registry."""

from __future__ import annotations

from typing import Any, Protocol


class ListingSourceAdapter(Protocol):
    id: str
    name: str

    def can_handle(self, url: str, domain: str) -> bool: ...

    def extract(self, html: str, *, url: str, domain: str) -> dict[str, Any]:
        """Return raw extracted dict (adapter-specific). Prefer structured keys."""
        ...

    def normalize(self, raw: dict[str, Any], *, url: str, domain: str) -> dict[str, Any]:
        """Return provenanced field map + flat draft helpers."""
        ...
