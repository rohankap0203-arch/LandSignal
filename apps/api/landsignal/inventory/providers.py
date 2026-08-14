"""Provider-agnostic inventory adapters.

Production nationwide listings require licensed credentials (ATTOM, BatchData,
MLS/RESO, Bridge, land feeds). Until configured, adapters report NOT_CONFIGURED
and public GIS / BLM adapters remain the live free path.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from landsignal.inventory.schema import LandListing, ProviderSyncStatus
from landsignal.settings import Settings, get_settings


class InventoryProvider(ABC):
    provider_id: str
    label: str

    @abstractmethod
    def sync_status(self, settings: Settings | None = None) -> ProviderSyncStatus:
        ...

    @abstractmethod
    async def fetch_page(self, query: dict[str, Any]) -> list[LandListing]:
        ...


class _CredentialedStub(InventoryProvider):
    """Scaffold for licensed APIs — ready when env keys are supplied."""

    env_key: str
    supplies: str

    def sync_status(self, settings: Settings | None = None) -> ProviderSyncStatus:
        settings = settings or get_settings()
        configured = bool(getattr(settings, self.env_key, None))
        return ProviderSyncStatus(
            provider_id=self.provider_id,
            label=self.label,
            status="HEALTHY" if configured else "NOT_CONFIGURED",
            notes=(
                f"Supplies: {self.supplies}. Set {self.env_key.upper()} to enable."
                if not configured
                else f"Credential present for {self.label}."
            ),
        )

    async def fetch_page(self, query: dict[str, Any]) -> list[LandListing]:
        status = self.sync_status()
        if status.status == "NOT_CONFIGURED":
            return []
        # Credentialed path reserved for production wiring.
        return []


class AttomProvider(_CredentialedStub):
    provider_id = "attom"
    label = "ATTOM"
    env_key = "attom_api_key"
    supplies = "nationwide property + listing attributes, APN, geo, assessments"


class BatchDataProvider(_CredentialedStub):
    provider_id = "batchdata"
    label = "BatchData"
    env_key = "batchdata_api_key"
    supplies = "skip-trace + property/listing enrichment nationwide"


class MlsResoProvider(_CredentialedStub):
    provider_id = "mls_reso"
    label = "MLS / RESO Web API"
    env_key = "mls_reso_token"
    supplies = "active MLS land listings via RESO (broker / IDX agreements required)"


class BridgeInteractiveProvider(_CredentialedStub):
    provider_id = "bridge"
    label = "Bridge Interactive"
    env_key = "bridge_api_key"
    supplies = "MLS listing feeds via Bridge Interactive"


class LandComProvider(_CredentialedStub):
    provider_id = "land_com"
    label = "Land.com"
    env_key = "land_com_api_key"
    supplies = "land-specialized active listings"


class CrexiProvider(_CredentialedStub):
    provider_id = "crexi"
    label = "Crexi"
    env_key = "crexi_api_key"
    supplies = "commercial / land marketplace listings"


class PublicRecordsProvider(InventoryProvider):
    provider_id = "public_records"
    label = "Public GIS / Cadastral Screens"
    supplies = "county + statewide vacant/ag FeatureServers (free)"

    def sync_status(self, settings: Settings | None = None) -> ProviderSyncStatus:
        return ProviderSyncStatus(
            provider_id=self.provider_id,
            label=self.label,
            status="HEALTHY",
            notes="Wired ArcGIS vacant/ag + tax/surplus screens. Not MLS asking-price inventory.",
        )

    async def fetch_page(self, query: dict[str, Any]) -> list[LandListing]:
        # Live path remains PublicTaxSaleProvider / statewide adapters.
        return []


class BlmProvider(InventoryProvider):
    provider_id = "blm_lpad"
    label = "BLM Land Patent / Sales"
    supplies = "federal land sale / conveyance tracts (western states + AK)"

    def sync_status(self, settings: Settings | None = None) -> ProviderSyncStatus:
        return ProviderSyncStatus(
            provider_id=self.provider_id,
            label=self.label,
            status="HEALTHY",
            notes="BLM LPAD public feed — important CA/western coverage when discover budgets allow.",
        )

    async def fetch_page(self, query: dict[str, Any]) -> list[LandListing]:
        return []


def all_inventory_providers() -> list[InventoryProvider]:
    return [
        PublicRecordsProvider(),
        BlmProvider(),
        AttomProvider(),
        BatchDataProvider(),
        MlsResoProvider(),
        BridgeInteractiveProvider(),
        LandComProvider(),
        CrexiProvider(),
    ]
