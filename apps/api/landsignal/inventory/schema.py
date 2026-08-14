"""Canonical nationwide land-listing schema + provider-agnostic inventory types.

Parcel Universe = underlying cadastral / property records (may be huge).
Active Land Inventory = currently marketed / scouting-eligible opportunities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LandListing(BaseModel):
    """Normalized internal listing — every provider adapter maps into this shape."""

    id: str | None = None
    source: str
    source_listing_id: str
    source_url: str | None = None

    status: str = "ACTIVE"
    listing_date: datetime | None = None
    last_updated: datetime | None = None
    ingested_at: datetime | None = None
    last_verified_at: datetime | None = None
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None

    address: str | None = None
    city: str | None = None
    county: str | None = None
    state: str | None = None
    state_code: str | None = None
    zip: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    region: str | None = None
    subregion: str | None = None

    price: float | None = None
    acreage: float | None = None
    price_per_acre: float | None = None

    property_type: str | None = None
    land_type: str | None = None
    zoning: str | None = None
    current_use: str | None = None
    permitted_uses: list[str] = Field(default_factory=list)

    description: str | None = None

    road_access: str | None = None
    legal_access: str | None = None
    utilities: dict[str, Any] = Field(default_factory=dict)
    water: str | None = None
    sewer: str | None = None
    electricity: str | None = None

    flood_zone: str | None = None
    wetlands: str | None = None
    topography: str | None = None

    parcel_number: str | None = None

    opportunity_score: float | None = None
    projected_roi: float | None = None
    projected_value: float | None = None
    strategy_scores: dict[str, float] = Field(default_factory=dict)
    hold_period_scores: dict[str, float] = Field(default_factory=dict)

    photos: list[str] = Field(default_factory=list)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    inventory_class: Literal["parcel_universe", "active_listing", "cadastral_screen"] = (
        "cadastral_screen"
    )
    is_demo: bool = False


class ProviderSyncStatus(BaseModel):
    provider_id: str
    label: str
    status: Literal["HEALTHY", "DEGRADED", "FAILED", "NOT_CONFIGURED", "STALE"]
    last_success_at: datetime | None = None
    last_error: str | None = None
    records_retrieved: int = 0
    notes: str | None = None


class StateCoverage(BaseModel):
    state_code: str
    state_name: str
    parcel_count: int = 0
    active_listing_count: int = 0
    counties: int = 0
    last_ingested_at: datetime | None = None
    healthy: bool = False


class InventoryHealth(BaseModel):
    """Admin / data-health snapshot — never confuse parcels with active listings."""

    data_mode: Literal["demo", "development", "production"]
    states_covered: int
    states_total: int = 50
    counties_covered: int
    parcel_records: int
    active_land_listings: int
    cadastral_screens: int
    demo_records: int
    listings_added_24h: int = 0
    listings_updated_24h: int = 0
    stale_listings: int = 0
    by_state: list[StateCoverage] = Field(default_factory=list)
    providers: list[ProviderSyncStatus] = Field(default_factory=list)
    inventory_label: str
    warnings: list[str] = Field(default_factory=list)
