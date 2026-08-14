"""Pull listing hints from URL path/query when HTML is blocked or thin."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlparse

_STATE_NAMES = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new-hampshire": "NH",
    "newhampshire": "NH",
    "new-jersey": "NJ",
    "newjersey": "NJ",
    "new-mexico": "NM",
    "newmexico": "NM",
    "new-york": "NY",
    "newyork": "NY",
    "north-carolina": "NC",
    "northcarolina": "NC",
    "north-dakota": "ND",
    "northdakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode-island": "RI",
    "rhodeisland": "RI",
    "south-carolina": "SC",
    "southcarolina": "SC",
    "south-dakota": "SD",
    "southdakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west-virginia": "WV",
    "westvirginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district-of-columbia": "DC",
}

_ACRES_RE = re.compile(
    r"(?P<acres>\d+(?:\.\d+)?)\s*[-_]?(?:\+)?\s*(?:acres?|ac)\b",
    re.I,
)
_PRICE_RE = re.compile(
    r"(?:\$|price[_-]?)(?P<price>\d{2,3}(?:,\d{3})+|\d{4,9})|(?P<price2>\d{2,3}(?:,\d{3}){1,2})\s*(?:usd)?",
    re.I,
)
_STATE_ABBR_RE = re.compile(r"(?:^|[^a-z])(?P<st>A[LKZR]|C[AOT]|D[EC]|F[LM]|G[AU]|HI|I[ADLN]|K[SY]|L[A]|M[ADEHINOST]|N[CDEHJMVY]|O[HKR]|P[A]|RI|S[CD]|T[NX]|UT|V[AIT]|W[AIVY])(?:[^a-z]|$)", re.I)
_ZILLOW_ADDR_RE = re.compile(
    r"/homedetails/(?P<slug>[^/]+)/\d+_zpid",
    re.I,
)
_COUNTY_PREFIXES = {
    "san",
    "santa",
    "los",
    "las",
    "la",
    "el",
    "de",
    "del",
    "new",
    "west",
    "east",
    "north",
    "south",
    "st",
    "saint",
}


def _county_from_blob(blob: str) -> str | None:
    """Parse '...-riverside-county-...' / '...-san-bernardino-county-...' from URL slugs."""
    parts = re.split(r"[^a-z0-9]+", blob.lower())
    junk = {"the", "a", "an", "in", "for", "sale", "acres", "acre", "land", "property", "listing"}
    for i, p in enumerate(parts):
        if p != "county" or i == 0:
            continue
        prev = parts[i - 1]
        if not prev or prev in junk or prev.isdigit():
            continue
        if i >= 2 and parts[i - 2] in _COUNTY_PREFIXES:
            return f"{parts[i - 2]} {prev}".title()
        return prev.title()
    return None


def _title_from_slug(slug: str) -> str:
    cleaned = re.sub(r"[-_]+", " ", slug).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:160].title() if cleaned else ""


def extract_from_listing_url(url: str) -> dict[str, Any]:
    """Best-effort structured hints from the listing URL itself."""
    parsed = urlparse(url.strip())
    path = unquote(parsed.path or "")
    blob = f"{path}?{parsed.query}".lower().replace("_", "-")
    out: dict[str, Any] = {}

    m = _ACRES_RE.search(blob)
    if m:
        try:
            acres = float(m.group("acres"))
            if 0.1 <= acres <= 100_000:
                out["acreage"] = acres
        except ValueError:
            pass

    county = _county_from_blob(blob)
    if county:
        out["county"] = county

    # State from full name in path (prefer longer matches)
    state = None
    for name, abbr in sorted(_STATE_NAMES.items(), key=lambda x: -len(x[0])):
        if re.search(rf"(?:^|[^a-z]){re.escape(name)}(?:[^a-z]|$)", blob):
            state = abbr
            break
    if not state:
        sm = _STATE_ABBR_RE.search(path.replace("-", " "))
        if sm:
            state = sm.group("st").upper()
    if state:
        out["state"] = state

    # Zillow-style address slug
    zm = _ZILLOW_ADDR_RE.search(path)
    if zm:
        slug = zm.group("slug")
        parts = slug.split("-")
        # trailing state + zip often present
        if len(parts) >= 3 and parts[-1].isdigit() and len(parts[-1]) == 5:
            out.setdefault("zip", parts[-1])
            if len(parts[-2]) == 2:
                out.setdefault("state", parts[-2].upper())
                addr = " ".join(parts[:-2]).replace("  ", " ").title()
            else:
                addr = " ".join(parts[:-1]).title()
            out.setdefault("address", addr)
            out.setdefault("title", addr)
        else:
            out.setdefault("title", _title_from_slug(slug))
            out.setdefault("address", _title_from_slug(slug))

    # Land.com / LandWatch property slug title
    if not out.get("title"):
        segs = [s for s in path.split("/") if s]
        for seg in reversed(segs):
            if "acre" in seg.lower() or "county" in seg.lower() or len(seg) > 12:
                title = _title_from_slug(seg)
                if title and title.lower() not in {"property", "listing", "homedetails"}:
                    out["title"] = title
                    break

    return out
