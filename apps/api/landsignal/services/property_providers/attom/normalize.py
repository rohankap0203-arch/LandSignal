"""Normalize ATTOM Property API payloads into LandSignal licensed-field records."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from landsignal.services.property_providers import (
    ListingVerification,
    MarketStatus,
    PersistencePolicy,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def licensed_field(
    value: Any,
    *,
    source: str = "ATTOM",
    as_of: str | None = None,
    confidence: str = "reported",
    ttl_seconds: int = 82_800,
) -> dict[str, Any]:
    now = _utcnow()
    return {
        "value": value,
        "source": source,
        "asOfDate": as_of or now.date().isoformat(),
        "confidence": confidence if value is not None else "unavailable",
        "retrievedAt": now.isoformat(),
        "expiresAt": (now + timedelta(seconds=min(ttl_seconds, 86400))).isoformat(),
        "persistencePolicy": PersistencePolicy.TEMPORARY_LICENSED.value,
        "licenseClass": "ATTOM_API",
        "dataSource": source,
    }


def _first_prop(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    props = payload.get("property") or []
    if isinstance(props, list) and props:
        return props[0] if isinstance(props[0], dict) else {}
    return {}


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def extract_acreage(lot: dict[str, Any] | None) -> float | None:
    """ATTOM lotSize1 / lotsize1 is acres; lotSize2 / lotsize2 is sqft."""
    lot = lot or {}
    acres = _num(lot.get("lotSize1") if lot.get("lotSize1") is not None else lot.get("lotsize1"))
    if acres is not None and acres > 0:
        return acres
    sqft = _num(lot.get("lotSize2") if lot.get("lotSize2") is not None else lot.get("lotsize2"))
    if sqft is not None and sqft > 0:
        return sqft / 43560.0
    return None


def detect_structure(summary: dict[str, Any], building: dict[str, Any]) -> dict[str, Any]:
    summary = summary or {}
    building = building or {}
    size = building.get("size") or {}
    rooms = building.get("rooms") or {}
    bsum = building.get("summary") or {}
    sqft = _num(size.get("livingsize") or size.get("bldgsize") or size.get("universalsize"))
    beds = _num(rooms.get("beds"))
    baths = _num(rooms.get("bathstotal") or rooms.get("bathsfull"))
    year_built = _num(summary.get("yearbuilt") or bsum.get("yearbuilteffective"))
    n_struct = _num(bsum.get("bldgsNum") or bsum.get("buildings"))
    propclass = str(summary.get("propclass") or summary.get("propertyType") or "")
    has = bool(
        (sqft and sqft > 0)
        or (beds and beds > 0)
        or (n_struct and n_struct > 0)
        or any(x in propclass.lower() for x in ("residence", "sfr", "house", "dwelling", "cabin", "farm"))
    )
    return {
        "hasStructure": has,
        "structureType": summary.get("proptype") or summary.get("propsubtype") or summary.get("propclass"),
        "yearBuilt": year_built,
        "buildingSqFt": sqft,
        "bedrooms": beds,
        "bathrooms": baths,
        "numberOfStructures": n_struct or (1 if has else 0),
    }


def normalize_property_detail(payload: dict[str, Any], *, ttl_seconds: int = 82_800) -> dict[str, Any]:
    p = _first_prop(payload)
    ident = p.get("identifier") or {}
    addr = p.get("address") or {}
    loc = p.get("location") or {}
    lot = p.get("lot") or {}
    summary = p.get("summary") or {}
    building = p.get("building") or {}
    utilities = p.get("utilities") or {}
    vintage = p.get("vintage") or {}

    acres = extract_acreage(lot)
    structure = detect_structure(summary, building)
    as_of = vintage.get("lastModified") or vintage.get("pubDate")

    def L(v: Any, conf: str = "reported") -> dict[str, Any]:
        return licensed_field(v, as_of=as_of, confidence=conf if v is not None else "unavailable", ttl_seconds=ttl_seconds)

    return {
        "attomId": ident.get("attomId") or ident.get("Id") or ident.get("obPropId"),
        "apn": ident.get("apn") or ident.get("apnOrig"),
        "fips": ident.get("fips"),
        "geoId": loc.get("geoid") or loc.get("geoIdV4") or loc.get("geoId"),
        "address": L(addr.get("oneLine") or addr.get("line1")),
        "city": L(addr.get("locality") or addr.get("city")),
        "county": L(addr.get("countrysecsubd") or (p.get("area") or {}).get("countrysecsubd")),
        "state": L((addr.get("countrySubd") or addr.get("state") or "").upper()[:2] or None),
        "zip": L(addr.get("postal1") or addr.get("postalcode")),
        "latitude": L(_num(loc.get("latitude"))),
        "longitude": L(_num(loc.get("longitude"))),
        "acreage": L(acres, "reported" if acres is not None else "unavailable"),
        "lotSqFt": L(_num(lot.get("lotSize2") or lot.get("lotsize2"))),
        "frontage": L(_num(lot.get("frontage"))),
        "depth": L(_num(lot.get("depth"))),
        "lotType": L(lot.get("lottype") or lot.get("lotType")),
        "landUse": L(summary.get("propLandUse") or summary.get("propclass")),
        "propertyClass": L(summary.get("propclass")),
        "propertySubtype": L(summary.get("propsubtype") or summary.get("proptype")),
        "propertyType": L(summary.get("propertyType") or summary.get("proptype")),
        "utilities": L(utilities if utilities else None),
        "hasStructure": structure["hasStructure"],
        "structureType": L(structure["structureType"]),
        "yearBuilt": L(structure["yearBuilt"]),
        "buildingSqFt": L(structure["buildingSqFt"]),
        "bedrooms": L(structure["bedrooms"]),
        "bathrooms": L(structure["bathrooms"]),
        "numberOfStructures": L(structure["numberOfStructures"]),
        # ATTOM parcel ≠ for-sale listing
        "marketStatus": MarketStatus.OFF_MARKET.value,
        "listingVerification": ListingVerification.UNVERIFIED.value,
        "availabilityStatus": "OFF-MARKET PROPERTY",
        "askingPrice": None,
        "sources": ["ATTOM"],
        "raw_keys": sorted(p.keys()),
    }


def normalize_assessment(payload: dict[str, Any], *, ttl_seconds: int = 82_800) -> dict[str, Any]:
    p = _first_prop(payload)
    assessment = p.get("assessment") or {}
    market = assessment.get("market") or {}
    assessed = assessment.get("assessed") or {}
    tax = p.get("tax") or assessment.get("tax") or {}
    return {
        "marketValue": licensed_field(_num(market.get("mktttlvalue") or market.get("mktTtlValue")), ttl_seconds=ttl_seconds),
        "assessedValue": licensed_field(
            _num(assessed.get("assdttlvalue") or assessed.get("assdTtlValue")), ttl_seconds=ttl_seconds
        ),
        "taxAmount": licensed_field(_num(tax.get("taxamt") or tax.get("taxAmt")), ttl_seconds=ttl_seconds),
        "taxYear": licensed_field(tax.get("taxyear") or tax.get("taxYear"), ttl_seconds=ttl_seconds),
        "sources": ["ATTOM"],
    }


def normalize_sale_history(payload: dict[str, Any], *, ttl_seconds: int = 82_800) -> dict[str, Any]:
    p = _first_prop(payload)
    sales = p.get("salehistory") or p.get("saleHistory") or p.get("sale") or []
    if isinstance(sales, dict):
        sales = [sales]
    hist = []
    for s in sales if isinstance(sales, list) else []:
        if not isinstance(s, dict):
            continue
        amount = s.get("amount") or {}
        hist.append(
            {
                "saleAmount": licensed_field(_num(amount.get("saleamt") or amount.get("saleAmt")), ttl_seconds=ttl_seconds),
                "saleDate": licensed_field(s.get("saleTransDate") or s.get("salesearchdate") or amount.get("salerecdate"), ttl_seconds=ttl_seconds),
                "saleType": licensed_field(amount.get("saletranstype") or s.get("saleTransType"), ttl_seconds=ttl_seconds),
            }
        )
    last = hist[0] if hist else {}
    return {
        "sales": hist,
        "lastSaleAmount": last.get("saleAmount"),
        "lastSaleDate": last.get("saleDate"),
        # Critical: historical sale is NOT asking price
        "askingPrice": None,
        "marketStatus": MarketStatus.SOLD.value if hist else MarketStatus.OFF_MARKET.value,
        "sources": ["ATTOM"],
    }


def normalize_avm(payload: dict[str, Any], *, ttl_seconds: int = 82_800) -> dict[str, Any]:
    p = _first_prop(payload)
    avm = p.get("avm") or {}
    amount = avm.get("amount") or {}
    return {
        "avmValue": licensed_field(_num(amount.get("value") or amount.get("valueLow")), ttl_seconds=ttl_seconds),
        "avmHigh": licensed_field(_num(amount.get("valueHigh")), ttl_seconds=ttl_seconds),
        "avmLow": licensed_field(_num(amount.get("valueLow")), ttl_seconds=ttl_seconds),
        "avmScore": licensed_field(_num(avm.get("eventScore") or avm.get("score")), ttl_seconds=ttl_seconds),
        "sources": ["ATTOM"],
    }


def normalize_owner(payload: dict[str, Any], *, ttl_seconds: int = 82_800) -> dict[str, Any]:
    p = _first_prop(payload)
    owner = p.get("owner") or {}
    # detailowner variants
    owner1 = owner.get("owner1") if isinstance(owner.get("owner1"), dict) else {}
    name = (
        owner.get("fullnameName")
        or owner.get("owner1full")
        or owner1.get("fullnameName")
        or owner.get("fullnamename")
    )
    mailing = owner.get("mailingaddressoneLine") or owner.get("mailingAddressOneLine") or owner.get("absenteeOwner")
    return {
        "ownerName": licensed_field(name, ttl_seconds=ttl_seconds, confidence="reported" if name else "unavailable"),
        "ownerMailingAddress": licensed_field(mailing, ttl_seconds=ttl_seconds),
        "ownerType": licensed_field(owner.get("ownerType") or owner.get("ownertype"), ttl_seconds=ttl_seconds),
        "phone": licensed_field(None, confidence="unavailable", ttl_seconds=ttl_seconds),  # never fabricate
        "email": licensed_field(None, confidence="unavailable", ttl_seconds=ttl_seconds),
        "contactUnavailableReason": None if name else "Contact information unavailable",
        "sources": ["ATTOM"],
    }


def normalize_id_search(payload: dict[str, Any], *, ttl_seconds: int = 82_800) -> list[dict[str, Any]]:
    props = (payload or {}).get("property") or []
    out: list[dict[str, Any]] = []
    for p in props if isinstance(props, list) else []:
        if not isinstance(p, dict):
            continue
        ident = p.get("identifier") or {}
        loc = p.get("location") or {}
        addr = p.get("address") or {}
        lot = p.get("lot") or {}
        out.append(
            {
                "attomId": ident.get("attomId") or ident.get("Id"),
                "apn": ident.get("apn"),
                "fips": ident.get("fips"),
                "latitude": _num(loc.get("latitude")),
                "longitude": _num(loc.get("longitude")),
                "address": addr.get("oneLine"),
                "state": (addr.get("countrySubd") or addr.get("state") or "").upper()[:2] or None,
                "county": addr.get("countrysecsubd"),
                "acreage": extract_acreage(lot),
                "marketStatus": MarketStatus.OFF_MARKET.value,
                "listingVerification": ListingVerification.UNVERIFIED.value,
                "availabilityStatus": "OFF-MARKET PROPERTY",
                "sources": ["ATTOM"],
                "persistencePolicy": PersistencePolicy.TEMPORARY_LICENSED.value,
            }
        )
    return out
