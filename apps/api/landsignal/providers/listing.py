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
    from landsignal.providers.public_markets import PublicSurplusProvider, PublicTaxSaleProvider

    providers: dict[str, ListingProvider] = {
        "manual": ManualListingProvider(),
        "csv": CsvListingProvider(),
        # Free public approximations of commercial listing/parcel networks
        "blm_lpad": BlmLpadProvider(),
        "public_tax_sale": PublicTaxSaleProvider(),
        "public_surplus": PublicSurplusProvider(),
    }
    # Licensed vendors — Cursor Cloud does not inject these keys; free adapters above are the live path
    providers["mls_reso"] = NotConfiguredListingProvider(
        "mls_reso",
        "MLS / RESO (licensed)",
        "MLS_RESO_TOKEN — use public_tax_sale / blm_lpad free feeds until licensed",
    )
    providers["land_com"] = NotConfiguredListingProvider(
        "land_com",
        "Land.com Family (licensed)",
        "LAND_COM_API_KEY — use blm_lpad + public_tax_sale free feeds until licensed",
    )
    providers["crexi"] = NotConfiguredListingProvider(
        "crexi",
        "Crexi (licensed)",
        "CREXI_API_KEY — use public_surplus free feeds until licensed",
    )
    return providers
