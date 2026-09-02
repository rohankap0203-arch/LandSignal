"""Free public market adapters approximating licensed listing/parcel vendors.

Cursor Cloud does NOT include MLS / Land.com / Crexi / Regrid credentials.
These adapters use authorized public GIS / government open data instead:

- Tax-sale / auction parcels (≈ distressed / opportunistic inventory)
- Municipal/county surplus property (≈ CRE / land bank inventory)
- Listing polygons themselves (≈ Regrid parcel geometry for discovered assets)

No ToS-circumventing scrapers.
"""

from __future__ import annotations

import asyncio
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

# Some county GIS stacks (e.g. Lake County FL) 403 bare httpx clients.
_ARCGIS_HEADERS = {
    "User-Agent": "LandSignalBot/1.0 (+https://landsignal.app; public GIS inventory)",
    "Accept": "application/json,application/geo+json,*/*",
}

# Credible US inventory only — reject junk normalize output before it hits discover.
_US_STATE_CODES = frozenset(
    {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
        "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
        "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
        "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    }
)

# Per-source wall clock so one hung ArcGIS host cannot stall nationwide discover.
# Statewide OID-shard pulls need more than 2 minutes to return real volume.
_SOURCE_FETCH_TIMEOUT_S = 240.0
_STATE_FETCH_TIMEOUT_S = 480.0
_HTTP_RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


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
        order_by: str | None = None,
        *,
        page_size: int | None = None,
        out_fields: str = "*",
        shard_by_objectid: bool = False,
        objectid_max: int | None = None,
        shard_field: str | None = None,
        shard_values: list[str] | None = None,
    ):
        self.source_id = source_id
        self.name = name
        self.url = url
        self.state = state
        self.county = county
        self.normalize = normalize
        self.where = where
        self.order_by = order_by
        self.page_size = page_size
        self.out_fields = out_fields
        # CO_NO is present on FL_Parcels but not reliably filterable; OBJECTID ranges work.
        self.shard_by_objectid = shard_by_objectid
        self.objectid_max = objectid_max
        # Alternate sharding when OBJECTID windows are unsupported (e.g. NC OneMap).
        self.shard_field = shard_field
        self.shard_values = shard_values


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


def _prop(props: dict, *names: str) -> Any:
    """Read a field by exact name or schema-qualified suffix (Toledo-style)."""
    for n in names:
        if n in props and props[n] is not None:
            return props[n]
    for n in names:
        for k, v in props.items():
            if v is None:
                continue
            if k.endswith(f".{n}") or k == n:
                return v
    return None


def _fnum(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _norm_mahoning(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _fnum(props.get("ACRES")) or geom_acres
    if acreage is not None and acreage < 0.2:
        return None
    pid = props.get("PARCEL_ID") or props.get("PARCEL_ID_1") or props.get("OBJECTID")
    market = props.get("TOTALMARKET") or props.get("MARKETLAND")
    addr = props.get("MVP_ADDRESS") or f"Mahoning County, OH · {pid}"
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"mahoning:{pid}",
        "title": f"Mahoning OH land-bank · {float(acreage):.2f} ac · {pid}"
        if acreage is not None
        else f"Mahoning OH land-bank · {pid}",
        "description": (
            f"Mahoning County, OH land-bank / tax-delinquent inventory (public GIS). "
            f"Land use={props.get('LANDUSE') or 'n/a'}. "
            f"Market mark=${market}. Distressed public inventory — not MLS."
        ),
        "asking_price_usd": float(market) if market is not None else None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "OH",
        "county": "Mahoning",
        "apn": str(pid),
        "address": str(addr),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.mahoningcountyoh.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_gadsden_lb(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _fnum(props.get("acres")) or geom_acres
    if acreage is not None and acreage < 0.15:
        return None
    pid = props.get("parcelid") or props.get("pin") or props.get("objectid")
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"gadsden:{pid}",
        "title": f"Gadsden AL land bank · {float(acreage):.2f} ac · {pid}"
        if acreage is not None
        else f"Gadsden AL land bank · {pid}",
        "description": (
            f"City of Gadsden, AL land-bank parcel (public GIS). "
            f"Owner mark={props.get('ownername') or 'Land Bank'}. "
            "Public land-bank channel — not MLS."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "AL",
        "county": "Etowah",
        "apn": str(pid),
        "address": f"Gadsden, AL · {pid}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": props.get("proplink") or "https://www.cityofgadsden.com/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_hartford_surplus(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    plan = (props.get("PROPERTY_PLAN") or "").strip().lower()
    tax_deed = (props.get("Aquired_via_Tax_Deed") or "").upper()
    if "surplus" not in plan and "land bank" not in plan and "TAX DEED" not in tax_deed:
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    sqft = _fnum(props.get("LOT_SIZE___SQ__FT__"))
    acreage = (sqft / 43560.0) if sqft else geom_acres
    if acreage is not None and acreage < 0.05:
        return None
    pid = props.get("PARCEL_NUMBER") or props.get("GIS_PIN") or props.get("OBJECTID")
    street = props.get("gisaddress") or props.get("STREET") or ""
    return {
        "provider_id": "public_surplus",
        "external_id": f"hartford:{pid}",
        "title": f"Hartford CT surplus / land bank · {street or pid}",
        "description": (
            f"City of Hartford, CT DDS-managed property (public GIS). "
            f"Plan={props.get('PROPERTY_PLAN')}. Tax deed note={props.get('Aquired_via_Tax_Deed') or 'n/a'}. "
            "Municipal surplus / land-bank path — not MLS."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "CT",
        "county": "Hartford",
        "apn": str(pid),
        "address": f"{street}, Hartford, CT".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.hartford.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_baltimore_taxsale(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    # Shape__Area often web-mercator m²; prefer geometry acres after outSR=4326
    acreage = geom_acres
    if acreage is not None and acreage < 0.08:
        return None  # skip tiny urban stubs; keep larger tax-sale tracts
    pid = props.get("Blocklot") or props.get("ObjectID")
    lien = _fnum(props.get("LIEN_AMOUNT"))
    addr = props.get("Address") or ""
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"balt:{pid}",
        "title": f"Baltimore MD tax sale · {addr or pid}",
        "description": (
            f"Baltimore City, MD tax-sale inventory (public GIS). "
            f"Owner mark={props.get('Owner') or 'n/a'}. Lien mark=${lien}. "
            "Public tax-sale channel — not MLS."
        ),
        "asking_price_usd": lien if lien and lien > 0 else None,
        "acreage": float(acreage) if acreage is not None else 0.1,
        "state": "MD",
        "county": "Baltimore City",
        "apn": str(pid),
        "address": f"{addr}, Baltimore, MD".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.baltimorecity.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_ramsey_forfeit(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    # Point layer often — use a workable default when acres missing
    acreage = geom_acres if geom_acres and geom_acres > 0.01 else 0.25
    pid = props.get("PIN") or props.get("OBJECTID")
    bid = _fnum(props.get("MinimumBid"))
    addr = props.get("Address") or props.get("AddressDescription") or ""
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"ramsey:{pid}",
        "title": f"Ramsey MN tax-forfeit · {addr or pid}",
        "description": (
            f"Ramsey County, MN tax-forfeited land (public GIS). "
            f"Status={props.get('Status') or 'n/a'}. Min bid=${bid}. "
            f"Municipality={props.get('Municipality') or 'n/a'}. Public forfeit channel — not MLS."
        ),
        "asking_price_usd": bid,
        "acreage": float(acreage),
        "state": "MN",
        "county": "Ramsey",
        "apn": str(pid),
        "address": f"{addr}, Ramsey County, MN".strip(", "),
        "latitude": lat or _fnum(props.get("Latitude")),
        "longitude": lon or _fnum(props.get("Longitude")),
        "polygon": polygon,
        "source_url": "https://www.ramseycounty.us/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_dakota_forfeit(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _fnum(props.get("TOTAL_ACRES")) or geom_acres
    if acreage is not None and acreage < 0.25:
        return None
    pid = props.get("TAXPIN") or props.get("Parcel_ID") or props.get("OBJECTID")
    addr = props.get("SITEADDRESS") or ""
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"dakota:{pid}",
        "title": f"Dakota MN tax-forfeit · {float(acreage):.2f} ac · {addr or pid}"
        if acreage is not None
        else f"Dakota MN tax-forfeit · {addr or pid}",
        "description": (
            f"Dakota County, MN tax-forfeit inventory (public GIS). "
            f"Last owner={props.get('Last_Owner') or 'n/a'}. Public forfeit channel — not MLS."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "MN",
        "county": "Dakota",
        "apn": str(pid),
        "address": f"{addr}, Dakota County, MN".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.co.dakota.mn.us/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_kc_landbank(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = geom_acres
    if acreage is not None and acreage < 0.08:
        return None
    pid = props.get("APN") or props.get("KIVAPIN") or props.get("OBJECTID")
    addr = props.get("ADDRESS") or props.get("ADDR") or ""
    return {
        "provider_id": "public_surplus",
        "external_id": f"kcmo:{pid}",
        "title": f"Kansas City MO land bank · {addr or pid}",
        "description": (
            f"Kansas City, MO land-bank inventory (public GIS). "
            f"Owner={props.get('OWN_NAME') or 'Land Bank'}. Land use={props.get('LANDUSECODE') or 'n/a'}. "
            "Municipal land-bank channel — not MLS."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage is not None else 0.12,
        "state": "MO",
        "county": "Jackson",
        "apn": str(pid),
        "address": f"{addr}, Kansas City, MO".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.kcmo.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_stl_lra(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    if str(props.get("LRA") or "").lower() not in ("yes", "y", "true", "1"):
        # Still allow LCRA-held if LRA flag blank
        if str(props.get("LCRA") or "").lower() not in ("yes", "y", "true", "1"):
            return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _fnum(props.get("Acres")) or geom_acres
    if acreage is not None and acreage < 0.15:
        return None
    pid = props.get("Handle") or props.get("OBJECTID")
    addr = props.get("Address") or ""
    return {
        "provider_id": "public_surplus",
        "external_id": f"stlra:{pid}",
        "title": f"St. Louis MO LRA · {float(acreage):.2f} ac · {addr or pid}"
        if acreage is not None
        else f"St. Louis MO LRA · {addr or pid}",
        "description": (
            f"St. Louis, MO Land Reutilization Authority / LCRA inventory (public GIS). "
            f"Neighborhood={props.get('Neighborhood') or 'n/a'}. "
            "Public land-bank channel — not MLS."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "MO",
        "county": "St. Louis City",
        "apn": str(pid),
        "address": f"{addr}, St. Louis, MO".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.stlouis-mo.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_lancaster_taxsale(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    # Prefer vacant / land-like tax-sale records over dense residential flips
    vac = _fnum(props.get("vac_cnt")) or 0
    class_d = (props.get("classdscrp") or "").lower()
    if vac <= 0 and "vacant" not in class_d and "ag" not in class_d and "land" not in class_d:
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = geom_acres if geom_acres and geom_acres > 0.05 else 0.5
    pid = props.get("parcelid") or props.get("pid") or props.get("fid")
    addr = props.get("siteaddres") or ""
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"lancaster:{pid}",
        "title": f"Lancaster NE tax sale · {addr or pid}",
        "description": (
            f"Lancaster County / Lincoln, NE tax-sale inventory (public GIS). "
            f"Class={props.get('classdscrp') or 'n/a'}. Tax-sale code={props.get('tax_sale_c') or 'n/a'}. "
            "Public tax-sale channel — not MLS."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage),
        "state": "NE",
        "county": "Lancaster",
        "apn": str(pid),
        "address": f"{addr}, Lancaster County, NE".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.lincoln.ne.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_toledo_forsale(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _fnum(_prop(props, "ACREAGE", "ACREAGE_CA")) or geom_acres
    if acreage is not None and acreage < 0.15:
        return None
    pid = _prop(props, "PARID", "ASSESSOR_N", "OBJECTID")
    addr = _prop(props, "PROPERTY_A", "SITEADD", "ADDRESS") or f"Toledo, OH · {pid}"
    owner = _prop(props, "OWNER", "OWN_NAME")
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"toledo:{pid}",
        "title": f"Toledo OH for-sale / land bank · {float(acreage):.2f} ac · {pid}"
        if acreage is not None
        else f"Toledo OH for-sale / land bank · {pid}",
        "description": (
            f"City of Toledo, OH public for-sale / land-bank inventory (public GIS). "
            f"Owner mark={owner or 'n/a'}. Distressed / municipal sales channel — not MLS."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "OH",
        "county": "Lucas",
        "apn": str(pid),
        "address": str(addr),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://toledo.oh.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _nj_acres(props: dict, geom_acres: float | None, *, min_ac: float, max_ac: float = 2500.0) -> float | None:
    """Prefer MOD-IV CALC_ACRE, but reject absurd assessor typos using geometry."""
    calc = _fnum(props.get("CALC_ACRE"))
    acreage = calc if calc is not None else geom_acres
    if acreage is None:
        return None
    if acreage > max_ac:
        if geom_acres is not None and min_ac <= geom_acres <= max_ac:
            acreage = geom_acres
        else:
            return None
    if acreage < min_ac:
        return None
    return float(acreage)


def _bounded_acres(
    preferred: float | None,
    geom_acres: float | None,
    *,
    min_ac: float,
    max_ac: float = 2500.0,
) -> float | None:
    """Prefer assessor acreage; fall back to geometry; reject absurd outliers.

    If assessor acres and polygon acres disagree by a wide margin, trust the
    polygon (common MassGIS / CAD typos publish thousands of acres on small lots).
    """
    acreage = preferred if preferred is not None else geom_acres
    if (
        preferred is not None
        and geom_acres is not None
        and preferred > 0
        and geom_acres > 0
        and (preferred / geom_acres > 3.0 or geom_acres / preferred > 3.0)
        and min_ac <= geom_acres <= max_ac
    ):
        acreage = geom_acres
    if acreage is None:
        return None
    if acreage > max_ac:
        if geom_acres is not None and min_ac <= geom_acres <= max_ac:
            acreage = geom_acres
        else:
            return None
    if acreage < min_ac:
        return None
    return float(acreage)


def _validate_inventory_row(row: dict | None) -> dict | None:
    """Reject non-credible normalize output before it enters discover/search."""
    if not isinstance(row, dict):
        return None
    try:
        state = str(row.get("state") or "").upper().strip()
        if state not in _US_STATE_CODES:
            return None
        ext = str(row.get("external_id") or "").strip()
        if not ext or ":" not in ext:
            return None
        provider = str(row.get("provider_id") or "").strip()
        if provider not in {"public_vacant_gis", "public_tax_sale", "public_surplus"}:
            return None
        acres = float(row.get("acreage"))
        if acres < 0.05 or acres > 50_000:
            return None
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
        if lat < -90 or lat > 90 or lon < -180 or lon > 180:
            return None
        # Rough North America guard — keeps ocean/null-island junk out.
        if lat < 17.0 or lat > 72.0 or lon < -180.0 or lon > -60.0:
            return None
        poly = row.get("polygon")
        if poly is not None:
            if not isinstance(poly, list) or not poly or not isinstance(poly[0], list):
                return None
        title = str(row.get("title") or "").strip()
        if not title:
            return None
        out = dict(row)
        out["state"] = state
        out["acreage"] = acres
        out["latitude"] = lat
        out["longitude"] = lon
        out["external_id"] = ext
        out["provider_id"] = provider
        out["is_demo"] = False
        if out.get("status") is None:
            out["status"] = "ACTIVE"
        from landsignal.services.purchase_credibility import sanitize_row_asking_price

        return sanitize_row_asking_price(out)
    except Exception:  # noqa: BLE001
        return None


def _dedupe_inventory_rows(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for row in rows:
        key = (str(row.get("provider_id") or ""), str(row.get("external_id") or ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


_NON_MARKET_OWNER_MARKERS = (
    "UNITED STATES",
    "U S A",
    "U.S.",
    "USA ",
    "STATE OF",
    "PEOPLE OF",
    "COMMONWEALTH OF",
    "COUNTY OF",
    "CITY OF",
    "TOWN OF",
    "VILLAGE OF",
    "NYS ",
    "NEW YORK STATE",
    "MASSACHUSETTS",
    "DEPT OF",
    "DEPARTMENT OF",
    "NATURE CONSERVANCY",
    "OPEN SPACE INSTITUTE",
    "LAND TRUST",
    "LAND, TRUST",
    "CONSERVANCY",
    "NATIONAL PARK",
    "FOREST SERVICE",
    "GAME & FISH",
    "GAME AND FISH",
    "FISH AND WILDLIFE",
    "WATER MGMT",
    "WATER MANAGEMENT",
    "WMD ",
    "ARMY",
    "AIR FORCE",
    "NAVY ",
    "CAMP ROBINSON",
)


def _non_market_owner(name: str | None) -> bool:
    """True for government / conservation holders we should not present as buys."""
    blob = " ".join(str(name or "").upper().split())
    if not blob:
        return False
    return any(m in blob for m in _NON_MARKET_OWNER_MARKERS)


def _norm_nj_mod4_vacant(raw: dict) -> dict | None:
    """NJ statewide MOD-IV class 1 vacant land (map screen — not a sale calendar)."""
    props = raw.get("properties") or {}
    if str(props.get("PROP_CLASS") or "").strip() != "1":
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _nj_acres(props, geom_acres, min_ac=1.0)
    if acreage is None:
        return None
    impr = _fnum(props.get("IMPRVT_VAL")) or 0
    if impr > 0:
        return None
    pid = props.get("PAMS_PIN") or props.get("GIS_PIN") or props.get("PIN_NODUP") or props.get("OBJECTID")
    county = (props.get("COUNTY") or "Unknown").title()
    mun = (props.get("MUN_NAME") or "").title()
    loc = props.get("PROP_LOC") or props.get("ST_ADDRESS") or ""
    land_val = _fnum(props.get("LAND_VAL"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"njmod4:{pid}",
        "title": f"New Jersey vacant · {float(acreage):.2f} ac · {mun or county}",
        "description": (
            f"New Jersey MOD-IV class-1 vacant land (statewide NJOGIS cadastral). "
            f"County={county}. Municipality={mun or 'n/a'}. Land appraisal mark=${land_val}. "
            f"Land desc={props.get('LAND_DESC') or 'n/a'}. "
            "Public map screen — not a confirmed tax sale; confirm owner / sale path before chasing."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": float(acreage),
        "state": "NJ",
        "county": county,
        "apn": str(pid),
        "address": f"{loc}, {mun or county}, NJ".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://maps.nj.gov/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_nj_mod4_farm(raw: dict) -> dict | None:
    """NJ statewide MOD-IV class 3B farmland (map screen for larger rural tracts)."""
    props = raw.get("properties") or {}
    if str(props.get("PROP_CLASS") or "").strip().upper() != "3B":
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _nj_acres(props, geom_acres, min_ac=10.0)
    if acreage is None:
        return None
    pid = props.get("PAMS_PIN") or props.get("GIS_PIN") or props.get("PIN_NODUP") or props.get("OBJECTID")
    county = (props.get("COUNTY") or "Unknown").title()
    mun = (props.get("MUN_NAME") or "").title()
    loc = props.get("PROP_LOC") or props.get("ST_ADDRESS") or ""
    land_val = _fnum(props.get("LAND_VAL"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"njfarm:{pid}",
        "title": f"New Jersey farmland · {float(acreage):.2f} ac · {mun or county}",
        "description": (
            f"New Jersey MOD-IV class-3B farmland (statewide NJOGIS cadastral). "
            f"County={county}. Municipality={mun or 'n/a'}. Land appraisal mark=${land_val}. "
            "Public map screen — not MLS; confirm whether the owner will sell before underwriting."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": float(acreage),
        "state": "NJ",
        "county": county,
        "apn": str(pid),
        "address": f"{loc}, {mun or county}, NJ".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://maps.nj.gov/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_ny_orpts_vacant(raw: dict) -> dict | None:
    """NY ORPTS vacant land (prop class 300–399, excl. underwater) — public map screen."""
    props = raw.get("properties") or {}
    try:
        pclass = int(float(props.get("PROP_CLASS")))
    except (TypeError, ValueError):
        return None
    if pclass < 300 or pclass >= 400 or pclass == 315:
        return None
    owner = props.get("PRIMARY_OWNER")
    if _non_market_owner(owner):
        return None
    addr = str(props.get("PARCEL_ADDR") or "")
    if "UNDERWATER" in addr.upper():
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(
        _fnum(props.get("CALC_ACRES")) or _fnum(props.get("ACRES")),
        geom_acres,
        min_ac=1.0,
    )
    if acreage is None:
        return None
    pid = props.get("PRINT_KEY") or props.get("SBL") or props.get("SWIS_PRINT_KEY_ID") or props.get("OBJECTID")
    county = str(props.get("COUNTY_NAME") or "Unknown").replace("StLawrence", "St. Lawrence").title()
    mun = str(props.get("MUNI_NAME") or "").title()
    land_val = _fnum(props.get("LAND_AV"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"nyorpts:{props.get('SWIS') or ''}:{pid}",
        "title": f"New York vacant · {float(acreage):.2f} ac · {mun or county}",
        "description": (
            "New York ORPTS vacant land (statewide NYS Tax Parcels Public; 38 participating counties). "
            f"Property class={pclass}. County={county}. Municipality={mun or 'n/a'}. "
            f"Land assessed value mark=${land_val}. "
            "Public cadastral screen — not a tax-sale calendar; confirm owner / sale path before chasing."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": float(acreage),
        "state": "NY",
        "county": county,
        "apn": str(pid),
        "address": f"{addr}, {mun or county}, NY".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://gis.ny.gov/parcels",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_ny_orpts_ag(raw: dict) -> dict | None:
    """NY ORPTS agricultural parcels (prop class 100–199) — larger rural map screen."""
    props = raw.get("properties") or {}
    try:
        pclass = int(float(props.get("PROP_CLASS")))
    except (TypeError, ValueError):
        return None
    if pclass < 100 or pclass >= 200:
        return None
    owner = props.get("PRIMARY_OWNER")
    if _non_market_owner(owner):
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(
        _fnum(props.get("CALC_ACRES")) or _fnum(props.get("ACRES")),
        geom_acres,
        min_ac=10.0,
    )
    if acreage is None:
        return None
    pid = props.get("PRINT_KEY") or props.get("SBL") or props.get("SWIS_PRINT_KEY_ID") or props.get("OBJECTID")
    county = str(props.get("COUNTY_NAME") or "Unknown").replace("StLawrence", "St. Lawrence").title()
    mun = str(props.get("MUNI_NAME") or "").title()
    addr = props.get("PARCEL_ADDR") or ""
    land_val = _fnum(props.get("LAND_AV"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"nyag:{props.get('SWIS') or ''}:{pid}",
        "title": f"New York farmland · {float(acreage):.2f} ac · {mun or county}",
        "description": (
            f"New York ORPTS agricultural parcel (statewide NYS Tax Parcels Public). "
            f"Property class={pclass}. County={county}. Municipality={mun or 'n/a'}. "
            f"Land assessed value mark=${land_val}. "
            "Public cadastral screen — not MLS; confirm whether the owner will sell before underwriting."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": float(acreage),
        "state": "NY",
        "county": county,
        "apn": str(pid),
        "address": f"{addr}, {mun or county}, NY".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://gis.ny.gov/parcels",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_ar_geostor_vacant(raw: dict) -> dict | None:
    """Arkansas statewide CAMP parcels — unimproved AV tracts (AGISO / GeoStor)."""
    props = raw.get("properties") or {}
    ptype = str(_prop(props, "parceltype", "ParcelType") or "").upper()
    if ptype and ptype != "AV":
        return None
    imp = _fnum(_prop(props, "impvalue", "ImpValue")) or 0.0
    if imp > 0:
        return None
    land_val = _fnum(_prop(props, "landvalue", "LandValue"))
    if land_val is not None and land_val <= 0:
        return None
    owner = _prop(props, "ownername", "OwnerName")
    if _non_market_owner(owner):
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(
        _fnum(_prop(props, "taxarea", "TaxArea")),
        geom_acres,
        min_ac=5.0,
    )
    if acreage is None:
        return None
    pid = _prop(props, "parcelid", "ParcelId", "countyid", "CountyId", "objectid", "OBJECTID")
    county = str(_prop(props, "county", "County") or "Unknown").title()
    loc = _prop(props, "adrlabel", "AdrLabel", "parcellgl", "ParcelLgl") or ""
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"argeostor:{county}:{pid}",
        "title": f"Arkansas vacant/ag · {float(acreage):.2f} ac · {county}",
        "description": (
            f"Arkansas statewide CAMP cadastral parcel (AGISO / GeoStor Planning_Cadastre). "
            f"Parcel type={ptype or 'AV'}. County={county}. Land value mark=${land_val}. "
            "Unimproved map screen — coverage varies by county production block; "
            "not a tax-sale list. Confirm owner / sale path before chasing."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": float(acreage),
        "state": "AR",
        "county": county,
        "apn": str(pid),
        "address": f"{str(loc)[:80]}, {county}, AR".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://gis.arkansas.gov/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_ma_massgis_vacant(raw: dict) -> dict | None:
    """MassGIS Level-3 vacant / open land (statewide assessor parcels)."""
    props = raw.get("properties") or {}
    use = str(props.get("USE_CODE") or "").strip()
    vacant_codes = {"130", "131", "132", "201", "202", "390", "391", "392", "393"}
    if use not in vacant_codes:
        return None
    bldg = _fnum(props.get("BLDG_VAL")) or 0.0
    if bldg > 0:
        return None
    units = str(props.get("LOT_UNITS") or "").lower()
    lot = _fnum(props.get("LOT_SIZE"))
    # Only trust LOT_SIZE when the town published acres (sq-ft towns are inconsistent).
    preferred = lot if "acre" in units else None
    owner = props.get("OWNER1")
    if _non_market_owner(owner):
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None:
        return None
    pid = props.get("PROP_ID") or props.get("MAP_PAR_ID") or props.get("LOC_ID") or props.get("OBJECTID")
    city = str(props.get("CITY") or "Unknown").title()
    addr = props.get("SITE_ADDR") or ""
    land_val = _fnum(props.get("LAND_VAL"))
    use_desc = props.get("USE_DESC") or use
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"massgis:{pid}",
        "title": f"Massachusetts vacant · {float(acreage):.2f} ac · {city}",
        "description": (
            f"Massachusetts MassGIS Level-3 property tax parcel (statewide). "
            f"Use={use} ({use_desc}). City/town={city}. Land value mark=${land_val}. "
            "Public cadastral screen — not a confirmed listing; confirm owner / sale path before chasing."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": float(acreage),
        "state": "MA",
        "county": city,  # MassGIS is town-based; city/town is the practical locality key
        "apn": str(pid),
        "address": f"{addr}, {city}, MA".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.mass.gov/info-details/massgis-data-property-tax-parcels",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_ma_massgis_chapter61(raw: dict) -> dict | None:
    """MassGIS Chapter 61 / 61A forest & farm land (larger rural tracts)."""
    props = raw.get("properties") or {}
    use = str(props.get("USE_CODE") or "").strip()
    if use not in {"601", "602", "713", "714", "717", "718"}:
        return None
    bldg = _fnum(props.get("BLDG_VAL")) or 0.0
    if bldg > 0:
        return None
    units = str(props.get("LOT_UNITS") or "").lower()
    lot = _fnum(props.get("LOT_SIZE"))
    preferred = lot if "acre" in units else None
    owner = props.get("OWNER1")
    if _non_market_owner(owner):
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=10.0)
    if acreage is None:
        return None
    pid = props.get("PROP_ID") or props.get("MAP_PAR_ID") or props.get("LOC_ID") or props.get("OBJECTID")
    city = str(props.get("CITY") or "Unknown").title()
    addr = props.get("SITE_ADDR") or ""
    land_val = _fnum(props.get("LAND_VAL"))
    use_desc = props.get("USE_DESC") or use
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"mach61:{pid}",
        "title": f"Massachusetts Ch.61 land · {float(acreage):.2f} ac · {city}",
        "description": (
            f"Massachusetts MassGIS Chapter 61 / 61A forest or farm parcel (statewide). "
            f"Use={use} ({use_desc}). City/town={city}. Land value mark=${land_val}. "
            "Public cadastral screen — not MLS; confirm whether the owner will sell before underwriting."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": float(acreage),
        "state": "MA",
        "county": city,
        "apn": str(pid),
        "address": f"{addr}, {city}, MA".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.mass.gov/info-details/massgis-data-property-tax-parcels",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
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


def _norm_dekalb(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    stated = props.get("STATEDAREA")
    if acreage is None and stated:
        try:
            acreage = float(str(stated).replace(",", "").split()[0])
        except Exception:
            pass
    if acreage is not None and acreage < 0.05:
        return None
    pid = props.get("PARCELID") or props.get("LOWPARCELID") or props.get("OBJECTID")
    use = props.get("USEDSCRP") or props.get("USECD") or "Unknown use"
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"dekalb:{pid}",
        "title": f"DeKalb GA delinquent · {use} · {pid}",
        "description": (
            f"DeKalb County, GA delinquent tax parcel (public GIS). "
            f"Use={use}. Tax district={props.get('CVTTXDSCRP') or 'n/a'}. "
            "Public distress inventory — not MLS/Crexi."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "GA",
        "county": "DeKalb",
        "apn": str(pid),
        "address": f"DeKalb County, GA · {pid}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.dekalbcountyga.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_allegheny(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage = props.get("CALCACREAGE")
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is None:
        acreage = geom_acres
    # Focus on larger vacant-ish parcels from the county layer
    if acreage is None or float(acreage) < 2.0:
        return None
    if float(acreage) > 500:
        return None
    pid = props.get("PIN") or props.get("MAPBLOCKLOT") or props.get("OBJECTID")
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"allegheny:{pid}",
        "title": f"Allegheny PA parcel · {float(acreage):.2f} ac · {pid}",
        "description": (
            "Allegheny County, PA public parcel GIS (≥2 ac screen for land thesis). "
            "Not a dedicated tax-sale feed — treat as public land inventory for screening only."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage),
        "state": "PA",
        "county": "Allegheny",
        "apn": str(pid),
        "address": f"Allegheny County, PA · {pid}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.alleghenycounty.us/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_dallas_vacant(raw: dict) -> dict | None:
    props = raw.get("properties") or raw.get("attributes") or {}
    area_ft = props.get("AREA_FEET") or props.get("Shape__Area")
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is None and area_ft:
        acreage = float(area_ft) / 43560.0
    if acreage is None or acreage < 0.5:
        return None
    pid = props.get("ACCT") or props.get("GIS_ACCT") or props.get("OBJECTID")
    use = props.get("PROP_CL") or "Vacant tract"
    land_val = _fnum(
        props.get("TOT_VAL")
        or props.get("LAND_VAL")
        or props.get("Land_Value")
        or props.get("MARKET_VALUE")
    )
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"dallas:{pid}",
        "title": f"Dallas CAD vacant · {acreage:.2f} ac · {use}",
        "description": (
            f"Dallas County, TX appraisal vacant/land tract (public CAD GIS). "
            f"Class={use}. SPTB={props.get('SPTBCODE')}. Land value mark=${land_val}. "
            "Public map screen — not a confirmed tax sale; confirm owner / sale status before chasing."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": float(acreage),
        "state": "TX",
        "county": "Dallas",
        "apn": str(pid),
        "address": f"{props.get('ST_NUM') or ''} {props.get('ST_NAME') or ''} {props.get('ST_TYPE') or ''}, Dallas County, TX".strip(),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.dallascad.org/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_bexar_vacant(raw: dict) -> dict | None:
    props = raw.get("properties") or raw.get("attributes") or {}
    acreage = props.get("Acres") or props.get("LglAcres")
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is None:
        acreage = geom_acres
    if acreage is None or float(acreage) < 2.0:
        return None
    # Prefer unimproved / low improvement marks when present
    houses = props.get("Houses")
    if houses not in (None, "0", 0, "0.0"):
        return None
    pid = props.get("PropID") or props.get("AcctNumb") or props.get("OBJECTID")
    land_val = _fnum(props.get("LandVal") or props.get("land_value"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"bexar:{pid}",
        "title": f"Bexar TX vacant land · {float(acreage):.2f} ac · {props.get('Situs') or pid}",
        "description": (
            f"Bexar County, TX (San Antonio) vacant/unimproved parcel from public CAD GIS. "
            f"Land value mark=${land_val}. Owner mark={props.get('Owner') or 'n/a'}. "
            "Public map screen — not a dedicated tax-sale feed."
        ),
        # Assessed land is the budget-filter price for vacant GIS (same as FL/NC).
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": float(acreage),
        "state": "TX",
        "county": "Bexar",
        "apn": str(pid),
        "address": f"{props.get('Situs') or ''}, {props.get('AddrCity') or 'San Antonio'}, TX".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.bcad.org/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_harris_tx_vacant(raw: dict) -> dict | None:
    """Harris County Appraisal District — unimproved 1ac+ with assessed land value."""
    props = raw.get("properties") or raw.get("attributes") or {}
    if (_fnum(props.get("impr_value")) or _fnum(props.get("bld_value")) or 0) > 0:
        return None
    preferred = _fnum(props.get("acreage_1")) or _fnum(props.get("Acreage")) or _fnum(props.get("StatedArea"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None or not polygon:
        return None
    land_val = _fnum(props.get("land_value"))
    if land_val is None or land_val <= 0:
        return None
    pid = props.get("HCAD_NUM") or props.get("acct_num") or props.get("OBJECTID")
    addr = " ".join(
        str(x).strip()
        for x in (
            props.get("site_str_num"),
            props.get("site_str_pfx"),
            props.get("site_str_name"),
            props.get("site_str_sfx"),
        )
        if x is not None and str(x).strip()
    )
    city = (props.get("site_city") or "Houston").strip()
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"harris_tx:{pid}",
        "title": f"Harris TX vacant · {acreage:.1f} ac · {city}",
        "description": (
            f"Harris County, TX (Houston) unimproved parcel from HCAD public GIS. "
            f"Land value=${land_val:,.0f}. Owner={props.get('owner_name_1')}. "
            "Public map screen — not MLS/Zillow."
        ),
        "asking_price_usd": float(land_val),
        "acreage": float(acreage),
        "state": "TX",
        "county": "Harris",
        "apn": str(pid) if pid else None,
        "address": f"{addr}, {city}, TX".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.hcad.org/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_king_vacant(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage = props.get("KCA_ACRES")
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is None:
        acreage = geom_acres
    if acreage is None or float(acreage) < 1.0:
        return None
    pid = props.get("PIN") or props.get("MAJOR") or props.get("OBJECTID")
    use = (props.get("PREUSE_DESC") or "Vacant").strip()
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"kingwa:{pid}",
        "title": f"King County WA vacant · {float(acreage):.2f} ac · {use}",
        "description": (
            f"King County, WA vacant land (public property info GIS). Use={use}. "
            "Public map screen — not MLS; confirm owner / marketing status before assuming a sale path."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage),
        "state": "WA",
        "county": "King",
        "apn": str(pid),
        "address": f"King County, WA · PIN {pid}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://gismaps.kingcounty.gov/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_nashville_vacant(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage = props.get("Acres") or props.get("DeededAcreage")
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is None:
        acreage = geom_acres
    if acreage is None or float(acreage) < 1.0:
        return None
    pid = props.get("APN") or props.get("ParID") or props.get("OBJECTID")
    land = _fnum(props.get("LandAppr") or props.get("LandAssd"))
    return {
        # Vacant cadastral GIS — NOT a confirmed tax-sale calendar. Mis-tagging as
        # public_tax_sale was inventing huge “buy edges” and crowding the radar with TN.
        "provider_id": "public_vacant_gis",
        "external_id": f"nash:{pid}",
        "title": f"Davidson TN vacant · {float(acreage):.2f} ac · {props.get('PropAddr') or pid}",
        "description": (
            f"Davidson County / Nashville vacant rural or vacant land (public cadastral GIS). "
            f"Use={props.get('LUDesc')}. Land appraisal mark=${land}. "
            "Public map screen — not a confirmed tax sale and not MLS."
        ),
        # Assessed land is the budget-filter price for vacant GIS (same as FL/TX/NY).
        "asking_price_usd": float(land) if land and land > 0 else None,
        "acreage": float(acreage),
        "state": "TN",
        "county": "Davidson",
        "apn": str(pid),
        "address": f"{props.get('PropAddr') or ''}, Nashville, TN".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.padctn.org/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_dlba(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    status = (props.get("inventory_status_socrata") or "").lower()
    if "for sale" not in status and "auction" not in status and "side lot" not in status:
        return None
    lat = props.get("latitude")
    lon = props.get("longitude")
    acreage, glat, glon, polygon = _acres_from_geom(raw.get("geometry"))
    if lat is None:
        lat = glat
    if lon is None:
        lon = glon
    # Typical Detroit side lot ~0.1 ac if geometry thin
    if acreage is None:
        acreage = 0.1
    pid = props.get("parcel_id") or props.get("ObjectId")
    street = " ".join(
        str(x)
        for x in [
            props.get("street_number"),
            props.get("street_direction"),
            props.get("street_name"),
            props.get("street_type"),
        ]
        if x
    ).strip()
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"dlba:{pid}",
        "title": f"Detroit Land Bank · {props.get('name') or street or pid}",
        "description": (
            f"Detroit Land Bank Authority owned inventory ({props.get('inventory_status_socrata')}). "
            f"Neighborhood={props.get('neighborhood')}. Public land-bank sales channel — not MLS."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage) if acreage else 0.1,
        "state": "MI",
        "county": "Wayne",
        "apn": str(pid),
        "address": f"{street or props.get('name')}, Detroit, MI",
        "latitude": float(lat) if lat is not None else None,
        "longitude": float(lon) if lon is not None else None,
        "polygon": polygon,
        "source_url": "https://buildingdetroit.org/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_utah_taxsale(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    status = str(props.get("Status") or "").lower()
    if status and status not in ("active", "available"):
        return None
    acreage = props.get("Deeded_Acr")
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    try:
        acreage = float(acreage) if acreage is not None else geom_acres
    except Exception:
        acreage = geom_acres
    if acreage is not None and acreage < 0.05:
        return None
    due = props.get("TotalDue")
    pid = props.get("Parcel_Num") or props.get("Account_Nu") or props.get("FID")
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"uttax:{pid}",
        "title": f"Utah tax sale · {acreage or '?'} ac · {pid}",
        "description": (
            f"Active tax-sale parcel layer (Utah public GIS). "
            f"Taxes due mark=${due}. Owner mark={props.get('Owner_Name')}. "
            "Distressed auction inventory — not MLS."
        ),
        "asking_price_usd": float(due) if due is not None else None,
        "acreage": float(acreage) if acreage is not None else None,
        "state": "UT",
        "county": props.get("Town") or "Beaver",
        "apn": str(pid),
        "address": f"{props.get('Situs_Addr') or ''}, UT".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": None,
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_whiteside_fc(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is not None and acreage < 0.08:
        return None
    pid = props.get("PARCELID") or props.get("OBJECTID")
    sale = props.get("SALEAMNT")
    return {
        "provider_id": "public_tax_sale",
        "external_id": f"whiteside:{pid}",
        "title": f"Whiteside IL foreclosure · {props.get('SITEADDRESS') or pid}",
        "description": (
            f"Whiteside County, IL tax-parcel foreclosure record (public GIS). "
            f"Sale amount mark=${sale}. Public distress inventory — not MLS."
        ),
        "asking_price_usd": float(sale) if sale is not None else None,
        "acreage": acreage,
        "state": "IL",
        "county": "Whiteside",
        "apn": str(pid),
        "address": f"{props.get('SITEADDRESS') or ''}, Whiteside County, IL".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.whiteside.org/",
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


def _norm_fairfax_large(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    area = props.get("SHAPE.STArea()") or props.get("SHAPE.STArea")
    if acreage is None and area:
        # Fairfax published area often in sq ft
        acreage = float(area) / 43560.0
    if acreage is None or acreage < 3.0:
        return None
    pid = props.get("PIN") or props.get("PARCEL_KEY") or props.get("OBJECTID")
    return {
        "provider_id": "public_surplus",
        "external_id": f"fairfax:{pid}",
        "title": f"Fairfax VA large parcel · {float(acreage):.2f} ac · {pid}",
        "description": (
            "Fairfax County, VA public parcel GIS (≥3 ac screen). "
            "Not a dedicated surplus feed — use as Northern Virginia land inventory for screening."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage),
        "state": "VA",
        "county": "Fairfax",
        "apn": str(pid),
        "address": f"Fairfax County, VA · {pid}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.fairfaxcounty.gov/",
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
    # Keep urban surplus, but drop flea-lot scraps that used to dominate FL inventory.
    if acreage is None or acreage < 1.0 or acreage > 2500:
        return None
    if not polygon:
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


def _norm_lake_fl_vacant(raw: dict) -> dict | None:
    """Lake County FL open-data vacant parcels (1ac+) — rural acreage Florida lacked."""
    props = raw.get("properties") or {}
    if str(props.get("Vacant") or "").strip().lower() not in {"yes", "y", "true", "1"}:
        return None
    owner = props.get("OwnerName")
    if _non_market_owner(owner):
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    preferred = _fnum(props.get("Acres"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None or not polygon:
        return None
    # Prefer vacant residential / commercial / industrial / ag-style DOR codes.
    luc = str(props.get("LandUseCode") or "").strip()
    if luc and not luc.startswith(("00", "10", "40", "50", "60", "66", "70", "80", "99")):
        return None
    pid = props.get("ParcelNumber") or props.get("AltKey") or props.get("OBJECTID")
    land_val = _fnum(props.get("LandValue"))
    bldg = _fnum(props.get("BuildingValue")) or 0
    if bldg > 0:
        return None
    addr = (props.get("PropertyAddress") or "").strip() or "Unassigned"
    use = props.get("LandUseDescription") or luc or "Vacant"
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"lake_fl:{pid}",
        "title": f"Lake FL vacant · {acreage:.1f} ac · {use}",
        "description": (
            f"Lake County FL property-appraiser vacant parcel screen. "
            f"Use={use}. Owner={owner}. Land value=${land_val}. "
            "Public GIS — not MLS/Land.com."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": acreage,
        "state": "FL",
        "county": "Lake",
        "apn": str(pid) if pid else None,
        "address": f"{addr}, Lake County, FL",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": props.get("PropertyLink"),
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_pbc_fl_vacant(raw: dict) -> dict | None:
    """Palm Beach County FDOR-joined vacant parcels (5ac+) via LND_SQFOOT."""
    props = raw.get("properties") or {}
    dor = str(props.get("DOR_UC") or "").strip()
    if not dor.startswith("00"):
        return None
    if _non_market_owner(props.get("OWN_NAME")):
        return None
    public = str(props.get("PUBLIC_LND") or "").strip().upper()
    if public in {"Y", "YES", "1", "T", "TRUE"}:
        return None
    living = _fnum(props.get("TOT_LVG_AR")) or 0
    if living > 0:
        return None
    sqft = _fnum(props.get("LND_SQFOOT"))
    preferred = (sqft / 43560.0) if sqft else None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=5.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("PARCEL_ID") or props.get("PARCELNO") or props.get("OBJECTID")
    city = (props.get("PHY_CITY") or "").strip() or "Palm Beach County"
    addr1 = (props.get("PHY_ADDR1") or "").strip()
    land_val = _fnum(props.get("LND_VAL"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"pbc_fl:{pid}",
        "title": f"Palm Beach FL vacant · {acreage:.1f} ac · DOR {dor}",
        "description": (
            f"Palm Beach County vacant (DOR 00*) parcel screen. "
            f"Owner={props.get('OWN_NAME')}. Land value=${land_val}. "
            "Public GIS — not MLS/Land.com."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": acreage,
        "state": "FL",
        "county": "Palm Beach",
        "apn": str(pid) if pid else None,
        "address": f"{addr1}, {city}, FL".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": None,
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_collier_fl_large(raw: dict) -> dict | None:
    """Collier County large parcels (5ac+) — acreage diversity for SW Florida."""
    props = raw.get("properties") or {}
    owner = props.get("NAME1") or props.get("OWNERNAME")
    if _non_market_owner(owner):
        return None
    preferred = _fnum(props.get("TOTALACRES"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=5.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("FOLIO") or props.get("PARCELID") or props.get("OID")
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"collier_fl:{pid}",
        "title": f"Collier FL parcel · {acreage:.1f} ac",
        "description": (
            f"Collier County parcel screen ({acreage:.1f} ac). Owner={owner}. "
            "Public GIS — not MLS/Land.com."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "FL",
        "county": "Collier",
        "apn": str(pid) if pid else None,
        "address": f"Collier County, FL · folio {pid}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": None,
        "status": "ACTIVE",
        "raw": props,
        "is_demo": False,
    }


_FL_COUNTY_NAMES = {
    1: "Alachua",
    2: "Baker",
    3: "Bay",
    4: "Bradford",
    5: "Brevard",
    6: "Broward",
    7: "Calhoun",
    8: "Charlotte",
    9: "Citrus",
    10: "Clay",
    11: "Collier",
    12: "Columbia",
    13: "Miami-Dade",
    14: "DeSoto",
    15: "Dixie",
    16: "Duval",
    17: "Escambia",
    18: "Flagler",
    19: "Franklin",
    20: "Gadsden",
    21: "Gilchrist",
    22: "Glades",
    23: "Gulf",
    24: "Hamilton",
    25: "Hardee",
    26: "Hendry",
    27: "Hernando",
    28: "Highlands",
    29: "Hillsborough",
    30: "Holmes",
    31: "Indian River",
    32: "Jackson",
    33: "Jefferson",
    34: "Lafayette",
    35: "Lake",
    36: "Lee",
    37: "Leon",
    38: "Levy",
    39: "Liberty",
    40: "Madison",
    41: "Manatee",
    42: "Marion",
    43: "Martin",
    44: "Monroe",
    45: "Nassau",
    46: "Okaloosa",
    47: "Okeechobee",
    48: "Orange",
    49: "Osceola",
    50: "Palm Beach",
    51: "Pasco",
    52: "Pinellas",
    53: "Polk",
    54: "Putnam",
    55: "St. Johns",
    56: "St. Lucie",
    57: "Santa Rosa",
    58: "Sarasota",
    59: "Seminole",
    60: "Sumter",
    61: "Suwannee",
    62: "Taylor",
    63: "Union",
    64: "Volusia",
    65: "Wakulla",
    66: "Walton",
    67: "Washington",
}


def _fl_county_name(co_no: Any) -> str:
    try:
        return _FL_COUNTY_NAMES.get(int(float(co_no)), "Florida")
    except Exception:
        return "Florida"


def _norm_fl_parcels_vacant(raw: dict) -> dict | None:
    """Statewide Florida vacant land (DOR 00*) from FL_Parcels — Zillow-scale coverage."""
    props = raw.get("properties") or {}
    dor = str(props.get("DOR_UC") or "").strip()
    if not dor.startswith("00"):
        return None
    if _non_market_owner(props.get("OWN_NAME")):
        return None
    public = str(props.get("PUBLIC_LND") or "").strip().upper()
    if public in {"Y", "YES", "1", "T", "TRUE"}:
        return None
    # DOR 00* is the vacant land use code. Assessor TOT_LVG_AR is often stale/noisy on
    # this layer (~80% of 00* rows), so only drop clear residential structures.
    living = _fnum(props.get("TOT_LVG_AR")) or 0
    if living >= 800:
        return None
    preferred = _fnum(props.get("Acres"))
    if preferred is None:
        sqft = _fnum(props.get("LND_SQFOOT"))
        preferred = (sqft / 43560.0) if sqft else None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("PARCEL_ID") or props.get("OBJECTID")
    county = _fl_county_name(props.get("CO_NO"))
    city = (props.get("PHY_CITY") or "").strip() or county
    addr1 = (props.get("PHY_ADDR1") or "").strip()
    land_val = _fnum(props.get("LND_VAL"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"fl_parcels:{pid}",
        "title": f"Florida vacant · {acreage:.1f} ac · {county}",
        "description": (
            f"Florida statewide vacant parcel (DOR {dor}). "
            f"County={county}. Owner={props.get('OWN_NAME')}. Land value=${land_val}. "
            "Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": acreage,
        "state": "FL",
        "county": county,
        "apn": str(pid) if pid else None,
        "address": f"{addr1}, {city}, FL".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": None,
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_fl_parcels_ag(raw: dict) -> dict | None:
    """Statewide Florida agricultural parcels (DOR 050–069)."""
    props = raw.get("properties") or {}
    dor = str(props.get("DOR_UC") or "").strip()
    if not (dor >= "050" and dor < "070"):
        return None
    if _non_market_owner(props.get("OWN_NAME")):
        return None
    public = str(props.get("PUBLIC_LND") or "").strip().upper()
    if public in {"Y", "YES", "1", "T", "TRUE"}:
        return None
    preferred = _fnum(props.get("Acres"))
    if preferred is None:
        sqft = _fnum(props.get("LND_SQFOOT"))
        preferred = (sqft / 43560.0) if sqft else None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=5.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("PARCEL_ID") or props.get("OBJECTID")
    county = _fl_county_name(props.get("CO_NO"))
    city = (props.get("PHY_CITY") or "").strip() or county
    addr1 = (props.get("PHY_ADDR1") or "").strip()
    land_val = _fnum(props.get("LND_VAL"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"fl_ag:{pid}",
        "title": f"Florida ag · {acreage:.1f} ac · {county}",
        "description": (
            f"Florida statewide agricultural parcel (DOR {dor}). "
            f"County={county}. Owner={props.get('OWN_NAME')}. Land value=${land_val}. "
            "Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": float(land_val) if land_val and land_val > 0 else None,
        "acreage": acreage,
        "state": "FL",
        "county": county,
        "apn": str(pid) if pid else None,
        "address": f"{addr1}, {city}, FL".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": None,
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
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
        "Fort Lauderdale Surplus Property (1ac+)",
        "https://gis.fortlauderdale.gov/arcgis/rest/services/PropertyReporter/Interactive/MapServer/37/query",
        "FL",
        "Broward",
        _norm_ftl,
    ),
    # Florida acreage coverage — FTL surplus alone was only sub-acre urban lots.
    ArcgisMarketSource(
        "lake_fl_vacant",
        "Lake County FL Vacant Land (1ac+)",
        "https://gis.lakecountyfl.gov/lakegis/rest/services/OpenData/OpenData1/FeatureServer/12/query",
        "FL",
        "Lake",
        _norm_lake_fl_vacant,
        # NOTE: avoid BuildingValue predicates here — Lake's WAF 403s some NULL checks.
        where="Vacant='Yes' AND Acres>=1 AND Acres<=2500 AND LandUseCode LIKE '00%'",
        order_by="Acres DESC",
    ),
    ArcgisMarketSource(
        "pbc_fl_vacant",
        "Palm Beach County FL Vacant Land (5ac+)",
        "https://services.arcgis.com/B7X7NCOKKXditlwZ/arcgis/rest/services/Palm_Beach_County_Parcels/FeatureServer/0/query",
        "FL",
        "Palm Beach",
        _norm_pbc_fl_vacant,
        where=(
            "DOR_UC LIKE '00%' AND LND_SQFOOT>=217800 AND LND_SQFOOT<=108900000 "
            "AND TOT_LVG_AR=0"
        ),
        order_by="LND_SQFOOT DESC",
    ),
    ArcgisMarketSource(
        "collier_fl_large",
        "Collier County FL Large Parcels (5ac+)",
        "https://services2.arcgis.com/SlIq32SqARUHIhSx/arcgis/rest/services/Parcels/FeatureServer/42/query",
        "FL",
        "Collier",
        _norm_collier_fl_large,
        where="CAST(TOTALACRES AS FLOAT) >= 5 AND CAST(TOTALACRES AS FLOAT) <= 2500",
    ),
    # Statewide Florida cadastral (~970k vacant 1ac+ / ~200k ag 5ac+) — Zillow-scale land coverage.
    # Shard by OBJECTID ranges (CO_NO filters 400 on this service; plain offset stays OBJECTID-biased).
    # Do NOT orderBy Acres: this layer rejects ORDER BY and slows to failure.
    # Do NOT filter TOT_LVG_AR in SQL — the service 400s / times out; normalize drops built parcels.
    ArcgisMarketSource(
        "fl_parcels_vacant",
        "Florida Statewide Vacant Land (1ac+)",
        "https://services5.arcgis.com/GcvM6vDlR2gM4x31/arcgis/rest/services/FL_Parcels/FeatureServer/0/query",
        "FL",
        "Statewide",
        _norm_fl_parcels_vacant,
        where="Acres>=1 AND Acres<=2500 AND DOR_UC LIKE '00%'",
        page_size=1000,
        out_fields=(
            "PARCEL_ID,OBJECTID,CO_NO,DOR_UC,Acres,LND_SQFOOT,TOT_LVG_AR,"
            "OWN_NAME,PUBLIC_LND,PHY_ADDR1,PHY_CITY,LND_VAL"
        ),
        shard_by_objectid=True,
        objectid_max=10_900_000,
    ),
    ArcgisMarketSource(
        "fl_parcels_agriculture",
        "Florida Statewide Agriculture (5ac+)",
        "https://services5.arcgis.com/GcvM6vDlR2gM4x31/arcgis/rest/services/FL_Parcels/FeatureServer/0/query",
        "FL",
        "Statewide",
        _norm_fl_parcels_ag,
        where="Acres>=5 AND Acres<=2500 AND DOR_UC >= '050' AND DOR_UC < '070'",
        page_size=1000,
        out_fields=(
            "PARCEL_ID,OBJECTID,CO_NO,DOR_UC,Acres,LND_SQFOOT,TOT_LVG_AR,"
            "OWN_NAME,PUBLIC_LND,PHY_ADDR1,PHY_CITY,LND_VAL"
        ),
        shard_by_objectid=True,
        objectid_max=10_900_000,
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
        "Mahoning County OH Land Bank Properties",
        # Layer 4 = county land-bank held (layer 0 geojson+ACRES filter was unreliable)
        "https://gisapp.mahoningcountyoh.gov/arcgis/rest/services/LANDBANK_DELINQUENT_PROPERTIES/MapServer/4/query",
        "OH",
        "Mahoning",
        _norm_mahoning,
        where="ACRES>=0.2",
    ),
    ArcgisMarketSource(
        "toledo_oh_forsale",
        "Toledo OH For-Sale / Land Bank",
        "https://gis.toledo.oh.gov/arcgis/rest/services/Public/For_Sale_Data/MapServer/0/query",
        "OH",
        "Lucas",
        _norm_toledo_forsale,
    ),
    ArcgisMarketSource(
        "gadsden_al_landbank",
        "Gadsden AL Land Bank",
        "https://coggis.cityofgadsden.com/arcgis/rest/services/Hosted/Land_Bank_Parcels_Public/FeatureServer/0/query",
        "AL",
        "Etowah",
        _norm_gadsden_lb,
        where="acres>=0.15",
    ),
    ArcgisMarketSource(
        "hartford_ct_surplus",
        "Hartford CT Surplus / Land Bank",
        "https://gis.hartford.gov/arcgis/rest/services/DDSManagedProperties/MapServer/0/query",
        "CT",
        "Hartford",
        _norm_hartford_surplus,
        where="PROPERTY_PLAN IN ('Surplus Property','Possible Land Bank')",
    ),
    ArcgisMarketSource(
        "baltimore_md_taxsale",
        "Baltimore City MD Tax Sale 2025",
        "https://egis.baltimorecity.gov/egis/rest/services/Housing/Tax_Sale_2025/FeatureServer/0/query",
        "MD",
        "Baltimore City",
        _norm_baltimore_taxsale,
    ),
    ArcgisMarketSource(
        "ramsey_mn_forfeit",
        "Ramsey County MN Tax Forfeit",
        "https://maps.co.ramsey.mn.us/arcgis/rest/services/PRR/TaxForfeitLand_PublicData/MapServer/0/query",
        "MN",
        "Ramsey",
        _norm_ramsey_forfeit,
    ),
    ArcgisMarketSource(
        "dakota_mn_forfeit",
        "Dakota County MN Tax Forfeit",
        "http://gis2.co.dakota.mn.us/arcgis/rest/services/AGOL/DC_OL_TaxForfeit/MapServer/0/query",
        "MN",
        "Dakota",
        _norm_dakota_forfeit,
        where="TOTAL_ACRES>=0.25",
    ),
    ArcgisMarketSource(
        "kcmo_mo_surplus",
        "Kansas City MO Land Bank",
        "https://mapd.kcmo.org/kcgis/rest/services/DataLayers/MapServer/12/query",
        "MO",
        "Jackson",
        _norm_kc_landbank,
    ),
    ArcgisMarketSource(
        "stl_mo_lra_surplus",
        "St. Louis MO LRA / LCRA",
        "https://maps8.stlouis-mo.gov/arcgis/rest/services/SLDC/LRA_and_LCRA_Properties/MapServer/0/query",
        "MO",
        "St. Louis City",
        _norm_stl_lra,
        where="Acres>=0.15",
    ),
    ArcgisMarketSource(
        "lancaster_ne_tax",
        "Lancaster County NE Tax Sales",
        "https://gis.lincoln.ne.gov/hosted/rest/services/Hosted/Lancaster_NE_Tax_Sales_2017_to_2024/FeatureServer/0/query",
        "NE",
        "Lancaster",
        _norm_lancaster_taxsale,
    ),
    ArcgisMarketSource(
        "cochise_az_tax",
        "Cochise County AZ Tax Lien Parcels",
        "https://services6.arcgis.com/Yxem0VOcqSy8T6TE/arcgis/rest/services/Cad_Parcel_TaxLien2025/FeatureServer/0/query",
        "AZ",
        "Cochise",
        _norm_cochise,
    ),
    ArcgisMarketSource(
        "dekalb_ga_tax",
        "DeKalb County GA Delinquent Parcels",
        "https://dcgis.dekalbcountyga.gov/hosted/rest/services/Delinquent_Parcels/MapServer/0/query",
        "GA",
        "DeKalb",
        _norm_dekalb,
    ),
    ArcgisMarketSource(
        "allegheny_pa_parcels",
        "Allegheny County PA Parcels (2ac+)",
        "https://gisdata.alleghenycounty.us/arcgis/rest/services/EGIS/Web_Parcels/MapServer/0/query",
        "PA",
        "Allegheny",
        _norm_allegheny,
    ),
    ArcgisMarketSource(
        "dallas_tx_vacant",
        "Dallas CAD Vacant Tracts",
        "https://services2.arcgis.com/rwnOSbfKSwyTBcwN/arcgis/rest/services/DallasTaxParcels/FeatureServer/0/query",
        "TX",
        "Dallas",
        _norm_dallas_vacant,
        where="SPTBCODE LIKE 'C%' AND AREA_FEET > 20000",
    ),
    ArcgisMarketSource(
        "bexar_tx_vacant",
        "Bexar County TX Vacant Land (2ac+)",
        "https://maps.bexar.org/arcgis/rest/services/Parcels/MapServer/0/query",
        "TX",
        "Bexar",
        _norm_bexar_vacant,
        where="Houses='0' AND Acres>=2",
    ),
    ArcgisMarketSource(
        "harris_tx_vacant",
        "Harris County TX Vacant Land (1ac+)",
        "https://www.gis.hctx.net/arcgis/rest/services/HCAD/Parcels/MapServer/0/query",
        "TX",
        "Harris",
        _norm_harris_tx_vacant,
        where="impr_value=0 AND acreage_1>=1 AND acreage_1<=2500 AND land_value>0",
        page_size=1000,
        out_fields=(
            "OBJECTID,HCAD_NUM,acct_num,Acreage,acreage_1,StatedArea,impr_value,bld_value,"
            "land_value,owner_name_1,site_str_num,site_str_pfx,site_str_name,site_str_sfx,"
            "site_city,site_county,state_class,land_use,total_market_val"
        ),
    ),
    ArcgisMarketSource(
        "king_wa_vacant",
        "King County WA Vacant Land",
        "https://gismaps.kingcounty.gov/arcgis/rest/services/Property/KingCo_PropertyInfo/MapServer/0/query",
        "WA",
        "King",
        _norm_king_vacant,
        where="PREUSE_DESC LIKE '%Vacant%' AND KCA_ACRES >= 1",
    ),
    ArcgisMarketSource(
        "nashville_tn_vacant",
        "Davidson County TN Vacant Land",
        "https://maps.nashville.gov/arcgis/rest/services/Cadastral/Parcels/MapServer/0/query",
        "TN",
        "Davidson",
        _norm_nashville_vacant,
        where="LUDesc LIKE '%Vacant%' AND Acres>=1",
    ),
    ArcgisMarketSource(
        "detroit_mi_dlba",
        "Detroit Land Bank For-Sale Inventory",
        "https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/DLBA_Owned_Properties/FeatureServer/0/query",
        "MI",
        "Wayne",
        _norm_dlba,
    ),
    ArcgisMarketSource(
        "utah_tax_sale",
        "Utah Tax Sale Parcels",
        "https://services6.arcgis.com/yVGfJlcJzFU5V5RT/arcgis/rest/services/TaxSaleParcels2025/FeatureServer/0/query",
        "UT",
        "Beaver",
        _norm_utah_taxsale,
    ),
    ArcgisMarketSource(
        "whiteside_il_foreclosure",
        "Whiteside County IL Tax Foreclosures",
        "https://services.arcgis.com/l0M0OC6J9QAHCiGx/arcgis/rest/services/Tax_Parcel_Foreclosures_Only/FeatureServer/0/query",
        "IL",
        "Whiteside",
        _norm_whiteside_fc,
    ),
    ArcgisMarketSource(
        "fairfax_va_large",
        "Fairfax County VA Large Parcels (3ac+)",
        "https://www.fairfaxcounty.gov/mercator/rest/services/OpenData/OpenData_A9/MapServer/0/query",
        "VA",
        "Fairfax",
        _norm_fairfax_large,
        where="SHAPE.STArea() >= 130680",
    ),
    ArcgisMarketSource(
        "nj_mod4_vacant",
        "New Jersey MOD-IV Vacant Land (1ac+)",
        "https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0/query",
        "NJ",
        "Statewide",
        _norm_nj_mod4_vacant,
        where="PROP_CLASS='1' AND CALC_ACRE>=1 AND IMPRVT_VAL=0",
        page_size=1000,
        shard_by_objectid=True,
        objectid_max=4_000_000,
    ),
    ArcgisMarketSource(
        "nj_mod4_farmland",
        "New Jersey MOD-IV Farmland (10ac+)",
        "https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0/query",
        "NJ",
        "Statewide",
        _norm_nj_mod4_farm,
        where="PROP_CLASS='3B' AND CALC_ACRE>=10",
        page_size=1000,
        shard_by_objectid=True,
        objectid_max=4_000_000,
    ),
    # Statewide cadastral screens — FL/NJ/NY/MA/AR here; NC/NE/WA/WI/UT/IN/VT/CT appended
    # from statewide_inventory.py. Remaining gaps stay on county tax-sale/surplus feeds until
    # a clean public vacant class filter exists (DE/HI/IA/KY/LA/ME/MS/ND/NH/OK/RI/SC/SD/WV/…).
    ArcgisMarketSource(
        "ny_orpts_vacant",
        "New York ORPTS Vacant Land (1ac+)",
        "https://gisservices.its.ny.gov/arcgis/rest/services/NYS_Tax_Parcels_Public/MapServer/1/query",
        "NY",
        "Statewide",
        _norm_ny_orpts_vacant,
        where=(
            "PROP_CLASS >= 300 AND PROP_CLASS < 400 AND PROP_CLASS <> 315 "
            "AND CALC_ACRES >= 1 AND CALC_ACRES <= 2500 AND OWNER_TYPE='8'"
        ),
        page_size=1000,
        shard_by_objectid=True,
        objectid_max=5_000_000,
    ),
    ArcgisMarketSource(
        "ny_orpts_agriculture",
        "New York ORPTS Agriculture (10ac+)",
        "https://gisservices.its.ny.gov/arcgis/rest/services/NYS_Tax_Parcels_Public/MapServer/1/query",
        "NY",
        "Statewide",
        _norm_ny_orpts_ag,
        where=(
            "PROP_CLASS >= 100 AND PROP_CLASS < 200 "
            "AND CALC_ACRES >= 10 AND CALC_ACRES <= 2500 AND OWNER_TYPE='8'"
        ),
        page_size=1000,
        shard_by_objectid=True,
        objectid_max=5_000_000,
    ),
    ArcgisMarketSource(
        "ar_geostor_vacant",
        "Arkansas GeoStor Unimproved AV (5ac+)",
        "https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/FeatureServer/6/query",
        "AR",
        "Statewide",
        _norm_ar_geostor_vacant,
        where="impvalue=0 AND taxarea>=5 AND taxarea<=2500 AND landvalue>0 AND parceltype='AV'",
        page_size=1000,
        shard_by_objectid=True,
        objectid_max=3_000_000,
    ),
    ArcgisMarketSource(
        "ma_massgis_vacant",
        "Massachusetts MassGIS Vacant Land (1ac+)",
        "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0/query",
        "MA",
        "Statewide",
        _norm_ma_massgis_vacant,
        where=(
            "BLDG_VAL=0 AND LOT_UNITS='Acres' AND LOT_SIZE>=1 AND LOT_SIZE<=2500 "
            "AND USE_CODE IN ('130','131','132','201','202','390','391','392','393')"
        ),
        page_size=1000,
        shard_by_objectid=True,
        objectid_max=3_000_000,
    ),
    ArcgisMarketSource(
        "ma_massgis_chapter61",
        "Massachusetts MassGIS Chapter 61/61A (10ac+)",
        "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0/query",
        "MA",
        "Statewide",
        _norm_ma_massgis_chapter61,
        where=(
            "BLDG_VAL=0 AND LOT_UNITS='Acres' AND LOT_SIZE>=10 AND LOT_SIZE<=2500 "
            "AND USE_CODE IN ('601','602','713','714','717','718')"
        ),
        page_size=1000,
        shard_by_objectid=True,
        objectid_max=3_000_000,
    ),
]

# Merge additional verified statewide vacant/ag screens (NC/NE/WA/WI/UT/IN/VT/CT…).
# Lazy import avoids circular init when extras import ArcgisMarketSource helpers.
def _extend_statewide_sources() -> None:
    from landsignal.providers.free_land_feeds import build_sources as _build_free_land
    from landsignal.providers.statewide_inventory import SOURCES as _STATEWIDE_EXTRA_SOURCES
    from landsignal.providers.statewide_inventory_extra import SOURCES as _STATEWIDE_COVERAGE_SOURCES

    SOURCES.extend(_STATEWIDE_EXTRA_SOURCES)
    SOURCES.extend(_STATEWIDE_COVERAGE_SOURCES)
    SOURCES.extend(_build_free_land())


_extend_statewide_sources()


async def _arcgis_get_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    *,
    source_id: str,
    attempts: int = 3,
) -> dict[str, Any] | None:
    """GET ArcGIS JSON with retries. Never raises — returns None on hard failure."""
    last_err: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            resp = await client.get(url, params=params, headers=_ARCGIS_HEADERS)
            if resp.status_code in _HTTP_RETRY_STATUSES and attempt + 1 < attempts:
                await asyncio.sleep(0.35 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                log.warning(
                    "public_tax_http_error",
                    source=source_id,
                    status=resp.status_code,
                    attempt=attempt + 1,
                )
                return None
            try:
                data = resp.json()
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.35 * (attempt + 1))
                    continue
                return None
            if isinstance(data, dict) and data.get("error"):
                # Invalid outFields / where often 200+error — caller may retry with *.
                return data
            return data if isinstance(data, dict) else None
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPError) as exc:
            last_err = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(0.45 * (attempt + 1))
                continue
            log.warning(
                "public_tax_transport_failed",
                source=source_id,
                error=str(exc)[:200],
            )
            return None
    if last_err:
        log.warning("public_tax_get_exhausted", source=source_id, error=str(last_err)[:200])
    return None


async def _fetch_arcgis_pages(
    client: httpx.AsyncClient,
    src: ArcgisMarketSource,
    *,
    target: int,
    page_size: int | None = None,
    start_offset: int = 0,
    where: str | None = None,
) -> list[dict]:
    """Page through an ArcGIS layer until we have `target` validated rows.

    Soft-fails on host errors so one bad county cannot fail nationwide discover.
    """
    out: list[dict] = []
    if target <= 0:
        return out
    offset = max(0, start_offset)
    page_size = max(1, int(page_size or src.page_size or 200))
    where_clause = where or src.where
    out_fields = (getattr(src, "out_fields", None) or "*").strip() or "*"
    # Over-page: statewide vacant rows often fail normalize, so raw ≫ normalized.
    max_pages = max(2, min(40, (max(1, target) // page_size) * 5 + 3))
    consecutive_failures = 0
    for _ in range(max_pages):
        if len(out) >= target:
            break
        params = {
            "where": where_clause,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": 4326,
            "resultRecordCount": page_size,
            "resultOffset": offset,
            "f": "geojson",
        }
        if getattr(src, "order_by", None):
            params["orderByFields"] = src.order_by
        data = await _arcgis_get_json(client, src.url, params, source_id=src.source_id)
        if data is None:
            consecutive_failures += 1
            if consecutive_failures >= 2:
                break
            continue
        if data.get("error"):
            err = data.get("error") or {}
            details = " ".join(str(x) for x in (err.get("details") or []))
            # Common: invalid outFields — retry once with *.
            if out_fields != "*" and "outFields" in details:
                log.warning(
                    "public_tax_outfields_fallback",
                    source=src.source_id,
                    out_fields=out_fields[:120],
                )
                out_fields = "*"
                consecutive_failures = 0
                continue
            log.warning(
                "public_tax_arcgis_error",
                source=src.source_id,
                error=err,
                where=where_clause[:160],
            )
            consecutive_failures += 1
            if consecutive_failures >= 2:
                break
            continue
        consecutive_failures = 0
        feats = data.get("features") or []
        if not feats:
            break
        for feat in feats:
            try:
                row = src.normalize(feat)
            except Exception as exc:  # noqa: BLE001
                log.warning("public_tax_normalize_failed", source=src.source_id, error=str(exc)[:160])
                continue
            valid = _validate_inventory_row(row)
            if valid:
                out.append(valid)
                if len(out) >= target:
                    break
        if len(feats) < page_size:
            break
        offset += len(feats)
    return out


async def _fetch_arcgis_value_shards(
    client: httpx.AsyncClient,
    src: ArcgisMarketSource,
    *,
    target: int,
    start_offset: int = 0,
) -> list[dict]:
    """Shard a layer by discrete field values (county name / FIPS) for geographic breadth."""
    values = [str(v) for v in (getattr(src, "shard_values", None) or []) if v]
    field = getattr(src, "shard_field", None)
    if not values or not field or target <= 0:
        return await _fetch_arcgis_pages(
            client, src, target=target, start_offset=start_offset
        )
    per_value = max(15, (target // len(values)) + 10)
    sem = asyncio.Semaphore(6)

    async def one(val: str) -> list[dict]:
        # Quote strings; leave bare tokens that look numeric.
        literal = val if val.replace(".", "", 1).isdigit() else f"'{val.replace(chr(39), chr(39)+chr(39))}'"
        where = f"({src.where}) AND {field}={literal}"
        async with sem:
            for attempt in range(2):
                try:
                    return await _fetch_arcgis_pages(
                        client,
                        src,
                        target=per_value,
                        start_offset=start_offset,
                        where=where,
                    )
                except Exception as exc:  # noqa: BLE001
                    if attempt == 0:
                        await asyncio.sleep(0.4)
                        continue
                    log.warning(
                        "public_tax_value_shard_failed",
                        source=src.source_id,
                        field=field,
                        value=val,
                        error=str(exc)[:200],
                    )
                    return []
        return []

    batches = await asyncio.gather(*[one(v) for v in values])
    queues = [list(batch) for batch in batches if batch]
    out: list[dict] = []
    while queues and len(out) < target:
        nxt: list[list[dict]] = []
        for q in queues:
            if not q:
                continue
            out.append(q.pop(0))
            if q:
                nxt.append(q)
            if len(out) >= target:
                break
        queues = nxt
    if out:
        return out[:target]
    # Shard predicates failed everywhere — degrade to plain paging so inventory still fills.
    log.warning("public_tax_value_shard_empty_fallback", source=src.source_id, field=field)
    return await _fetch_arcgis_pages(
        client, src, target=target, start_offset=start_offset
    )


async def _fetch_arcgis_objectid_shards(
    client: httpx.AsyncClient,
    src: ArcgisMarketSource,
    *,
    target: int,
    start_offset: int = 0,
) -> list[dict]:
    """Pull a statewide layer via OBJECTID ranges for breadth + Zillow-scale volume.

    Plain resultOffset on ~1M vacant rows is slow/biased; CO_NO predicates 400 on FL_Parcels.
    OBJECTID windows are fast and fan out across the cadastral.
    """
    if target <= 0:
        return []
    max_oid = int(getattr(src, "objectid_max", None) or 11_000_000)
    shard_count = 56
    shard_span = max(80_000, (max_oid // shard_count) + 1)
    ranges = [(lo, min(lo + shard_span, max_oid + 1)) for lo in range(1, max_oid + 1, shard_span)]
    per_shard = max(50, (target // max(1, len(ranges))) + 40)
    # Keep concurrency modest — this ArcGIS host 504s when hammered.
    sem = asyncio.Semaphore(10)

    async def one(lo: int, hi: int) -> list[dict]:
        where = f"({src.where}) AND OBJECTID>={int(lo)} AND OBJECTID<{int(hi)}"
        async with sem:
            for attempt in range(2):
                try:
                    return await _fetch_arcgis_pages(
                        client,
                        src,
                        target=per_shard,
                        start_offset=start_offset,
                        where=where,
                    )
                except Exception as exc:  # noqa: BLE001
                    if attempt == 0:
                        await asyncio.sleep(0.6)
                        continue
                    log.warning(
                        "public_tax_oid_shard_failed",
                        source=src.source_id,
                        lo=lo,
                        hi=hi,
                        error=str(exc)[:240],
                    )
                    return []
        return []

    batches = await asyncio.gather(*[one(lo, hi) for lo, hi in ranges])
    queues = [list(batch) for batch in batches if batch]
    out: list[dict] = []
    while queues and len(out) < target:
        nxt: list[list[dict]] = []
        for q in queues:
            if not q:
                continue
            out.append(q.pop(0))
            if q:
                nxt.append(q)
            if len(out) >= target:
                break
        queues = nxt
    if out:
        return out[:target]
    log.warning("public_tax_oid_shard_empty_fallback", source=src.source_id)
    return await _fetch_arcgis_pages(
        client, src, target=target, start_offset=start_offset
    )


class PublicTaxSaleProvider(ListingProvider):
    """Free county tax-sale / for-sale GIS feeds ≈ opportunistic MLS/auction inventory."""

    id = "public_tax_sale"
    name = "Public Tax-Sale / County For-Sale GIS"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def search_listings(self, query: dict[str, Any]) -> ProviderResult[list[dict]]:
        """Pull public GIS inventory. Always returns ok=True — soft-fails per source/state."""
        from collections import defaultdict

        limit = max(1, int(query.get("limit") or 2000))
        errors: list[str] = []
        try:
            # Include land-bank / LRA feeds in the tax inventory path so MO/VA-style
            # states get the same large equal-state budget (not the tiny surplus cap).
            tax_sources = [
                s
                for s in SOURCES
                if "fairfax" not in s.source_id
                and (
                    "surplus" not in s.source_id
                    or "landbank" in s.source_id
                    or "land_bank" in s.source_id
                    or "lra" in s.source_id
                )
            ]
            prefer = {str(s).upper() for s in (query.get("states") or []) if s}
            if prefer:
                # Honor the filter even when empty — never silently widen to all states.
                tax_sources = [s for s in tax_sources if s.state.upper() in prefer]
            if not tax_sources:
                return ProviderResult(
                    True,
                    ProviderStatus.CONFIGURED,
                    [],
                    error="No sources for request" if prefer else None,
                )

            by_state_sources: dict[str, list[ArcgisMarketSource]] = defaultdict(list)
            for src in tax_sources:
                by_state_sources[src.state.upper()].append(src)
            state_keys = sorted(by_state_sources.keys())
            n_states = max(1, len(state_keys))
            # Every state gets a large floor — FL is not special-cased for nationwide pulls.
            min_per_state = max(1500, int(query.get("min_per_state") or 5000))
            per_state = max(min_per_state, (limit + n_states - 1) // n_states)
            if prefer and n_states <= 3:
                # Targeted few-state discovers may still consume nearly the full budget.
                per_state = max(
                    per_state,
                    min(limit, max(8000, (limit * 95) // 100 // n_states)),
                )
            start_offset = max(0, int(query.get("offset") or 0))
            out: list[dict] = []
            timeout = httpx.Timeout(connect=12.0, read=55.0, write=30.0, pool=30.0)
            # More parallel state fetches so nationwide equal pulls finish sooner.
            state_sem = asyncio.Semaphore(12)

            async with httpx.AsyncClient(
                timeout=timeout, headers=_ARCGIS_HEADERS, verify=False
            ) as client:

                async def fetch_state(st: str) -> list[dict]:
                    async with state_sem:
                        try:
                            return await asyncio.wait_for(
                                _fetch_state_inventory(
                                    client,
                                    by_state_sources[st],
                                    per_state=per_state,
                                    errors=errors,
                                    start_offset=start_offset,
                                ),
                                timeout=_STATE_FETCH_TIMEOUT_S,
                            )
                        except asyncio.TimeoutError:
                            errors.append(f"{st}: state fetch timed out")
                            log.warning("public_tax_state_timeout", state=st)
                            return []
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"{st}: {exc}")
                            log.warning("public_tax_state_failed", state=st, error=str(exc)[:200])
                            return []

                results = await asyncio.gather(*[fetch_state(st) for st in state_keys])
                for batch in results:
                    out.extend(batch)

            out = _dedupe_inventory_rows(
                [r for r in (_validate_inventory_row(x) for x in out) if r]
            )

            by_state_feed: dict[str, dict[str, list[dict]]] = defaultdict(
                lambda: defaultdict(list)
            )
            for row in out:
                st = (row.get("state") or "??").upper()
                feed = (row.get("external_id") or "").split(":")[0] or st
                by_state_feed[st][feed].append(row)
            for st in by_state_feed:
                for feed in by_state_feed[st]:
                    by_state_feed[st][feed].sort(
                        key=lambda r: (
                            0 if r.get("asking_price_usd") is not None else 1,
                            -(r.get("acreage") or 0),
                        )
                    )
            # Equal-state quota first so large states (e.g. FL) cannot crowd out others.
            state_quota = max(1, min(per_state, (limit + n_states - 1) // n_states))
            taken: dict[str, int] = {st: 0 for st in state_keys}
            diversified: list[dict] = []

            def _take_round(*, respect_quota: bool) -> bool:
                """Return True if any row was taken this pass."""
                progressed = False
                for st in list(by_state_feed.keys()):
                    if respect_quota and taken.get(st, 0) >= state_quota:
                        continue
                    if len(diversified) >= limit:
                        break
                    feeds = by_state_feed.get(st) or {}
                    if not feeds:
                        by_state_feed.pop(st, None)
                        continue
                    for feed in list(feeds.keys()):
                        if not feeds.get(feed):
                            feeds.pop(feed, None)
                            continue
                        diversified.append(feeds[feed].pop(0))
                        taken[st] = taken.get(st, 0) + 1
                        progressed = True
                        if not feeds.get(feed):
                            feeds.pop(feed, None)
                        break
                    if not feeds:
                        by_state_feed.pop(st, None)
                return progressed

            while len(diversified) < limit and by_state_feed and _take_round(respect_quota=True):
                pass
            while len(diversified) < limit and by_state_feed and _take_round(respect_quota=False):
                pass
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                diversified,
                error="; ".join(errors[:12]) if errors else None,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("public_tax_search_fatal", error=str(exc))
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                [],
                error=f"soft-fail: {exc}",
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


async def _fetch_state_inventory(
    client: httpx.AsyncClient,
    srcs: list[ArcgisMarketSource],
    *,
    per_state: int,
    errors: list[str],
    start_offset: int = 0,
) -> list[dict]:
    statewide = [s for s in srcs if (s.county or "").lower() == "statewide"]
    county = [s for s in srcs if s not in statewide]
    if statewide:
        pool = min(per_state, max(200, (per_state * 9) // 10))
        county_budget = max(0, per_state - pool)
        per_county = max(40, county_budget // max(1, len(county))) if county else 0
        batches = await asyncio_gather_sources(
            client,
            srcs,
            per_county,
            errors,
            start_offset=start_offset,
            statewide_target=max(100, pool // max(1, len(statewide))),
            statewide_pool=pool,
        )
    else:
        per_src = max(40, per_state // max(1, len(srcs)))
        batches = await asyncio_gather_sources(
            client,
            srcs,
            per_src,
            errors,
            start_offset=start_offset,
        )
    rows: list[dict] = []
    for batch in batches:
        rows.extend(batch)
    return rows


async def asyncio_gather_sources(
    client: httpx.AsyncClient,
    sources: list[ArcgisMarketSource],
    per_source: int,
    errors: list[str],
    start_offset: int = 0,
    *,
    statewide_target: int | None = None,
    statewide_pool: int = 0,
) -> list[list[dict]]:
    statewide_sources = [s for s in sources if (s.county or "").lower() == "statewide"]
    vacant_statewide = [s for s in statewide_sources if "vacant" in s.source_id]
    other_statewide = [s for s in statewide_sources if s not in vacant_statewide]

    async def one(src: ArcgisMarketSource) -> list[dict]:
        target = max(0, int(per_source))
        if statewide_pool and (src.county or "").lower() == "statewide":
            if src in vacant_statewide:
                share = (0.75 if other_statewide else 1.0) / max(1, len(vacant_statewide))
                target = max(statewide_target or per_source, int(statewide_pool * share))
            elif src in other_statewide:
                share = 0.25 / max(1, len(other_statewide))
                target = max(statewide_target or per_source, int(statewide_pool * share))
            else:
                target = max(per_source, statewide_target or per_source)
        elif statewide_target and (src.county or "").lower() == "statewide":
            target = max(per_source, statewide_target)

        async def _pull() -> list[dict]:
            if getattr(src, "shard_field", None) and getattr(src, "shard_values", None):
                return await _fetch_arcgis_value_shards(
                    client, src, target=target, start_offset=start_offset
                )
            if getattr(src, "shard_by_objectid", False):
                return await _fetch_arcgis_objectid_shards(
                    client, src, target=target, start_offset=start_offset
                )
            return await _fetch_arcgis_pages(
                client, src, target=target, start_offset=start_offset
            )

        # OID / value shards need a longer wall clock than single-page county feeds.
        pull_timeout = _SOURCE_FETCH_TIMEOUT_S
        if getattr(src, "shard_by_objectid", False) or getattr(src, "shard_field", None):
            pull_timeout = max(pull_timeout, 360.0)
        try:
            return await asyncio.wait_for(_pull(), timeout=pull_timeout)
        except asyncio.TimeoutError:
            errors.append(f"{src.source_id}: timed out")
            log.warning("public_tax_source_timeout", source=src.source_id)
            # Last-chance plain page — often recovers partial inventory quickly.
            try:
                return await asyncio.wait_for(
                    _fetch_arcgis_pages(
                        client, src, target=min(target, 800), start_offset=start_offset
                    ),
                    timeout=45.0,
                )
            except Exception:  # noqa: BLE001
                return []
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src.source_id}: {exc}")
            log.warning("public_tax_source_failed", source=src.source_id, error=str(exc))
            return []

    if not sources:
        return []
    return list(await asyncio.gather(*[one(s) for s in sources]))


class PublicSurplusProvider(ListingProvider):
    """Municipal/county surplus property ≈ CRE disposal / land-bank inventory."""

    id = "public_surplus"
    name = "Public Surplus / Land-Bank GIS"

    def status(self) -> ProviderStatus:
        return ProviderStatus.CONFIGURED

    async def search_listings(self, query: dict[str, Any]) -> ProviderResult[list[dict]]:
        limit = max(1, int(query.get("limit") or 200))
        errors: list[str] = []
        try:
            surplus_sources = [
                s for s in SOURCES if "surplus" in s.source_id or "fairfax" in s.source_id
            ]
            prefer = {str(s).upper() for s in (query.get("states") or []) if s}
            if prefer:
                surplus_sources = [s for s in surplus_sources if s.state.upper() in prefer]
            if not surplus_sources:
                return ProviderResult(True, ProviderStatus.CONFIGURED, [])
            per_source = max(50, limit // max(1, len(surplus_sources)))
            out: list[dict] = []
            timeout = httpx.Timeout(connect=12.0, read=45.0, write=20.0, pool=20.0)
            async with httpx.AsyncClient(
                timeout=timeout, headers=_ARCGIS_HEADERS, verify=False
            ) as client:
                batches = await asyncio_gather_sources(
                    client, surplus_sources, per_source, errors
                )
                for batch in batches:
                    out.extend(batch)
            out = _dedupe_inventory_rows(
                [r for r in (_validate_inventory_row(x) for x in out) if r]
            )
            out.sort(key=lambda r: -(r.get("acreage") or 0))
            return ProviderResult(
                True,
                ProviderStatus.CONFIGURED,
                out[:limit],
                error="; ".join(errors[:12]) if errors else None,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("public_surplus_search_fatal", error=str(exc))
            return ProviderResult(True, ProviderStatus.CONFIGURED, [], error=f"soft-fail: {exc}")

    async def get_listing(self, external_id: str) -> ProviderResult[dict]:
        res = await self.search_listings({"limit": 200})
        for row in res.data or []:
            if row.get("external_id") == external_id:
                return ProviderResult(True, ProviderStatus.CONFIGURED, row)
        return ProviderResult(False, ProviderStatus.CONFIGURED, error="Not found")

    def normalize_listing(self, raw: dict) -> dict:
        return raw
