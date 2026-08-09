"""Shared plain-English voice helpers — never lead with raw parcel IDs."""

from __future__ import annotations

from typing import Any


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def place_phrase(parcel) -> str:
    county = (getattr(parcel, "county", None) if parcel else None) or None
    state = (getattr(parcel, "state", None) if parcel else None) or None
    if county and state:
        return f"{county}, {state}"
    if state:
        return str(state)
    if county:
        return str(county)
    return "this area"


def this_property(parcel=None, listing=None, *, with_place: bool = False, with_acres: bool = False) -> str:
    """Human label for copy. Prefer 'this property' — never lead with APN digits."""
    acres = _f(getattr(parcel, "acreage", None) if parcel else None)
    place = place_phrase(parcel) if parcel else ""
    bits: list[str] = []
    if with_acres and acres is not None:
        bits.append(f"this {acres:,.1f}-acre property")
    else:
        bits.append("this property")
    if with_place and place and place != "this area":
        bits.append(f"in {place}")
    return " ".join(bits)


def display_title(parcel=None, listing=None) -> str:
    """Card/page title without raw APN strings."""
    import re

    raw = (getattr(listing, "title", None) if listing else None) or ""
    cleaned = re.sub(r"\bAPN\s*[:#]?\s*[\w./-]+", "", str(raw), flags=re.I)
    cleaned = re.sub(r"\b\d{7,}\b", "", cleaned)
    cleaned = re.sub(r"\s*[·|\-]\s*", " · ", cleaned)
    cleaned = re.sub(r"(?:\s*·\s*)+", " · ", cleaned).strip(" ·")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if cleaned and not re.fullmatch(r"[\d.\-]+", cleaned):
        return cleaned[:90]
    acres = _f(getattr(parcel, "acreage", None) if parcel else None)
    place = place_phrase(parcel)
    size = f"{acres:,.1f}-acre " if acres is not None else ""
    provider = getattr(listing, "provider_id", None) if listing else None
    channel = {
        "public_tax_sale": "Tax-sale land",
        "public_surplus": "Surplus land",
        "blm_lpad": "Federal BLM land",
    }.get(provider or "", "Land")
    return f"{channel}: {size}property in {place}".replace("  ", " ")


def strip_apn_mentions(text: str) -> str:
    """Replace bare long digit IDs / 'APN …' with 'this property' in prose."""
    import re

    if not text:
        return text
    out = re.sub(r"\bAPN\s*[:#]?\s*[\w./-]+", "this property", text, flags=re.I)
    out = re.sub(r"\bParcel\s+ID\s*[:#]?\s*[\w./-]+", "this property", out, flags=re.I)
    out = re.sub(r"\bID\s+\d{6,}\b", "this property", out, flags=re.I)
    # Bare assessor-style numbers when used as a noun phrase
    out = re.sub(r"\b(?:parcel|listing)\s+\d{6,}\b", "this property", out, flags=re.I)
    out = re.sub(r"\bfor\s+\d{6,}(\s|\.|\,)", r"for this property\1", out, flags=re.I)
    out = re.sub(r"\bon\s+\d{6,}(\s|\.|\,)", r"on this property\1", out, flags=re.I)
    out = re.sub(r"\b\d{8,}(?:\.\d+)?\b", "this property", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()
