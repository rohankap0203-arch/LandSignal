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
        order_by: str | None = None,
    ):
        self.source_id = source_id
        self.name = name
        self.url = url
        self.state = state
        self.county = county
        self.normalize = normalize
        self.where = where
        self.order_by = order_by


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
    acreage = _nj_acres(props, geom_acres, min_ac=5.0)
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
        "asking_price_usd": None,
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
        "raw": props,
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
        "asking_price_usd": None,
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
        "raw": props,
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
        min_ac=5.0,
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
        "asking_price_usd": None,
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
        "raw": props,
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
        "asking_price_usd": None,
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
        "raw": props,
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
        "asking_price_usd": None,
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
        "raw": props,
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
    acreage = _bounded_acres(preferred, geom_acres, min_ac=5.0)
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
        "asking_price_usd": None,
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
        "raw": props,
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
        "asking_price_usd": None,
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
    props = raw.get("properties") or {}
    area_ft = props.get("AREA_FEET") or props.get("Shape__Area")
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acreage is None and area_ft:
        acreage = float(area_ft) / 43560.0
    if acreage is None or acreage < 0.5:
        return None
    pid = props.get("ACCT") or props.get("GIS_ACCT") or props.get("OBJECTID")
    use = props.get("PROP_CL") or "Vacant tract"
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"dallas:{pid}",
        "title": f"Dallas CAD vacant · {acreage:.2f} ac · {use}",
        "description": (
            f"Dallas County, TX appraisal vacant/land tract (public CAD GIS). "
            f"Class={use}. SPTB={props.get('SPTBCODE')}. "
            "Public map screen — not a confirmed tax sale; confirm owner / sale status before chasing."
        ),
        "asking_price_usd": None,
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
        "raw": props,
        "is_demo": False,
    }


def _norm_bexar_vacant(raw: dict) -> dict | None:
    props = raw.get("properties") or {}
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
    land_val = props.get("LandVal")
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"bexar:{pid}",
        "title": f"Bexar TX vacant land · {float(acreage):.2f} ac · {props.get('Situs') or pid}",
        "description": (
            f"Bexar County, TX (San Antonio) vacant/unimproved parcel from public CAD GIS. "
            f"Land value mark=${land_val}. Owner mark={props.get('Owner') or 'n/a'}. "
            "Public map screen — not a dedicated tax-sale feed."
        ),
        # LandVal is assessed mark, not an auction opener — don't fake a bid price
        "asking_price_usd": None,
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
        "raw": props,
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
    land = props.get("LandAppr")
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
        # LandAppr is assessed mark, not a list/bid price
        "asking_price_usd": None,
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
        "raw": props,
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
        "New Jersey MOD-IV Vacant Land (5ac+)",
        "https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0/query",
        "NJ",
        "Statewide",
        _norm_nj_mod4_vacant,
        where="PROP_CLASS='1' AND CALC_ACRE>=5 AND IMPRVT_VAL=0",
        order_by="CALC_ACRE DESC",
    ),
    ArcgisMarketSource(
        "nj_mod4_farmland",
        "New Jersey MOD-IV Farmland (10ac+)",
        "https://maps.nj.gov/arcgis/rest/services/Framework/Cadastral/MapServer/0/query",
        "NJ",
        "Statewide",
        _norm_nj_mod4_farm,
        where="PROP_CLASS='3B' AND CALC_ACRE>=10",
        order_by="CALC_ACRE DESC",
    ),
    # Statewide cadastral screens — only states with verified official vacant/ag attributes.
    # Skipped for now (no equally clean public vacant filter): DE, HI, IA, KY, LA, ME, MS,
    # ND, NH, OK, RI, SC, SD, VT, WV, DC (county-only / centroids-only / stale / no class codes).
    ArcgisMarketSource(
        "ny_orpts_vacant",
        "New York ORPTS Vacant Land (5ac+)",
        "https://gisservices.its.ny.gov/arcgis/rest/services/NYS_Tax_Parcels_Public/MapServer/1/query",
        "NY",
        "Statewide",
        _norm_ny_orpts_vacant,
        where=(
            "PROP_CLASS >= 300 AND PROP_CLASS < 400 AND PROP_CLASS <> 315 "
            "AND CALC_ACRES >= 5 AND CALC_ACRES <= 2500 AND OWNER_TYPE='8'"
        ),
        order_by="CALC_ACRES DESC",
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
        order_by="CALC_ACRES DESC",
    ),
    ArcgisMarketSource(
        "ar_geostor_vacant",
        "Arkansas GeoStor Unimproved AV (5ac+)",
        "https://gis.arkansas.gov/arcgis/rest/services/FEATURESERVICES/Planning_Cadastre/FeatureServer/6/query",
        "AR",
        "Statewide",
        _norm_ar_geostor_vacant,
        where="impvalue=0 AND taxarea>=5 AND taxarea<=2500 AND landvalue>0 AND parceltype='AV'",
        order_by="taxarea DESC",
    ),
    ArcgisMarketSource(
        "ma_massgis_vacant",
        "Massachusetts MassGIS Vacant Land (5ac+)",
        "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Property_Tax_Parcels/FeatureServer/0/query",
        "MA",
        "Statewide",
        _norm_ma_massgis_vacant,
        where=(
            "BLDG_VAL=0 AND LOT_UNITS='Acres' AND LOT_SIZE>=5 AND LOT_SIZE<=2500 "
            "AND USE_CODE IN ('130','131','132','201','202','390','391','392','393')"
        ),
        order_by="LOT_SIZE DESC",
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
        order_by="LOT_SIZE DESC",
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
        if getattr(src, "order_by", None):
            params["orderByFields"] = src.order_by
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
            if "surplus" not in s.source_id and "fairfax" not in s.source_id
        ]
        prefer = {str(s).upper() for s in (query.get("states") or []) if s}
        if prefer:
            # When a state filter is active, spend budget on that state's layers first
            preferred = [s for s in tax_sources if s.state.upper() in prefer]
            if preferred:
                tax_sources = preferred
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
        surplus_sources = [s for s in SOURCES if "surplus" in s.source_id or "fairfax" in s.source_id]
        prefer = {str(s).upper() for s in (query.get("states") or []) if s}
        if prefer:
            preferred = [s for s in surplus_sources if s.state.upper() in prefer]
            if preferred:
                surplus_sources = preferred
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
