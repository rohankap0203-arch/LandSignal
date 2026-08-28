from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog
from shapely.geometry import shape
from shapely.ops import unary_union

from landsignal.models import ProviderStatus
from landsignal.providers.base import ListingProvider, ProviderResult
from landsignal.scoring.geospatial import (
    acres_from_square_meters,
    interior_pin_lat_lon,
    ring_area_square_meters,
)

log = structlog.get_logger()

BLM_QUERY = (
    "https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_LPAD/MapServer/0/query"
)

# States known to publish LPAD Sale/SaleExchange tracts (queried individually for nationwide mix)
BLM_STATES = [
    "AK", "AZ", "CA", "CO", "ID", "MT", "NM", "NV", "OR", "UT", "WY",
]


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
        limit = int(query.get("limit") or 100)
        min_acres = float(query.get("min_acres") or 5)
        max_acres = float(query.get("max_acres") or 5000)
        states = query.get("states") or BLM_STATES
        # Western states need deep BLM pulls to help hit the 10k/state floor.
        per_state = max(50, min(2500, (limit // max(1, len(states))) + 100))

        async with httpx.AsyncClient(timeout=45.0) as client:
            results = await asyncio.gather(
                *[
                    self._fetch_state(client, st, per_state, min_acres, max_acres)
                    for st in states
                ],
                return_exceptions=True,
            )

        out: list[dict] = []
        errors: list[str] = []
        for st, res in zip(states, results):
            if isinstance(res, Exception):
                errors.append(f"{st}: {res}")
                log.warning("blm_state_failed", state=st, error=str(res))
                continue
            out.extend(res)

        by_state: dict[str, list[dict]] = {}
        for row in out:
            by_state.setdefault(row.get("state") or "??", []).append(row)
        diversified: list[dict] = []
        while len(diversified) < limit and any(by_state.values()):
            for st in list(by_state.keys()):
                if by_state.get(st):
                    diversified.append(by_state[st].pop(0))
                if len(diversified) >= limit:
                    break
                if st in by_state and not by_state[st]:
                    by_state.pop(st, None)

        return ProviderResult(
            True,
            ProviderStatus.CONFIGURED if diversified else ProviderStatus.DEGRADED,
            diversified,
            error="; ".join(errors) if errors else None,
        )

    async def _fetch_state(
        self,
        client: httpx.AsyncClient,
        state: str,
        per_state: int,
        min_acres: float,
        max_acres: float,
    ) -> list[dict]:
        where = (
            "IDENT_DSPSL_TYPE IN ('Sale','SaleExchange') "
            f"AND ADMIN_ST='{state}'"
        )
        params = {
            "where": where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "resultRecordCount": min(1000, max(per_state * 2, 50)),
            "orderByFields": "OBJECTID DESC",
            "f": "geojson",
        }
        # Page within a state when we need a deep haul
        collected: list[dict] = []
        offset = 0
        while len(collected) < per_state:
            params["resultOffset"] = offset
            resp = await client.get(BLM_QUERY, params=params)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features") or []
            if not features:
                break
            for f in features:
                row = self.normalize_listing(f)
                if (
                    row.get("acreage")
                    and min_acres <= float(row["acreage"]) <= max_acres
                    and row.get("latitude") is not None
                ):
                    collected.append(row)
                    if len(collected) >= per_state:
                        break
            if len(features) < params["resultRecordCount"]:
                break
            offset += len(features)
        return collected[:per_state]

    async def get_listing(self, external_id: str) -> ProviderResult[dict]:
        params = {
            "where": f"LUPA_ID='{external_id}' OR OBJECTID={external_id}"
            if str(external_id).isdigit()
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
                    lat, lon = interior_pin_lat_lon(g)
                    if geom.get("type") == "Polygon":
                        acreage = acres_from_square_meters(
                            ring_area_square_meters(geom["coordinates"][0])
                        )
                        polygon = geom["coordinates"]
                    elif geom.get("type") == "MultiPolygon":
                        total = 0.0
                        best = None
                        best_area = -1.0
                        for poly in geom["coordinates"]:
                            a = ring_area_square_meters(poly[0])
                            total += a
                            if a > best_area:
                                best_area = a
                                best = poly
                        acreage = acres_from_square_meters(total)
                        polygon = best
            except Exception as exc:  # noqa: BLE001
                log.warning("blm_geom_parse_failed", error=str(exc))

        # Prefer published GIS acres when present
        if props.get("GIS_ACRES") is not None:
            try:
                acreage = float(props["GIS_ACRES"])
            except Exception:
                pass

        object_id = props.get("OBJECTID")
        lupa_id = props.get("LUPA_ID")
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
            "asking_price_usd": None,
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
