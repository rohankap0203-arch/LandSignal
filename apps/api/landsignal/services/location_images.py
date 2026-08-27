"""Location imagery for View Images — real aerial + nearby ground photos.

ATTOM under the current entitlement does not return MLS listing photo galleries.
We assemble a mixed gallery from:
  - USGS Imagery Only (true aerial photography — not the same Esri satellite zoom stack)
  - Wikimedia Commons File: geosearch (ground-level / landscape photos near the pin)
  - Wikipedia page images for nearby places (towns, landmarks, parks)
  - Esri World Imagery as a last-resort extra aerial frame when no ground photos exist
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import structlog

log = structlog.get_logger()

_UA = "LandSignal/1.0 (land investment intelligence; contact: landsignal@local)"


def _http_json(url: str, timeout: float = 12.0) -> dict[str, Any] | None:
    try:
        req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        log.info("location_images_http_json_failed", error=str(exc)[:160])
        return None


def _pad_for_acres(acres: float | None, mult: float = 1.0) -> float:
    base = 0.006
    if acres is not None and acres > 0:
        base = max(0.0028, min(0.045, (float(acres) ** 0.5) * 0.00115))
    return base * mult


def _img(
    *,
    fid: str,
    label: str,
    url: str,
    source: str,
    kind: str,
    attribution: str,
    thumb_url: str | None = None,
    page_url: str | None = None,
) -> dict[str, Any]:
    return {
        "id": fid,
        "label": label,
        "url": url,
        "thumb_url": thumb_url or url,
        "source": source,
        "kind": kind,
        "attribution": attribution,
        "page_url": page_url,
    }


def _usgs_aerial(lat: float, lon: float, acres: float | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    frames = (
        ("usgs-close", "USGS aerial — close-in", 0.55),
        ("usgs-parcel", "USGS aerial — parcel frame", 1.0),
        ("usgs-area", "USGS aerial — surrounding land", 2.4),
    )
    for fid, label, mult in frames:
        pad = _pad_for_acres(acres, mult)
        url = (
            "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export"
            f"?bbox={lon - pad},{lat - pad},{lon + pad},{lat + pad}"
            "&bboxSR=4326&imageSR=4326&size=1280,960&format=jpg&f=image"
        )
        out.append(
            _img(
                fid=fid,
                label=label,
                url=url,
                source="usgs",
                kind="aerial",
                attribution="USGS The National Map",
            )
        )
    return out


def _esri_fallback(lat: float, lon: float, acres: float | None) -> list[dict[str, Any]]:
    pad = _pad_for_acres(acres, 1.2)
    url = (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
        f"?bbox={lon - pad},{lat - pad},{lon + pad},{lat + pad}"
        "&bboxSR=4326&imageSR=4326&size=1280,960&format=jpg&f=image"
    )
    return [
        _img(
            fid="esri-aerial",
            label="Satellite aerial overview",
            url=url,
            source="esri",
            kind="aerial",
            attribution="Esri World Imagery",
        )
    ]


def _wikimedia_ground(lat: float, lon: float, *, limit: int = 10) -> list[dict[str, Any]]:
    """Nearby File: photos from Wikimedia Commons (real ground photos when available)."""
    gs_url = (
        "https://commons.wikimedia.org/w/api.php?action=query&list=geosearch"
        f"&gscoord={lat}|{lon}&gsradius=10000&gslimit={max(4, min(limit, 16))}"
        "&gsnamespace=6&format=json"
    )
    data = _http_json(gs_url)
    hits = ((data or {}).get("query") or {}).get("geosearch") or []
    if not hits:
        return []
    page_ids = [str(h["pageid"]) for h in hits if h.get("pageid")]
    if not page_ids:
        return []
    info_url = (
        "https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo"
        f"&pageids={'|'.join(page_ids[:12])}"
        "&iiprop=url|mime|size|extmetadata&iiurlwidth=1600&format=json"
    )
    info = _http_json(info_url)
    pages = ((info or {}).get("query") or {}).get("pages") or {}
    out: list[dict[str, Any]] = []
    for page in pages.values():
        ii = (page.get("imageinfo") or [None])[0]
        if not isinstance(ii, dict):
            continue
        mime = str(ii.get("mime") or "")
        if not mime.startswith("image/"):
            continue
        url = ii.get("thumburl") or ii.get("url")
        if not url:
            continue
        title = str(page.get("title") or "Nearby photo").replace("File:", "").strip()
        if int(ii.get("width") or 0) and int(ii.get("width") or 0) < 400:
            continue
        page_url = f"https://commons.wikimedia.org/wiki/{quote(str(page.get('title') or ''))}"
        out.append(
            _img(
                fid=f"wiki-{page.get('pageid')}",
                label=title[:90],
                url=url,
                thumb_url=url,
                source="wikimedia",
                kind="ground",
                attribution="Wikimedia Commons",
                page_url=page_url,
            )
        )
        if len(out) >= limit:
            break
    return out


def _wikipedia_nearby(lat: float, lon: float, *, limit: int = 6) -> list[dict[str, Any]]:
    """Nearby Wikipedia article thumbnails — towns, parks, landmarks near the pin."""
    gs_url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=geosearch"
        f"&gscoord={lat}|{lon}&gsradius=10000&gslimit={max(4, min(limit, 12))}&format=json"
    )
    data = _http_json(gs_url)
    hits = ((data or {}).get("query") or {}).get("geosearch") or []
    if not hits:
        return []
    page_ids = [str(h["pageid"]) for h in hits if h.get("pageid")]
    if not page_ids:
        return []
    info_url = (
        "https://en.wikipedia.org/w/api.php?action=query&prop=pageimages|info"
        f"&pageids={'|'.join(page_ids[:10])}"
        "&piprop=thumbnail|name&pithumbsize=1200&inprop=url&format=json"
    )
    info = _http_json(info_url)
    pages = ((info or {}).get("query") or {}).get("pages") or {}
    out: list[dict[str, Any]] = []
    for page in pages.values():
        thumb = page.get("thumbnail") or {}
        url = thumb.get("source")
        if not url:
            continue
        title = str(page.get("title") or "Nearby place").strip()
        out.append(
            _img(
                fid=f"wp-{page.get('pageid')}",
                label=f"Nearby — {title}"[:90],
                url=url,
                thumb_url=url,
                source="wikipedia",
                kind="ground",
                attribution="Wikipedia",
                page_url=page.get("fullurl"),
            )
        )
        if len(out) >= limit:
            break
    return out


def build_location_images(
    *,
    lat: float | None,
    lon: float | None,
    acres: float | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    if lat is None or lon is None or not (abs(lat) <= 90 and abs(lon) <= 180):
        return {
            "ok": False,
            "images": [],
            "count": 0,
            "note": "No coordinates on this parcel yet.",
            "attom_photos": False,
            "maps": {},
        }

    lat_f = float(lat)
    lon_f = float(lon)
    images: list[dict[str, Any]] = []
    images.extend(_usgs_aerial(lat_f, lon_f, acres))
    ground = _wikimedia_ground(lat_f, lon_f, limit=6)
    images.extend(ground)
    wiki_places = _wikipedia_nearby(lat_f, lon_f, limit=5)
    seen = {i["url"] for i in images}
    for row in wiki_places:
        if row["url"] in seen:
            continue
        images.append(row)
        seen.add(row["url"])
    if not ground and not wiki_places:
        images.extend(_esri_fallback(lat_f, lon_f, acres))

    ground_n = sum(1 for i in images if i.get("kind") == "ground")
    note = (
        f"Gallery mixes USGS aerial photography with {ground_n} nearby ground/place photo"
        f"{'' if ground_n == 1 else 's'} when available. "
        "ATTOM under the current key enriches property records — it does not supply MLS listing photo sets. "
        "Use Street View / Google Maps for more ground-level coverage."
    )

    return {
        "ok": True,
        "images": images,
        "count": len(images),
        "attom_photos": False,
        "title": title,
        "lat": lat_f,
        "lon": lon_f,
        "note": note,
        "maps": {
            "google_maps": (
                "https://www.google.com/maps/@?api=1&map_action=map"
                f"&center={lat_f}%2C{lon_f}&zoom=17"
            ),
            "google_street_view": (
                "https://www.google.com/maps/@?api=1&map_action=pano"
                f"&viewpoint={lat_f}%2C{lon_f}"
            ),
            "google_earth": f"https://earth.google.com/web/@{lat_f},{lon_f},200a,1000d,35y,0h,0t,0r",
            "openstreetmap": (
                f"https://www.openstreetmap.org/?mlat={lat_f}&mlon={lon_f}#map=17/{lat_f}/{lon_f}"
            ),
        },
    }
