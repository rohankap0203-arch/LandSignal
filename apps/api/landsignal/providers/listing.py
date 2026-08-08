from __future__ import annotations

from typing import Any

from landsignal.models import ProviderStatus
from landsignal.providers.base import ListingProvider, ProviderResult
from landsignal.settings import Settings


class ManualListingProvider(ListingProvider):
    id = "manual"
    name = "Manual Entry"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def search_listings(self, query: dict[str, Any]) -> ProviderResult[list[dict]]:
        return ProviderResult(True, ProviderStatus.CONFIGURED, [])

    async def get_listing(self, external_id: str) -> ProviderResult[dict]:
        return ProviderResult(False, ProviderStatus.CONFIGURED, error="Not found")

    def normalize_listing(self, raw: dict) -> dict:
        acres = raw.get("acreage")
        ask = raw.get("asking_price_usd")
        ppa = (ask / acres) if ask and acres else None
        return {
            "provider_id": self.id,
            "external_id": raw.get("external_id") or raw.get("apn") or raw.get("title"),
            "title": raw.get("title"),
            "description": raw.get("description"),
            "asking_price_usd": ask,
            "acreage": acres,
            "price_per_acre_usd": ppa,
            "state": raw.get("state"),
            "county": raw.get("county"),
            "apn": raw.get("apn"),
            "address": raw.get("address"),
            "latitude": raw.get("latitude"),
            "longitude": raw.get("longitude"),
            "polygon": raw.get("polygon"),
            "source_url": raw.get("source_url"),
            "status": raw.get("status") or "ACTIVE",
        }


class CsvListingProvider(ManualListingProvider):
    id = "csv"
    name = "CSV Import"


class NotConfiguredListingProvider(ListingProvider):
    def __init__(self, provider_id: str, name: str, env_hint: str):
        self.id = provider_id
        self.name = name
        self.env_hint = env_hint

    def status(self) -> ProviderStatus:
        return ProviderStatus.NOT_CONFIGURED

    async def search_listings(self, query: dict[str, Any]) -> ProviderResult[list[dict]]:
        return ProviderResult(
            False,
            ProviderStatus.NOT_CONFIGURED,
            error=f"{self.name} is NOT_CONFIGURED. Set {self.env_hint}.",
        )

    async def get_listing(self, external_id: str) -> ProviderResult[dict]:
        return await self.search_listings({})

    def normalize_listing(self, raw: dict) -> dict:
        raise RuntimeError(f"{self.name} is NOT_CONFIGURED")


def build_listing_providers(settings: Settings) -> dict[str, ListingProvider]:
    from landsignal.providers.blm_lpad import BlmLpadProvider

    providers: dict[str, ListingProvider] = {
        "manual": ManualListingProvider(),
        "csv": CsvListingProvider(),
        "blm_lpad": BlmLpadProvider(),
    }
    providers["mls_reso"] = NotConfiguredListingProvider(
        "mls_reso",
        "MLS / RESO",
        "MLS_RESO_TOKEN"
        if not settings.mls_reso_token
        else "MLS_RESO_TOKEN present but licensed RESO client adapter pending board contract",
    )
    providers["land_com"] = NotConfiguredListingProvider(
        "land_com",
        "Land.com Family",
        "LAND_COM_API_KEY"
        if not settings.land_com_api_key
        else "LAND_COM_API_KEY present but licensed adapter pending vendor access",
    )
    providers["crexi"] = NotConfiguredListingProvider(
        "crexi", "Crexi", "CREXI_API_KEY"
    )
    return providers
