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
    auto_discover_on_startup: bool = True
    # Aim for Zillow-scale statewide vacant/ag screens (esp. FL_Parcels).
    discover_limit: int = 100000
    discover_min_acres: float = 0.1
    # Always-on Land Alerts monitor (seconds between discovery cycles; respects source rate limits)
    land_alerts_monitor_enabled: bool = True
    land_alerts_poll_seconds: int = 900
    # Keep in step with discover_limit so the always-on monitor rebuilds full inventory
    # after restarts (memory store) instead of capping around ~2.5k parcels.
    land_alerts_discover_limit: int = 100000
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
