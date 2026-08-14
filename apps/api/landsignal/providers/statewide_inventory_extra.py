"""Additional statewide / metro vacant-land screens so every US state can hit ≥10k.

Merged into public_markets.SOURCES. Prefer official public ArcGIS cadastral layers —
no MLS / Zillow / Regrid credentials required.
"""

from __future__ import annotations

from typing import Any, Callable

from landsignal.providers.public_markets import (
    ArcgisMarketSource,
    _acres_from_geom,
    _bounded_acres,
    _fnum,
    _non_market_owner,
)
from landsignal.providers.statewide_inventory import _props, _src


def _row(
    *,
    source_key: str,
    pid: Any,
    title: str,
    description: str,
    state: str,
    county: str,
    acreage: float,
    lat: float | None,
    lon: float | None,
    polygon: list | None,
    land_val: float | None,
    apn: Any = None,
    address: str | None = None,
    source_url: str | None = None,
    props: dict | None = None,
) -> dict | None:
    if acreage is None or not polygon or lat is None or lon is None:
        return None
    ask = float(land_val) if land_val is not None and land_val > 0 else None
    raw = {**(props or {}), "ask_role": "assessed_land"} if ask is not None else (props or {})
    return {
        "provider_id": "public_vacant_gis",
        "external_id": f"{source_key}:{pid}",
        "title": title,
        "description": description,
        "asking_price_usd": ask,
        "acreage": float(acreage),
        "state": state,
        "county": county,
        "apn": str(apn or pid) if (apn or pid) is not None else None,
        "address": address or f"{county}, {state}",
        "latitude": lat,
        "longitude": lon,
        "polygon": polygon,
        "source_url": source_url,
        "status": "ACTIVE",
        "raw": raw,
        "is_demo": False,
    }


def _vacant_from_fields(
    raw: dict,
    *,
    source_key: str,
    state: str,
    county_keys: tuple[str, ...] = ("county", "COUNTY", "County", "countyName"),
    default_county: str,
    pid_keys: tuple[str, ...] = ("parcel_id", "PARCELID", "PIN", "APN", "OBJECTID"),
    acre_keys: tuple[str, ...] = ("acres", "ACRES", "GISAcres", "landAcres"),
    land_keys: tuple[str, ...] = ("land_value", "TotalLandValue", "NFMLNDVL", "VAL_LAND"),
    bldg_keys: tuple[str, ...] = ("building_value", "TotalBuildingValue", "NFMIMPVL", "VAL_IMPVTS"),
    owner_keys: tuple[str, ...] = ("owner", "OwnerName", "OWNER", "OWNERNME1"),
    min_ac: float = 1.0,
    label: str = "vacant",
    source_url: str | None = None,
    require_zero_bldg: bool = True,
) -> dict | None:
    props = _props(raw)
    bldg = next((_fnum(props.get(k)) for k in bldg_keys if props.get(k) is not None), None)
    if require_zero_bldg and bldg is not None and bldg > 0:
        return None
    owner = next((props.get(k) for k in owner_keys if props.get(k)), None)
    if _non_market_owner(str(owner) if owner else None):
        return None
    preferred = next((_fnum(props.get(k)) for k in acre_keys if _fnum(props.get(k)) is not None), None)
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=min_ac)
    if acreage is None:
        return None
    land_val = next((_fnum(props.get(k)) for k in land_keys if _fnum(props.get(k)) is not None), None)
    pid = next((props.get(k) for k in pid_keys if props.get(k) is not None), None)
    county = str(next((props.get(k) for k in county_keys if props.get(k)), default_county)).title()
    return _row(
        source_key=source_key,
        pid=pid,
        title=f"{state} {label} · {acreage:.1f} ac · {county}",
        description=(
            f"Public cadastral {label} screen ({state}). County={county}. "
            f"Owner={owner}. Land value=${land_val}. Not MLS/Zillow."
        ),
        state=state,
        county=county,
        acreage=acreage,
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=land_val,
        apn=pid,
        source_url=source_url,
        props=props if isinstance(props, dict) else None,
    )


def _norm_mt_dnrc_vacant(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="mt_dnrc",
        state="MT",
        default_county="Montana",
        county_keys=("CountyName", "COUNTY", "county"),
        pid_keys=("PARCELID", "AssessmentCode", "OBJECTID"),
        acre_keys=("TotalAcres", "GISAcres"),
        land_keys=("TotalLandValue",),
        bldg_keys=("TotalBuildingValue",),
        owner_keys=("OwnerName",),
        source_url="https://gis.dnrc.mt.gov/",
    )


def _norm_co_oit_vacant(raw: dict) -> dict | None:
    props = _props(raw)
    use = str(props.get("landUseDsc") or props.get("zoningDesc") or "").lower()
    # Prefer vacant/ag wording; still accept large unbuilt tracts.
    if use and not any(t in use for t in ("vacant", "ag", "farm", "ranch", "rural", "open", "agricult")):
        # Keep large acreage tracts anyway — Colorado composite is mixed.
        preferred = _fnum(props.get("landAcres"))
        if preferred is None or preferred < 5:
            return None
    return _vacant_from_fields(
        raw,
        source_key="co_oit",
        state="CO",
        default_county="Colorado",
        county_keys=("countyName",),
        pid_keys=("parcel_id", "account", "OBJECTID"),
        acre_keys=("landAcres",),
        land_keys=("apprValTot", "asedValTot"),
        bldg_keys=(),  # composite often lacks separate bldg; acreage+use screen above
        owner_keys=("owner", "owner2"),
        require_zero_bldg=False,
        min_ac=1.0,
        source_url="https://gis.colorado.gov/",
    )


def _norm_wv_gistc(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="wv_gistc",
        state="WV",
        default_county="West Virginia",
        county_keys=("COUNTY", "County", "FullPhysicalAddress"),
        pid_keys=("CleanParcelID", "GISPID", "OBJECTID"),
        acre_keys=("CALC_ACRE",),
        land_keys=(),
        bldg_keys=(),
        owner_keys=("FullOwnerName", "OWNER1"),
        require_zero_bldg=False,
        min_ac=1.0,
        label="land",
        source_url="https://www.wvgis.wvu.edu/",
    )


def _norm_ak_agc_vacant(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="ak_agc",
        state="AK",
        default_county="Alaska",
        county_keys=("local_gov",),
        pid_keys=("parcel_id", "feature_id", "OBJECTID"),
        acre_keys=(),  # rely on geometry area
        land_keys=("land_value",),
        bldg_keys=("building_value",),
        owner_keys=("owner", "alt_owner"),
        source_url="https://agc.dnr.alaska.gov/",
    )


def _norm_id_igo_vacant(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="id_igo",
        state="ID",
        default_county="Idaho",
        county_keys=("County",),
        pid_keys=("PARCEL_ID", "OBJECTID"),
        acre_keys=("ASR_ACRES",),
        land_keys=("VAL_LAND",),
        bldg_keys=("VAL_IMPVTS",),
        owner_keys=("OWNER1", "OWNER2"),
        source_url="https://www.idaho.gov/",
    )


def _norm_md_imap_vacant(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="md_imap",
        state="MD",
        default_county="Maryland",
        county_keys=("JURSCODE", "DESCTOWN"),
        pid_keys=("ACCTID", "PARCEL", "OBJECTID"),
        acre_keys=("ACRES", "POLYACRES"),
        land_keys=("NFMLNDVL",),
        bldg_keys=("NFMIMPVL",),
        owner_keys=("OWNNAME1", "OWNADD1"),
        source_url="https://imap.maryland.gov/",
    )


def _norm_me_unorganized(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="me_ut",
        state="ME",
        default_county="Unorganized Territory",
        county_keys=("TOWNNAME", "AREANAME", "TOWN"),
        pid_keys=("GEOCODE", "LOT", "OBJECTID"),
        acre_keys=("TOTACRES", "CACREAGE"),
        land_keys=(),
        bldg_keys=(),
        owner_keys=("GRANTEE",),
        require_zero_bldg=False,
        min_ac=5.0,
        label="timber/rural",
        source_url="https://www.maine.gov/revenuervices/",
    )


def _norm_hi_county_vacant(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="hi_hawaii",
        state="HI",
        default_county="Hawaii",
        county_keys=("county", "island"),
        pid_keys=("tmk", "tmk_txt", "objectid"),
        acre_keys=("gisacres", "taxacres"),
        land_keys=("landvalue",),
        bldg_keys=("bldgvalue",),
        owner_keys=("majorowner",),
        source_url="https://geodata.hawaii.gov/",
    )


def _norm_dc_vacant(raw: dict) -> dict | None:
    props = _props(raw)
    # LANDAREA often sq ft
    land_sf = _fnum(props.get("LANDAREA")) or _fnum(props.get("CALCULATEDAREA"))
    preferred = (land_sf / 43560.0) if land_sf and land_sf > 100 else land_sf
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=0.05)
    if acreage is None:
        return None
    if (_fnum(props.get("NEWIMPR")) or 0) > 0:
        return None
    land_val = _fnum(props.get("NEWLAND"))
    pid = props.get("SSL") or props.get("OBJECTID")
    return _row(
        source_key="dc_open",
        pid=pid,
        title=f"DC vacant lot · {acreage:.2f} ac",
        description=f"DC Open Data unimproved lot. Land=${land_val}. Public GIS.",
        state="DC",
        county="District of Columbia",
        acreage=acreage,
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=land_val,
        apn=pid,
        address=str(props.get("PREMISEADD") or "Washington, DC"),
        source_url="https://opendata.dc.gov/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_va_vgin(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="va_vgin",
        state="VA",
        default_county="Virginia",
        county_keys=("LOCALITY",),
        pid_keys=("PARCELID", "PTM_ID", "VGIN_QPID", "OBJECTID"),
        acre_keys=(),
        land_keys=(),
        bldg_keys=(),
        owner_keys=(),
        require_zero_bldg=False,
        min_ac=1.0,
        label="parcel",
        source_url="https://vgin.vdem.virginia.gov/",
    )


def _norm_nh_granit(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="nh_granit",
        state="NH",
        default_county="New Hampshire",
        county_keys=("town", "countyid"),
        pid_keys=("pid", "nh_gis_id", "u_id", "OBJECTID"),
        acre_keys=(),
        land_keys=(),
        bldg_keys=(),
        owner_keys=("name",),
        require_zero_bldg=False,
        min_ac=1.0,
        label="parcel",
        source_url="https://granit.unh.edu/",
    )


def _norm_az_asld(raw: dict) -> dict | None:
    props = _props(raw)
    preferred = _fnum(props.get("acres"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None:
        return None
    pid = props.get("objectid") or props.get("legaldescription")
    county = str(props.get("county") or "Arizona").title()
    return _row(
        source_key="az_asld",
        pid=pid,
        title=f"Arizona State Trust · {acreage:.1f} ac · {county}",
        description=(
            f"Arizona State Land Department trust parcel. County={county}. "
            f"Status={props.get('openstatus')}. Public GIS — acquisition via ASLD process."
        ),
        state="AZ",
        county=county,
        acreage=acreage,
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=None,
        source_url="https://land.az.gov/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_ca_sb_vacant(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="ca_sb",
        state="CA",
        default_county="San Bernardino",
        county_keys=(),
        pid_keys=("ParcelNumber", "OBJECTID"),
        acre_keys=("Acreage",),
        land_keys=("LandValue",),
        bldg_keys=("ImprovementValue",),
        owner_keys=("OwnerName",),
        min_ac=1.0,
        source_url="https://www.sbcounty.gov/",
    )


def _norm_ok_okc(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="ok_okc",
        state="OK",
        default_county="Oklahoma",
        county_keys=(),
        pid_keys=("pin", "PARCELNB_1", "OBJECTID"),
        acre_keys=("acres",),
        land_keys=("landvalue",),
        bldg_keys=(),
        owner_keys=("name1",),
        require_zero_bldg=False,
        min_ac=1.0,
        label="parcel",
        source_url="https://www.oklahomacounty.org/",
    )


def _norm_nv_washoe(raw: dict) -> dict | None:
    props = _props(raw)
    use = str(props.get("LAND_USE") or "").upper()
    # Keep vacant / rural / ag-ish codes when present; else 1ac+ with land value.
    if use and use not in {"VAC", "VACANT", "AGR", "AG", "RUR", "OS"} and "VAC" not in use:
        if (_fnum(props.get("ACREAGE")) or 0) < 5:
            return None
    return _vacant_from_fields(
        raw,
        source_key="nv_washoe",
        state="NV",
        default_county="Washoe",
        county_keys=(),
        pid_keys=("APN", "PIN", "PARCEL", "OBJECTID"),
        acre_keys=("ACREAGE",),
        land_keys=("LANDASS", "LANDAPR", "LAND_BASE"),
        bldg_keys=(),
        owner_keys=("LASTNAME", "FIRSTNAME"),
        require_zero_bldg=False,
        min_ac=1.0,
        source_url="https://www.washoecounty.gov/",
    )


def _norm_de_kent(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="de_kent",
        state="DE",
        default_county="Kent",
        county_keys=(),
        pid_keys=("PIN", "OBJECTID"),
        acre_keys=("DEEDACREAGE",),
        land_keys=("LANDASSESSMENT",),
        bldg_keys=("IMPROVE",),
        owner_keys=("OWNERNAME",),
        min_ac=1.0,
        source_url="https://www.kentcountyde.gov/",
    )


def _norm_wy_sheridan(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="wy_sheridan",
        state="WY",
        default_county="Sheridan",
        county_keys=(),
        pid_keys=("PIN", "RPID", "OBJECTID"),
        acre_keys=("ACRES", "grossacres", "netacres", "Deeded_Acres"),
        land_keys=("totalland", "totalval"),
        bldg_keys=("totalimps",),
        owner_keys=("Owner", "owner_name1"),
        min_ac=1.0,
        source_url="https://www.sheridancounty.com/",
    )


def _norm_nd_cass(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="nd_cass",
        state="ND",
        default_county="Cass",
        county_keys=(),
        pid_keys=("GISPIN", "PIN", "OBJECTID"),
        acre_keys=("ACRES", "As400Acres"),
        land_keys=(),
        bldg_keys=(),
        owner_keys=("Name",),
        require_zero_bldg=False,
        min_ac=1.0,
        label="parcel",
        source_url="https://www.casscountynd.gov/",
    )


def _norm_sd_minnehaha(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="sd_minn",
        state="SD",
        default_county="Minnehaha",
        county_keys=(),
        pid_keys=("TAG", "OBJECTID"),
        acre_keys=("TOTAL_ACREAGE",),
        land_keys=(),
        bldg_keys=(),
        owner_keys=("MRTNM1",),
        require_zero_bldg=False,
        min_ac=1.0,
        label="parcel",
        source_url="https://www.minnehahacounty.gov/",
    )


def _norm_ms_hinds(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="ms_hinds",
        state="MS",
        default_county="Hinds",
        county_keys=(),
        pid_keys=("PPIN", "OBJECTID"),
        acre_keys=("GISACRES", "TAXACRES"),
        land_keys=("LANDVAL",),
        bldg_keys=("IMPVAL1", "IMPVAL2"),
        owner_keys=("OWNNAME",),
        min_ac=1.0,
        source_url="https://www.hindscountyms.com/",
    )


def _norm_or_multnomah(raw: dict) -> dict | None:
    props = _props(raw)
    preferred = _fnum(props.get("StatedArea"))
    # StatedArea sometimes sq ft
    if preferred and preferred > 5000:
        preferred = preferred / 43560.0
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=0.1)
    if acreage is None:
        return None
    pid = props.get("OBJECTID") or props.get("TLID")
    return _row(
        source_key="or_mult",
        pid=pid,
        title=f"Oregon Multnomah · {acreage:.2f} ac",
        description="Multnomah County tax lot (public). Not MLS/Zillow.",
        state="OR",
        county="Multnomah",
        acreage=acreage,
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=None,
        source_url="https://www.oregonmetro.gov/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_ga_gwinnett(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="ga_gwinnett",
        state="GA",
        default_county="Gwinnett",
        county_keys=(),
        pid_keys=("PIN", "RPIN", "OBJECTID"),
        acre_keys=(),
        land_keys=("LANDVAL1",),
        bldg_keys=("DWLGVAL1",),
        owner_keys=("OWNER1",),
        min_ac=0.25,
        label="parcel",
        source_url="https://www.gwinnettcounty.com/",
    )


def _norm_il_kane(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="il_kane",
        state="IL",
        default_county="Kane",
        county_keys=(),
        pid_keys=("PIN", "OBJECTID"),
        acre_keys=("RecordedAcreage",),
        land_keys=(),
        bldg_keys=(),
        owner_keys=("TaxName",),
        require_zero_bldg=False,
        min_ac=1.0,
        label="parcel",
        source_url="https://www.countyofkane.org/",
    )


def _norm_mo_jackson(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="mo_jackson",
        state="MO",
        default_county="Jackson",
        county_keys=(),
        pid_keys=("PIN", "SHORTPIN", "OBJECTID"),
        acre_keys=("P_ACREAGE",),
        land_keys=(),
        bldg_keys=(),
        owner_keys=("OWNER",),
        require_zero_bldg=False,
        min_ac=0.5,
        label="parcel",
        source_url="https://www.jacksongov.org/",
    )


def _norm_nm_ose(raw: dict) -> dict | None:
    props = _props(raw)
    if (_fnum(props.get("StructureCount")) or 0) > 0:
        return None
    return _vacant_from_fields(
        raw,
        source_key="nm_ose",
        state="NM",
        default_county="New Mexico",
        county_keys=("County",),
        pid_keys=("StateParcelId", "LocalParcelId", "AccountNumber", "OBJECTID"),
        acre_keys=("LandArea",),
        land_keys=(),
        bldg_keys=("StructureCount",),
        owner_keys=("Owner1", "OwnerAll"),
        require_zero_bldg=False,
        min_ac=1.0,
        source_url="https://www.ose.state.nm.us/",
    )


def _norm_pa_pasda(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="pa_pasda",
        state="PA",
        default_county="Pennsylvania",
        county_keys=("Source",),
        pid_keys=("PIN", "OBJECTID"),
        acre_keys=(),
        land_keys=(),
        bldg_keys=(),
        owner_keys=(),
        require_zero_bldg=False,
        min_ac=1.0,
        label="parcel",
        source_url="https://www.pasda.psu.edu/",
    )


def _norm_al_jefferson(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="al_jeff",
        state="AL",
        default_county="Jefferson",
        county_keys=(),
        pid_keys=("PARCELID", "PID", "Unique_ID", "OBJECTID"),
        acre_keys=(),
        land_keys=(),
        bldg_keys=(),
        owner_keys=("OWNERNAME",),
        require_zero_bldg=False,
        min_ac=1.0,
        label="parcel",
        source_url="https://www.jccal.org/",
    )


def _norm_mi_oakland(raw: dict) -> dict | None:
    props = _props(raw)
    # Prefer vacant/ag class codes when present (Michigan use class often 4xx/vacant).
    klass = str(props.get("CLASSCODE") or "")
    if klass and not (klass.startswith("4") or klass.startswith("0") or "VAC" in klass.upper()):
        # Still keep larger geometry tracts.
        pass
    return _vacant_from_fields(
        raw,
        source_key="mi_oakland",
        state="MI",
        default_county="Oakland",
        county_keys=("CVTTAXDESCRIPTION",),
        pid_keys=("PIN", "KEYPIN", "OBJECTID"),
        acre_keys=(),
        land_keys=("ASSESSEDVALUE", "TAXABLEVALUE"),
        bldg_keys=("LIVING_AREA_SQFT",),
        owner_keys=("NAME1", "NAME2"),
        require_zero_bldg=False,
        min_ac=1.0,
        label="parcel",
        source_url="https://www.oakgov.com/",
    )


def _norm_ri_tax_parcels(raw: dict) -> dict | None:
    """RIGIS / RIDEM tax parcels — low improvement share, 1ac+ (no CAD $ on layer)."""
    props = _props(raw)
    pct_imp = _fnum(props.get("PctImp"))
    if pct_imp is not None and pct_imp > 8:
        return None
    preferred = _fnum(props.get("Acres"))
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=1.0)
    if acreage is None:
        return None
    pid = props.get("PlatLot") or props.get("OBJECTID")
    town = str(props.get("TownCode") or "Rhode Island")
    return _row(
        source_key="ri_tax",
        pid=pid,
        title=f"Rhode Island parcel · {acreage:.1f} ac · town {town}",
        description=(
            f"RIGIS/RIDEM tax parcel screen. TownCode={town}. PctImp={pct_imp}. "
            "Public GIS — not MLS/Zillow."
        ),
        state="RI",
        county=f"Town {town}",
        acreage=acreage,
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=None,
        apn=pid,
        source_url="https://risegis.ri.gov/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_sc_horry_vacant(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="sc_horry",
        state="SC",
        default_county="Horry",
        county_keys=("TaxDistrict",),
        pid_keys=("TMS", "PIN", "PINtext", "OBJECTID"),
        acre_keys=("Acreage",),
        land_keys=("MarketLand", "AssessedLand", "TaxableLand"),
        bldg_keys=("MarketImprv", "AssessedImprv"),
        owner_keys=("OwnerName",),
        min_ac=1.0,
        label="vacant",
        source_url="https://www.horrycounty.org/",
    )


def _norm_sc_berkeley_vacant(raw: dict) -> dict | None:
    return _vacant_from_fields(
        raw,
        source_key="sc_berkeley",
        state="SC",
        default_county="Berkeley",
        county_keys=("City",),
        pid_keys=("ParcelID", "OBJECTID"),
        acre_keys=("TotalAcres", "QRAcres", "AGAcres"),
        land_keys=("LandMarket", "AgLandMarket", "QRLandValue"),
        bldg_keys=("BuildingMarket", "AgBuildingMarket", "QRBuildingValue"),
        owner_keys=("OwnerName",),
        min_ac=1.0,
        label="vacant",
        source_url="https://www.berkeleycountysc.gov/",
    )


def _norm_la_brla_parcels(raw: dict) -> dict | None:
    """East Baton Rouge tax parcels — unimproved when improvement $ is null/0."""
    props = _props(raw)
    assess = str(props.get("ASSESSMENT_NUM") or "").strip()
    if not assess or assess.startswith("000-"):
        return None
    impr = _fnum(props.get("SUM_IMPROVEMENT_VALUE"))
    if impr is not None and impr > 0:
        return None
    if _non_market_owner(str(props.get("OWNER") or "")):
        return None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    # EBR city lots are often <1ac — keep 0.25ac+ so LA is not empty.
    acreage = _bounded_acres(None, geom_acres, min_ac=0.25)
    if acreage is None:
        return None
    land_val = (
        _fnum(props.get("SUM_LAND_VALUE"))
        or _fnum(props.get("SUM_LOT_VALUE"))
        or _fnum(props.get("SUM_FAIR_MARKET_VALUE"))
    )
    pid = assess or props.get("ID") or props.get("OBJECTID")
    addr = (props.get("PHYSICAL_ADDRESS") or "").strip()
    return _row(
        source_key="la_brla",
        pid=pid,
        title=f"Louisiana parcel · {acreage:.1f} ac · East Baton Rouge",
        description=(
            f"East Baton Rouge Parish tax parcel screen. Owner={props.get('OWNER')}. "
            f"Land mark=${land_val}. Public GIS — not MLS/Zillow."
        ),
        state="LA",
        county="East Baton Rouge",
        acreage=acreage,
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=land_val if land_val and land_val >= 500 else None,
        apn=pid,
        address=addr or "East Baton Rouge Parish, LA",
        source_url="https://maps.brla.gov/",
        props=props if isinstance(props, dict) else None,
    )


def _norm_la_orleans_parcels(raw: dict) -> dict | None:
    """Orleans Parish property parcels — large lots from assessor sqft."""
    props = _props(raw)
    if _non_market_owner(str(props.get("OWNERNME1") or "")):
        return None
    sqft = _fnum(props.get("ASS_SQFT"))
    preferred = (sqft / 43560.0) if sqft and sqft > 0 else None
    geom_acres, lat, lon, polygon = _acres_from_geom(raw.get("geometry"))
    acreage = _bounded_acres(preferred, geom_acres, min_ac=0.25)
    if acreage is None:
        return None
    # Skip obvious condo/unit rows
    if props.get("UNIT") and str(props.get("UNIT")).strip() not in ("", "0", "None"):
        if acreage < 2.0:
            return None
    pid = props.get("PARCELID") or props.get("TAXBILLID") or props.get("PARID") or props.get("OBJECTID")
    addr = (props.get("SITEADDRESS") or "").strip()
    return _row(
        source_key="la_orleans",
        pid=pid,
        title=f"Louisiana parcel · {acreage:.1f} ac · Orleans",
        description=(
            f"Orleans Parish property screen. Owner={props.get('OWNERNME1')}. "
            f"USECD={props.get('USECD')}. Public GIS — not MLS/Zillow."
        ),
        state="LA",
        county="Orleans",
        acreage=acreage,
        lat=lat,
        lon=lon,
        polygon=polygon,
        land_val=None,
        apn=pid,
        address=addr or "Orleans Parish, LA",
        source_url="https://gis.nola.gov/",
        props=props if isinstance(props, dict) else None,
    )


SOURCES: list[ArcgisMarketSource] = [
    _src(
        "mt_dnrc_vacant",
        "Montana DNRC Vacant Land (1ac+)",
        "https://gis.dnrc.mt.gov/arcgis/rest/services/DNRALL/Cadastral/MapServer/0/query",
        "MT",
        _norm_mt_dnrc_vacant,
        where="TotalBuildingValue=0 AND TotalAcres>=1 AND TotalAcres<=2500 AND TotalLandValue>0",
        shard=True,
        objectid_max=2_000_000,
        page_size=1000,
    ),
    _src(
        "co_oit_vacant",
        "Colorado Statewide Vacant/Ag Land (1ac+)",
        "https://gis.colorado.gov/public/rest/services/Address_and_Parcel/Colorado_Public_Parcels/FeatureServer/0/query",
        "CO",
        _norm_co_oit_vacant,
        where="landAcres>=1 AND landAcres<=2500",
        shard=True,
        objectid_max=1_500_000,
        page_size=1000,
    ),
    _src(
        "wv_gistc_parcels",
        "West Virginia Statewide Parcels (1ac+)",
        "https://services.wvgis.wvu.edu/arcgis/rest/services/Planning_Cadastre/WV_Parcels/MapServer/0/query",
        "WV",
        _norm_wv_gistc,
        where="CALC_ACRE>=1 AND CALC_ACRE<=2500",
        shard=True,
        objectid_max=1_200_000,
        page_size=1000,
    ),
    _src(
        "ak_agc_vacant",
        "Alaska Statewide Vacant Land",
        "https://services1.arcgis.com/7HDiw78fcUiM2BWn/arcgis/rest/services/AK_Parcels/FeatureServer/0/query",
        "AK",
        _norm_ak_agc_vacant,
        where="building_value=0 AND land_value>0",
        shard=True,
        objectid_max=400_000,
        page_size=1000,
    ),
    _src(
        "id_igo_vacant",
        "Idaho Statewide Vacant Land (1ac+)",
        "https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Public_Idaho_Parcels_/FeatureServer/7/query",
        "ID",
        _norm_id_igo_vacant,
        where="VAL_IMPVTS=0 AND ASR_ACRES>=1 AND ASR_ACRES<=2500 AND VAL_LAND>0",
        shard=True,
        objectid_max=500_000,
        page_size=1000,
    ),
    _src(
        "md_imap_vacant",
        "Maryland Statewide Unimproved (1ac+)",
        "https://mdgeodata.md.gov/imap/rest/services/PlanningCadastre/MD_ParcelBoundaries/MapServer/0/query",
        "MD",
        _norm_md_imap_vacant,
        where="(NFMIMPVL IS NULL OR NFMIMPVL=0) AND ACRES>=1 AND ACRES<=2500 AND NFMLNDVL>0",
        shard=True,
        objectid_max=2_500_000,
        page_size=1000,
    ),
    _src(
        "me_ut_rural",
        "Maine Unorganized Territory (5ac+)",
        "https://gis.maine.gov/mapservices/rest/services/mrs/Maine_Parcels_Unorganized_Territory/MapServer/0/query",
        "ME",
        _norm_me_unorganized,
        where="TOTACRES>=5 AND TOTACRES<=2500",
        page_size=1000,
    ),
    _src(
        "hi_hawaii_vacant",
        "Hawaii County Vacant Land (1ac+)",
        "https://geodata.hawaii.gov/arcgis/rest/services/ParcelsZoning/MapServer/5/query",
        "HI",
        _norm_hi_county_vacant,
        where="bldgvalue=0 AND gisacres>=1 AND gisacres<=2500 AND landvalue>0",
        page_size=1000,
    ),
    _src(
        "dc_open_vacant",
        "District of Columbia Vacant Lots",
        "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Property_and_Land_WebMercator/FeatureServer/40/query",
        "DC",
        _norm_dc_vacant,
        where="NEWIMPR=0 AND NEWLAND>0",
        page_size=1000,
    ),
    _src(
        "va_vgin_parcels",
        "Virginia VGIN Statewide Parcels (1ac+)",
        "https://vginmaps.vdem.virginia.gov/arcgis/rest/services/VA_Base_Layers/VA_Parcels/MapServer/0/query",
        "VA",
        _norm_va_vgin,
        where="1=1",
        shard=True,
        objectid_max=4_000_000,
        page_size=1000,
    ),
    _src(
        "nh_granit_parcels",
        "New Hampshire GRANIT Parcel Mosaic (1ac+)",
        "https://nhgeodata.unh.edu/hosting/rest/services/Hosted/CAD_ParcelMosaic/FeatureServer/1/query",
        "NH",
        _norm_nh_granit,
        where="1=1",
        shard=True,
        objectid_max=800_000,
        page_size=1000,
    ),
    _src(
        "az_asld_trust",
        "Arizona State Trust Land Parcels",
        "https://server.azgeo.az.gov/arcgis/rest/services/azland/State_Trust_Parcels/FeatureServer/0/query",
        "AZ",
        _norm_az_asld,
        where="acres>=1 AND acres<=2500",
        page_size=1000,
    ),
    _src(
        "ca_sb_vacant",
        "San Bernardino CA Vacant Land (1ac+)",
        "https://services.arcgis.com/aA3snZwJfFkVyDuP/arcgis/rest/services/Parcels_for_San_Bernardino_County/FeatureServer/0/query",
        "CA",
        _norm_ca_sb_vacant,
        where="ImprovementValue=0 AND Acreage>=1 AND Acreage<=2500 AND LandValue>0",
        shard=True,
        objectid_max=1_500_000,
        page_size=1000,
    ),
    _src(
        "ok_okc_parcels",
        "Oklahoma County Parcels (1ac+)",
        "https://services8.arcgis.com/euhkr1dAJeQBIjV0/arcgis/rest/services/TaxParcelsPublics_view/FeatureServer/0/query",
        "OK",
        _norm_ok_okc,
        where="acres>=1 AND acres<=2500",
        shard=True,
        objectid_max=500_000,
        page_size=1000,
    ),
    _src(
        "nv_washoe_parcels",
        "Washoe County NV Parcels (1ac+)",
        "https://wcgisweb.washoecounty.us/arcgis/rest/services/OpenData/OpenData/MapServer/0/query",
        "NV",
        _norm_nv_washoe,
        where="ACREAGE>=1 AND ACREAGE<=2500",
        shard=True,
        objectid_max=400_000,
        page_size=1000,
    ),
    _src(
        "de_kent_parcels",
        "Kent County DE Parcels (1ac+)",
        "https://gis.kentcountyde.gov/server/rest/services/Parcels/Parcels/FeatureServer/0/query",
        "DE",
        _norm_de_kent,
        where="DEEDACREAGE>=1 AND DEEDACREAGE<=2500 AND (IMPROVE IS NULL OR IMPROVE=0)",
        page_size=1000,
    ),
    _src(
        "wy_sheridan_parcels",
        "Sheridan County WY Parcels (1ac+)",
        "https://services5.arcgis.com/V4b98G4pSkzvUam9/arcgis/rest/services/Parcels/FeatureServer/0/query",
        "WY",
        _norm_wy_sheridan,
        where="ACRES>=1 AND ACRES<=2500",
        page_size=1000,
    ),
    _src(
        "nd_cass_parcels",
        "Cass County ND Parcels (1ac+)",
        "https://gisweb.casscountynd.gov/arcgis/rest/services/Public/CountyParcels/MapServer/0/query",
        "ND",
        _norm_nd_cass,
        where="ACRES>=1 AND ACRES<=2500",
        page_size=1000,
    ),
    _src(
        "sd_minnehaha_parcels",
        "Minnehaha County SD Parcels (1ac+)",
        "https://gis.minnehahacounty.gov/minnemap/rest/services/Parcels/MapServer/0/query",
        "SD",
        _norm_sd_minnehaha,
        where="TOTAL_ACREAGE>=1 AND TOTAL_ACREAGE<=2500",
        page_size=1000,
    ),
    _src(
        "ms_hinds_vacant",
        "Hinds County MS Vacant Land (1ac+)",
        "https://opcgis.deq.state.ms.us/opcgis/rest/services/Government/HINDS_PARCELS/MapServer/0/query",
        "MS",
        _norm_ms_hinds,
        where="(IMPVAL1 IS NULL OR IMPVAL1=0) AND GISACRES>=1 AND GISACRES<=2500 AND LANDVAL>0",
        page_size=1000,
    ),
    _src(
        "or_multnomah_lots",
        "Multnomah County OR Tax Lots",
        "https://services3.arcgis.com/tNPgIZWOB0Efvm0g/ArcGIS/rest/services/Tax_Lots/FeatureServer/0/query",
        "OR",
        _norm_or_multnomah,
        where="1=1",
        shard=True,
        objectid_max=200_000,
        page_size=1000,
    ),
    _src(
        "ga_gwinnett_parcels",
        "Gwinnett County GA Parcels",
        "https://services3.arcgis.com/RfpmnkSAQleRbndX/arcgis/rest/services/Property_and_Tax/FeatureServer/3/query",
        "GA",
        _norm_ga_gwinnett,
        where="(DWLGVAL1 IS NULL OR DWLGVAL1=0) AND LANDVAL1>0",
        shard=True,
        objectid_max=500_000,
        page_size=1000,
    ),
    _src(
        "il_kane_parcels",
        "Kane County IL Parcels (1ac+)",
        "https://gistech.countyofkane.org/arcgis/rest/services/KanePINList/MapServer/0/query",
        "IL",
        _norm_il_kane,
        where="RecordedAcreage>=1 AND RecordedAcreage<=2500",
        page_size=1000,
    ),
    _src(
        "mo_jackson_parcels",
        "Jackson County MO Parcels",
        "https://gis.mijackson.org/countygis/rest/services/RealEstate/RealEstateParcels/FeatureServer/0/query",
        "MO",
        _norm_mo_jackson,
        where="P_ACREAGE>=1 AND P_ACREAGE<=2500",
        page_size=1000,
    ),
    _src(
        "nm_ose_bernalillo",
        "New Mexico OSE Bernalillo Vacant",
        "https://gis.ose.nm.gov/server_s/rest/services/Parcels/County_Parcels_2025/MapServer/0/query",
        "NM",
        _norm_nm_ose,
        where="StructureCount=0",
        shard=True,
        objectid_max=400_000,
        page_size=1000,
    ),
    _src(
        "pa_pasda_parcels",
        "Pennsylvania PASDA Parcel Composite",
        "https://apps.pasda.psu.edu/arcgis/rest/services/PA_Parcels/MapServer/1/query",
        "PA",
        _norm_pa_pasda,
        where="1=1",
        shard=True,
        objectid_max=5_000_000,
        page_size=1000,
    ),
    _src(
        "al_jefferson_parcels",
        "Jefferson County AL Parcels (1ac+)",
        "https://jccgis.jccal.org/server/rest/services/Basemap/Parcels/MapServer/0/query",
        "AL",
        _norm_al_jefferson,
        where="1=1",
        shard=True,
        objectid_max=600_000,
        page_size=1000,
    ),
    _src(
        "mi_oakland_parcels",
        "Oakland County MI Parcels (1ac+)",
        "https://gisservices.oakgov.com/arcgis/rest/services/Enterprise/EnterpriseOpenParcelDataMapService/MapServer/1/query",
        "MI",
        _norm_mi_oakland,
        where="1=1",
        shard=True,
        objectid_max=700_000,
        page_size=1000,
    ),
    _src(
        "ri_tax_parcels",
        "Rhode Island Tax Parcels (1ac+ low-imp)",
        "https://risegis.ri.gov/hosting/rest/services/RIDEM/Tax_Parcels/MapServer/0/query",
        "RI",
        _norm_ri_tax_parcels,
        where="Acres>=1 AND Acres<=2500 AND (PctImp IS NULL OR PctImp<=8)",
        shard=True,
        objectid_max=400_000,
        page_size=1000,
    ),
    _src(
        "sc_horry_vacant",
        "Horry County SC Vacant Land (1ac+)",
        "https://www.horrycounty.org/gispublic/rest/services/Public/HorryCountyGIS_GS/MapServer/24/query",
        "SC",
        _norm_sc_horry_vacant,
        where="(MarketImprv IS NULL OR MarketImprv=0) AND MarketLand>0 AND Acreage>=1 AND Acreage<=2500",
        shard=True,
        objectid_max=300_000,
        page_size=1000,
    ),
    _src(
        "sc_berkeley_vacant",
        "Berkeley County SC Vacant Land (1ac+)",
        "https://gis.berkeleycountysc.gov/arcgis/rest/services/custom/Addr_muni/MapServer/1/query",
        "SC",
        _norm_sc_berkeley_vacant,
        where="(BuildingMarket IS NULL OR BuildingMarket=0) AND LandMarket>0 AND TotalAcres>=1 AND TotalAcres<=2500",
        shard=True,
        objectid_max=250_000,
        page_size=1000,
    ),
    _src(
        "la_brla_parcels",
        "East Baton Rouge LA Parcels (0.25ac+)",
        "https://maps.brla.gov/gis/rest/services/Cadastral/Tax_Parcel/MapServer/0/query",
        "LA",
        _norm_la_brla_parcels,
        # Layer has no usable OBJECTID windows — page by offset; skip placeholder 000-* rows in norm.
        # outFields=* returns 0 features on this MapServer — must list fields.
        where="ASSESSMENT_NUM NOT LIKE '000-%'",
        page_size=500,
        out_fields=(
            "ID,ASSESSMENT_NUM,OWNER,PHYSICAL_ADDRESS,SUM_LAND_VALUE,SUM_LOT_VALUE,"
            "SUM_IMPROVEMENT_VALUE,SUM_FAIR_MARKET_VALUE,STATUS"
        ),
    ),
    _src(
        "la_orleans_parcels",
        "Orleans Parish LA Parcels (0.25ac+)",
        "https://gis.nola.gov/arcgis/rest/services/apps/property3/MapServer/15/query",
        "LA",
        _norm_la_orleans_parcels,
        where="1=1",
        page_size=500,
        out_fields=(
            "OBJECTID,PARCELID,TAXBILLID,PARID,SITEADDRESS,OWNERNME1,UNIT,USECD,ASS_SQFT"
        ),
    ),
]
