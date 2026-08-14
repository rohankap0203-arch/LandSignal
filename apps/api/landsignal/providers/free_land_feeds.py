"""Additional free/public LAND inventory feeds (not homes MLS).

These are official open ArcGIS cadastral / surplus / vacant layers — no Land.com,
ATTOM, MLS, or scraping behind logins. Merged into public_markets.SOURCES.
"""

from __future__ import annotations

from typing import Any


def _props(raw: dict) -> dict:
    from landsignal.providers.statewide_inventory import _props as _impl

    return _impl(raw)


def _acres_from_geom(geom: dict | None):
    from landsignal.providers.public_markets import _acres_from_geom as _impl

    return _impl(geom)


def _fnum(v: Any) -> float | None:
    from landsignal.providers.public_markets import _fnum as _impl

    return _impl(v)


def _row(**kwargs):
    from landsignal.providers.statewide_inventory_extra import _row as _impl

    return _impl(**kwargs)


def _norm_ct_vacant_cama(raw: dict) -> dict | None:
    props = _props(raw)
    pid = props.get("Parcel_ID") or props.get("OBJECTID")
    acres = _fnum(props.get("Land_Acres"))
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acres and acres > 0:
        acreage = acres
    if acreage is None or acreage < 1 or acreage > 2500 or not polygon or lat is None or lon is None:
        return None
    town = str(props.get("Town_Name") or "Connecticut").strip() or "Connecticut"
    land_val = _fnum(props.get("Assessed_Land")) or _fnum(props.get("Appraised_Land"))
    use = props.get("State_Use_Description") or props.get("State_Use") or "Vacant"
    loc = (props.get("Location") or "").strip()
    return _row(
        source_key="ct_vacant_cama",
        pid=pid,
        title=f"Connecticut vacant · {float(acreage):.1f} ac · {town}",
        description=(
            f"Connecticut open vacant CAMA parcel. Town={town}. Use={use}. "
            f"Assessed land=${land_val}. Public GIS — not MLS."
        ),
        state="CT",
        county=town,
        acreage=float(acreage),
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=land_val,
        apn=pid,
        address=loc or f"{town}, CT",
        source_url="https://geodata-ctmaps.opendata.arcgis.com/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_la_county_vacant(raw: dict) -> dict | None:
    """LA County Assessor parcels with $0 improvement and ≥1 acre geometry."""
    props = _props(raw)
    pid = props.get("AIN") or props.get("APN") or props.get("OBJECTID")
    imp = _fnum(props.get("Roll_ImpValue"))
    if imp is not None and imp > 0:
        return None
    land_val = _fnum(props.get("Roll_LandValue"))
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    # Shape.STArea() filter is applied in WHERE; still require polygon + acres.
    if acreage is None or acreage < 1 or acreage > 2500 or not polygon or lat is None or lon is None:
        return None
    city = (props.get("SitusCity") or "Los Angeles County").strip() or "Los Angeles County"
    use = props.get("UseDescription") or props.get("UseType") or "Vacant/unimproved"
    return _row(
        source_key="ca_la_vacant",
        pid=pid,
        title=f"Los Angeles County vacant · {float(acreage):.1f} ac",
        description=(
            f"LA County Assessor unimproved parcel (Roll_ImpValue=0). "
            f"Use={use}. Land value=${land_val}. Public GIS — not MLS."
        ),
        state="CA",
        county="Los Angeles",
        acreage=float(acreage),
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=land_val,
        apn=props.get("APN") or pid,
        address=city,
        source_url="https://public.gis.lacounty.gov/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_broward_vacant(raw: dict) -> dict | None:
    props = _props(raw)
    pid = props.get("FOLIO") or props.get("FOLIO_NUMBER") or props.get("OBJECTID")
    acres = _fnum(props.get("Land_Size_In_Acres"))
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acres and acres > 0:
        acreage = acres
    if acreage is None or acreage < 1 or acreage > 2500 or not polygon or lat is None or lon is None:
        return None
    land_val = _fnum(props.get("Land_And_Building_Value"))
    addr = (props.get("SITE_ADDRESS") or "").strip()
    city = (props.get("CITYNAME") or "Broward").strip()
    return _row(
        source_key="fl_broward_vacant",
        pid=pid,
        title=f"Broward FL vacant · {float(acreage):.1f} ac",
        description=(
            f"Broward County Property Appraiser vacant parcel layer. "
            f"City={city}. Public GIS — not MLS."
        ),
        state="FL",
        county="Broward",
        acreage=float(acreage),
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=land_val,
        apn=pid,
        address=addr or f"{city}, FL",
        source_url="https://bcpa.net/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_rochester_vacant(raw: dict) -> dict | None:
    props = _props(raw)
    pid = props.get("PARCELID") or props.get("OBJECTID")
    acres = _fnum(props.get("SHAPEACRES")) or _fnum(props.get("STATEDAREA"))
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acres and acres > 0:
        acreage = acres
    if acreage is None or acreage < 0.5 or acreage > 2500 or not polygon or lat is None or lon is None:
        return None
    land_val = _fnum(props.get("CURRENT_LAND_VALUE"))
    return _row(
        source_key="ny_rochester_vacant",
        pid=pid,
        title=f"Rochester NY vacant · {float(acreage):.2f} ac",
        description=(
            "City of Rochester open-data tax parcels classified vacant land. "
            "Public GIS — not MLS."
        ),
        state="NY",
        county="Monroe",
        acreage=float(acreage),
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=land_val,
        apn=pid,
        address="Rochester, NY",
        source_url="https://www.cityofrochester.gov/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_cuyahoga_vacant(raw: dict) -> dict | None:
    props = _props(raw)
    pid = props.get("parcelpin") or props.get("parcel_id") or props.get("OBJECTID")
    imp = _fnum(props.get("tax_assessed_improvement"))
    if imp is not None and imp > 0:
        return None
    acres = _fnum(props.get("parcel_acreage"))
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acres and acres > 0:
        acreage = acres
    if acreage is None or acreage < 1 or acreage > 2500 or not polygon or lat is None or lon is None:
        return None
    land_val = _fnum(props.get("tax_assessed_land")) or _fnum(props.get("certified_tax_land"))
    addr = (props.get("parcel_addr") or "").strip()
    city = (props.get("parcel_city") or "Cuyahoga").strip()
    return _row(
        source_key="oh_cuyahoga_vacant",
        pid=pid,
        title=f"Cuyahoga OH vacant · {float(acreage):.1f} ac",
        description=(
            f"Cuyahoga County parcel fabric — unimproved (tax_assessed_improvement=0). "
            f"Public GIS — not MLS."
        ),
        state="OH",
        county="Cuyahoga",
        acreage=float(acreage),
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=land_val,
        apn=pid,
        address=addr or f"{city}, OH",
        source_url="https://gis.cuyahogacounty.gov/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_txdot_surplus(raw: dict) -> dict | None:
    """TxDOT surplus / excess right-of-way land offered publicly."""
    props = _props(raw)
    pid = props.get("Job_Piece_Vault") or props.get("Parcel") or props.get("OBJECTID_1") or props.get("OBJECTID")
    acres = _fnum(props.get("Acres_Remaining"))
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acres and acres > 0:
        acreage = acres
    # Point layer (id 0) may lack polygon — accept point with acres.
    if acreage is None or acreage < 0.25 or acreage > 2500:
        return None
    if lat is None or lon is None:
        # Center-point layer
        geom = raw.get("geometry") or {}
        lat = _fnum(geom.get("y"))
        lon = _fnum(geom.get("x"))
    if lat is None or lon is None:
        return None
    if not polygon:
        # Synthetic small square so invent/store accepts the row
        d = 0.0003
        polygon = [[[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]]
    county = str(props.get("County") or "Texas").strip() or "Texas"
    name = (props.get("Name") or "").strip()
    return {
        "provider_id": "public_surplus",
        "external_id": f"txdot_surplus:{pid}",
        "title": f"TxDOT surplus · {float(acreage):.2f} ac · {county}",
        "description": (
            f"Texas Department of Transportation surplus / excess land. "
            f"Name={name or 'n/a'}. Sale sign={props.get('SALE_SIGN')}. Public surplus — not MLS."
        ),
        "asking_price_usd": None,
        "acreage": float(acreage),
        "state": "TX",
        "county": county,
        "apn": str(props.get("Parcel") or pid),
        "address": f"{county} County, TX",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": "https://www.txdot.gov/",
        "status": "ACTIVE",
        "raw": {**(props if isinstance(props, dict) else {}), "ask_role": "process"},
        "is_demo": False,
    }


def _norm_az_asld_mineral(raw: dict) -> dict | None:
    """Arizona State Land Department trust parcels (surface/mineral inventory screen)."""
    props = _props(raw)
    pid = props.get("parcelnumber") or props.get("id") or props.get("objectid")
    acres = _fnum(props.get("acres"))
    acreage, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    if acres and acres > 0:
        acreage = acres
    if acreage is None or acreage < 1 or acreage > 2500 or not polygon or lat is None or lon is None:
        return None
    county = str(props.get("county") or "Arizona").strip() or "Arizona"
    return _row(
        source_key="az_asld_mineral",
        pid=pid,
        title=f"Arizona State Trust · {float(acreage):.1f} ac · {county}",
        description=(
            f"ASLD state trust land parcel. OpenStatus={props.get('openstatus')}. "
            f"Classification={props.get('classification')}. Public trust inventory — not MLS."
        ),
        state="AZ",
        county=county,
        acreage=float(acreage),
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=None,
        apn=pid,
        address=f"{county} County, AZ",
        source_url="https://land.az.gov/",
        props=props if isinstance(props, dict) else None,
    )


def build_sources():
    """Build source list lazily to avoid circular import with public_markets."""
    from landsignal.providers.public_markets import ArcgisMarketSource
    from landsignal.providers.statewide_inventory import _src

    return [
        _src(
            "ct_vacant_cama",
            "Connecticut Statewide Vacant Parcels (1ac+)",
            "https://services3.arcgis.com/3FL1kr7L4LvwA2Kb/arcgis/rest/services/Connecticut_CAMA_and_Parcel_Layer_Vacant_Parcels/FeatureServer/0/query",
            "CT",
            _norm_ct_vacant_cama,
            where="Land_Acres>=1 AND Land_Acres<=2500",
            page_size=1000,
            shard=True,
            objectid_max=200_000,
        ),
        ArcgisMarketSource(
            "ca_la_vacant",
            "Los Angeles County CA Vacant Land (1ac+)",
            "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0/query",
            "CA",
            "Los Angeles",
            _norm_la_county_vacant,
            where="Roll_ImpValue=0 AND Roll_LandValue>0 AND Shape.STArea()>=43560",
            page_size=1000,
            out_fields=(
                "AIN,APN,UseCode,UseType,UseDescription,Roll_LandValue,Roll_ImpValue,SitusCity,OBJECTID"
            ),
            shard_by_objectid=True,
            objectid_max=3_000_000,
        ),
        ArcgisMarketSource(
            "fl_broward_vacant",
            "Broward County FL Vacant Land (1ac+)",
            "https://services.arcgis.com/JMAJrTsHNLrSsWf5/arcgis/rest/services/BCPAParcelsVacant/FeatureServer/11/query",
            "FL",
            "Broward",
            _norm_broward_vacant,
            where="Land_Size_In_Acres>=1 AND Land_Size_In_Acres<=2500",
            page_size=1000,
        ),
        ArcgisMarketSource(
            "ny_rochester_vacant",
            "Rochester NY Vacant Land Tax Parcels",
            "https://maps.cityofrochester.gov/server/rest/services/Open_Data/Tax_Parcels_Vacant_Land_Open_Data/FeatureServer/3/query",
            "NY",
            "Monroe",
            _norm_rochester_vacant,
            where="SHAPEACRES>=0.5 AND SHAPEACRES<=2500",
            page_size=1000,
        ),
        ArcgisMarketSource(
            "oh_cuyahoga_vacant",
            "Cuyahoga County OH Vacant Land (1ac+)",
            "https://gis.cuyahogacounty.gov/server/rest/services/CCFO/Parcel_Fabric_Taxparcels/FeatureServer/0/query",
            "OH",
            "Cuyahoga",
            _norm_cuyahoga_vacant,
            where=(
                "tax_assessed_improvement=0 AND parcel_acreage>=1 AND parcel_acreage<=2500 "
                "AND tax_assessed_land>0"
            ),
            page_size=1000,
            shard_by_objectid=True,
            objectid_max=600_000,
        ),
        ArcgisMarketSource(
            "txdot_surplus",
            "TxDOT Surplus / Excess Land",
            "https://services6.arcgis.com/RBtoEUQ2lmN0K3GY/arcgis/rest/services/Surplus_Property_Public_Current/FeatureServer/1/query",
            "TX",
            "Statewide",
            _norm_txdot_surplus,
            where="Acres_Remaining>0",
            page_size=500,
        ),
        ArcgisMarketSource(
            "az_asld_mineral",
            "Arizona ASLD State Trust Parcels",
            "https://gisdata.azland.gov/server/rest/services/ASLD/Arizona_State_Trust_Land_Mineral_Parcels/FeatureServer/0/query",
            "AZ",
            "Statewide",
            _norm_az_asld_mineral,
            where="acres>=1 AND acres<=2500",
            page_size=1000,
            shard_by_objectid=True,
            objectid_max=50_000,
        ),
    ]


# Populated on first access / by public_markets._extend_statewide_sources().
SOURCES = []
