"""On-demand exact parcel boundary fetch from the same public ArcGIS layers we ingest.

View Map always rehydrates the true cadastral exterior (not a simplified sketch,
never a fake acreage square). Nationwide inventory may omit full rings for RAM;
opening the map pulls the exact GIS ring for that one parcel and caches it.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from landsignal.services.parcel_outline import exact_polygon, outline_matches_acreage

log = structlog.get_logger(__name__)

_ARCGIS_HEADERS = {
    "User-Agent": "LandSignal/1.0 (parcel-boundary; +https://landsignal.app)",
    "Accept": "application/json, application/geo+json",
}

# external_id prefix → preferred ArcGIS source_id (when names diverge).
_PREFIX_SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "tx_nri": ("tx_hillcountry_vacant",),
    "fl_parcels": ("fl_parcels_vacant", "fl_parcels_agriculture"),
    "nc_parcels": ("nc_parcels_vacant",),
    "nyorpts": ("ny_orpts_centroids", "ny_orpts", "nyorpts"),
    "nyag": ("ny_ag", "nyag"),
    "massgis": ("massgis_vacant", "ma_massgis", "massgis"),
    "njmod4": ("nj_mod4", "njmod4"),
    "argeostor": ("ar_geostor", "argeostor"),
}


def _ext_prefix(external_id: str | None) -> str | None:
    if not external_id or ":" not in external_id:
        return None
    return external_id.split(":", 1)[0].strip().lower() or None


def _sources_for_parcel(
    *,
    state: str | None,
    county: str | None,
    external_id: str | None,
    source_id: str | None,
) -> list[Any]:
    from landsignal.providers.public_markets import SOURCES

    st = (state or "").upper().strip()
    if not st:
        return []
    candidates = [s for s in SOURCES if (s.state or "").upper() == st]
    if not candidates:
        return []

    ranked: list[tuple[int, Any]] = []
    pref = (source_id or "").strip().lower()
    prefix = _ext_prefix(external_id)
    aliases = _PREFIX_SOURCE_ALIASES.get(prefix or "", ())
    county_l = (county or "").strip().lower()

    for s in candidates:
        sid = (s.source_id or "").lower()
        county_s = (s.county or "").strip().lower()
        statewide = county_s in {"statewide", "state", st.lower(), ""}
        score = 0

        if pref and sid == pref:
            score += 200
        if any(sid == a or sid.startswith(a) for a in aliases):
            score += 150
        if prefix and (sid.startswith(prefix) or prefix in sid):
            score += 80
        if county_l and county_l in county_s:
            score += 40
        if statewide:
            score += 15
        if "vacant" in sid or "parcel" in sid:
            score += 5
        if "surplus" in sid or "tax" in sid or "sale" in sid:
            score -= 5

        if county_l and not statewide and county_l not in county_s and score < 80:
            continue

        ranked.append((score, s))

    ranked.sort(key=lambda t: (-t[0], t[1].source_id))
    out = [s for score, s in ranked if score > 0][:5]
    if out:
        return out
    statewide = [
        s
        for s in candidates
        if (s.county or "").lower() in {"statewide", "state", st.lower(), ""}
        or "vacant" in (s.source_id or "").lower()
    ]
    return (statewide or candidates)[:3]


def _polygon_from_geojson_feature(
    feat: dict,
    *,
    expected_acres: float | None = None,
) -> list[list[list[float]]] | None:
    from landsignal.providers.public_markets import _acres_from_geom

    geom = feat.get("geometry")
    if not geom:
        return None
    outline: list[list[list[float]]] | None = None
    if isinstance(geom, dict) and geom.get("type") in {"Polygon", "MultiPolygon"}:
        _, _, _, polygon = _acres_from_geom(geom)
        outline = exact_polygon(polygon)
    else:
        rings = geom.get("rings") if isinstance(geom, dict) else None
        if isinstance(rings, list) and rings:
            outline = exact_polygon([rings[0]])
    if not outline:
        return None
    if expected_acres is not None and not outline_matches_acreage(outline, expected_acres):
        return None
    return outline


async def _query_point(
    client: httpx.AsyncClient,
    url: str,
    *,
    lat: float,
    lon: float,
    source_id: str,
    expected_acres: float | None = None,
) -> list[list[list[float]]] | None:
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
    }
    try:
        resp = await client.get(url, params=params)
        if resp.status_code >= 400:
            return None
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.info("parcel_boundary_query_failed", source=source_id, error=str(exc)[:160])
        return None
    if not isinstance(data, dict) or data.get("error"):
        return None
    feats = data.get("features") or []
    if not feats:
        pad = 0.0002
        envelope = f"{lon - pad},{lat - pad},{lon + pad},{lat + pad}"
        params2 = {
            "geometry": envelope,
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "resultRecordCount": 5,
            "f": "geojson",
        }
        try:
            resp2 = await client.get(url, params=params2)
            if resp2.status_code >= 400:
                return None
            data2 = resp2.json()
        except Exception:
            return None
        if not isinstance(data2, dict) or data2.get("error"):
            return None
        feats = data2.get("features") or []
    for feat in feats:
        outline = _polygon_from_geojson_feature(
            feat if isinstance(feat, dict) else {},
            expected_acres=expected_acres,
        )
        if outline:
            return outline
    return None


async def _query_by_key(
    client: httpx.AsyncClient,
    url: str,
    *,
    key: str,
    source_id: str,
    expected_acres: float | None = None,
) -> list[list[list[float]]] | None:
    key_s = str(key).strip()
    if not key_s or len(key_s) < 2:
        return None
    safe = key_s.replace("'", "''")
    wheres = [
        f"prop_id='{safe}'",
        f"PROP_ID='{safe}'",
        f"PARCELID='{safe}'",
        f"APN='{safe}'",
        f"PIN='{safe}'",
        f"objectid={safe}" if safe.isdigit() else None,
    ]
    for where in wheres:
        if not where:
            continue
        params = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "resultRecordCount": 1,
            "f": "geojson",
        }
        try:
            resp = await client.get(url, params=params)
            if resp.status_code >= 400:
                continue
            data = resp.json()
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("error"):
            continue
        for feat in data.get("features") or []:
            outline = _polygon_from_geojson_feature(
                feat if isinstance(feat, dict) else {},
                expected_acres=expected_acres,
            )
            if outline:
                log.info("parcel_boundary_key_hit", source=source_id, key=key_s[:40])
                return outline
    return None


async def fetch_real_parcel_outline(
    *,
    latitude: float | None,
    longitude: float | None,
    state: str | None,
    county: str | None = None,
    apn: str | None = None,
    external_id: str | None = None,
    source_id: str | None = None,
    acreage: float | None = None,
) -> list[list[list[float]]] | None:
    """Exact GIS exterior ring for View Map (cleaned, not simplified)."""
    lat = float(latitude) if latitude is not None else None
    lon = float(longitude) if longitude is not None else None
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    sources = _sources_for_parcel(
        state=state,
        county=county,
        external_id=external_id,
        source_id=source_id,
    )
    if not sources:
        return None

    timeout = httpx.Timeout(connect=5.0, read=14.0, write=5.0, pool=5.0)
    async with httpx.AsyncClient(
        timeout=timeout, headers=_ARCGIS_HEADERS, verify=False, follow_redirects=True
    ) as client:
        for src in sources:
            hit = await _query_point(
                client,
                src.url,
                lat=lat,
                lon=lon,
                source_id=src.source_id,
                expected_acres=acreage,
            )
            if hit:
                log.info(
                    "parcel_boundary_live",
                    source=src.source_id,
                    via="point",
                    verts=len(hit[0]),
                )
                return hit

            keys: list[str] = []
            if apn:
                keys.append(str(apn).strip())
            if external_id and ":" in external_id:
                tail = external_id.split(":", 1)[1].strip()
                if ":" in tail:
                    tail = tail.rsplit(":", 1)[-1].strip()
                if tail and tail not in keys:
                    keys.append(tail)
            for key in keys[:2]:
                hit = await _query_by_key(
                    client,
                    src.url,
                    key=key,
                    source_id=src.source_id,
                    expected_acres=acreage,
                )
                if hit:
                    log.info(
                        "parcel_boundary_live",
                        source=src.source_id,
                        via="key",
                        verts=len(hit[0]),
                    )
                    return hit

    log.info(
        "parcel_boundary_miss",
        state=state,
        county=county,
        external_id=(external_id or "")[:48],
    )
    return None
