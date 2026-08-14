"""Search index abstraction.

Today: in-memory / Postgres-ready filtering in the API layer.
Tomorrow: Elasticsearch / OpenSearch / Typesense / Meilisearch behind the same interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal


SortKey = Literal[
    "recommended",
    "fit_desc",
    "score_desc",
    "risk_asc",
    "price_asc",
    "price_desc",
    "acres_asc",
    "acres_desc",
    "price_per_acre_asc",
    "recent",
    "roi_desc",
]


class SearchIndex(ABC):
    """Provider-agnostic search surface for LandListing documents."""

    @abstractmethod
    async def search(self, query: dict[str, Any]) -> dict[str, Any]:
        """Return {exact_match_count, results, facets, pagination, search_metadata}."""

    @abstractmethod
    async def upsert(self, docs: list[dict[str, Any]]) -> int:
        ...

    @abstractmethod
    async def delete(self, ids: list[str]) -> int:
        ...


class MemorySearchIndex(SearchIndex):
    """Placeholder — live path currently uses MemoryStore + radar filters.

    Kept so a dedicated engine can be swapped without rewriting Land Signal.
    """

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}

    async def search(self, query: dict[str, Any]) -> dict[str, Any]:
        return {
            "exact_match_count": 0,
            "results": [],
            "facets": {},
            "pagination": {"page": query.get("page", 1), "page_size": query.get("page_size", 50)},
            "search_metadata": {
                "engine": "memory_store_radar",
                "note": "Production queries currently execute via /v1/radar against MemoryStore; "
                "swap this backend when inventory exceeds comfortable in-process scanning.",
            },
        }

    async def upsert(self, docs: list[dict[str, Any]]) -> int:
        for d in docs:
            doc_id = str(d.get("id") or d.get("source_listing_id"))
            if doc_id:
                self._docs[doc_id] = d
        return len(docs)

    async def delete(self, ids: list[str]) -> int:
        n = 0
        for i in ids:
            if self._docs.pop(i, None) is not None:
                n += 1
        return n


# Compound index guidance for Postgres / future engines (documentation for ops):
RECOMMENDED_INDEXES = [
    "(state, status, price, acreage)",
    "(state, region, price)",
    "(state, county)",
    "(latitude, longitude)",  # or PostGIS GIST
    "(listing_date DESC)",
    "(opportunity_score DESC)",
    "(land_type, state)",
]
