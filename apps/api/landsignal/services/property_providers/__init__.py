"""Property / listing provider abstractions for multi-source search.

ListingProvider  → marketed / discoverable opportunities (public GIS, BLM, MLS…)
PropertyIntelligenceProvider → parcel IQ (ATTOM, county assessors, etc.)

ATTOM is an intelligence provider under current entitlement — not active-listing inventory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class IntelligenceProviderState(str, Enum):
    AVAILABLE = "AVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    AUTH_ERROR = "AUTH_ERROR"
    TRIAL_EXPIRED = "TRIAL_EXPIRED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    DISABLED = "DISABLED"


class PersistencePolicy(str, Enum):
    TEMPORARY_LICENSED = "TEMPORARY_LICENSED"
    PERMANENT_INDEPENDENT = "PERMANENT_INDEPENDENT"
    USER_SUPPLIED = "USER_SUPPLIED"
    LANDSIGNAL_MODEL = "LANDSIGNAL_MODEL"


class MarketStatus(str, Enum):
    ACTIVE_LISTING = "active_listing"
    OFF_MARKET = "off_market"
    SOLD = "sold"
    UNKNOWN = "unknown"


class ListingVerification(str, Enum):
    VERIFIED = "verified"
    PROBABLE = "probable"
    UNVERIFIED = "unverified"


class ProviderResult(Generic[T]):
    def __init__(
        self,
        ok: bool,
        state: IntelligenceProviderState,
        data: T | None = None,
        error: str | None = None,
        meta: dict[str, Any] | None = None,
    ):
        self.ok = ok
        self.state = state
        self.data = data
        self.error = error
        self.meta = meta or {}


class PropertyIntelligenceProvider(ABC):
    """Authoritative parcel / ownership / valuation intelligence — not listings."""

    id: str
    name: str
    kind: str = "PROPERTY_INTELLIGENCE"

    @abstractmethod
    def health_check(self) -> ProviderResult[dict[str, Any]]: ...

    @abstractmethod
    async def get_property_detail(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]: ...

    @abstractmethod
    async def get_ownership(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]: ...

    @abstractmethod
    async def get_assessment(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]: ...

    @abstractmethod
    async def get_sale_history(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]: ...

    @abstractmethod
    async def get_valuation(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]: ...

    @abstractmethod
    async def get_building_data(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]: ...

    async def search_candidates(self, query: dict[str, Any]) -> ProviderResult[list[dict[str, Any]]]:
        """Optional geo/id discovery. Default: not supported."""
        return ProviderResult(False, IntelligenceProviderState.UNAVAILABLE, error="search_not_supported")


class ActiveListingProvider(ABC):
    """Providers that supply currently marketed / process opportunities."""

    id: str
    name: str
    kind: str = "ACTIVE_LISTING"

    @abstractmethod
    def health_check(self) -> ProviderResult[dict[str, Any]]: ...

    @abstractmethod
    async def search_listings(self, query: dict[str, Any]) -> ProviderResult[list[dict[str, Any]]]: ...
