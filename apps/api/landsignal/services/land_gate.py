"""Land-only inventory gate.

Live LandSignal inventory must be land / unimproved acreage — not urban
buildings that happen to appear on tax-sale calendars.
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
_BUILDING_HINT = re.compile(
    r"\b("
    r"condo|condominium|apartment|duplex|triplex|townhome|townhouse|"
    r"hotel|motel|warehouse|office building|retail|restaurant|church|"
    r"school|hospital|industrial building|multi-?family|dwelling|"
    r"single family|sfr\b|home\b|house\b|residence"
    r")\b",
    re.I,
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
    # Building street-number field used by Baltimore tax sale (None = no structure mark).
    if "bldg_no" in raw and raw.get("bldg_no") not in (None, "", 0, "0"):
        # Baltimore stores the house number here for improved lots; vacant lots are null.
        addr = str(raw.get("Address") or raw.get("address") or "").strip()
        if addr:
            return True
    for key in (
        "IMPRVT_VAL",
        "impr_value",
        "IMPROVEMENT_VALUE",
        "NFMIMPVL",
        "TOT_LVG_AR",
        "Houses",
        "building_count",
        "BLDG_COUNT",
        "RES_BLDG_COUNT",
    ):
        n = _f(raw.get(key))
        if n is not None and n > 0:
            return True
    return False


def is_land_inventory(
    *,
    provider_id: str | None,
    title: str | None = None,
    description: str | None = None,
    address: str | None = None,
    acreage: float | None = None,
    raw: Mapping[str, Any] | None = None,
) -> bool:
    """Return True only when the row is credible land / unimproved inventory."""
    provider = str(provider_id or "").strip()
    acres = _f(acreage)
    title_s = str(title or "").strip()
    desc_s = str(description or "").strip()
    addr_s = str(address or "").strip()
    blob = f"{title_s} {desc_s} {addr_s}"

    if acres is not None and (acres < 0.05 or acres > 50_000):
        return False

    if _raw_improved(raw):
        return False
    if _BUILDING_HINT.search(blob):
        return False

    # Federal BLM disposals and statewide vacant GIS screens are already land-oriented.
    if provider in {"blm_lpad", "public_vacant_gis"}:
        return True if acres is None else acres >= 0.1

    landish = bool(_LAND_HINT.search(f"{title_s} {addr_s}"))
    numbered = bool(
        _STREET_NUMBERED.search(title_s)
        or _STREET_NUMBERED.search(addr_s)
        or (addr_s[:1].isdigit() and re.search(r"\d+\s+[A-Za-z]", addr_s))
    )

    # Tax sale / surplus / manual: numbered street addresses under 1 acre are buildings.
    # Do not trust description boilerplate ("tax-forfeited land") to override that.
    if provider in {"public_tax_sale", "public_surplus", "manual", ""}:
        if numbered and (acres is None or acres < 1.0):
            return False
        # Sub-acre tax-sale rows need an explicit land cue in the title/address.
        if acres is not None and acres < 1.0 and not landish:
            return False
        return True

    # Unknown providers: keep only when acreage looks like land.
    if acres is not None and acres < 0.5 and numbered and not landish:
        return False
    return True


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
            if isinstance(wl, set):
                wl.discard(pid)
    return len(drop)
