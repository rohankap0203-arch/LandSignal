from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from landsignal.models import KnowledgeState, Provenanced, ProviderStatus
from landsignal.providers.base import EnrichmentProvider, ProviderResult
from landsignal.settings import Settings

log = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SsurgoSoilProvider(EnrichmentProvider[Provenanced]):
    """USDA Soil Data Access — public. Uses MapServer/SDA style point query.

    Production path: submit parcel polygon to SDA tabular + spatial services,
    intersect mapunits, area-weight farmland class / NCCPI / AWC.
    Phase 1: centroid-based mapunit properties via SDA query; polygon weighting deferred.
    """

    id = "ssurgo"
    name = "USDA SSURGO / SDA"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4))
    async def _sda_query(self, lat: float, lon: float) -> dict[str, Any]:
        # SDA REST endpoint — QUERY using point intersection via spatial filter
        url = "https://sdmdataaccess.nrcs.usda.gov/tabular/post.rest"
        # Keep query simple: mukey at point via SDA example pattern
        query = f"""
        SELECT TOP 1 mu.musym, mu.muname, mu.mukey,
               (SELECT TOP 1 farmlndcl FROM mucropyld WHERE mukey = mu.mukey) AS farmlndcl
        FROM mapunit mu
        INNER JOIN SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon} {lat})') z ON z.mukey = mu.mukey
        """
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, data={"query": query, "format": "JSON"})
            resp.raise_for_status()
            return resp.json()

    async def enrich(self, parcel: dict) -> ProviderResult[Provenanced]:
        lat, lon = parcel.get("latitude"), parcel.get("longitude")
        if lat is None or lon is None:
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(
                    knowledge_state=KnowledgeState.UNKNOWN,
                    source=self.id,
                    retrieved_at=_now(),
                    confidence=0,
                    normalized={"reason": "missing_coordinates"},
                ),
            )
        try:
            raw = await self._sda_query(float(lat), float(lon))
            table = raw.get("Table") or raw.get("table") or []
            if not table:
                return ProviderResult(
                    True,
                    ProviderStatus.CONFIGURED,
                    Provenanced(
                        knowledge_state=KnowledgeState.UNKNOWN,
                        source=self.id,
                        retrieved_at=_now(),
                        raw=raw,
                        confidence=20,
                        geographic_resolution="point",
                        normalized={"reason": "no_mapunit_at_point"},
                    ),
                )
            # SDA JSON is often header row + data rows
            rows = table
            header = rows[0] if rows and isinstance(rows[0][0], str) else None
            data_row = rows[1] if header and len(rows) > 1 else rows[0]
            mapping = dict(zip(header, data_row)) if header else {}
            farm = mapping.get("farmlndcl") or (data_row[3] if len(data_row) > 3 else None)
            prime_pct = 70.0 if farm and "All areas are prime" in str(farm) else 35.0 if farm else None
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(
                    value={
                        "farmland_classification": farm,
                        "prime_farmland_pct": prime_pct,
                        "mapunit": mapping or data_row,
                    },
                    knowledge_state=KnowledgeState.ESTIMATED
                    if prime_pct is not None
                    else KnowledgeState.KNOWN,
                    source=self.id,
                    retrieved_at=_now(),
                    confidence=55 if prime_pct is not None else 70,
                    geographic_resolution="point_mapunit",
                    raw=raw,
                    normalized={
                        "farmland_classification": farm,
                        "prime_farmland_pct": prime_pct,
                        "note": "Point sample — not polygon area-weighted",
                    },
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("ssurgo_enrich_failed", error=str(exc))
            return ProviderResult(
                False,
                ProviderStatus.DEGRADED,
                Provenanced(
                    knowledge_state=KnowledgeState.TEMPORARILY_UNAVAILABLE,
                    source=self.id,
                    retrieved_at=_now(),
                    confidence=0,
                    raw={"error": str(exc)},
                ),
                error=str(exc),
            )


class FemaFloodProvider(EnrichmentProvider[Provenanced]):
    """FEMA NFHL MapServer identify — screening grade only."""

    id = "fema_nfhl"
    name = "FEMA NFHL"
    LAYER_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def enrich(self, parcel: dict) -> ProviderResult[Provenanced]:
        lat, lon = parcel.get("latitude"), parcel.get("longitude")
        if lat is None or lon is None:
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(knowledge_state=KnowledgeState.UNKNOWN, source=self.id, retrieved_at=_now()),
            )
        try:
            params = {
                "f": "json",
                "geometry": f"{lon},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF",
                "returnGeometry": "false",
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(self.LAYER_URL, params=params)
                resp.raise_for_status()
                raw = resp.json()
            feats = raw.get("features") or []
            if not feats:
                return ProviderResult(
                    True,
                    ProviderStatus.CONFIGURED,
                    Provenanced(
                        value={"flood_zone_pct": 0.0, "zones": []},
                        knowledge_state=KnowledgeState.ESTIMATED,
                        source=self.id,
                        retrieved_at=_now(),
                        confidence=45,
                        geographic_resolution="point",
                        raw=raw,
                        normalized={
                            "flood_zone_pct": 0.0,
                            "note": "No NFHL feature at centroid — not a full polygon overlay",
                        },
                    ),
                )
            attrs = feats[0].get("attributes") or {}
            sfha = str(attrs.get("SFHA_TF", "")).upper() == "T"
            flood_pct = 80.0 if sfha else 15.0
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(
                    value={"flood_zone_pct": flood_pct, "zone": attrs.get("FLD_ZONE"), "attributes": attrs},
                    knowledge_state=KnowledgeState.ESTIMATED,
                    source=self.id,
                    retrieved_at=_now(),
                    confidence=50,
                    geographic_resolution="point",
                    raw=raw,
                    normalized={
                        "flood_zone_pct": flood_pct,
                        "zone": attrs.get("FLD_ZONE"),
                        "note": "Point identify — replace with polygon intersection for production",
                    },
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("fema_enrich_failed", error=str(exc))
            return ProviderResult(
                False,
                ProviderStatus.DEGRADED,
                Provenanced(
                    knowledge_state=KnowledgeState.TEMPORARILY_UNAVAILABLE,
                    source=self.id,
                    retrieved_at=_now(),
                    raw={"error": str(exc)},
                    confidence=0,
                ),
                error=str(exc),
            )


class NwiWetlandsProvider(EnrichmentProvider[Provenanced]):
    """USFWS NWI MapServer — screening grade."""

    id = "nwi"
    name = "USFWS NWI"
    LAYER_URL = "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0/query"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def enrich(self, parcel: dict) -> ProviderResult[Provenanced]:
        lat, lon = parcel.get("latitude"), parcel.get("longitude")
        if lat is None or lon is None:
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(knowledge_state=KnowledgeState.UNKNOWN, source=self.id, retrieved_at=_now()),
            )
        try:
            params = {
                "f": "json",
                "geometry": f"{lon},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "WETLAND_TYPE,ATTRIBUTE",
                "returnGeometry": "false",
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(self.LAYER_URL, params=params)
                resp.raise_for_status()
                raw = resp.json()
            feats = raw.get("features") or []
            wetland_pct = 40.0 if feats else 0.0
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(
                    value={
                        "wetland_pct": wetland_pct,
                        "features": [f.get("attributes") for f in feats[:5]],
                    },
                    knowledge_state=KnowledgeState.ESTIMATED,
                    source=self.id,
                    retrieved_at=_now(),
                    confidence=45 if feats else 40,
                    geographic_resolution="point",
                    raw=raw,
                    normalized={
                        "wetland_pct": wetland_pct,
                        "note": "Point intersect — not percent-of-polygon",
                    },
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("nwi_enrich_failed", error=str(exc))
            return ProviderResult(
                False,
                ProviderStatus.DEGRADED,
                Provenanced(
                    knowledge_state=KnowledgeState.TEMPORARILY_UNAVAILABLE,
                    source=self.id,
                    retrieved_at=_now(),
                    raw={"error": str(exc)},
                    confidence=0,
                ),
                error=str(exc),
            )


class UsgsElevationProvider(EnrichmentProvider[Provenanced]):
    """USGS EPQS elevation point service."""

    id = "usgs_3dep"
    name = "USGS 3DEP Elevation"
    URL = "https://epqs.nationalmap.gov/v1/json"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def enrich(self, parcel: dict) -> ProviderResult[Provenanced]:
        lat, lon = parcel.get("latitude"), parcel.get("longitude")
        if lat is None or lon is None:
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(knowledge_state=KnowledgeState.UNKNOWN, source=self.id, retrieved_at=_now()),
            )
        try:
            params = {"x": lon, "y": lat, "wkid": 4326, "units": "Meters", "includeDate": "false"}
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(self.URL, params=params)
                resp.raise_for_status()
                raw = resp.json()
            value = raw.get("value")
            elev = float(value) if value not in (None, "NaN") else None
            # Slope requires DEM neighborhood; mark UNKNOWN for slope, KNOWN for elev
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(
                    value={"elevation_m": elev, "avg_slope_pct": None, "max_slope_pct": None},
                    knowledge_state=KnowledgeState.KNOWN if elev is not None else KnowledgeState.UNKNOWN,
                    source=self.id,
                    retrieved_at=_now(),
                    confidence=75 if elev is not None else 0,
                    geographic_resolution="point",
                    raw=raw,
                    normalized={
                        "elevation_m": elev,
                        "avg_slope_pct": None,
                        "max_slope_pct": None,
                        "note": "Elevation point only; slope requires DEM sampling",
                    },
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("usgs_enrich_failed", error=str(exc))
            return ProviderResult(
                False,
                ProviderStatus.DEGRADED,
                Provenanced(
                    knowledge_state=KnowledgeState.TEMPORARILY_UNAVAILABLE,
                    source=self.id,
                    retrieved_at=_now(),
                    raw={"error": str(exc)},
                    confidence=0,
                ),
                error=str(exc),
            )


class RegridParcelProvider(EnrichmentProvider[Provenanced]):
    """Licensed Regrid stub. Free path: open GIS polygons on discovered listings."""

    id = "regrid"
    name = "Regrid Parcel Data (licensed) / Open GIS polygons"

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def status(self) -> ProviderStatus:
        # Open GIS polygons from public listing feeds act as the free Regrid stand-in
        return ProviderStatus.CONFIGURED

    async def enrich(self, parcel: dict) -> ProviderResult[Provenanced]:
        if parcel.get("polygon"):
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(
                    value={
                        "has_polygon": True,
                        "source": "open_gis_listing_polygon",
                        "note": "Parcel polygon from public GIS feed (Regrid substitute)",
                    },
                    knowledge_state=KnowledgeState.KNOWN,
                    source="open_gis_parcel",
                    confidence=75,
                    retrieved_at=_now(),
                    normalized={
                        "has_polygon": True,
                        "regrid_licensed": bool(self.api_key),
                        "geometry_source": "public_gis",
                    },
                ),
            )
        if not self.api_key:
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(
                    knowledge_state=KnowledgeState.UNKNOWN,
                    source="open_gis_parcel",
                    normalized={
                        "status": "NO_POLYGON",
                        "regrid_licensed": False,
                        "note": "No public polygon; licensed Regrid key not present in Cursor Cloud",
                    },
                    confidence=0,
                ),
            )
        return ProviderResult(
            False,
            ProviderStatus.DEGRADED,
            Provenanced(
                knowledge_state=KnowledgeState.TEMPORARILY_UNAVAILABLE,
                source=self.id,
                normalized={"status": "KEY_PRESENT_ADAPTER_PENDING"},
            ),
            error="API key present but licensed client adapter not implemented",
        )


def build_enrichment_providers(settings: Settings) -> dict[str, EnrichmentProvider]:
    from landsignal.providers.infrastructure_enrichment import (
        CensusGrowthProvider,
        TransmissionProximityProvider,
    )

    return {
        "ssurgo": SsurgoSoilProvider(),
        "fema_nfhl": FemaFloodProvider(),
        "nwi": NwiWetlandsProvider(),
        "usgs_3dep": UsgsElevationProvider(),
        "hifld_transmission": TransmissionProximityProvider(),
        "census_acs": CensusGrowthProvider(),
        "regrid": RegridParcelProvider(settings.regrid_api_key),
    }
