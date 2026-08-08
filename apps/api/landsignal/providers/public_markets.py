"""Free public market adapters approximating licensed listing/parcel vendors.

Cursor Cloud does NOT include MLS / Land.com / Crexi / Regrid credentials.
These adapters use authorized public GIS / government open data instead:

- Tax-sale / auction parcels (≈ distressed / opportunistic inventory)
- Municipal/county surplus property (≈ CRE / land bank inventory)
- Listing polygons themselves (≈ Regrid parcel geometry for discovered assets)

No ToS-circumventing scrapers.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import structlog

# NOTE: asyncio used via gather helper below
from shapely.geometry import shape
from shapely.ops import unary_union

from landsignal.models import ProviderStatus
from landsignal.providers.base import ListingProvider, ProviderResult
from landsignal.scoring.geospatial import acres_from_square_meters, ring_area_square_meters

log = structlog.get_logger()


def _acres_from_geom(geom: dict | None) -> tuple[float | None, float | None, float | None, list | None]:
    if not geom:
        return None, None, None, None
    try:
        g = shape(geom)
        if g.is_empty:
            return None, None, None, None
        g = unary_union(g)
        lat, lon = g.centroid.y, g.centroid.x
        acreage = None
        polygon = None
        if geom.get("type") == "Polygon":
            acreage = acres_from_square_meters(ring_area_square_meters(geom["coordinates"][0]))
            polygon = geom["coordinates"]
        elif geom.get("type") == "MultiPolygon":
            total = 0.0
            first = None
            for poly in geom["coordinates"]:
                total += ring_area_square_meters(poly[0])
                first = first or poly
            acreage = acres_from_square_meters(total)
            polygon = first
        return acreage, lat, lon, polygon
    except Exception as exc:  # noqa: BLE001
        log.warning("geom_parse_failed", error=str(exc))
        return None, None, None, None


class ArcgisMarketSource:
    def __init__(
        self,
        source_id: str,
        name: str,
        url: str,
        state: str,
        county: str,
        normalize: Callable[[dict], dict | None],
        where: str = "1=1",
    ):
        self.source_id = source_id
        self.name = name
        self.url = url
        self.state = state
        self.county = county
        self.normalize = normalize
        self.where = where


def _norm_shasta(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    if (props.get("Status") or "").lower() != "active":
        return None
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    # Prefer assessor land value / min bid; acreage from geometry
    ask = props.get("MinimumBid")
    land_val = props.get("Land")
    use = props.get("UseCodeDescription") or "Unknown"
    apn = props.get("APN") or props.get("APNLabel")
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"shasta:{apn}",
        "title": f"Shasta CA tax auction · {use} · APN {props.get('APNLabel') or apn}",
        "description": (
            f"County tax-sale inventory (Shasta County, CA). Status={props.get('Status')}. "
            f"Use={use}. Minimum bid=${ask}. Assessor land=${land_val}. "
            f"Assessor map: {props.get('APPageLink') or 'n/a'}. "
            "Public GIS feed — not MLS/Land.com."
        ),
        "asking_price_usd": float(ask) if ask is not None else None,
        "acreage": acreage,
        "state": "CA",
        "county": "Shasta",
        "apn": str(apn) if apn else None,
        "address": f"Shasta County, CA · {props.get('APNLabel') or ''}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": props.get("APPageLink"),
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_sauk(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage = props.get("TOTALACREAGE")
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is None:
        acreage = geom_acres
    if acreage is not None and float(acreage) < 0.1:
        return None
    pid = props.get("PARCELID") or props.get("OBJECTID")
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"sauk:{pid}",
        "title": f"Sauk WI parcel for sale · {float(acreage):.2f} ac · {pid}",
        "description": (
            f"Sauk County, WI tax parcels offered for sale (county Land Records GIS). "
            f"Notes: {props.get('LRSNOTES') or '—'}. Public feed — not MLS/Land.com."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "WI",
        "county": "Sauk",
        "apn": str(pid),
        "address": props.get("SITEADDRESS") or props.get("PSTLADDRESS") or "Sauk County, WI",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": props.get("URL"),
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_indy(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    sqft = props.get("ESTSQFT")
    if acreage is None and sqft:
        acreage = float(sqft) / 43560.0
    if acreage is not None and acreage < 0.05:
        return None
    ask = props.get("TAXSALECOST")
    if ask is None:
        # sum common fee fields when present
        parts = [props.get(k) for k in ("TAXSALECOST", "ADMINFEE", "SEARCHFEE", "DELTAXPEN", "DELSATAX")]
        nums = [float(x) for x in parts if x is not None]
        ask = sum(nums) if nums else None
    pid = props.get("PARCELNUMBER") or props.get("PARCEL_I") or props.get("OBJECTID")
    street = props.get("FULL_STNAME") or props.get("STREET_NAME") or ""
    num = props.get("STNUMBER") or ""
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"indy:{pid}",
        "title": f"Indianapolis tax sale · {num} {street}".strip() or f"Indianapolis tax sale · {pid}",
        "description": (
            "Marion County / Indianapolis tax-sale parcel (public GIS). "
            "Distressed inventory approximating auction channels — not Crexi/MLS."
        ),
        "asking_price_usd": float(ask) if ask is not None else None,
        "acreage": acreage,
        "state": "IN",
        "county": props.get("COUNTY") or "Marion",
        "apn": str(pid),
        "address": f"{num} {street}, {props.get('CITY') or 'Indianapolis'}, IN {props.get('ZIPCODE') or ''}".strip(),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": None,
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_brunswick(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage = props.get("CALCAC")
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if not acreage:
        acreage = geom_acres
    pid = props.get("PARCEL_ID") or props.get("PIN") or props.get("Parcel_Number")
    return {
        "provider_id": "public_surplus",
        "external_id": f"brunswick:{pid}",
        "title": f"Brunswick NC surplus · {float(acreage or 0):.2f} ac · {pid}",
        "description": (
            "Brunswick County, NC surplus county property (public GIS). "
            "Government surplus approximating off-market / CRE disposal inventory."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage else None,
        "state": "NC",
        "county": "Brunswick",
        "apn": str(pid),
        "address": f"Brunswick County, NC · {pid}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": None,
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_wyco(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage = props.get("ACRE")
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is None:
        acreage = geom_acres
    if acreage is not None and float(acreage) < 0.2:
        return None
    pid = props.get("PARCEL") or props.get("STATE_ID") or props.get("OBJECTID")
    street = " ".join(
        str(x) for x in [props.get("NUMB"), props.get("ST_NAME"), props.get("MISC")] if x
    ).strip()
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"wyco:{pid}",
        "title": f"Wyandotte KS tax-sale eligible · {street or pid}",
        "description": (
            f"Unified Government of Wyandotte County / KCK tax-sale eligible parcel. "
            f"Land use={props.get('LAND_USE') or 'n/a'}. Vacant mark={props.get('VACANT') or 'n/a'}. "
            "Public GIS — not MLS/Crexi."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "KS",
        "county": "Wyandotte",
        "apn": str(pid),
        "address": f"{street}, {props.get('CITY') or 'Kansas City'}, KS {props.get('ZIP') or ''}".strip(),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.wycokck.org/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_mahoning(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = geom_acres
    if acreage is not None and acreage < 0.2:
        return None
    pid = props.get("PARCEL_ID") or props.get("PARCEL_ID_1") or props.get("OBJECTID")
    market = props.get("TOTALMARKET") or props.get("MARKETLAND")
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"mahoning:{pid}",
        "title": f"Mahoning OH land-bank / delinquent · {pid}",
        "description": (
            f"Mahoning County, OH tax-delinquent / land-bank inventory (public GIS). "
            f"Land use={props.get('LANDUSE') or 'n/a'}. "
            f"Market mark=${market}. Distressed public inventory — not MLS."
        ),
        "asking_price_usd": float(market) if market is not None else None,
        "acreage": acreage,
        "state": "OH",
        "county": "Mahoning",
        "apn": str(pid),
        "address": f"Mahoning County, OH · {pid}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.mahoningcountyoh.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_cochise(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is not None and acreage < 0.5:
        return None
    pid = props.get("apn") or props.get("accountno") or props.get("OBJECTID")
    situs = props.get("situs_address") or ""
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"cochise:{pid}",
        "title": f"Cochise AZ tax-lien parcel · {situs or pid}",
        "description": (
            f"Cochise County, AZ tax-lien parcel layer (public ArcGIS). "
            f"Tax year={props.get('tax_year')}. Owner mark={props.get('owner_name1') or 'n/a'}. "
            "Public distress inventory — not Land.com/MLS."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "AZ",
        "county": "Cochise",
        "apn": str(pid),
        "address": f"{situs}, Cochise County, AZ".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.cochise.az.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_ftl(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    sqft = props.get("CNTYGISSQFT")
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is None and sqft:
        acreage = float(sqft) / 43560.0
    if acreage is not None and acreage < 0.2:
        return None
    pid = props.get("PARCELID") or props.get("FOLIO")
    return {
        "provider_id": "public_surplus",
        "external_id": f"ftl:{pid}",
        "title": f"Fort Lauderdale surplus · {props.get('SITEADDRESS') or pid}",
        "description": (
            f"City of Fort Lauderdale surplus property. Use={props.get('USEDSCRP')}. "
            f"Owner={props.get('OWNERS')}. Public GIS — not LoopNet/Crexi."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "FL",
        "county": "Broward",
        "apn": str(pid),
        "address": f"{props.get('SITEADDRESS') or ''}, {props.get('PARCELCITY') or 'Fort Lauderdale'}, FL".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": None,
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


SOURCES: list[ArcgisMarketSource] = [
    ArcgisMarketSource(
        "shasta_ca_tax",
        "Shasta County CA Tax Auction",
        "https://gis.shastacounty.gov/arcgis/rest/services/Internet/Property_Tax_Auction_Layers/MapServer/0/query",
        "CA",
        "Shasta",
        _norm_shasta,
        where="Status='Active'",
    ),
    ArcgisMarketSource(
        "sauk_wi_sale",
        "Sauk County WI Parcels For Sale",
        "https://gis.co.sauk.wi.us/arcgis/rest/services/Sauk/TaxParcelsForSale/FeatureServer/0/query",
        "WI",
        "Sauk",
        _norm_sauk,
    ),
    ArcgisMarketSource(
        "indy_tax_sale",
        "Indianapolis Tax Sale Parcels",
        "https://gistest.indy.gov/server/rest/services/TaxSaleViewer/TaxSaleParcels_BuildingBlocks/MapServer/0/query",
        "IN",
        "Marion",
        _norm_indy,
    ),
    ArcgisMarketSource(
        "brunswick_nc_surplus",
        "Brunswick County NC Surplus",
        "https://bcgis.brunswickcountync.gov/arcgis/rest/services/Mapping/SurplusProperty/MapServer/1/query",
        "NC",
        "Brunswick",
        _norm_brunswick,
    ),
    ArcgisMarketSource(
        "ftl_surplus",
        "Fort Lauderdale Surplus Property",
        "https://gis.fortlauderdale.gov/arcgis/rest/services/PropertyReporter/Interactive/MapServer/37/query",
        "FL",
        "Broward",
        _norm_ftl,
    ),
    ArcgisMarketSource(
        "wyco_ks_tax",
        "Wyandotte County KS Tax Sale Eligible",
        "https://gisweb.wycokck.org/arcgis/rest/services/GISPUB/UGMAPS_4_V02/MapServer/30/query",
        "KS",
        "Wyandotte",
        _norm_wyco,
    ),
    ArcgisMarketSource(
        "mahoning_oh_tax",
        "Mahoning County OH Tax Delinquent / Land Bank",
        "https://gisapp.mahoningcountyoh.gov/arcgis/rest/services/LANDBANK_DELINQUENT_PROPERTIES/MapServer/0/query",
        "OH",
        "Mahoning",
        _norm_mahoning,
    ),
    ArcgisMarketSource(
        "cochise_az_tax",
        "Cochise County AZ Tax Lien Parcels",
        "https://services6.arcgis.com/Yxem0VOcqSy8T6TE/arcgis/rest/services/Cad_Parcel_TaxLien2025/FeatureServer/0/query",
        "AZ",
        "Cochise",
        _norm_cochise,
    ),
]


async def _fetch_arcgis_pages(
    client: httpx.AsyncClient,
    src: ArcgisMarketSource,
    *,
    target: int,
    page_size: int = 200,
    start_offset: int = 0,
) -> list[dict]:
    """Page through an ArcGIS layer until we have `target` normalized rows."""
    out: list[dict] = []
    offset = max(0, start_offset)
    # Cap pages so a single county can't hang the whole discover
    max_pages = max(1, (target // page_size) + 3)
    for _ in range(max_pages):
        if len(out) >= target:
            break
        params = {
            "where": src.where,
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": 4326,
            "resultRecordCount": page_size,
            "resultOffset": offset,
            "f": "geojson",
        }
        resp = await client.get(src.url, params=params)
        resp.raise_for_status()
        data = resp.json()
        feats = data.get("features") or []
        if not feats:
            break
        for feat in feats:
            row = src.normalize(feat)
            if row:
                out.append(row)
                if len(out) >= target:
                    break
        if len(feats) < page_size:
            break
        offset += len(feats)
    return out


class PublicTaxSaleProvider(ListingProvider):
    """Free county tax-sale / for-sale GIS feeds ≈ opportunistic MLS/auction inventory."""

    id = "public_tax_sale"
    name = "Public Tax-Sale / County For-Sale GIS"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def search_listings(self, query: dict[str, Any]) -> ProviderResult[list[dict]]:
        limit = int(query.get("limit") or 2000)
        out: list[dict] = []
        errors: list[str] = []
        tax_sources = [
            s
            for s in SOURCES
            if "tax" in s.source_id
            or "sale" in s.source_id
            or s.source_id.startswith(("sauk", "indy", "shasta", "wyco", "mahoning", "cochise"))
        ]
        # Split the budget across counties so one mega-layer doesn't dominate
        per_source = max(300, limit // max(1, len(tax_sources)))
        start_offset = int(query.get("offset") or 0)
        async with httpx.AsyncClient(timeout=90.0) as client:
            results = await asyncio_gather_sources(
                client, tax_sources, per_source, errors, start_offset=start_offset
            )
            for batch in results:
                out.extend(batch)
        by_state: dict[str, list[dict]] = {}
        for row in out:
            by_state.setdefault(row.get("state") or "??", []).append(row)
        for st in by_state:
            by_state[st].sort(
                key=lambda r: (
                    0 if r.get("asking_price_usd") is not None else 1,
                    -(r.get("acreage") or 0),
                )
            )
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
            ProviderStatus.CONFIGURED,
            diversified,
            error="; ".join(errors) if errors else None,
        )

    async def get_listing(self, external_id: str) -> ProviderResult[dict]:
        res = await self.search_listings({"limit": 200})
        if not res.data:
            return ProviderResult(False, ProviderStatus.CONFIGURED, error="Not found")
        for row in res.data:
            if row.get("external_id") == external_id:
                return ProviderResult(True, ProviderStatus.CONFIGURED, row)
        return ProviderResult(False, ProviderStatus.CONFIGURED, error="Not found")

    def normalize_listing(self, raw: dict) -> dict:
        return raw


async def asyncio_gather_sources(
    client: httpx.AsyncClient,
    sources: list[ArcgisMarketSource],
    per_source: int,
    errors: list[str],
    start_offset: int = 0,
) -> list[list[dict]]:
    import asyncio

    async def one(src: ArcgisMarketSource) -> list[dict]:
        try:
            return await _fetch_arcgis_pages(
                client, src, target=per_source, start_offset=start_offset
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.source_id}: {exc}")
            log.warning("public_tax_source_failed", source=src.source_id, error=str(exc))
            return []

    return list(await asyncio.gather(*[one(s) for s in sources]))


class PublicSurplusProvider(ListingProvider):
    """Municipal/county surplus property ≈ CRE disposal / land-bank inventory."""

    id = "public_surplus"
    name = "Public Surplus / Land-Bank GIS"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def search_listings(self, query: dict[str, Any]) -> ProviderResult[list[dict]]:
        limit = int(query.get("limit") or 200)
        out: list[dict] = []
        surplus_sources = [s for s in SOURCES if "surplus" in s.source_id]
        errors: list[str] = []
        per_source = max(50, limit // max(1, len(surplus_sources)))
        async with httpx.AsyncClient(timeout=60.0) as client:
            batches = await asyncio_gather_sources(client, surplus_sources, per_source, errors)
            for batch in batches:
                out.extend(batch)
        out.sort(key=lambda r: -(r.get("acreage") or 0))
        return ProviderResult(True, ProviderStatus.CONFIGURED, out[:limit], error="; ".join(errors) if errors else None)

    async def get_listing(self, external_id: str) -> ProviderResult[dict]:
        res = await self.search_listings({"limit": 200})
        for row in res.data or []:
            if row.get("external_id") == external_id:
                return ProviderResult(True, ProviderStatus.CONFIGURED, row)
        return ProviderResult(False, ProviderStatus.CONFIGURED, error="Not found")

    def normalize_listing(self, raw: dict) -> dict:
        return raw
