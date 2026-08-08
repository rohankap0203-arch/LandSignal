from __future__ import annotations

from typing import Any

import httpx
import structlog
from shapely.geometry import shape
from shapely.ops import unary_union

from landsignal.models import ProviderStatus
from landsignal.providers.base import ListingProvider, ProviderResult
from landsignal.scoring.geospatial import acres_from_square_meters

log = structlog.get_logger()

BLM_QUERY = (
    "https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_LPAD/MapServer/0/query"
)


class BlmLpadProvider(ListingProvider):
    """BLM Lands Potentially Available for Disposal — public ArcGIS REST.

    These are real federal tracts identified for potential sale/exchange under FLPMA/FLTFA.
    Not an MLS feed; acquisition follows federal disposal process.
    """

    id = "blm_lpad"
    name = "BLM LPAD (Federal Disposal Lands)"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def search_listings(self, query: dict[str, Any]) -> ProviderResult[list[dict]]:
        limit = int(query.get("limit") or 40)
        min_acres = float(query.get("min_acres") or 20)
        max_acres = float(query.get("max_acres") or 2500)
        states = query.get("states")  # optional list of ADMIN_ST codes e.g. ["NM","AZ"]
        where = "IDENT_DSPSL_TYPE IN ('Sale','SaleExchange')"
        if states:
            quoted = ",".join(f"'{s}'" for s in states)
            where += f" AND ADMIN_ST IN ({quoted})"
        # Pull a wider page then filter to investable tract sizes (many LPAD rows are huge plan units)
        params = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "resultRecordCount": 200,
            "resultOffset": int(query.get("offset") or 0),
            "orderByFields": "OBJECTID DESC",
            "f": "geojson",
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(BLM_QUERY, params=params)
                resp.raise_for_status()
                data = resp.json()
            features = data.get("features") or []
            out = [self.normalize_listing(f) for f in features]
            out = [
                x
                for x in out
                if x.get("acreage")
                and min_acres <= float(x["acreage"]) <= max_acres
                and x.get("latitude") is not None
            ]
            # Diversify by state
            by_state: dict[str, list[dict]] = {}
            for row in out:
                by_state.setdefault(row.get("state") or "??", []).append(row)
            diversified: list[dict] = []
            while len(diversified) < limit and any(by_state.values()):
                for st in list(by_state.keys()):
                    if by_state[st]:
                        diversified.append(by_state[st].pop(0))
                    if len(diversified) >= limit:
                        break
                    if not by_state[st]:
                        by_state.pop(st, None)
            return ProviderResult(True, ProviderStatus.CONFIGURED, diversified)
        except Exception as exc:  # noqa: BLE001
            log.warning("blm_lpad_search_failed", error=str(exc))
            return ProviderResult(False, ProviderStatus.DEGRADED, error=str(exc))

    async def get_listing(self, external_id: str) -> ProviderResult[dict]:
        params = {
            "where": f"LUPA_ID='{external_id}' OR OBJECTID={external_id}"
            if external_id.isdigit()
            else f"LUPA_ID='{external_id}'",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "f": "geojson",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(BLM_QUERY, params=params)
                resp.raise_for_status()
                data = resp.json()
            feats = data.get("features") or []
            if not feats:
                return ProviderResult(False, ProviderStatus.CONFIGURED, error="Not found")
            return ProviderResult(True, ProviderStatus.CONFIGURED, self.normalize_listing(feats[0]))
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(False, ProviderStatus.DEGRADED, error=str(exc))

    def normalize_listing(self, raw: dict) -> dict:
        props = raw.get("properties") or raw
        geom = raw.get("geometry")
        acreage = None
        lat = lon = None
        polygon = None
        if geom:
            try:
                g = shape(geom)
                if not g.is_empty:
                    g = unary_union(g)
                    acreage = acres_from_square_meters(g.area) if g.area else None
                    # shapely area is in deg² for geographic CRS — inaccurate.
                    # Recompute with projected equirectangular using centroid.
                    c = g.centroid
                    lat, lon = c.y, c.x
                    # Better acreage via our ring helper when polygon available
                    if geom.get("type") == "Polygon":
                        from landsignal.scoring.geospatial import ring_area_square_meters

                        acreage = acres_from_square_meters(
                            ring_area_square_meters(geom["coordinates"][0])
                        )
                        polygon = geom["coordinates"]
                    elif geom.get("type") == "MultiPolygon":
                        from landsignal.scoring.geospatial import ring_area_square_meters

                        total = 0.0
                        rings = []
                        for poly in geom["coordinates"]:
                            total += ring_area_square_meters(poly[0])
                            rings.append(poly[0])
                        acreage = acres_from_square_meters(total)
                        polygon = [rings[0]] if rings else None
            except Exception as exc:  # noqa: BLE001
                log.warning("blm_geom_parse_failed", error=str(exc))

        object_id = props.get("OBJECTID")
        lupa_id = props.get("LUPA_ID")
        # OBJECTID is unique per geometry; LUPA_ID can repeat across tracts in a plan
        external_id = str(object_id or lupa_id)
        state = props.get("ADMIN_ST")
        name = props.get("LUPA_NM") or props.get("AUTH_NM") or f"BLM LPAD {external_id}"
        disposal = props.get("IDENT_DSPSL_TYPE")
        acres_label = f"{acreage:.1f} ac" if acreage else "acreage n/a"
        return {
            "provider_id": self.id,
            "external_id": external_id,
            "title": f"{name} · {acres_label} · {state} ({disposal})",
            "description": (
                f"BLM land potentially available for disposal via {disposal}. "
                f"LUPA_ID={lupa_id}. Authority: {props.get('AUTH_NM') or '—'}. "
                f"Management direction: {props.get('MNGMNT_DRCTN') or '—'}. "
                f"Conditions: {props.get('DSPSL_CNDTNS') or 'None listed'}. "
                "Federal disposal process applies — not a private MLS listing. "
                "Asking price is typically established through the disposal process, not a retail ask."
            ),
            "asking_price_usd": None,  # federal disposal; no retail ask
            "acreage": acreage,
            "price_per_acre_usd": None,
            "state": state,
            "county": props.get("ADM_UNIT_NR") or props.get("ADM_UNIT_CD"),
            "apn": f"BLM-{external_id}",
            "address": f"BLM {state} — {props.get('ADM_UNIT_CD') or ''}".strip(),
            "latitude": lat,
            "longitude": lon,
            "polygon": polygon,
            "source_url": props.get("DOC_URL") or props.get("PLAN_URL") or props.get("FO_URL"),
            "status": "ACTIVE",
            "disposal_type": disposal,
            "raw": props,
            "is_demo": False,
        }
