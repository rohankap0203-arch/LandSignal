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
        "provider_id": "public_tax_sale",
        "external_id": f"dallas:{pid}",
        "title": f"Dallas CAD vacant · {acreage:.2f} ac · {use}",
        "description": (
            f"Dallas County, TX appraisal vacant/land tract (public CAD GIS). "
            f"Class={use}. SPTB={props.get('SPTBCODE')}. "
            "Vacant land screen — not MLS/Crexi; confirm sale status with DCAD / broker."
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
        "provider_id": "public_tax_sale",
        "external_id": f"bexar:{pid}",
        "title": f"Bexar TX vacant land · {float(acreage):.2f} ac · {props.get('Situs') or pid}",
        "description": (
            f"Bexar County, TX (San Antonio) vacant/unimproved parcel from public CAD GIS. "
            f"Land value mark=${land_val}. Owner mark={props.get('Owner') or 'n/a'}. "
            "Not a dedicated tax-sale feed — screen for land thesis only."
        ),
        "asking_price_usd": float(land_val) * 0.55 if land_val else None,
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
        "provider_id": "public_tax_sale",
        "external_id": f"kingwa:{pid}",
        "title": f"King County WA vacant · {float(acreage):.2f} ac · {use}",
        "description": (
            f"King County, WA vacant land (public property info GIS). Use={use}. "
            "Not MLS — confirm marketing status with a local broker / assessor."
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
        "provider_id": "public_tax_sale",
        "external_id": f"nash:{pid}",
        "title": f"Davidson TN vacant · {float(acreage):.2f} ac · {props.get('PropAddr') or pid}",
        "description": (
            f"Davidson County / Nashville vacant rural or vacant land (public cadastral GIS). "
            f"Use={props.get('LUDesc')}. Land appraisal mark=${land}. "
            "Public land inventory screen — not MLS."
        ),
        "asking_price_usd": float(land) * 0.65 if land else None,
        "acreage": float(acreage),
        "state": "TN",
        "county": "Davidson",
        "apn": str(pid),
        "address": f"{props.get('PropAddr') or ''}, Nashville, TN".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.nashville.gov/",
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
            if "surplus" not in s.source_id and "fairfax" not in s.source_id
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
        surplus_sources = [s for s in SOURCES if "surplus" in s.source_id or "fairfax" in s.source_id]
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
