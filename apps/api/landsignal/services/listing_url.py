"""User-initiated listing URL → draft fields for Land Signal intelligence.

This is NOT bulk marketplace scraping. A user pastes one URL they already found;
we attempt lightweight extraction (Open Graph / JSON-LD / obvious text patterns)
and fall back to a confirm form when sites block bots or hide data in apps.
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

log = structlog.get_logger()

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOST_HINTS = (
    # Still attempt fetch — these often need manual fallback
)

_PRICE_RE = re.compile(
    r"(?:\$|USD\s*)\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)\s*(K|M|k|m)?",
    re.I,
)
_ACRES_RE = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s*(?:\+)?\s*(?:acres?|ac\.?\b)",
    re.I,
)
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


def _host_label(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "land.com" in host or "landsofamerica" in host or "landwatch" in host:
        return "Land.com family"
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


def _parse_money(raw: str | None) -> float | None:
    if not raw:
        return None
    m = _PRICE_RE.search(str(raw).replace("\u00a0", " "))
    if not m:
        # plain number
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


def _parse_acres(raw: str | None) -> float | None:
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
            # still accept generic Product/Offer-ish
            if "name" not in n and "offers" not in n:
                continue
        if n.get("name") and not draft.get("title"):
            draft["title"] = str(n["name"])[:200]
        if n.get("description") and not draft.get("description"):
            draft["description"] = str(n["description"])[:2000]
        offers = n.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price") or offers.get("lowPrice")
            p = _parse_money(str(price) if price is not None else None)
            if p:
                draft["asking_price_usd"] = p
        elif isinstance(offers, list):
            for o in offers:
                if isinstance(o, dict):
                    p = _parse_money(str(o.get("price") or ""))
                    if p:
                        draft["asking_price_usd"] = p
                        break
        addr = n.get("address")
        if isinstance(addr, dict):
            draft.setdefault("address", ", ".join(
                str(addr.get(k) or "")
                for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode")
                if addr.get(k)
            ).strip(", "))
            region = addr.get("addressRegion")
            if region and len(str(region)) == 2:
                draft["state"] = str(region).upper()
            locality = addr.get("addressLocality")
            if locality:
                draft["county"] = str(locality)
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


def extract_listing_draft_from_html(html: str, *, url: str) -> dict[str, Any]:
    meta = _meta_map(html)
    title_m = _TITLE_RE.search(html)
    page_title = unescape(title_m.group(1)).strip() if title_m else None
    draft: dict[str, Any] = {
        "source_url": url,
        "source_host": _host_label(url),
        "title": meta.get("og:title") or meta.get("twitter:title") or page_title,
        "description": meta.get("og:description") or meta.get("description") or meta.get("twitter:description"),
    }
    draft.update({k: v for k, v in _from_jsonld(_jsonld_nodes(html)).items() if v})

    blob = " ".join(
        str(x)
        for x in (
            draft.get("title"),
            draft.get("description"),
            meta.get("og:description"),
            page_title,
        )
        if x
    )
    if not draft.get("asking_price_usd"):
        # Prefer larger plausible land prices from blob
        prices = []
        for m in _PRICE_RE.finditer(blob):
            p = _parse_money(m.group(0))
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
            # Prefer mid/large acre mentions over tiny "0.1 ac" noise when multiple
            draft["acreage"] = max(acres)

    if not draft.get("state"):
        sm = _STATE_RE.search(blob)
        if sm:
            draft["state"] = sm.group(1).upper()

    # Cleanup empties
    for k in list(draft.keys()):
        if draft[k] in ("", None):
            draft.pop(k)
    return draft


def missing_required(draft: dict[str, Any]) -> list[str]:
    need = []
    if not draft.get("title"):
        need.append("title")
    if not draft.get("state") or len(str(draft.get("state"))) != 2:
        need.append("state")
    if draft.get("acreage") is None:
        need.append("acreage")
    if draft.get("latitude") is None or draft.get("longitude") is None:
        need.append("coordinates")
    return need


async def geocode_address(address: str, state: str | None = None) -> dict[str, float] | None:
    """Free Nominatim geocode — best-effort only."""
    q = address if not state else f"{address}, {state}, USA"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 1},
                headers={"User-Agent": "LandSignal/1.0 (user-submitted listing analyze)"},
            )
            if resp.status_code >= 400:
                return None
            data = resp.json()
            if not data:
                return None
            return {"latitude": float(data[0]["lat"]), "longitude": float(data[0]["lon"])}
    except Exception as exc:  # noqa: BLE001
        log.info("geocode_failed", error=str(exc)[:160])
        return None


async def fetch_listing_url(url: str) -> dict[str, Any]:
    """Fetch one user-pasted URL and return a draft + status."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
        return {
            "ok": False,
            "error": "Enter a full http(s) listing URL.",
            "draft": {"source_url": url},
            "missing": ["title", "state", "acreage", "coordinates"],
            "fetch_status": "invalid_url",
        }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; LandSignalBot/1.0; +https://landsignal.app; "
            "user-initiated single listing analyze)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    fetch_status = "ok"
    html = ""
    try:
        async with httpx.AsyncClient(timeout=18.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code in (401, 403, 429):
                fetch_status = "blocked"
            elif resp.status_code >= 400:
                fetch_status = "http_error"
            else:
                html = resp.text or ""
                # Many listing sites are JS apps with almost no SSR content
                if len(html) < 800 or ("__NEXT_DATA__" in html and "og:title" not in html.lower()):
                    # still try extraction; may be thin
                    if "og:title" not in html.lower() and "application/ld+json" not in html.lower():
                        fetch_status = "thin_or_app_shell"
    except Exception as exc:  # noqa: BLE001
        log.info("listing_url_fetch_failed", url=url[:180], error=str(exc)[:200])
        return {
            "ok": False,
            "error": (
                "Could not open that page automatically (blocked or unavailable). "
                "Paste the key details below — we’ll still run the full intelligence report."
            ),
            "draft": {
                "source_url": url,
                "source_host": _host_label(url),
                "title": f"Listing from {_host_label(url)}",
            },
            "missing": ["title", "state", "acreage", "coordinates"],
            "fetch_status": "network_error",
        }

    draft = extract_listing_draft_from_html(html, url=url) if html else {
        "source_url": url,
        "source_host": _host_label(url),
        "title": f"Listing from {_host_label(url)}",
    }

    # Optional geocode when address-like description exists but no coords
    if (draft.get("latitude") is None or draft.get("longitude") is None) and draft.get("address"):
        geo = await geocode_address(str(draft["address"]), draft.get("state"))
        if geo:
            draft.update(geo)

    miss = missing_required(draft)
    note = None
    if fetch_status in {"blocked", "thin_or_app_shell", "http_error"}:
        note = (
            f"{draft.get('source_host') or 'This site'} often hides listing details from bots. "
            "Confirm or fill the missing fields — LandSignal will still score it with public "
            "soils/flood/terrain and the Future Scenario Engine."
        )
    elif miss:
        note = "We pulled a draft from the page. Confirm the fields below, then run intelligence."
    else:
        note = "Draft looks complete. Review once, then run intelligence."

    return {
        "ok": True,
        "error": None,
        "draft": draft,
        "missing": miss,
        "fetch_status": fetch_status,
        "note": note,
        "source_host": draft.get("source_host"),
    }
