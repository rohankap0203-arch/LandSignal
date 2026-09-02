"""Exhaustive listing-URL keyword / phrase / param screening.

When marketplace HTML is blocked, the pasted URL itself is often the best
structured signal (acres, county, state, city, lat/lon, price, APN).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

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
    "new hampshire": "NH",
    "new-hampshire": "NH",
    "newhampshire": "NH",
    "new jersey": "NJ",
    "new-jersey": "NJ",
    "newjersey": "NJ",
    "new mexico": "NM",
    "new-mexico": "NM",
    "newmexico": "NM",
    "new york": "NY",
    "new-york": "NY",
    "newyork": "NY",
    "north carolina": "NC",
    "north-carolina": "NC",
    "northcarolina": "NC",
    "north dakota": "ND",
    "north-dakota": "ND",
    "northdakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "rhode-island": "RI",
    "rhodeisland": "RI",
    "south carolina": "SC",
    "south-carolina": "SC",
    "southcarolina": "SC",
    "south dakota": "SD",
    "south-dakota": "SD",
    "southdakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "west-virginia": "WV",
    "westvirginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
    "district-of-columbia": "DC",
}

# Broad acreage patterns across slug / query / prose forms
_ACRES_PATTERNS = [
    re.compile(r"(?P<acres>\d+(?:\.\d+)?)\s*[\-_+/]?\s*(?:\+)?\s*(?:acres?|acrs?|ac)\b", re.I),
    re.compile(r"(?:acres?|acreage|lot[_-]?size|size|ac)[=:_/\-](?P<acres>\d+(?:\.\d+)?)", re.I),
    re.compile(r"(?P<acres>\d+(?:\.\d+)?)[\-_]?(?:acre)\b", re.I),  # 40-acre / 40acre
    re.compile(r"\b(?P<acres>\d+(?:\.\d+)?)ac\b", re.I),
]

_PRICE_PATTERNS = [
    re.compile(r"(?:asking|price|list[_-]?price|for[_-]?sale)[=:_/\-]?\$?\s*(?P<p>\d{1,3}(?:,\d{3})+|\d{4,9})", re.I),
    re.compile(r"\$\s*(?P<p>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,7}(?:\.\d+)?)", re.I),
]

_APN_PATTERNS = [
    re.compile(
        r"(?:apn|pin|parcel[_-]?id|parcel[_-]?num(?:ber)?|parcel[_-]?no)[=:_/\-](?P<apn>[A-Za-z0-9][A-Za-z0-9.\-]{3,30})",
        re.I,
    ),
    re.compile(r"\bapn[\-_:=\s]+(?P<apn>[A-Za-z0-9][A-Za-z0-9.\-]{3,30})\b", re.I),
]

_COORD_QUERY_KEYS = {
    "lat": "latitude",
    "latitude": "latitude",
    "y": "latitude",
    "lon": "longitude",
    "lng": "longitude",
    "long": "longitude",
    "longitude": "longitude",
    "x": "longitude",
}

_STATE_ABBR_RE = re.compile(
    r"(?:^|[^a-z])(?P<st>A[LKZR]|C[AOT]|D[EC]|F[LM]|G[AU]|HI|I[ADLN]|K[SY]|L[A]|M[ADEHINOST]|N[CDEHJMVY]|"
    r"O[HKR]|P[A]|RI|S[CD]|T[NX]|UT|V[AIT]|W[AIVY])(?:[^a-z]|$)",
    re.I,
)
_ZILLOW_ADDR_RE = re.compile(r"/homedetails/(?P<slug>[^/]+)/\d+_zpid", re.I)
_REALTOR_ADDR_RE = re.compile(
    r"/realestateandhomes-detail/(?P<slug>[^/]+?)(?:_M|_P|/|$)",
    re.I,
)
_REDFIN_ADDR_RE = re.compile(r"/[A-Z]{2}/(?P<city>[^/]+)/(?P<slug>[^/]+)/\d+/home/\d+", re.I)
_LL_PAIR_RE = re.compile(
    r"(?P<lat>[-+]?\d{1,2}\.\d{3,})[,/ ](?P<lon>[-+]?\d{1,3}\.\d{3,})"
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
_CITY_HINT_RE = re.compile(
    r"(?:^|[^a-z])(?:near|in|at)\s+(?P<city>[a-z][a-z\- ]{2,40?}?)(?:\s*,\s*|\s+)(?P<st>[a-z]{2}|[a-z\- ]+)(?:[^a-z]|$)",
    re.I,
)


def _title_from_slug(slug: str) -> str:
    cleaned = re.sub(r"[-_]+", " ", unquote(slug)).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:160].title() if cleaned else ""


def _full_text_blob(url: str) -> str:
    """Normalize the entire URL into a searchable keyword blob."""
    raw = unquote(url.strip())
    # Turn separators into spaces so keyword regexes can match across slug tokens
    spaced = re.sub(r"[?#&=+/_|]+", " ", raw)
    spaced = re.sub(r"[-]+", " ", spaced)
    spaced = re.sub(r"\s+", " ", spaced)
    return spaced


def _county_from_blob(blob: str) -> str | None:
    parts = re.split(r"[^a-z0-9]+", blob.lower())
    junk = {
        "the",
        "a",
        "an",
        "in",
        "for",
        "sale",
        "acres",
        "acre",
        "land",
        "property",
        "listing",
        "near",
        "and",
    }
    found = None
    for i, p in enumerate(parts):
        if p != "county" or i == 0:
            continue
        prev = parts[i - 1]
        if not prev or prev in junk or prev.isdigit():
            continue
        if i >= 2 and parts[i - 2] in _COUNTY_PREFIXES:
            found = f"{parts[i - 2]} {prev}".title()
        else:
            found = prev.title()
    return found


def _state_from_blob(blob: str, path: str) -> str | None:
    low = blob.lower()
    for name, abbr in sorted(_STATE_NAMES.items(), key=lambda x: -len(x[0])):
        needle = name.replace("-", " ")
        if re.search(rf"(?:^|[^a-z]){re.escape(needle)}(?:[^a-z]|$)", low):
            return abbr
    sm = _STATE_ABBR_RE.search(path.replace("-", " "))
    if sm:
        return sm.group("st").upper()
    # Trailing , CA / -CA- patterns in spaced blob
    sm2 = re.search(r"(?:^|[^a-z])([a-z]{2})(?:\s+\d{5})?(?:[^a-z]|$)", low)
    # too noisy — skip
    del sm2
    return None


def _acres_from_text(text: str) -> float | None:
    hits: list[float] = []
    for rx in _ACRES_PATTERNS:
        for m in rx.finditer(text):
            try:
                n = float(m.group("acres"))
            except (ValueError, IndexError):
                continue
            if 0.1 <= n <= 100_000:
                hits.append(n)
    if not hits:
        return None
    # Prefer mid/large land parcels over tiny "0.25 ac" noise when multiple
    return max(hits)


def _price_from_text(text: str) -> float | None:
    hits: list[float] = []
    for rx in _PRICE_PATTERNS:
        for m in rx.finditer(text):
            raw = (m.groupdict().get("p") or "").replace(",", "")
            try:
                n = float(raw)
            except ValueError:
                continue
            if 1_000 <= n <= 500_000_000:
                hits.append(n)
    return max(hits) if hits else None


def _apn_from_text(text: str) -> str | None:
    for rx in _APN_PATTERNS:
        m = rx.search(text)
        if m:
            return m.group("apn").strip()
    return None


def _coords_from_query(qs: dict[str, list[str]]) -> dict[str, float]:
    out: dict[str, float] = {}
    flat = {k.lower(): (v[0] if v else "") for k, v in qs.items()}
    # ll=lat,lon / center=lon,lat / geo=
    for key in ("ll", "center", "geo", "coordinates", "coord", "latlng", "latlon"):
        if key in flat and flat[key]:
            m = _LL_PAIR_RE.search(flat[key].replace("%2C", ","))
            if m:
                lat, lon = float(m.group("lat")), float(m.group("lon"))
                # Heuristic: US lon is negative; if first value looks like lon, swap
                if key == "center" and abs(lat) > 50 and abs(lon) < 50:
                    lat, lon = lon, lat
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    out["latitude"] = lat
                    out["longitude"] = lon
                    return out
    for k, dest in _COORD_QUERY_KEYS.items():
        if k in flat and flat[k]:
            try:
                out[dest] = float(flat[k])
            except ValueError:
                pass
    if "latitude" in out and "longitude" in out:
        return out
    return {}


def _coords_from_text(text: str) -> dict[str, float]:
    # Avoid matching version numbers; require decimal degrees
    for m in _LL_PAIR_RE.finditer(text):
        lat, lon = float(m.group("lat")), float(m.group("lon"))
        if 15 <= abs(lat) <= 72 and 50 <= abs(lon) <= 170:
            # Assume western hemisphere for US land if lon positive and large
            if lon > 0 and lat > 0 and lon > 30:
                lon = -lon
            return {"latitude": lat, "longitude": lon}
    return {}


def extract_from_listing_url(url: str) -> dict[str, Any]:
    """Screen the entire pasted URL for land-listing keywords and structured data."""
    parsed = urlparse(url.strip())
    path = unquote(parsed.path or "")
    query = unquote(parsed.query or "")
    fragment = unquote(parsed.fragment or "")
    qs = parse_qs(parsed.query, keep_blank_values=False)

    # Keyword blob: full URL with separators normalized + raw path/query
    spaced = _full_text_blob(url)
    raw_join = f"{path} {query} {fragment} {spaced}"
    blob_low = raw_join.lower()

    out: dict[str, Any] = {}

    # --- Query-string first-class fields ---
    flat = {k.lower(): (v[0] if v else "") for k, v in qs.items()}
    for acres_key in ("acres", "acreage", "ac", "lot_size", "lotsize", "size"):
        if acres_key in flat:
            try:
                n = float(re.sub(r"[^0-9.]", "", flat[acres_key]))
                if 0.1 <= n <= 100_000:
                    out["acreage"] = n
            except ValueError:
                pass
    for state_key in ("state", "region", "st", "addressregion"):
        if state_key in flat and len(flat[state_key].strip()) == 2:
            out["state"] = flat[state_key].strip().upper()
    for county_key in ("county", "admin1", "admin2"):
        if county_key in flat and flat[county_key].strip():
            out["county"] = flat[county_key].strip().title()
    for city_key in ("city", "locality", "town"):
        if city_key in flat and flat[city_key].strip():
            out["city"] = flat[city_key].strip().title()
    for addr_key in ("address", "street", "streetaddress", "location"):
        if addr_key in flat and len(flat[addr_key].strip()) > 4:
            out["address"] = flat[addr_key].strip()
    for price_key in ("price", "asking", "asking_price", "list_price", "listprice"):
        if price_key in flat:
            try:
                n = float(re.sub(r"[^0-9.]", "", flat[price_key]))
                if n >= 1000:
                    out["asking_price_usd"] = n
            except ValueError:
                pass
    for apn_key in ("apn", "pin", "parcel", "parcel_id", "parcelid"):
        if apn_key in flat and flat[apn_key].strip():
            out["apn"] = flat[apn_key].strip()

    out.update(_coords_from_query(qs))

    # --- Keyword / phrase scan of full URL text ---
    acres = _acres_from_text(raw_join) or _acres_from_text(spaced)
    if acres is not None:
        out.setdefault("acreage", acres)

    price = _price_from_text(raw_join)
    if price is not None:
        out.setdefault("asking_price_usd", price)

    apn = _apn_from_text(raw_join)
    if apn:
        out.setdefault("apn", apn)

    county = _county_from_blob(blob_low)
    if county:
        out.setdefault("county", county)

    state = _state_from_blob(spaced, path)
    if state:
        out.setdefault("state", state)

    if "latitude" not in out or "longitude" not in out:
        out.update({k: v for k, v in _coords_from_text(raw_join).items() if k not in out})

    # City hints: "...-in-bakersfield-california..." / near X
    if "city" not in out:
        m = re.search(
            r"(?:in|near|at)\s+([a-z][a-z\-]+(?:\s+[a-z][a-z\-]+)?)\s+(?:california|texas|florida|arizona|oregon|washington|colorado|nevada|utah|idaho|montana|wyoming|new mexico|georgia|alabama|tennessee|missouri|oklahoma|kansas|iowa|illinois|ohio|michigan|pennsylvania|new york|carolina|virginia|kentucky|arkansas|louisiana|mississippi|minnesota|wisconsin|indiana|nebraska|dakota)",
            spaced.lower(),
        )
        if m:
            city = m.group(1).replace("-", " ").title()
            if "county" not in city.lower() and city.lower() not in {"land", "acre", "acres", "property"}:
                out["city"] = city

    # Zillow / Realtor / Redfin address slugs
    zm = _ZILLOW_ADDR_RE.search(path)
    if zm:
        slug = zm.group("slug")
        parts = slug.split("-")
        if len(parts) >= 3 and parts[-1].isdigit() and len(parts[-1]) == 5:
            out.setdefault("zip", parts[-1])
            if len(parts[-2]) == 2:
                out.setdefault("state", parts[-2].upper())
                addr = " ".join(parts[:-2]).replace("  ", " ").title()
            else:
                addr = " ".join(parts[:-1]).title()
            out.setdefault("address", addr)
            out.setdefault("title", addr)
            # city often second-to-last place token before state
            if len(parts) >= 4 and len(parts[-2]) == 2:
                out.setdefault("city", parts[-3].replace("_", " ").title())
        else:
            out.setdefault("title", _title_from_slug(slug))
            out.setdefault("address", _title_from_slug(slug))

    rm = _REALTOR_ADDR_RE.search(path)
    if rm and "address" not in out:
        slug = rm.group("slug")
        parts = [p for p in slug.split("_") if p]
        if len(parts) >= 3 and re.fullmatch(r"[A-Za-z]{2}", parts[-2] if not parts[-1][0].isdigit() else parts[-2] if len(parts) > 2 else ""):
            pass
        # realtor: Street_City_ST_ZIP_M123
        if len(parts) >= 4 and len(parts[-2]) == 2 and parts[-1][:1].isdigit() is False and re.match(r"^\d{5}", parts[-1]):
            out.setdefault("zip", parts[-1][:5])
            out.setdefault("state", parts[-2].upper())
            out.setdefault("city", parts[-3].replace("-", " ").title())
            out.setdefault("address", " ".join(parts[:-1]).replace("-", " ").title())
        elif len(parts) >= 4:
            # Street_City_ST_ZIP_Mxxx
            for i, p in enumerate(parts):
                if len(p) == 2 and p.isalpha() and i + 1 < len(parts) and parts[i + 1][:5].isdigit():
                    out.setdefault("state", p.upper())
                    out.setdefault("zip", parts[i + 1][:5])
                    out.setdefault("city", parts[i - 1].replace("-", " ").title() if i else None)
                    out.setdefault("address", " ".join(parts[: i + 2]).replace("-", " ").title())
                    break

    # Descriptive title from richest path segment
    if not out.get("title"):
        segs = [s for s in path.split("/") if s]
        for seg in reversed(segs):
            low = seg.lower()
            if any(k in low for k in ("acre", "county", "land", "ranch", "lot")) or len(seg) > 12:
                title = _title_from_slug(seg)
                if title and title.lower() not in {"property", "listing", "homedetails", "properties"}:
                    out["title"] = title
                    break

    # Build a geocode-friendly address line when possible
    if not out.get("address"):
        bits = [out.get("city"), out.get("county") and f"{out['county']} County", out.get("state")]
        line = ", ".join(str(b) for b in bits if b)
        if line:
            out["geocode_query"] = line
    else:
        out["geocode_query"] = out["address"]

    return {k: v for k, v in out.items() if v not in (None, "", [])}
