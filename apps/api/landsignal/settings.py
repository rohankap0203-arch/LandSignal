from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LandSignal API"
    environment: Literal["development", "production", "test"] = "development"
    api_prefix: str = "/v1"
    database_url: str | None = None
    redis_url: str | None = None
    store_backend: Literal["memory", "postgres"] = "memory"
    demo_seed: bool = False
    force_live_on_demo: bool = False
    # Default OFF in cloud VMs — startup nationwide discover OOMs 15Gi pods.
    # Use POST /v1/discover (background) when you want to grow inventory.
    auto_discover_on_startup: bool = False
    discover_limit: int = 1_000_000
    # ~2.5k × 50 states ≈ 125k inventory target without needing MLS.
    discover_min_per_state: int = 2500
    discover_min_acres: float = 0.1
    # Always-on Land Alerts monitor (seconds between discovery cycles; respects source rate limits)
    # Default OFF — the monitor re-runs discover and was a top OOM trigger on cloud agents.
    land_alerts_monitor_enabled: bool = False
    land_alerts_poll_seconds: int = 900
    # Keep in step with discover_limit so the always-on monitor rebuilds full inventory
    # after restarts (memory store) instead of capping around ~2.5k parcels.
    land_alerts_discover_limit: int = 1_000_000
    # Hard RSS ceiling (MB) for discover/rescore — leave headroom for web + agent.
    hard_rss_mb: int = 7500
    soft_rss_mb: int = 6000
    http_timeout_seconds: float = 20.0
    mapbox_token: str | None = None
    smtp_url: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    mls_reso_token: str | None = None
    land_com_api_key: str | None = None
    crexi_api_key: str | None = None
    regrid_api_key: str | None = None
    enable_live_gov_enrichment: bool = True

    # ATTOM Property API — server-side only. Never expose to the browser.
    attom_api_key: str | None = None
    # api | bulk | disabled  (bulk reserved for a future licensed bulk feed)
    attom_data_mode: Literal["api", "bulk", "disabled"] = "api"
    # Must stay ≤ 86400 under current ATTOM API retention terms
    attom_cache_ttl_seconds: int = 82_800
    attom_enrich_on_analyze: bool = True
    attom_enrich_top_n: int = 40


@lru_cache
def get_settings() -> Settings:
    return Settings()
