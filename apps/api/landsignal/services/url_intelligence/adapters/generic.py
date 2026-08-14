"""Generic listing HTML extraction (JSON-LD, OpenGraph, regex)."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

from landsignal.services.url_intelligence.provenance import provenanced

_PRICE_RE = re.compile(
    r"(?:\$|USD\s*)\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*(K|M|k|m)?",
    re.I,
)
_ACRES_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:\+)?\s*(?:acres?|ac\.?\b)", re.I)
_APN_RE = re.compile(
    r"\b(?:APN|PIN|Parcel\s*(?:#|No\.?|Number)?|Assessor(?:'s)?\s*Parcel)\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9.\-/]{3,})",
    re.I,
)
_COUNTY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s+County\b")
_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
_STATE_RE = re.compile(
    r"\b(A[LKZR]|C[AOT]|D[EC]|F[LM]|G[AU]|HI|I[ADLN]|K[SY]|L[A]|M[ADEHINOST]|N[CDEHJMVY]|"
    r"O[HKR]|P[A]|RI|S[CD]|T[NX]|UT|V[AIT]|W[AIVY])\b"
)
_META_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
    re.I,
)
_META_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']([^"\']+)["\']',
    re.I,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_IMG_OG = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I)


def host_label(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "land.com" in host or "landsofamerica" in host:
        return "Land.com"
    if "landwatch" in host:
        return "LandWatch"
    if "landsearch" in host:
        return "LandSearch"
    if "landandfarm" in host or "land-and-farm" in host:
        return "Land And Farm"
    if "zillow" in host:
        return "Zillow"
    if "realtor.com" in host:
        return "Realtor.com"
    if "redfin" in host:
        return "Redfin"
    if "crexi" in host:
        return "Crexi"
    if "loopnet" in host:
        return "LoopNet"
    if "lands" in host:
        return "Land listing site"
    return host or "listing site"


def parse_money(raw: str | None) -> float | None:
    if not raw:
        return None
    m = _PRICE_RE.search(str(raw).replace("\u00a0", " "))
    if not m:
        try:
            n = float(re.sub(r"[^0-9.]", "", str(raw)))
            return n if n > 0 else None
        except ValueError:
            return None
    num = float(m.group(1).replace(",", ""))
    suf = (m.group(2) or "").upper()
    if suf == "K":
        num *= 1_000
    elif suf == "M":
        num *= 1_000_000
    return num if num > 0 else None


def parse_acres(raw: str | None) -> float | None:
    if not raw:
        return None
    m = _ACRES_RE.search(str(raw))
    if not m:
        try:
            n = float(re.sub(r"[^0-9.]", "", str(raw)))
            return n if 0 < n < 100_000 else None
        except ValueError:
            return None
    n = float(m.group(1))
    return n if 0 < n < 100_000 else None


def _meta_map(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _META_RE.finditer(html):
        out[m.group(1).lower()] = unescape(m.group(2)).strip()
    for m in _META_RE_ALT.finditer(html):
        out[m.group(2).lower()] = unescape(m.group(1)).strip()
    return out


def _jsonld_nodes(html: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for m in _JSONLD_RE.finditer(html):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, list):
            nodes.extend([x for x in data if isinstance(x, dict)])
        elif isinstance(data, dict):
            if "@graph" in data and isinstance(data["@graph"], list):
                nodes.extend([x for x in data["@graph"] if isinstance(x, dict)])
            else:
                nodes.append(data)
    return nodes


def _from_jsonld(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    draft: dict[str, Any] = {}
    for n in nodes:
        types = n.get("@type")
        type_l = (
            " ".join(types).lower()
            if isinstance(types, list)
            else str(types or "").lower()
        )
        if not any(
            t in type_l
            for t in (
                "realestate",
                "product",
                "place",
                "residence",
                "apartment",
                "house",
                "land",
                "offer",
            )
        ):
            if "name" not in n and "offers" not in n:
                continue
        if n.get("name") and not draft.get("title"):
            draft["title"] = str(n["name"])[:200]
        if n.get("description") and not draft.get("description"):
            draft["description"] = str(n["description"])[:4000]
        offers = n.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price") or offers.get("lowPrice")
            p = parse_money(str(price) if price is not None else None)
            if p:
                draft["asking_price_usd"] = p
        elif isinstance(offers, list):
            for o in offers:
                if isinstance(o, dict):
                    p = parse_money(str(o.get("price") or ""))
                    if p:
                        draft["asking_price_usd"] = p
                        break
        addr = n.get("address")
        if isinstance(addr, dict):
            draft.setdefault(
                "address",
                ", ".join(
                    str(addr.get(k) or "")
                    for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode")
                    if addr.get(k)
                ).strip(", "),
            )
            region = addr.get("addressRegion")
            if region and len(str(region)) == 2:
                draft["state"] = str(region).upper()
            locality = addr.get("addressLocality")
            if locality:
                draft["city"] = str(locality)
            if addr.get("postalCode"):
                draft["zip"] = str(addr["postalCode"])[:10]
        geo = n.get("geo")
        if isinstance(geo, dict):
            try:
                if geo.get("latitude") is not None:
                    draft["latitude"] = float(geo["latitude"])
                if geo.get("longitude") is not None:
                    draft["longitude"] = float(geo["longitude"])
            except (TypeError, ValueError):
                pass
    return draft


def extract_raw(html: str, *, url: str) -> dict[str, Any]:
    meta = _meta_map(html)
    title_m = _TITLE_RE.search(html)
    page_title = unescape(title_m.group(1)).strip() if title_m else None
    draft: dict[str, Any] = {
        "source_url": url,
        "source_host": host_label(url),
        "title": meta.get("og:title") or meta.get("twitter:title") or page_title,
        "description": meta.get("og:description")
        or meta.get("description")
        or meta.get("twitter:description"),
    }
    draft.update({k: v for k, v in _from_jsonld(_jsonld_nodes(html)).items() if v})

    blob = " ".join(
        str(x)
        for x in (
            draft.get("title"),
            draft.get("description"),
            meta.get("og:description"),
            page_title,
            html[:12000] if html else "",
        )
        if x
    )
    if not draft.get("asking_price_usd"):
        prices = []
        for m in _PRICE_RE.finditer(blob):
            p = parse_money(m.group(0))
            if p and p >= 500:
                prices.append(p)
        if prices:
            draft["asking_price_usd"] = max(prices)
    if not draft.get("acreage"):
        acres = []
        for m in _ACRES_RE.finditer(blob):
            a = float(m.group(1))
            if 0.1 <= a <= 50000:
                acres.append(a)
        if acres:
            draft["acreage"] = max(acres)
    if not draft.get("state"):
        sm = _STATE_RE.search(blob)
        if sm:
            draft["state"] = sm.group(1).upper()
    if not draft.get("county"):
        cm = _COUNTY_RE.search(blob)
        if cm:
            draft["county"] = cm.group(1)
    if not draft.get("apn"):
        am = _APN_RE.search(blob)
        if am:
            draft["apn"] = am.group(1).strip()
    if not draft.get("zip"):
        zm = _ZIP_RE.search(draft.get("address") or blob[:500])
        if zm:
            draft["zip"] = zm.group(1)

    imgs = []
    for m in _IMG_OG.finditer(html or ""):
        imgs.append(m.group(1))
        if len(imgs) >= 5:
            break
    if imgs:
        draft["image_urls"] = imgs

    for k in list(draft.keys()):
        if draft[k] in ("", None):
            draft.pop(k)
    return draft


def normalize_raw(raw: dict[str, Any], *, url: str, domain: str) -> dict[str, Any]:
    """Convert flat raw extract into provenanced field map."""
    fields: dict[str, Any] = {}
    method = "structured_html_extraction"
    src = "listing"

    def add(key: str, value: Any, conf: float, *, unit: str | None = None, text: str | None = None):
        if value is None or value == "":
            return
        fields[key] = provenanced(
            value,
            source=src,
            confidence=conf,
            extraction_method=method,
            source_url=url,
            source_text=text,
            unit=unit,
        )

    add("title", raw.get("title"), 0.9)
    add("description", raw.get("description"), 0.85)
    add("askingPrice", raw.get("asking_price_usd"), 0.92, unit="USD")
    add("acreage", raw.get("acreage"), 0.9, unit="acres")
    add("state", raw.get("state"), 0.95)
    add("county", raw.get("county"), 0.8)
    add("city", raw.get("city"), 0.75)
    add("address", raw.get("address"), 0.85)
    add("zip", raw.get("zip"), 0.8)
    add("latitude", raw.get("latitude"), 0.88)
    add("longitude", raw.get("longitude"), 0.88)
    add("apn", raw.get("apn"), 0.7)
    add("zoning", raw.get("zoning"), 0.6)
    add("propertyType", raw.get("property_type") or "land", 0.7)
    add("sourceUrl", url, 1.0)
    add("sourceDomain", domain, 1.0)
    add("sourceHost", raw.get("source_host") or host_label(url), 1.0)
    if raw.get("image_urls"):
        add("imageUrls", raw["image_urls"], 0.8)
    if raw.get("asking_price_usd") and raw.get("acreage"):
        try:
            ppa = float(raw["asking_price_usd"]) / float(raw["acreage"])
            add("pricePerAcre", round(ppa, 2), 0.85, unit="USD/acre")
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return fields


class GenericListingAdapter:
    id = "generic"
    name = "Generic listing"

    def can_handle(self, url: str, domain: str) -> bool:
        return True

    def extract(self, html: str, *, url: str, domain: str) -> dict[str, Any]:
        return extract_raw(html, url=url)

    def normalize(self, raw: dict[str, Any], *, url: str, domain: str) -> dict[str, Any]:
        return normalize_raw(raw, url=url, domain=domain)
