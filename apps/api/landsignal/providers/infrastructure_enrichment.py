from __future__ import annotations

from datetime import datetime, timezone

import httpx
import structlog

from landsignal.models import KnowledgeState, Provenanced, ProviderStatus
from landsignal.providers.base import EnrichmentProvider, ProviderResult

log = structlog.get_logger()

HIFLD_TX = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Electric_Power_Transmission_Lines/FeatureServer/0/query"
)


class TransmissionProximityProvider(EnrichmentProvider[Provenanced]):
    """HIFLD electric transmission lines — proximity only, NOT interconnection capacity."""

    id = "hifld_transmission"
    name = "HIFLD Transmission Proximity"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def enrich(self, parcel: dict) -> ProviderResult[Provenanced]:
        lat, lon = parcel.get("latitude"), parcel.get("longitude")
        if lat is None or lon is None:
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(knowledge_state=KnowledgeState.UNKNOWN, source=self.id),
            )
        # Query lines within ~25km using envelope around point (degrees approx)
        d = 0.25
        params = {
            "geometry": f"{lon-d},{lat-d},{lon+d},{lat+d}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "OBJECTID,TYPE,VOLTAGE",
            "returnGeometry": "true",
            "outSR": 4326,
            "resultRecordCount": 20,
            "f": "geojson",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(HIFLD_TX, params=params)
                resp.raise_for_status()
                data = resp.json()
            feats = data.get("features") or []
            nearest_m = None
            from landsignal.scoring.geospatial import haversine_meters

            for f in feats:
                geom = f.get("geometry") or {}
                coords = geom.get("coordinates") or []
                # LineString coordinates
                points = coords if geom.get("type") == "LineString" else []
                if geom.get("type") == "MultiLineString":
                    points = [p for line in coords for p in line]
                for pt in points[:: max(1, len(points) // 20 or 1)]:
                    if len(pt) >= 2:
                        d_m = haversine_meters(lat, lon, pt[1], pt[0])
                        nearest_m = d_m if nearest_m is None else min(nearest_m, d_m)
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(
                    value={
                        "nearest_transmission_m": nearest_m,
                        "lines_in_search_window": len(feats),
                        "note": "Proximity ≠ interconnection capacity or queue availability",
                    },
                    knowledge_state=KnowledgeState.ESTIMATED if nearest_m is not None else KnowledgeState.UNKNOWN,
                    source=self.id,
                    retrieved_at=datetime.now(timezone.utc),
                    confidence=55 if nearest_m is not None else 20,
                    geographic_resolution="line_vertex_sample",
                    normalized={
                        "nearest_transmission_m": nearest_m,
                        "interconnection_capacity_known": False,
                    },
                    raw={"feature_count": len(feats)},
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("hifld_enrich_failed", error=str(exc))
            return ProviderResult(
                False,
                ProviderStatus.DEGRADED,
                Provenanced(
                    knowledge_state=KnowledgeState.TEMPORARILY_UNAVAILABLE,
                    source=self.id,
                    raw={"error": str(exc)},
                    confidence=0,
                ),
                error=str(exc),
            )


class CensusGrowthProvider(EnrichmentProvider[Provenanced]):
    """County population trend via Census API (no key for basic ACS calls may rate-limit)."""

    id = "census_acs"
    name = "Census ACS Growth Proxy"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def enrich(self, parcel: dict) -> ProviderResult[Provenanced]:
        state = (parcel.get("state") or "").upper()
        # Without county FIPS we can only produce a coarse state-level placeholder UNKNOWN
        if len(state) != 2:
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(knowledge_state=KnowledgeState.UNKNOWN, source=self.id),
            )
        # Use a simple geocoder-free heuristic: query Census geocoder for coordinates → county
        lat, lon = parcel.get("latitude"), parcel.get("longitude")
        if lat is None or lon is None:
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(knowledge_state=KnowledgeState.UNKNOWN, source=self.id),
            )
        try:
            geo_url = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
            params = {
                "x": lon,
                "y": lat,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            }
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.get(geo_url, params=params)
                resp.raise_for_status()
                geo = resp.json()
            geos = (((geo.get("result") or {}).get("geographies") or {}).get("Counties") or [])
            if not geos:
                return ProviderResult(
                    True,
                    ProviderStatus.CONFIGURED,
                    Provenanced(
                        knowledge_state=KnowledgeState.UNKNOWN,
                        source=self.id,
                        raw=geo,
                        confidence=10,
                    ),
                )
            county = geos[0]
            # Path-of-growth proxy from county centroid distance is weak; store county identity
            # and a neutral-estimated growth score pending ACS time-series (Phase 2).
            score = 50.0
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                Provenanced(
                    value={
                        "county_name": county.get("NAME"),
                        "geoid": county.get("GEOID"),
                        "path_of_growth_score": score,
                        "note": "County identified; multi-year ACS growth velocity is Phase 2",
                    },
                    knowledge_state=KnowledgeState.ESTIMATED,
                    source=self.id,
                    retrieved_at=datetime.now(timezone.utc),
                    confidence=40,
                    geographic_resolution="county",
                    normalized={
                        "county_name": county.get("NAME"),
                        "path_of_growth_score": score,
                        "county_geoid": county.get("GEOID"),
                    },
                    raw=county,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("census_enrich_failed", error=str(exc))
            return ProviderResult(
                False,
                ProviderStatus.DEGRADED,
                Provenanced(
                    knowledge_state=KnowledgeState.TEMPORARILY_UNAVAILABLE,
                    source=self.id,
                    raw={"error": str(exc)},
                    confidence=0,
                ),
                error=str(exc),
            )
