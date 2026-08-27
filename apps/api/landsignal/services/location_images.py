"""Location imagery for View Images — street-level + clear aerials.

ATTOM under the current entitlement does not return MLS listing photo galleries.
We assemble a non-redundant gallery from:
  - Google Street View (interactive embed at the pin)
  - KartaView / OpenStreetCam nearby drive-by street photos
  - Filtered Wikimedia Commons ground photos (skip maps/diagrams/logos)
  - Wikipedia nearby place photos
  - One clear USGS aerial (plus a wide context frame only when street coverage is thin)
  - Esri World Imagery only as last-resort aerial when nothing else lands
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import structlog

log = structlog.get_logger()

_UA = "LandSignal/1.0 (land investment intelligence; contact: landsignal@local)"

_SKIP_LABEL = re.compile(
    r"(map|diagram|chart|logo|seal|coat of arms|flag of|svg|icon|qr.?code|"
    r"signature|passport|certificate|blank|placeholder|locator|"
    r"administrative|boundary|census|topographic|dem\b|orthophoto|"
    r"naip|landsat|sentinel|view of earth|iss\d|from space|"
    r"\btif\b|\.tif|\.tiff|geotiff|aerial.?index|doqq)",
    re.I,
)


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
    embed: bool = False,
    heading: float | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": fid,
        "label": label,
        "url": url,
        "thumb_url": thumb_url or url,
        "source": source,
        "kind": kind,
        "attribution": attribution,
        "page_url": page_url,
        "embed": embed,
    }
    if heading is not None:
        row["heading"] = heading
    return row


def _heading_gap(a: float, b: float) -> float:
    d = abs((a % 360.0) - (b % 360.0))
    return min(d, 360.0 - d)


def _usgs_aerial(lat: float, lon: float, acres: float | None, *, wide: bool) -> list[dict[str, Any]]:
    """One sharp parcel aerial; optional wide context only when street coverage is thin."""
    frames: list[tuple[str, str, float]] = [
        ("usgs-parcel", "Aerial — parcel", 0.85),
    ]
    if wide:
        frames.append(("usgs-area", "Aerial — surrounding land", 2.6))
    out: list[dict[str, Any]] = []
    for fid, label, mult in frames:
        pad = _pad_for_acres(acres, mult)
        url = (
            "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export"
            f"?bbox={lon - pad},{lat - pad},{lon + pad},{lat + pad}"
            "&bboxSR=4326&imageSR=4326&size=1440,1080&format=jpg&f=image"
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
    pad = _pad_for_acres(acres, 1.0)
    url = (
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
        f"?bbox={lon - pad},{lat - pad},{lon + pad},{lat + pad}"
        "&bboxSR=4326&imageSR=4326&size=1440,1080&format=jpg&f=image"
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


def _street_view_embed(lat: float, lon: float, acres: float | None = None) -> dict[str, Any]:
    """Interactive Google Street View at the pin (no Static API key required)."""
    embed_url = (
        "https://www.google.com/maps/embed?origin=mfe&pb="
        f"!6m6!1m5!2m2!1d{lat}!2d{lon}!4f0!5f1"
    )
    # Reliable aerial thumbnail for the strip (no third-party static-map host).
    pad = _pad_for_acres(acres, 0.55)
    thumb = (
        "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export"
        f"?bbox={lon - pad},{lat - pad},{lon + pad},{lat + pad}"
        "&bboxSR=4326&imageSR=4326&size=320x240&format=jpg&f=image"
    )
    return _img(
        fid="google-street-view",
        label="Street View — look around",
        url=embed_url,
        thumb_url=thumb,
        source="google",
        kind="streetview",
        attribution="Google Street View",
        page_url=f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat}%2C{lon}",
        embed=True,
    )


def _kartaview_street(lat: float, lon: float, *, limit: int = 6) -> list[dict[str, Any]]:
    """Nearby drive-by street photos from KartaView / OpenStreetCam."""
    # Prefer tight radius first for clarity; widen if empty.
    rows: list[dict[str, Any]] = []
    for radius in (900, 2500, 6000):
        data = _http_json(
            f"https://api.openstreetcam.org/2.0/photo/?lat={lat}&lng={lon}&radius={radius}",
            timeout=14.0,
        )
        rows = ((data or {}).get("result") or {}).get("data") or []
        if rows:
            break
    if not rows:
        return []

    scored: list[tuple[float, float, dict[str, Any]]] = []
    for r in rows:
        try:
            dist = float(r.get("distance") or 99999)
            heading = float(r.get("heading") or 0.0)
        except (TypeError, ValueError):
            continue
        fu = str(r.get("fileurl") or "")
        if "{{sizeprefix}}" not in fu:
            continue
        scored.append((dist, heading, r))
    scored.sort(key=lambda t: t[0])

    picked: list[dict[str, Any]] = []
    used_headings: list[float] = []
    used_sequences: set[str] = set()
    for dist, heading, r in scored:
        if any(_heading_gap(heading, h) < 48.0 for h in used_headings):
            continue
        seq = str(r.get("sequenceId") or "")
        # Keep at most two frames from the same drive sequence.
        if seq and sum(1 for p in picked if str(p.get("_seq") or "") == seq) >= 2:
            continue
        fu = str(r["fileurl"])
        url = fu.replace("{{sizeprefix}}", "proc")
        thumb = fu.replace("{{sizeprefix}}", "lth")
        pid = r.get("id") or r.get("sequenceId") or len(picked)
        meters = max(1, int(round(dist)))
        compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((heading + 22.5) % 360) // 45]
        if meters < 25:
            label = f"Street level — facing {compass}"
        elif meters < 1000:
            label = f"Street level — {meters} m · {compass}"
        else:
            label = f"Street level — {meters / 1000:.1f} km · {compass}"
        row = _img(
            fid=f"kv-{pid}",
            label=label,
            url=url,
            thumb_url=thumb,
            source="kartaview",
            kind="street",
            attribution="KartaView (OpenStreetCam)",
            page_url=f"https://kartaview.org/details/{r.get('sequenceId')}/{r.get('sequenceIndex')}"
            if r.get("sequenceId") is not None
            else "https://kartaview.org/",
            heading=heading,
        )
        row["_seq"] = seq
        picked.append(row)
        used_headings.append(heading)
        if seq:
            used_sequences.add(seq)
        if len(picked) >= limit:
            break
    for row in picked:
        row.pop("_seq", None)
    return picked


def _wikimedia_ground(lat: float, lon: float, *, limit: int = 5) -> list[dict[str, Any]]:
    """Nearby File: photos from Wikimedia Commons — filtered for real ground scenes."""
    gs_url = (
        "https://commons.wikimedia.org/w/api.php?action=query&list=geosearch"
        f"&gscoord={lat}|{lon}&gsradius=10000&gslimit={max(8, min(limit * 3, 20))}"
        "&gsnamespace=6&format=json"
    )
    data = _http_json(gs_url)
    hits = ((data or {}).get("query") or {}).get("geosearch") or []
    if not hits:
        return []
    # Prefer closer photos first.
    hits = sorted(hits, key=lambda h: float(h.get("dist") or 1e9))
    page_ids = [str(h["pageid"]) for h in hits if h.get("pageid")]
    if not page_ids:
        return []
    info_url = (
        "https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo"
        f"&pageids={'|'.join(page_ids[:16])}"
        "&iiprop=url|mime|size|extmetadata&iiurlwidth=1600&format=json"
    )
    info = _http_json(info_url)
    pages = ((info or {}).get("query") or {}).get("pages") or {}
    by_id = {str(p.get("pageid")): p for p in pages.values() if p.get("pageid") is not None}
    out: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for hit in hits:
        page = by_id.get(str(hit.get("pageid")))
        if not page:
            continue
        ii = (page.get("imageinfo") or [None])[0]
        if not isinstance(ii, dict):
            continue
        mime = str(ii.get("mime") or "")
        if not mime.startswith("image/") or "svg" in mime or "tiff" in mime:
            continue
        title = str(page.get("title") or "").replace("File:", "").strip()
        if _SKIP_LABEL.search(title):
            continue
        if title.lower().endswith((".tif", ".tiff", ".svg")):
            continue
        width = int(ii.get("width") or 0)
        height = int(ii.get("height") or 0)
        if width and width < 640:
            continue
        # Prefer landscape / street-ish aspect (not tall portraits or ultra-wide maps).
        if width and height:
            ratio = width / max(height, 1)
            if ratio < 0.55 or ratio > 2.6:
                continue
        # Skip tiny thumbs that are mostly satellite tiles pretending to be photos.
        if height and height < 420:
            continue
        url = ii.get("thumburl") or ii.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        dist = hit.get("dist")
        label = title[:80]
        if dist is not None:
            try:
                meters = int(round(float(dist)))
                label = f"{title[:64]} · {meters} m"
            except (TypeError, ValueError):
                pass
        page_url = f"https://commons.wikimedia.org/wiki/{quote(str(page.get('title') or ''))}"
        out.append(
            _img(
                fid=f"wiki-{page.get('pageid')}",
                label=label,
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


def _wikipedia_nearby(lat: float, lon: float, *, limit: int = 3) -> list[dict[str, Any]]:
    """Nearby Wikipedia article thumbnails — towns, parks, landmarks near the pin."""
    gs_url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=geosearch"
        f"&gscoord={lat}|{lon}&gsradius=10000&gslimit={max(4, min(limit * 3, 12))}&format=json"
    )
    data = _http_json(gs_url)
    hits = ((data or {}).get("query") or {}).get("geosearch") or []
    if not hits:
        return []
    hits = sorted(hits, key=lambda h: float(h.get("dist") or 1e9))
    page_ids = [str(h["pageid"]) for h in hits if h.get("pageid")]
    if not page_ids:
        return []
    info_url = (
        "https://en.wikipedia.org/w/api.php?action=query&prop=pageimages|info"
        f"&pageids={'|'.join(page_ids[:10])}"
        "&piprop=thumbnail|name&pithumbsize=1280&inprop=url&format=json"
    )
    info = _http_json(info_url)
    pages = ((info or {}).get("query") or {}).get("pages") or {}
    by_id = {str(p.get("pageid")): p for p in pages.values() if p.get("pageid") is not None}
    out: list[dict[str, Any]] = []
    for hit in hits:
        page = by_id.get(str(hit.get("pageid")))
        if not page:
            continue
        thumb = page.get("thumbnail") or {}
        url = thumb.get("source")
        if not url:
            continue
        title = str(page.get("title") or "Nearby place").strip()
        if _SKIP_LABEL.search(title) or title.lower().startswith("list of"):
            continue
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

    street = _kartaview_street(lat_f, lon_f, limit=6)
    ground = _wikimedia_ground(lat_f, lon_f, limit=4)
    wiki_places = _wikipedia_nearby(lat_f, lon_f, limit=3)

    images: list[dict[str, Any]] = []
    images.append(_street_view_embed(lat_f, lon_f, acres))
    # Prefer a real street photo thumb for the Street View slot when available.
    if street and street[0].get("thumb_url"):
        images[0]["thumb_url"] = street[0]["thumb_url"]
    images.extend(street)

    seen = {i["url"] for i in images}
    for row in ground + wiki_places:
        if row["url"] in seen:
            continue
        images.append(row)
        seen.add(row["url"])

    streetish_photos = len(street)
    # Keep aerials minimal — never stack USGS + Esri lookalikes.
    images.extend(
        _usgs_aerial(
            lat_f,
            lon_f,
            acres,
            wide=streetish_photos == 0 and not ground and not wiki_places,
        )
    )

    street_n = sum(1 for i in images if i.get("kind") in ("street", "streetview"))
    ground_n = sum(1 for i in images if i.get("kind") == "ground")
    note = (
        f"Gallery prioritizes Street View and {street_n} street-level frame"
        f"{'' if street_n == 1 else 's'}, plus {ground_n} nearby place photo"
        f"{'' if ground_n == 1 else 's'} when available. "
        "ATTOM enriches property records on this key — it does not supply MLS listing photos."
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
            "kartaview": f"https://kartaview.org/map/@{lat_f},{lon_f},16z",
        },
    }
