"""Thin host-specific adapters that improve extraction hints, then fall back to generic."""

from __future__ import annotations

from typing import Any

from landsignal.services.url_intelligence.adapters.generic import GenericListingAdapter, extract_raw, normalize_raw


class _HostAdapter(GenericListingAdapter):
    id = "host"
    name = "Host adapter"
    domains: tuple[str, ...] = ()

    def can_handle(self, url: str, domain: str) -> bool:
        d = domain.lower()
        return any(h in d for h in self.domains)

    def extract(self, html: str, *, url: str, domain: str) -> dict[str, Any]:
        raw = extract_raw(html, url=url)
        raw["adapter_id"] = self.id
        return raw

    def normalize(self, raw: dict[str, Any], *, url: str, domain: str) -> dict[str, Any]:
        fields = normalize_raw(raw, url=url, domain=domain)
        # Slight confidence bump for known marketplace layouts when structured data present
        if raw.get("asking_price_usd") and "askingPrice" in fields:
            fields["askingPrice"]["confidence"] = min(0.99, float(fields["askingPrice"]["confidence"]) + 0.03)
        if raw.get("acreage") and "acreage" in fields:
            fields["acreage"]["confidence"] = min(0.98, float(fields["acreage"]["confidence"]) + 0.03)
        return fields


class LandComAdapter(_HostAdapter):
    id = "land_com"
    name = "Land.com"
    domains = ("land.com", "landsofamerica.com")


class LandWatchAdapter(_HostAdapter):
    id = "landwatch"
    name = "LandWatch"
    domains = ("landwatch.com",)


class LandSearchAdapter(_HostAdapter):
    id = "landsearch"
    name = "LandSearch"
    domains = ("landsearch.com",)


class LandAndFarmAdapter(_HostAdapter):
    id = "land_and_farm"
    name = "Land And Farm"
    domains = ("landandfarm.com", "land-and-farm.com")


class ZillowAdapter(_HostAdapter):
    id = "zillow"
    name = "Zillow"
    domains = ("zillow.com",)


class RealtorAdapter(_HostAdapter):
    id = "realtor"
    name = "Realtor.com"
    domains = ("realtor.com",)


class RedfinAdapter(_HostAdapter):
    id = "redfin"
    name = "Redfin"
    domains = ("redfin.com",)


class LoopNetAdapter(_HostAdapter):
    id = "loopnet"
    name = "LoopNet"
    domains = ("loopnet.com",)


KNOWN_ADAPTERS = [
    LandComAdapter(),
    LandWatchAdapter(),
    LandSearchAdapter(),
    LandAndFarmAdapter(),
    ZillowAdapter(),
    RealtorAdapter(),
    RedfinAdapter(),
    LoopNetAdapter(),
]
