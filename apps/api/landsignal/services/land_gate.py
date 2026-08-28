"""Inventory gate: vacant land vs property-on-site vs non-land junk.

LandSignal sells land intelligence. Rural homes / cottages / ranch houses are
allowed into inventory only when flagged as property-on-site so they can live
under the "Property on site" strategy — never as fake vacant-land bargains.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

_STREET_NUMBERED = re.compile(
    r"(?:^|[·\-–—,:]\s*)\d{1,6}\s+[A-Za-z.#]",
    re.I,
)
_LAND_HINT = re.compile(
    r"\b("
    r"vacant|unimproved|acreage|farm(?:land)?|timber|ag(?:ricultural)?|"
    r"pasture|ranch|tract|raw land|open land|land bank|surplus land|"
    r"forfeit(?:ed)? land|tax.?lien land|undeveloped|no building|"
    r"lot only|vacant lot|vacant land|unassigned|outlot|acre\b"
    r")\b",
    re.I,
)
# Real dwelling / ranch house on the dirt — bucket as Property on site.
_STRUCTURE_ON_SITE = re.compile(
    r"\b("
    r"home\b|house\b|cottage|cabin|dwelling|residence|sfr\b|"
    r"single[\s-]?family|farmhouse|ranch house|homestead|"
    r"mobile home|manufactured home|modular home|bungalow|"
    r"villa|chalet|lodge\b|barndominium|guest house|guest house|"
    r"with (?:a )?home|with (?:a )?house|with (?:a )?cabin|"
    r"improved|improvements|living area|bedrooms?"
    r")\b",
    re.I,
)
# Never inventory — urban / commercial buildings, not land plays.
_NON_LAND_PRODUCT = re.compile(
    r"\b("
    r"condo|condominium|apartment|duplex|triplex|townhome|townhouse|"
    r"hotel|motel|warehouse|office building|retail|restaurant|church|"
    r"school|hospital|industrial building|multi-?family|"
    r"shopping|strip mall|plaza\b"
    r")\b",
    re.I,
)

_IMPROVEMENT_KEYS = (
    "IMPRVT_VAL",
    "impr_value",
    "IMPROVEMENT_VALUE",
    "ImprovementValue",
    "improvement_value",
    "NFMIMPVL",
    "BLDG_VAL",
    "BldgVal",
    "BuildingValue",
    "building_value",
    "TOT_LVG_AR",
    "LivingArea",
    "living_area",
    "Houses",
    "building_count",
    "BLDG_COUNT",
    "RES_BLDG_COUNT",
    "bldg_sqft",
    "BuildingSqFt",
    "buildingSqFt",
    "Beds",
    "bedrooms",
    "Bedrooms",
)


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        n = float(v)
        return n if n == n else None
    except (TypeError, ValueError):
        return None


def _raw_improved(raw: Mapping[str, Any] | None) -> bool:
    if not isinstance(raw, dict) or not raw:
        return False
    if raw.get("has_structure") is True or raw.get("hasStructure") is True:
        return True
    if "bldg_no" in raw and raw.get("bldg_no") not in (None, "", 0, "0"):
        addr = str(raw.get("Address") or raw.get("address") or "").strip()
        if addr:
            return True
    for key in _IMPROVEMENT_KEYS:
        n = _f(raw.get(key))
        if n is not None and n > 0:
            return True
    return False


def detect_property_on_site(
    *,
    title: str | None = None,
    description: str | None = None,
    address: str | None = None,
    raw: Mapping[str, Any] | None = None,
) -> bool:
    """True when a real home / cottage / ranch house / etc. sits on the parcel."""
    if isinstance(raw, dict):
        if raw.get("has_structure") is True or raw.get("hasStructure") is True:
            return True
        if _raw_improved(raw):
            return True
    blob = f"{title or ''} {description or ''} {address or ''}"
    if _STRUCTURE_ON_SITE.search(blob):
        # "ranch" alone is land; "ranch house" / "home on ranch" hits structure regex.
        return True
    return False


def is_non_land_product(
    *,
    title: str | None = None,
    description: str | None = None,
    address: str | None = None,
) -> bool:
    blob = f"{title or ''} {description or ''} {address or ''}"
    return bool(_NON_LAND_PRODUCT.search(blob))


def is_land_inventory(
    *,
    provider_id: str | None,
    title: str | None = None,
    description: str | None = None,
    address: str | None = None,
    acreage: float | None = None,
    raw: Mapping[str, Any] | None = None,
) -> bool:
    """Eligible for LandSignal inventory (vacant land OR flagged property-on-site).

    Urban condos / apartments / commercial buildings are still rejected.
    Homes on acreage are allowed so "Property on site" can surface them —
    radar hard-excludes them unless that strategy is selected.
    """
    provider = str(provider_id or "").strip()
    acres = _f(acreage)
    title_s = str(title or "").strip()
    desc_s = str(description or "").strip()
    addr_s = str(address or "").strip()
    blob = f"{title_s} {desc_s} {addr_s}"

    if acres is not None and (acres < 0.05 or acres > 50_000):
        return False

    # Never take condo / multi-family / commercial building inventory.
    if is_non_land_product(title=title_s, description=desc_s, address=addr_s):
        return False

    on_site = detect_property_on_site(
        title=title_s, description=desc_s, address=addr_s, raw=raw
    )

    # Property-on-site: keep rural / tax-sale / surplus homes for the dedicated strategy.
    if on_site:
        if provider in {"blm_lpad"}:
            # BLM disposals are land only — a "house" in the title is almost always noise.
            return False if acres is not None and acres < 1.0 else (acres is None or acres >= 1.0)
        if provider == "public_vacant_gis":
            # Vacant GIS claiming a dwelling: keep for Property on site if acreage looks rural.
            return acres is None or acres >= 0.5
        if provider in {"public_tax_sale", "public_surplus", "manual", ""}:
            return True if acres is None else acres >= 0.25
        return acres is None or acres >= 0.5

    # Federal BLM disposals and statewide vacant GIS screens are already land-oriented.
    if provider in {"blm_lpad", "public_vacant_gis"}:
        return True if acres is None else acres >= 0.1

    landish = bool(_LAND_HINT.search(f"{title_s} {addr_s}"))
    numbered = bool(
        _STREET_NUMBERED.search(title_s)
        or _STREET_NUMBERED.search(addr_s)
        or (addr_s[:1].isdigit() and re.search(r"\d+\s+[A-Za-z]", addr_s))
    )

    # Tax sale / surplus / manual: numbered street addresses are usually buildings.
    # Allow only large rural acreage, or an explicit land cue in the title/address.
    if provider in {"public_tax_sale", "public_surplus", "manual", ""}:
        if numbered and not landish and (acres is None or acres < 5.0):
            return False
        if acres is not None and acres < 1.0 and not landish:
            return False
        return True

    if acres is not None and acres < 0.5 and numbered and not landish:
        return False
    return True


def stamp_structure_flags(raw: dict[str, Any] | None, *, title: str | None = None, description: str | None = None, address: str | None = None) -> dict[str, Any]:
    """Return a raw dict with has_structure stamped for downstream radar/scoring."""
    out = dict(raw or {})
    on_site = detect_property_on_site(
        title=title, description=description, address=address, raw=out
    )
    out["has_structure"] = bool(on_site)
    if on_site and not out.get("structure_label"):
        out["structure_label"] = "Property on site"
    return out


def listing_has_structure(listing: Any, parcel: Any | None = None) -> bool:
    raw = getattr(listing, "raw", None)
    if not isinstance(raw, dict):
        raw = {}
    addr = getattr(parcel, "address", None) if parcel is not None else None
    if not addr:
        addr = raw.get("address") or raw.get("Address")
    return detect_property_on_site(
        title=getattr(listing, "title", None),
        description=getattr(listing, "description", None),
        address=addr,
        raw=raw,
    )


def listing_is_land(listing: Any, parcel: Any | None = None) -> bool:
    """Convenience wrapper for store ListingRecord / ParcelRecord objects."""
    raw = getattr(listing, "raw", None)
    if not isinstance(raw, dict):
        raw = {}
    acres = getattr(parcel, "acreage", None) if parcel is not None else None
    if acres is None:
        acres = raw.get("acreage")
    addr = getattr(parcel, "address", None) if parcel is not None else None
    if not addr:
        addr = getattr(listing, "address", None) if hasattr(listing, "address") else raw.get("address")
    return is_land_inventory(
        provider_id=getattr(listing, "provider_id", None) or raw.get("provider_id"),
        title=getattr(listing, "title", None),
        description=getattr(listing, "description", None),
        address=addr,
        acreage=acres,
        raw=raw,
    )


def purge_non_land_from_store(store: Any) -> int:
    """Drop non-land live parcels from the in-memory store. Returns removed count."""
    drop: list[Any] = []
    for pid, parcel in list(getattr(store, "parcels", {}).items()):
        if getattr(parcel, "is_demo", False):
            continue
        listing = store.listing_for_parcel(pid)
        if listing is None:
            continue
        if listing_is_land(listing, parcel):
            continue
        drop.append(pid)

    for pid in drop:
        listing = store.listing_for_parcel(pid)
        if listing is not None:
            ext = (str(getattr(listing, "provider_id", "") or ""), str(getattr(listing, "external_id", "") or ""))
            store.listings.pop(getattr(listing, "id", None), None)
            by_ext = getattr(store, "_listing_id_by_external", None)
            if isinstance(by_ext, dict) and ext[0] and ext[1]:
                by_ext.pop(ext, None)
        store.parcels.pop(pid, None)
        store.scores.pop(pid, None)
        store.enrichments.pop(pid, None)
        store.dd_items.pop(pid, None)
        store.watch_snapshots.pop(pid, None)
        by_parcel = getattr(store, "_listing_id_by_parcel", None)
        if isinstance(by_parcel, dict):
            by_parcel.pop(pid, None)
        for wl in getattr(store, "watchlists", {}).values():
            items = getattr(wl, "parcel_ids", None)
            if isinstance(items, list) and pid in items:
                items.remove(pid)
    return len(drop)
