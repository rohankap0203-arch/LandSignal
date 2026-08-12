"""Statewide vacant/ag cadastral screens (FL-style coverage for every state we can).

Cursor Cloud has no MLS / Zillow / Land.com / Regrid credentials. These adapters use
official public statewide (or near-statewide) parcel FeatureServers with vacant / ag
use-codes — the same pattern as FL_Parcels.

States still lacking a clean public vacant filter stay on county tax-sale / surplus
feeds registered in public_markets.SOURCES.
"""

from __future__ import annotations

from typing import Callable

from landsignal.providers.public_markets import (
    ArcgisMarketSource,
    _acres_from_geom,
    _bounded_acres,
    _fnum,
    _non_market_owner,
)

# Washington FIPS → county (WaTech statewide parcels use FIPS_NR).
_WA_COUNTY_FIPS = {
    "001": "Adams",
    "003": "Asotin",
    "005": "Benton",
    "007": "Chelan",
    "009": "Clallam",
    "011": "Clark",
    "013": "Columbia",
    "015": "Cowlitz",
    "017": "Douglas",
    "019": "Ferry",
    "021": "Franklin",
    "023": "Garfield",
    "025": "Grant",
    "027": "Grays Harbor",
    "029": "Island",
    "031": "Jefferson",
    "033": "King",
    "035": "Kitsap",
    "037": "Kittitas",
    "039": "Klickitat",
    "041": "Lewis",
    "043": "Lincoln",
    "045": "Mason",
    "047": "Okanogan",
    "049": "Pacific",
    "051": "Pend Oreille",
    "053": "Pierce",
    "055": "San Juan",
    "057": "Skagit",
    "059": "Skamania",
    "061": "Snohomish",
    "063": "Spokane",
    "065": "Stevens",
    "067": "Thurston",
    "069": "Wahkiakum",
    "071": "Walla Walla",
    "073": "Whatcom",
    "075": "Whitman",
    "077": "Yakima",
}


def _props(raw: dict) -> dict:
    return raw.get("properties") or raw.get("attributes") or {}


def _norm_nc_parcels_vacant(raw: dict) -> dict | None:
    """NC OneMap statewide parcels — unimproved 1ac+ (improvval=0)."""
    props = _props(raw)
    if (_fnum(props.get("improvval")) or 0) > 0:
        return None
    if _non_market_owner(props.get("ownname")):
        return None
    preferred = _fnum(props.get("gisacres")) or _fnum(props.get("recareano"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("parno") or props.get("nparno") or props.get("objectid")
    county = str(props.get("cntyname") or props.get("COUNTY") or "North Carolina").title()
    addr = (props.get("siteadd") or "").strip()
    land_val = _fnum(props.get("landval"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"nc_parcels:{pid}",
        "title": f"North Carolina vacant · {acreage:.1f} ac · {county}",
        "description": (
            f"North Carolina OneMap statewide parcel (unimproved). County={county}. "
            f"Owner={props.get('ownname')}. Land value=${land_val}. "
            "Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "NC",
        "county": county,
        "apn": str(pid) if pid else None,
        "address": f"{addr}, {county}, NC".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.nconemap.gov/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_ne_parcels_vacant(raw: dict) -> dict | None:
    """Nebraska OCIO statewide parcels — Improvements_Value=0, 5ac+."""
    props = _props(raw)
    if (_fnum(props.get("Improvements_Value")) or 0) > 0:
        return None
    land_val = _fnum(props.get("Land_Value"))
    if land_val is not None and land_val <= 0:
        return None
    preferred = _fnum(props.get("GIS_Acres")) or _fnum(props.get("Acres_Deeded"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=5.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("Parcel_ID") or props.get("State_PID") or props.get("OBJECTID")
    county = str(props.get("County_ID") or "Nebraska")
    addr = (props.get("Ph_Full_Address") or props.get("Situs_Address") or "").strip()
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"ne_parcels:{county}:{pid}",
        "title": f"Nebraska vacant · {acreage:.1f} ac · county {county}",
        "description": (
            f"Nebraska statewide parcel (OCIO / county CAMA merge). County_ID={county}. "
            f"Land value=${land_val}. Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "NE",
        "county": f"County {county}" if county.isdigit() or len(county) <= 3 else county.title(),
        "apn": str(pid) if pid else None,
        "address": f"{addr}, NE".strip(", ") if addr else f"County {county}, NE",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.nebraskamap.gov/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_wa_parcels_vacant(raw: dict) -> dict | None:
    """Washington WaTech statewide parcels — DOR land use 91–99, no building value."""
    props = _props(raw)
    try:
        lu = int(float(props.get("LANDUSE_CD")))
    except (TypeError, ValueError):
        return None
    if lu < 91 or lu > 99:
        return None
    if (_fnum(props.get("VALUE_BLDG")) or 0) > 0:
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(None, geom_acres, min_ac=1.0)
    if acreage is None or not polygon:
        return None
    fips = str(props.get("FIPS_NR") or "").zfill(3)
    county = _WA_COUNTY_FIPS.get(fips, f"County {fips}")
    pid = props.get("PARCEL_ID_NR") or props.get("ORIG_PARCEL_ID") or props.get("OBJECTID")
    addr = (props.get("SITUS_ADDRESS") or "").strip()
    city = (props.get("SITUS_CITY_NM") or county).strip()
    land_val = _fnum(props.get("VALUE_LAND"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"wa_parcels:{pid}",
        "title": f"Washington vacant · {acreage:.1f} ac · {county}",
        "description": (
            f"Washington statewide parcel (WaTech / DOR land use {lu}). County={county}. "
            f"Land value=${land_val}. Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "WA",
        "county": county,
        "apn": str(pid) if pid else None,
        "address": f"{addr}, {city}, WA".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": props.get("DATA_LINK") or "https://geo.wa.gov/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_wi_parcels_vacant(raw: dict) -> dict | None:
    """Wisconsin statewide parcels — PROPCLASS 1* vacant, 1ac+."""
    props = _props(raw)
    pclass = str(props.get("PROPCLASS") or "").strip()
    if not pclass.startswith("1"):
        return None
    if _non_market_owner(props.get("OWNERNME1")):
        return None
    preferred = _fnum(props.get("GISACRES")) or _fnum(props.get("ASSDACRES")) or _fnum(props.get("DEEDACRES"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("PARCELID") or props.get("OBJECTID")
    county = str(props.get("PARCELSRC") or props.get("COUNTY") or "Wisconsin").title()
    addr = (props.get("SITEADRESS") or props.get("PSTLADRESS") or "").strip()
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"wi_parcels:{pid}",
        "title": f"Wisconsin vacant · {acreage:.1f} ac · {county}",
        "description": (
            f"Wisconsin statewide parcel (WLIP V11+). PROPCLASS={pclass}. County={county}. "
            f"Owner={props.get('OWNERNME1')}. Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "WI",
        "county": county,
        "apn": str(pid) if pid else None,
        "address": f"{addr}, {county}, WI".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.sco.wisc.edu/parcels/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_wi_parcels_ag(raw: dict) -> dict | None:
    """Wisconsin statewide parcels — PROPCLASS 4* agricultural, 10ac+."""
    props = _props(raw)
    pclass = str(props.get("PROPCLASS") or "").strip()
    if not pclass.startswith("4"):
        return None
    if _non_market_owner(props.get("OWNERNME1")):
        return None
    preferred = _fnum(props.get("GISACRES")) or _fnum(props.get("ASSDACRES")) or _fnum(props.get("DEEDACRES"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=10.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("PARCELID") or props.get("OBJECTID")
    county = str(props.get("PARCELSRC") or props.get("COUNTY") or "Wisconsin").title()
    addr = (props.get("SITEADRESS") or props.get("PSTLADRESS") or "").strip()
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"wi_ag:{pid}",
        "title": f"Wisconsin ag · {acreage:.1f} ac · {county}",
        "description": (
            f"Wisconsin statewide agricultural parcel (WLIP). PROPCLASS={pclass}. "
            f"County={county}. Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "WI",
        "county": county,
        "apn": str(pid) if pid else None,
        "address": f"{addr}, {county}, WI".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.sco.wisc.edu/parcels/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_ut_parcels_vacant(raw: dict) -> dict | None:
    """Utah AGRC LIR parcels — PROP_CLASS Vacant, 1ac+."""
    props = _props(raw)
    if str(props.get("PROP_CLASS") or "").strip().lower() != "vacant":
        return None
    preferred = _fnum(props.get("PARCEL_ACRES"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("PARCEL_ID") or props.get("OBJECTID")
    county = str(props.get("COUNTY_NAME") or "Utah").replace(" County", "").title()
    land_val = _fnum(props.get("LAND_MKT_VALUE"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"ut_parcels:{pid}",
        "title": f"Utah vacant · {acreage:.1f} ac · {county}",
        "description": (
            f"Utah statewide LIR parcel (AGRC). County={county}. Land market value=${land_val}. "
            "Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "UT",
        "county": county,
        "apn": str(pid) if pid else None,
        "address": f"{county}, UT",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://gis.utah.gov/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_in_parcels_vacant(raw: dict) -> dict | None:
    """Indiana statewide parcel boundaries — DLGF class 100 vacant."""
    props = _props(raw)
    code = str(props.get("dlgf_prop_class_code") or "").strip()
    if not code.startswith("100"):
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    # Layer often omits assessor acres — trust geometry.
    acreage = _bounded_acres(None, geom_acres, min_ac=1.0)
    if lat is None:
        lat = _fnum(props.get("latitude"))
        lon = _fnum(props.get("longitude"))
    if acreage is None or not polygon or lat is None:
        return None
    pid = props.get("state_parcel_id") or props.get("parcel_id") or props.get("objectid")
    county = str(props.get("tax_county") or props.get("source_originator") or "Indiana")
    county = county.replace(" County", "").replace(" COUNTY", "").title()
    addr = (props.get("dlgf_prop_address") or props.get("prop_add") or "").strip()
    city = (props.get("dlgf_prop_address_city") or props.get("prop_city") or county).strip()
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"in_parcels:{pid}",
        "title": f"Indiana vacant · {acreage:.1f} ac · {county}",
        "description": (
            f"Indiana statewide parcel (DLGF class {code}). County={county}. "
            "Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "IN",
        "county": county,
        "apn": str(pid) if pid else None,
        "address": f"{addr}, {city}, IN".strip(", "),
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.in.gov/gis/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_vt_parcels_vacant(raw: dict) -> dict | None:
    """Vermont VCGI standardized parcels — DESCPROP land-only, 1ac+."""
    props = _props(raw)
    desc = str(props.get("DESCPROP") or "").strip().upper()
    # Prefer pure land; allow "LAND & …" only when no dwelling token.
    if "DWELL" in desc or "HOUSE" in desc or "MOBILE" in desc:
        return None
    if not desc.startswith("LAND"):
        return None
    if _non_market_owner(props.get("OWNER1")):
        return None
    preferred = _fnum(props.get("ACRESGL"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("SPAN") or props.get("OBJECTID")
    town = str(props.get("TOWN") or "Vermont").title()
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"vt_parcels:{pid}",
        "title": f"Vermont land · {acreage:.1f} ac · {town}",
        "description": (
            f"Vermont statewide standardized parcel (VCGI). Town={town}. DESCPROP={props.get('DESCPROP')}. "
            "Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "VT",
        "county": town,
        "apn": str(pid) if pid else None,
        "address": f"{town}, VT",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://vcgi.vermont.gov/",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


def _norm_ct_parcels_vacant(raw: dict) -> dict | None:
    """Connecticut statewide CAMA/parcel layer — vacant use + no building assessment."""
    props = _props(raw)
    use = str(props.get("State_Use") or "").strip()
    use_desc = str(props.get("State_Use_Description") or "").lower()
    vacantish = use.startswith("100") or "vacant" in use_desc
    if not vacantish:
        return None
    if (_fnum(props.get("Assessed_Building")) or 0) > 0:
        return None
    if _non_market_owner(props.get("Owner")):
        return None
    preferred = _fnum(props.get("Land_Acres"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None or not polygon:
        return None
    pid = props.get("Link") or props.get("OBJECTID") or props.get("Location")
    town = str(props.get("Town_Name") or "Connecticut").title()
    land_val = _fnum(props.get("Assessed_Land"))
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"ct_parcels:{town}:{pid}",
        "title": f"Connecticut vacant · {acreage:.1f} ac · {town}",
        "description": (
            f"Connecticut statewide CAMA parcel. Use={use} ({props.get('State_Use_Description')}). "
            f"Town={town}. Assessed land=${land_val}. Public GIS — not MLS/Zillow."
        ),
        "asking_price_usd": None,
        "acreage": acreage,
        "state": "CT",
        "county": town,
        "apn": str(pid) if pid else None,
        "address": f"{town}, CT",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://portal.ct.gov/deep",
        "status": "ACTIVE",
        "raw": {**props, "ask_role": "assessed_land"} if isinstance(props, dict) else props,
        "is_demo": False,
    }


# NC county names for geographic sharding (OneMap rejects OBJECTID windows).
_NC_COUNTIES = [
    "Alamance", "Alexander", "Alleghany", "Anson", "Ashe", "Avery", "Beaufort", "Bertie",
    "Bladen", "Brunswick", "Buncombe", "Burke", "Cabarrus", "Caldwell", "Camden", "Carteret",
    "Caswell", "Catawba", "Chatham", "Cherokee", "Chowan", "Clay", "Cleveland", "Columbus",
    "Craven", "Cumberland", "Currituck", "Dare", "Davidson", "Davie", "Duplin", "Durham",
    "Edgecombe", "Forsyth", "Franklin", "Gaston", "Gates", "Graham", "Granville", "Greene",
    "Guilford", "Halifax", "Harnett", "Haywood", "Henderson", "Hertford", "Hoke", "Hyde",
    "Iredell", "Jackson", "Johnston", "Jones", "Lee", "Lenoir", "Lincoln", "Macon",
    "Madison", "Martin", "McDowell", "Mecklenburg", "Mitchell", "Montgomery", "Moore",
    "Nash", "New Hanover", "Northampton", "Onslow", "Orange", "Pamlico", "Pasquotank",
    "Pender", "Perquimans", "Person", "Pitt", "Polk", "Randolph", "Richmond", "Robeson",
    "Rockingham", "Rowan", "Rutherford", "Sampson", "Scotland", "Stanly", "Stokes", "Surry",
    "Swain", "Transylvania", "Tyrrell", "Union", "Vance", "Wake", "Warren", "Washington",
    "Watauga", "Wayne", "Wilkes", "Wilson", "Yadkin", "Yancey",
]


def _src(
    source_id: str,
    name: str,
    url: str,
    state: str,
    normalize: Callable[[dict], dict | None],
    where: str,
    *,
    page_size: int = 1000,
    shard: bool = False,
    objectid_max: int | None = None,
    order_by: str | None = None,
    out_fields: str = "*",
    shard_field: str | None = None,
    shard_values: list[str] | None = None,
) -> ArcgisMarketSource:
    return ArcgisMarketSource(
        source_id,
        name,
        url,
        state,
        "Statewide",
        normalize,
        where=where,
        order_by=order_by,
        page_size=page_size,
        out_fields=out_fields,
        shard_by_objectid=shard,
        objectid_max=objectid_max,
        shard_field=shard_field,
        shard_values=shard_values,
    )


# Extra statewide screens merged into public_markets.SOURCES at import time.
SOURCES: list[ArcgisMarketSource] = [
    _src(
        "nc_parcels_vacant",
        "North Carolina OneMap Vacant Land (1ac+)",
        "https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/1/query",
        "NC",
        _norm_nc_parcels_vacant,
        where="improvval=0 AND gisacres>=1 AND gisacres<=2500 AND landval>0",
        # OBJECTID windows return 0 here — shard a spread of counties (full 100 is too slow).
        page_size=500,
        shard_field="cntyname",
        shard_values=_NC_COUNTIES[::4],
        out_fields=(
            "objectid,parno,nparno,ownname,improvval,landval,gisacres,recareano,"
            "siteadd,cntyname,parusecode,struct"
        ),
    ),
    _src(
        "ne_parcels_vacant",
        "Nebraska Statewide Vacant Land (5ac+)",
        "https://giscat.ne.gov/enterprise/rest/services/StatewideParcelsExternal/FeatureServer/0/query",
        "NE",
        _norm_ne_parcels_vacant,
        where="Improvements_Value=0 AND GIS_Acres>=5 AND GIS_Acres<=2500 AND Land_Value>0",
        shard=True,
        objectid_max=2_500_000,
    ),
    _src(
        "wa_parcels_vacant",
        "Washington Statewide Vacant Land (1ac+)",
        "https://services.arcgis.com/jsIt88o09Q0r1j8h/arcgis/rest/services/Current_Parcels/FeatureServer/0/query",
        "WA",
        _norm_wa_parcels_vacant,
        where="VALUE_BLDG=0 AND LANDUSE_CD>=91 AND LANDUSE_CD<=99",
        shard=True,
        objectid_max=3_500_000,
        out_fields=(
            "OBJECTID,FIPS_NR,COUNTY_NM,PARCEL_ID_NR,ORIG_PARCEL_ID,SITUS_ADDRESS,"
            "SITUS_CITY_NM,LANDUSE_CD,VALUE_LAND,VALUE_BLDG,DATA_LINK"
        ),
    ),
    _src(
        "wi_parcels_vacant",
        "Wisconsin Statewide Vacant Land (1ac+)",
        "https://services3.arcgis.com/n6uYoouQZW75n5WI/arcgis/rest/services/Wisconsin_Statewide_Parcels_DB/FeatureServer/0/query",
        "WI",
        _norm_wi_parcels_vacant,
        where="PROPCLASS LIKE '1%' AND GISACRES>=1 AND GISACRES<=2500",
        shard=True,
        objectid_max=3_600_000,
        out_fields=(
            "OBJECTID,PARCELID,PROPCLASS,AUXCLASS,GISACRES,ASSDACRES,DEEDACRES,"
            "OWNERNME1,PARCELSRC,SITEADRESS,PSTLADRESS"
        ),
    ),
    _src(
        "wi_parcels_agriculture",
        "Wisconsin Statewide Agriculture (10ac+)",
        "https://services3.arcgis.com/n6uYoouQZW75n5WI/arcgis/rest/services/Wisconsin_Statewide_Parcels_DB/FeatureServer/0/query",
        "WI",
        _norm_wi_parcels_ag,
        where="PROPCLASS LIKE '4%' AND GISACRES>=10 AND GISACRES<=2500",
        shard=True,
        objectid_max=3_600_000,
        out_fields=(
            "OBJECTID,PARCELID,PROPCLASS,AUXCLASS,GISACRES,ASSDACRES,DEEDACRES,"
            "OWNERNME1,PARCELSRC,SITEADRESS,PSTLADRESS"
        ),
    ),
    _src(
        "ut_parcels_vacant",
        "Utah Statewide Vacant Land (1ac+)",
        "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services/Parcels_Utah_LIR/FeatureServer/0/query",
        "UT",
        _norm_ut_parcels_vacant,
        where="PROP_CLASS='Vacant' AND PARCEL_ACRES>=1 AND PARCEL_ACRES<=2500",
        page_size=1000,
    ),
    _src(
        "in_parcels_vacant",
        "Indiana Statewide Vacant Land (1ac+)",
        "https://gisdata.in.gov/server/rest/services/Hosted/Parcel_Boundaries_of_Indiana_Current/FeatureServer/0/query",
        "IN",
        _norm_in_parcels_vacant,
        where="dlgf_prop_class_code LIKE '100%'",
        shard=True,
        objectid_max=4_000_000,
        out_fields=(
            "objectid,state_parcel_id,parcel_id,dlgf_prop_class_code,tax_county,"
            "source_originator,dlgf_prop_address,dlgf_prop_address_city,prop_add,prop_city,"
            "latitude,longitude"
        ),
    ),
    _src(
        "vt_parcels_vacant",
        "Vermont Statewide Land (1ac+)",
        "https://services1.arcgis.com/BkFxaEFNwHqX3tAw/arcgis/rest/services/FS_VCGI_OPENDATA_Cadastral_VTPARCELS_poly_standardized_parcels_SP_v1/FeatureServer/0/query",
        "VT",
        _norm_vt_parcels_vacant,
        where="DESCPROP LIKE 'LAND%' AND ACRESGL>=1 AND ACRESGL<=2500",
        page_size=1000,
        out_fields="OBJECTID,SPAN,PROPTYPE,DESCPROP,ACRESGL,TOWN,OWNER1",
    ),
    _src(
        "ct_parcels_vacant",
        "Connecticut Statewide Vacant Land (1ac+)",
        "https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/rest/services/Connecticut_CAMA_and_Parcel_Layer/FeatureServer/0/query",
        "CT",
        _norm_ct_parcels_vacant,
        where=(
            "Assessed_Building=0 AND Land_Acres>=1 AND Land_Acres<=2500 AND "
            "(State_Use LIKE '100%' OR State_Use_Description LIKE '%Vacant%')"
        ),
        page_size=1000,
        out_fields=(
            "OBJECTID,Link,Location,State_Use,State_Use_Description,Land_Acres,"
            "Assessed_Building,Assessed_Land,Town_Name,Owner"
        ),
    ),
]
