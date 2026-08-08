from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from landsignal.models import ProviderStatus

T = TypeVar("T")


class ProviderResult(Generic[T]):
    def __init__(
        self,
        ok: bool,
        status: ProviderStatus,
        data: T | None = None,
        error: str | None = None,
    ):
        self.ok = ok
        self.status = status
        self.data = data
        self.error = error


class ListingProvider(ABC):
    id: str
    name: str
    kind: str = "LISTING"

    @abstractmethod
    def status(self) -> ProviderStatus: ...

    @abstractmethod
    async def search_listings(self, query: dict[str, Any]) -> ProviderResult[list[dict]]: ...

    @abstractmethod
    async def get_listing(self, external_id: str) -> ProviderResult[dict]: ...

    @abstractmethod
    def normalize_listing(self, raw: dict) -> dict: ...

    def detect_changes(self, prev: dict, nxt: dict) -> list[dict]:
        changes = []
        for key in ("asking_price_usd", "status", "description", "days_on_market"):
            if prev.get(key) != nxt.get(key):
                changes.append(
                    {"field": key, "old": prev.get(key), "new": nxt.get(key)}
                )
        return changes


class EnrichmentProvider(ABC, Generic[T]):
    id: str
    name: str
    kind: str = "ENRICHMENT"

    @abstractmethod
    def status(self) -> ProviderStatus: ...

    @abstractmethod
    async def enrich(self, parcel: dict) -> ProviderResult[T]: ...
