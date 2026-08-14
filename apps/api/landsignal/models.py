from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class KnowledgeState(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    ESTIMATED = "ESTIMATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"


class ProviderStatus(str, Enum):
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"


class ScreenResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class Signal(str, Enum):
    EXCEPTIONAL = "EXCEPTIONAL"
    STRONG = "STRONG"
    WATCH = "WATCH"
    REJECT = "REJECT"


class Strategy(str, Enum):
    FARMLAND = "FARMLAND"
    DEVELOPMENT = "DEVELOPMENT"
    LAND_BANK = "LAND_BANK"
    RECREATIONAL = "RECREATIONAL"
    ENERGY = "ENERGY"
    TIMBER = "TIMBER"


class Provenanced(BaseModel):
    value: Any = None
    knowledge_state: KnowledgeState = KnowledgeState.UNKNOWN
    confidence: float | None = None
    source: str | None = None
    retrieved_at: datetime | None = None
    effective_date: str | None = None
    geographic_resolution: str | None = None
    raw: Any = None
    normalized: Any = None


class ProviderInfo(BaseModel):
    id: str
    kind: str
    name: str
    status: ProviderStatus
    detail: str | None = None


class ManualIngestRequest(BaseModel):
    title: str
    state: str = Field(min_length=2, max_length=2)
    county: str | None = None
    apn: str | None = None
    address: str | None = None
    acreage: float | None = None
    asking_price_usd: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    # GeoJSON polygon coordinates [ [ [lon,lat], ... ] ]
    polygon: list[list[list[float]]] | None = None
    source_url: str | None = None
    description: str | None = None


class AlertRuleCreate(BaseModel):
    name: str
    predicate: dict[str, Any]
    channels: list[str] = Field(default_factory=lambda: ["IN_APP"])


class InvestorProfileUpdate(BaseModel):
    capital_available_usd: float | None = None
    min_acres: float | None = None
    max_price_usd: float | None = None
    target_hold_years_min: int | None = None
    target_hold_years_max: int | None = None
    min_target_irr: float | None = None
    preferred_strategies: list[Strategy] | list[str] = Field(default_factory=list)
    risk_tolerance: str | float | int = "MODERATE"
    notify_email: str | None = None
    watchlist_email_updates: bool = True


class ParcelRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    parcel_id: str | None = None
    apn: str | None = None
    address: str | None = None
    county: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    polygon: list[list[list[float]]] | None = None
    acreage: float | None = None
    geometry_confidence: float | None = None
    land_use: str | None = None
    zoning: str | None = None
    future_land_use: str | None = None
    is_demo: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ListingRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    parcel_id: UUID
    provider_id: str
    external_id: str
    status: str = "ACTIVE"
    asking_price_usd: float | None = None
    price_per_acre_usd: float | None = None
    listed_at: datetime | None = None
    last_seen_at: datetime | None = None
    days_on_market: int | None = None
    title: str | None = None
    description: str | None = None
    source_url: str | None = None
    is_demo: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EnrichmentBundle(BaseModel):
    soil: Provenanced = Field(default_factory=Provenanced)
    flood: Provenanced = Field(default_factory=Provenanced)
    wetlands: Provenanced = Field(default_factory=Provenanced)
    terrain: Provenanced = Field(default_factory=Provenanced)
    access: Provenanced = Field(default_factory=Provenanced)
    comps: Provenanced = Field(default_factory=Provenanced)
    infrastructure: Provenanced = Field(default_factory=Provenanced)
    growth: Provenanced = Field(default_factory=Provenanced)
    narratives: dict = Field(default_factory=dict)
    scenarios: list[dict] = Field(default_factory=list)


class ScoreRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    parcel_id: UUID
    listing_id: UUID | None = None
    algorithm_version: str
    weight_version: str
    opportunity: float
    risk: float
    confidence: float
    asymmetry: float
    signal: Signal
    best_strategy: Strategy | None = None
    secondary_strategy: Strategy | None = None
    personalized_opportunity: float | None = None
    estimated_value_usd: float | None = None
    asking_discount_pct: float | None = None
    deal_readiness: float
    strategy_scores: dict[str, float] = Field(default_factory=dict)
    strategy_screens: dict[str, str] = Field(default_factory=dict)
    components: list[dict[str, Any]] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)
    why_interesting: list[str] = Field(default_factory=list)
    why_mispriced: list[str] = Field(default_factory=list)
    what_could_kill: list[str] = Field(default_factory=list)
    why_still_available: list[str] = Field(default_factory=list)
    manual_verification: list[str] = Field(default_factory=list)
    input_hash: str
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class AlertRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    rule_id: UUID | None = None
    parcel_id: UUID
    severity: str
    title: str
    body: dict[str, Any]
    delivered_channels: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AlertRuleRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    predicate: dict[str, Any]
    channels: list[str]
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PrefMode(str, Enum):
    MUST = "must"
    PREFER = "prefer"
    FLEXIBLE = "flexible"


class LandAlertNotify(BaseModel):
    email: bool = True
    sms: bool = False
    in_app: bool = True
    push: bool = False
    sensitivity: str = "strong"  # exceptional | strong | all
    frequency: str = "immediate"  # immediate | daily_digest | weekly_digest | in_app_only
    email_address: str = ""
    phone: str = ""


class LandAlertProfile(BaseModel):
    """Preference-driven land acquisition profile (soft scoring, not rigid SQL filters).

    Supports multiple profiles per user later — keyed by id, scoped by user_id.
    Preferences are soft unless a field's *_mode is \"must\".
    """

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str = "My Land Alert"
    paused: bool = False
    active: bool = True
    preferences: dict[str, Any] = Field(default_factory=dict)
    notify: LandAlertNotify = Field(default_factory=LandAlertNotify)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class LandAlertProfileUpsert(BaseModel):
    id: UUID | None = None
    name: str = "My Land Alert"
    preferences: dict[str, Any] = Field(default_factory=dict)
    notify: LandAlertNotify | None = None
    paused: bool | None = None


class LandAlertMatch(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    profile_id: UUID
    user_id: UUID
    parcel_id: UUID
    preference_match_pct: float
    landsignal_score: float
    why_matched: list[str] = Field(default_factory=list)
    watch_flags: list[str] = Field(default_factory=list)
    status: str = "unseen"  # new | unseen | viewed
    origin: str = "existing_inventory"  # existing_inventory | new_discovery | preference_change | price_update
    is_new_discovery: bool = False
    update_kind: str | None = None  # new_listing | price_drop | price_increase | status_change | new_data
    viewed_at: datetime | None = None
    qualified_for_alert: bool = True
    notified: bool = False
    notified_at: datetime | None = None
    notification_channels: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RadarRow(BaseModel):
    parcel_id: UUID
    listing_id: UUID | None = None
    signal: Signal
    property_name: str
    location: str
    state: str | None = None
    county: str | None = None
    region: str | None = None
    acres: float | None
    acres_display: str
    ask: float | None
    price_display: str
    price_label: str
    price_per_acre: float | None
    price_per_acre_display: str
    estimated_value: float | None
    estimated_value_display: str
    value_knowledge: str
    discount_pct: float | None
    discount_display: str
    discount_help: str | None = None
    opportunity: float
    asymmetry: float
    risk: float
    confidence: float
    deal_readiness: float
    best_strategy: Strategy | None
    best_strategy_label: str
    secondary_strategy_label: str
    freshness_hours: float | None
    status: str
    status_label: str
    is_demo: bool = False
    personalized_opportunity: float | None = None
    fit_score: float | None = None
    summary: str
    match_reasons: list[str] = Field(default_factory=list)
    rating_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    provider_id: str | None = None
    provider_label: str
    headline_metric: str
    risk_label: str
    confidence_label: str
    source_name: str | None = None
    contact_office: str | None = None
    contact_phone: str | None = None
    contact_website: str | None = None
    how_to_buy: str | None = None
    return_thesis: str | None = None
    conviction: str | None = None
    scout_note: str | None = None
    trajectory_regime: str | None = None
    trajectory_label: str | None = None
    trajectory_cagr_5y: str | None = None
    trajectory_sparkline: list[float] = Field(default_factory=list)
    match_tier: str = "exact"  # "exact" | "near"
    near_match_reason: str | None = None
