"""ATTOM PropertyIntelligenceProvider implementation."""

from __future__ import annotations

from typing import Any

from landsignal.services.property_providers import (
    IntelligenceProviderState,
    PropertyIntelligenceProvider,
    ProviderResult,
)
from landsignal.services.property_providers.attom.client import AttomClient
from landsignal.services.property_providers.attom import normalize as norm
from landsignal.services.property_providers.cache import AttomResponseCache, CircuitBreaker
from landsignal.settings import Settings, get_settings

# Module singletons — shared circuit + cache across requests
_CACHE: AttomResponseCache | None = None
_BREAKER: CircuitBreaker | None = None
_CLIENT: AttomClient | None = None


def get_attom_client(settings: Settings | None = None) -> AttomClient:
    global _CACHE, _BREAKER, _CLIENT
    settings = settings or get_settings()
    ttl = int(getattr(settings, "attom_cache_ttl_seconds", 82_800) or 82_800)
    if _CACHE is None or _CACHE.ttl_seconds != max(60, min(ttl, 86_400)):
        _CACHE = AttomResponseCache(ttl_seconds=ttl)
    if _BREAKER is None:
        _BREAKER = CircuitBreaker()
    key = getattr(settings, "attom_api_key", None)
    mode = getattr(settings, "attom_data_mode", "api") or "api"
    # Rebuild client when key/mode change
    if (
        _CLIENT is None
        or _CLIENT._api_key != ((key or "").strip() or None)
        or _CLIENT.data_mode != mode.lower()
    ):
        _CLIENT = AttomClient(
            key,
            timeout=float(getattr(settings, "http_timeout_seconds", 20.0) or 20.0),
            cache=_CACHE,
            breaker=_BREAKER,
            data_mode=mode,
        )
    return _CLIENT


def reset_attom_singletons() -> None:
    """Test helper — clears shared cache/breaker/client."""
    global _CACHE, _BREAKER, _CLIENT
    _CACHE = None
    _BREAKER = None
    _CLIENT = None


def _query_params(query: dict[str, Any]) -> dict[str, Any]:
    """Map LandSignal identity fields → ATTOM query params."""
    if query.get("attomId") is not None:
        return {"attomId": query["attomId"]}
    if query.get("id") is not None:
        return {"id": query["id"]}
    if query.get("apn") and query.get("fips"):
        return {"fips": query["fips"], "apn": query["apn"]}
    address = query.get("address") or query.get("address1")
    city_state_zip = query.get("address2") or query.get("city_state_zip")
    if address and city_state_zip:
        return {"address1": address, "address2": city_state_zip}
    if address and query.get("city") and query.get("state"):
        z = query.get("zip") or ""
        return {"address1": address, "address2": f"{query['city']}, {query['state']} {z}".strip()}
    lat, lon = query.get("latitude"), query.get("longitude")
    if lat is not None and lon is not None:
        return {"latitude": lat, "longitude": lon, "radius": query.get("radius") or 0.25}
    return {k: v for k, v in query.items() if v is not None}


class AttomPropertyProvider(PropertyIntelligenceProvider):
    id = "attom"
    name = "ATTOM Property API"

    def __init__(self, client: AttomClient | None = None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.client = client or get_attom_client(self.settings)
        self.ttl = int(getattr(self.settings, "attom_cache_ttl_seconds", 82_800) or 82_800)

    def health_check(self) -> ProviderResult[dict[str, Any]]:
        state = self.client.health_state()
        return ProviderResult(
            ok=state == IntelligenceProviderState.AVAILABLE and self.client.configured,
            state=state,
            data={
                "provider": self.id,
                "name": self.name,
                "stats": self.client.stats(),
                "active_listing_access": False,
                "note": "ATTOM used for property intelligence enrichment only under current entitlement",
            },
            error=None if self.client.configured else "ATTOM_API_KEY not configured",
        )

    async def get_property_detail(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]:
        res = await self.client.get("/property/detail", _query_params(query))
        if not res.ok or not res.data:
            return ProviderResult(False, res.state, error=res.error, meta=res.meta)
        return ProviderResult(
            True,
            res.state,
            data=norm.normalize_property_detail(res.data, ttl_seconds=self.ttl),
            meta=res.meta,
        )

    async def get_ownership(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]:
        res = await self.client.get("/property/detailowner", _query_params(query))
        if not res.ok or not res.data:
            return ProviderResult(False, res.state, error=res.error, meta=res.meta)
        return ProviderResult(
            True,
            res.state,
            data=norm.normalize_owner(res.data, ttl_seconds=self.ttl),
            meta=res.meta,
        )

    async def get_assessment(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]:
        res = await self.client.get("/assessment/detail", _query_params(query))
        if not res.ok or not res.data:
            return ProviderResult(False, res.state, error=res.error, meta=res.meta)
        return ProviderResult(
            True,
            res.state,
            data=norm.normalize_assessment(res.data, ttl_seconds=self.ttl),
            meta=res.meta,
        )

    async def get_sale_history(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]:
        res = await self.client.get("/saleshistory/detail", _query_params(query))
        if not res.ok or not res.data:
            return ProviderResult(False, res.state, error=res.error, meta=res.meta)
        return ProviderResult(
            True,
            res.state,
            data=norm.normalize_sale_history(res.data, ttl_seconds=self.ttl),
            meta=res.meta,
        )

    async def get_valuation(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]:
        res = await self.client.get("/avm/detail", _query_params(query))
        if not res.ok or not res.data:
            return ProviderResult(False, res.state, error=res.error, meta=res.meta)
        return ProviderResult(
            True,
            res.state,
            data=norm.normalize_avm(res.data, ttl_seconds=self.ttl),
            meta=res.meta,
        )

    async def get_building_data(self, query: dict[str, Any]) -> ProviderResult[dict[str, Any]]:
        # Building lives on property/detail under current entitlement
        detail = await self.get_property_detail(query)
        if not detail.ok or not detail.data:
            return ProviderResult(False, detail.state, error=detail.error, meta=detail.meta)
        d = detail.data
        return ProviderResult(
            True,
            detail.state,
            data={
                "hasStructure": d.get("hasStructure"),
                "structureType": d.get("structureType"),
                "yearBuilt": d.get("yearBuilt"),
                "buildingSqFt": d.get("buildingSqFt"),
                "bedrooms": d.get("bedrooms"),
                "bathrooms": d.get("bathrooms"),
                "numberOfStructures": d.get("numberOfStructures"),
                "sources": ["ATTOM"],
            },
            meta=detail.meta,
        )

    async def search_candidates(self, query: dict[str, Any]) -> ProviderResult[list[dict[str, Any]]]:
        """Geo ID search — returns OFF-MARKET property records, not listings."""
        params = _query_params(query)
        if "latitude" not in params or "longitude" not in params:
            return ProviderResult(
                False,
                IntelligenceProviderState.UNAVAILABLE,
                error="ATTOM candidate search requires latitude/longitude",
            )
        params.setdefault("pagesize", min(int(query.get("pagesize") or 20), 100))
        params.setdefault("page", int(query.get("page") or 1))
        res = await self.client.get("/property/id", params)
        if not res.ok or not res.data:
            return ProviderResult(False, res.state, error=res.error, meta=res.meta)
        rows = norm.normalize_id_search(res.data, ttl_seconds=self.ttl)
        return ProviderResult(True, res.state, data=rows, meta={**res.meta, "count": len(rows)})

    async def enrich_parcel(self, parcel: dict[str, Any], *, deep: bool = False) -> dict[str, Any]:
        """Staged enrichment used by analyze / radar. Never raises — soft-fails."""
        out: dict[str, Any] = {
            "provider": self.id,
            "ok": False,
            "state": self.client.health_state().value,
            "fields": {},
        }
        if not self.client.configured:
            out["state"] = IntelligenceProviderState.NOT_CONFIGURED.value
            return out

        query: dict[str, Any] = {}
        if parcel.get("attom_id") or parcel.get("attomId"):
            query["attomId"] = parcel.get("attom_id") or parcel.get("attomId")
        elif parcel.get("apn") and parcel.get("fips"):
            query["apn"] = parcel["apn"]
            query["fips"] = parcel["fips"]
        elif parcel.get("address") and parcel.get("state"):
            query["address"] = parcel["address"]
            city = parcel.get("city") or parcel.get("county") or ""
            query["address2"] = f"{city}, {parcel['state']} {parcel.get('zip') or ''}".strip()
        elif parcel.get("latitude") is not None and parcel.get("longitude") is not None:
            query["latitude"] = parcel["latitude"]
            query["longitude"] = parcel["longitude"]
            query["radius"] = 0.15
        else:
            out["error"] = "insufficient identity for ATTOM lookup"
            return out

        detail = await self.get_property_detail(query)
        out["state"] = detail.state.value
        if not detail.ok or not detail.data:
            out["error"] = detail.error
            return out

        fields = dict(detail.data)
        out["ok"] = True

        # Attach attomId for subsequent cheap calls
        if fields.get("attomId"):
            query = {"attomId": fields["attomId"]}

        if deep:
            for name, coro in (
                ("assessment", self.get_assessment(query)),
                ("valuation", self.get_valuation(query)),
                ("sale_history", self.get_sale_history(query)),
                ("ownership", self.get_ownership(query)),
            ):
                try:
                    res = await coro
                    if res.ok and res.data:
                        fields[name] = res.data
                    else:
                        fields[f"{name}_unavailable"] = res.error or res.state.value
                except Exception:  # noqa: BLE001
                    fields[f"{name}_unavailable"] = "error"

        out["fields"] = fields
        return out
