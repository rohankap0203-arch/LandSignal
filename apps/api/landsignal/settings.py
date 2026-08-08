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
    demo_seed: bool = True
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
