"""Location imagery for View Images — instant aerials + nearby street context.

Why this is not as slow as "wait for every upstream":
  Zillow / land.com serve pre-hosted MLS listing photos from a CDN.
  LandSignal has no MLS photo entitlement — we synthesize a land-true gallery
  from public aerials + street imagery. Aerial URLs are built locally (0 ms of
  upstream wait) so the first paint can match that "open → see land" feeling.
  Slower enrichments (KartaView / Commons) arrive in the background.

Gallery rules:
  - Always lead with a clear satellite / aerial of THIS pin
  - Interactive Street View at the pin
  - Nearby KartaView drive-bys (hard distance gate)
  - Tightly filtered Wikimedia ground photos
  - Wikipedia town thumbs intentionally omitted
"""

from __future__ import annotations

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal
from urllib.parse import quote
from urllib.request import Request, urlopen

import structlog

log = structlog.get_logger()

_UA = "LandSignal/1.0 (land investment intelligence; contact: landsignal@local)"

# Maps, logos, people, interiors, civic buildings — not usable land context.
_SKIP_LABEL = re.compile(
    r"(map|diagram|chart|logo|seal|coat of arms|flag of|svg|icon|qr.?code|"
    r"signature|passport|certificate|blank|placeholder|locator|"
    r"administrative|boundary|census|topographic|dem\b|orthophoto|"
    r"naip|landsat|sentinel|view of earth|iss\d|from space|"
    r"\btif\b|\.tif|\.tiff|geotiff|aerial.?index|doqq|"
    r"portrait|selfie|wedding|funeral|interior|museum|stadium|arena|"
    r"cathedral|church|mosque|synagogue|temple|skyscraper|skyline|"
    r"city hall|courthouse|capitol|school|university|hospital|airport|"
    r"train station|bus station|subway|metro|shopping|mall|"
    r"statue of|monument to|memorial to|plaque|poster|flyer|"
    r"actor|actress|politician|senator|governor|president|"
    r"baseball|football|basketball|soccer|hockey|"
    r"night.?sky|star.?trail|milky.?way|aurora)",
    re.I,
)

_LANDISH = re.compile(
    r"(land|farm|ranch|field|pasture|meadow|prairie|forest|woods|timber|"
    r"creek|river|lake|pond|marsh|wetland|hill|ridge|valley|canyon|"
    r"desert|mountain|bluff|trail|road|highway|acre|parcel|lot|"
    r"rural|countryside|agriculture|orchard|vineyard|range|"
    r"grass|soil|fence|gate|barn|silo|view from)",
    re.I,
)

# In-process gallery cache — same pin shouldn't re-scout every open.
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_S = 45 * 60
_CACHE_MAX = 400

# Upstream budgets — keep enrichments snappy; aerials never wait on these.
_STREET_TIMEOUT_S = 3.2
_GROUND_TIMEOUT_S = 3.5


def _http_json(url: str, timeout: float = 4.0) -> dict[str, Any] | None:
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


def _max_street_m(acres: float | None) -> float:
    if acres is None or acres <= 0:
        return 700.0
    return float(min(1200.0, max(450.0, math.sqrt(float(acres)) * 85.0)))


def _max_ground_m(acres: float | None) -> float:
    if acres is None or acres <= 0:
        return 1200.0
    return float(min(1800.0, max(800.0, math.sqrt(float(acres)) * 110.0)))


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
    distance_m: float | None = None,
    caption: str | None = None,
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
        "caption": caption or label,
    }
    if heading is not None:
        row["heading"] = heading
    if distance_m is not None:
        row["distance_m"] = round(float(distance_m), 1)
    return row


def _heading_gap(a: float, b: float) -> float:
    d = abs((a % 360.0) - (b % 360.0))
    return min(d, 360.0 - d)


def _export_url(
    service: Literal["esri", "usgs"],
    lat: float,
    lon: float,
    pad: float,
    *,
    size: str = "1440,1080",
) -> str:
    if service == "esri":
        base = (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/export"
        )
    else:
        base = (
            "https://basemap.nationalmap.gov/arcgis/rest/services/"
            "USGSImageryOnly/MapServer/export"
        )
    return (
        f"{base}?bbox={lon - pad},{lat - pad},{lon + pad},{lat + pad}"
        f"&bboxSR=4326&imageSR=4326&size={size}&format=jpg&f=image"
    )


def _mapbox_static(lat: float, lon: float, acres: float | None, *, wide: bool) -> dict[str, Any] | None:
    """CDN satellite when MAPBOX_TOKEN is set — closest feel to Zillow-speed tiles."""
    try:
        from landsignal.settings import get_settings

        token = (get_settings().mapbox_token or "").strip()
    except Exception:  # noqa: BLE001
        token = ""
    if not token:
        return None
    zoom = 14 if wide else (16 if (acres or 0) < 40 else 15)
    w, h = (1280, 960) if not wide else (1280, 960)
    url = (
        f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
        f"{lon:.6f},{lat:.6f},{zoom},0/{w}x{h}@2x?access_token={quote(token)}"
    )
    thumb = (
        f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
        f"{lon:.6f},{lat:.6f},{zoom},0/480x360@2x?access_token={quote(token)}"
    )
    return _img(
        fid="mapbox-sat" if not wide else "mapbox-sat-wide",
        label="Satellite — this land" if not wide else "Satellite — surrounding land",
        url=url,
        thumb_url=thumb,
        source="mapbox",
        kind="aerial",
        attribution="Mapbox Satellite",
        distance_m=0.0,
        caption=(
            "High-clarity satellite centered on this land."
            if not wide
            else "Wider satellite context around this land."
        ),
    )


def _aerial_frames(lat: float, lon: float, acres: float | None, *, wide: bool) -> list[dict[str, Any]]:
    """Instant aerials — no upstream JSON. Esri leads (clearer for most US land)."""
    out: list[dict[str, Any]] = []
    mb = _mapbox_static(lat, lon, acres, wide=False)
    if mb:
        out.append(mb)
        if wide:
            mbw = _mapbox_static(lat, lon, acres, wide=True)
            if mbw:
                out.append(mbw)
        return out

    # Esri World Imagery — sharp, CDN-backed, feels "Zillow-like"
    pad = _pad_for_acres(acres, 0.9)
    out.append(
        _img(
            fid="esri-parcel",
            label="Satellite — this land",
            url=_export_url("esri", lat, lon, pad, size="1440,1080"),
            thumb_url=_export_url("esri", lat, lon, pad, size="480,360"),
            source="esri",
            kind="aerial",
            attribution="Esri World Imagery",
            distance_m=0.0,
            caption="Clear satellite view centered on this land.",
        )
    )
    # USGS as a second angle / backup source
    pad_u = _pad_for_acres(acres, 0.85)
    out.append(
        _img(
            fid="usgs-parcel",
            label="Aerial — USGS of this land",
            url=_export_url("usgs", lat, lon, pad_u, size="1440,1080"),
            thumb_url=_export_url("usgs", lat, lon, pad_u, size="480,360"),
            source="usgs",
            kind="aerial",
            attribution="USGS The National Map",
            distance_m=0.0,
            caption="USGS aerial of the same pin for a second look.",
        )
    )
    if wide:
        pad_w = _pad_for_acres(acres, 2.6)
        out.append(
            _img(
                fid="esri-area",
                label="Satellite — surrounding land",
                url=_export_url("esri", lat, lon, pad_w, size="1440,1080"),
                thumb_url=_export_url("esri", lat, lon, pad_w, size="480,360"),
                source="esri",
                kind="aerial",
                attribution="Esri World Imagery",
                distance_m=0.0,
                caption="Wider satellite of the land and neighboring ground.",
            )
        )
    return out


def _usgs_aerial(lat: float, lon: float, acres: float | None, *, wide: bool) -> list[dict[str, Any]]:
    """Compat shim for tests / callers — prefer _aerial_frames."""
    return _aerial_frames(lat, lon, acres, wide=wide)


def _esri_fallback(lat: float, lon: float, acres: float | None) -> list[dict[str, Any]]:
    pad = _pad_for_acres(acres, 1.0)
    return [
        _img(
            fid="esri-aerial",
            label="Satellite — this land",
            url=_export_url("esri", lat, lon, pad),
            thumb_url=_export_url("esri", lat, lon, pad, size="480,360"),
            source="esri",
            kind="aerial",
            attribution="Esri World Imagery",
            distance_m=0.0,
            caption="Clear satellite view centered on this land.",
        )
    ]


def _street_view_embed(lat: float, lon: float, acres: float | None = None) -> dict[str, Any]:
    embed_url = (
        "https://www.google.com/maps/embed?origin=mfe&pb="
        f"!6m6!1m5!2m2!1d{lat}!2d{lon}!4f0!5f1"
    )
    pad = _pad_for_acres(acres, 0.55)
    thumb = _export_url("esri", lat, lon, pad, size="320,240")
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
        distance_m=0.0,
        caption="Interactive street-level view from the nearest road coverage.",
    )


def _kartaview_street(lat: float, lon: float, *, acres: float | None = None, limit: int = 4) -> list[dict[str, Any]]:
    max_m = _max_street_m(acres)
    query_radii = [int(min(900, max_m)), int(min(1600, max(max_m, 900)))]
    rows: list[dict[str, Any]] = []
    for radius in query_radii:
        data = _http_json(
            f"https://api.openstreetcam.org/2.0/photo/?lat={lat}&lng={lon}&radius={radius}",
            timeout=_STREET_TIMEOUT_S,
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
        if dist > max_m:
            continue
        fu = str(r.get("fileurl") or "")
        if "{{sizeprefix}}" not in fu:
            continue
        scored.append((dist, heading, r))
    scored.sort(key=lambda t: t[0])

    picked: list[dict[str, Any]] = []
    used_headings: list[float] = []
    for dist, heading, r in scored:
        if any(_heading_gap(heading, h) < 48.0 for h in used_headings):
            continue
        seq = str(r.get("sequenceId") or "")
        if seq and sum(1 for p in picked if str(p.get("_seq") or "") == seq) >= 2:
            continue
        fu = str(r["fileurl"])
        url = fu.replace("{{sizeprefix}}", "proc")
        thumb = fu.replace("{{sizeprefix}}", "lth")
        pid = r.get("id") or r.get("sequenceId") or len(picked)
        meters = max(1, int(round(dist)))
        compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((heading + 22.5) % 360) // 45]
        if meters < 25:
            label = f"Road by this land — facing {compass}"
            caption = f"Drive-by photo on the road next to this land, looking {compass}."
        else:
            label = f"Road by this land — {meters} m · {compass}"
            caption = f"Drive-by photo about {meters} m from this land, looking {compass}."
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
            distance_m=dist,
            caption=caption,
        )
        row["_seq"] = seq
        picked.append(row)
        used_headings.append(heading)
        if len(picked) >= limit:
            break
    for row in picked:
        row.pop("_seq", None)
    return picked


def _wikimedia_ground(lat: float, lon: float, *, acres: float | None = None, limit: int = 2) -> list[dict[str, Any]]:
    max_m = _max_ground_m(acres)
    gs_url = (
        "https://commons.wikimedia.org/w/api.php?action=query&list=geosearch"
        f"&gscoord={lat}|{lon}&gsradius={min(10000, int(max_m * 2))}"
        f"&gslimit={max(8, min(limit * 4, 16))}"
        "&gsnamespace=6&format=json"
    )
    data = _http_json(gs_url, timeout=_GROUND_TIMEOUT_S)
    hits = ((data or {}).get("query") or {}).get("geosearch") or []
    if not hits:
        return []
    hits = sorted(hits, key=lambda h: float(h.get("dist") or 1e9))
    page_ids = [str(h["pageid"]) for h in hits if h.get("pageid")]
    if not page_ids:
        return []
    info_url = (
        "https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo"
        f"&pageids={'|'.join(page_ids[:16])}"
        "&iiprop=url|mime|size|extmetadata&iiurlwidth=1600&format=json"
    )
    info = _http_json(info_url, timeout=_GROUND_TIMEOUT_S)
    pages = ((info or {}).get("query") or {}).get("pages") or {}
    by_id = {str(p.get("pageid")): p for p in pages.values() if p.get("pageid") is not None}
    out: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for hit in hits:
        try:
            dist = float(hit.get("dist") or 1e9)
        except (TypeError, ValueError):
            continue
        if dist > max_m:
            continue
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
        if dist > 600 and not _LANDISH.search(title):
            continue
        width = int(ii.get("width") or 0)
        height = int(ii.get("height") or 0)
        if width and width < 640:
            continue
        if width and height:
            ratio = width / max(height, 1)
            if ratio < 0.55 or ratio > 2.6:
                continue
        if height and height < 420:
            continue
        url = ii.get("thumburl") or ii.get("url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        meters = int(round(dist))
        short = title[:56].rstrip()
        label = f"{short} · {meters} m away"
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
                distance_m=dist,
                caption=f"Ground photo near this land (~{meters} m): {short}.",
            )
        )
        if len(out) >= limit:
            break
    return out


def _cache_key(lat: float, lon: float, acres: float | None, mode: str) -> str:
    ac = round(float(acres), 1) if acres is not None else 0.0
    return f"v5:{mode}:{lat:.4f}:{lon:.4f}:{ac}"


def _cache_get(key: str) -> dict[str, Any] | None:
    hit = _CACHE.get(key)
    if not hit:
        return None
    ts, payload = hit
    if time.time() - ts > _CACHE_TTL_S:
        _CACHE.pop(key, None)
        return None
    return {**payload, "cached": True}


def _cache_put(key: str, payload: dict[str, Any]) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        # Drop oldest ~20%
        for k, _ in sorted(_CACHE.items(), key=lambda kv: kv[1][0])[: max(1, _CACHE_MAX // 5)]:
            _CACHE.pop(k, None)
    _CACHE[key] = (time.time(), payload)


def _maps_links(lat: float, lon: float) -> dict[str, str]:
    return {
        "google_maps": (
            "https://www.google.com/maps/@?api=1&map_action=map"
            f"&center={lat}%2C{lon}&zoom=17"
        ),
        "google_street_view": (
            "https://www.google.com/maps/@?api=1&map_action=pano"
            f"&viewpoint={lat}%2C{lon}"
        ),
        "google_earth": f"https://earth.google.com/web/@{lat},{lon},200a,1000d,35y,0h,0t,0r",
        "openstreetmap": (
            f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
        ),
        "kartaview": f"https://kartaview.org/map/@{lat},{lon},16z",
    }


def build_instant_images(
    *,
    lat: float,
    lon: float,
    acres: float | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Zero-wait gallery: satellite + Street View. Safe to show before enrichments."""
    images = _aerial_frames(lat, lon, acres, wide=True)
    images.append(_street_view_embed(lat, lon, acres))
    return {
        "ok": True,
        "images": images,
        "count": len(images),
        "attom_photos": False,
        "title": title,
        "lat": lat,
        "lon": lon,
        "phase": "instant",
        "note": (
            "Satellite of this land loads instantly. Nearby road photos fill in next — "
            "this is public imagery, not MLS listing photos."
        ),
        "maps": _maps_links(lat, lon),
        "cached": False,
    }


def build_location_images(
    *,
    lat: float | None,
    lon: float | None,
    acres: float | None = None,
    title: str | None = None,
    mode: str = "full",
) -> dict[str, Any]:
    if lat is None or lon is None or not (abs(lat) <= 90 and abs(lon) <= 180):
        return {
            "ok": False,
            "images": [],
            "count": 0,
            "note": "No coordinates on this parcel yet.",
            "attom_photos": False,
            "maps": {},
            "phase": mode,
        }

    lat_f = float(lat)
    lon_f = float(lon)
    acres_f = float(acres) if acres is not None else None
    mode_n = (mode or "full").strip().lower()
    if mode_n not in {"instant", "full", "enrich"}:
        mode_n = "full"

    if mode_n == "instant":
        return build_instant_images(lat=lat_f, lon=lon_f, acres=acres_f, title=title)

    cache_key = _cache_key(lat_f, lon_f, acres_f, "full")
    cached = _cache_get(cache_key)
    if cached:
        return cached

    instant = build_instant_images(lat=lat_f, lon=lon_f, acres=acres_f, title=title)
    images: list[dict[str, Any]] = list(instant["images"])

    street: list[dict[str, Any]] = []
    ground: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_street = pool.submit(_kartaview_street, lat_f, lon_f, acres=acres_f, limit=4)
        fut_ground = pool.submit(_wikimedia_ground, lat_f, lon_f, acres=acres_f, limit=2)
        try:
            street = fut_street.result(timeout=4.5)
        except Exception as exc:  # noqa: BLE001
            log.info("location_images_enrich_failed", kind="street", error=str(exc)[:120])
            street = []
        try:
            ground = fut_ground.result(timeout=4.5)
        except Exception as exc:  # noqa: BLE001
            log.info("location_images_enrich_failed", kind="ground", error=str(exc)[:120])
            ground = []

    if street and street[0].get("thumb_url"):
        for i, row in enumerate(images):
            if row.get("id") == "google-street-view":
                images[i] = {**row, "thumb_url": street[0]["thumb_url"]}
                break

    # If we have real road photos, drop the redundant "wide" aerial to keep the strip tight.
    if street:
        images = [r for r in images if r.get("id") not in {"esri-area", "mapbox-sat-wide", "usgs-area"}]

    seen = {i["url"] for i in images}
    for row in street + ground:
        if row["url"] in seen:
            continue
        images.append(row)
        seen.add(row["url"])

    if not any(i.get("kind") == "aerial" for i in images):
        images = _esri_fallback(lat_f, lon_f, acres_f) + images

    street_n = sum(1 for i in images if i.get("kind") in ("street", "streetview"))
    ground_n = sum(1 for i in images if i.get("kind") == "ground")
    note = (
        "Public imagery of this land — satellite first, then Street View"
        f" and {street_n} nearby road frame{'' if street_n == 1 else 's'}"
        + (f" plus {ground_n} close land photo{'' if ground_n == 1 else 's'}" if ground_n else "")
        + ". Not MLS listing photos; far town landmarks are filtered out."
    )

    payload = {
        "ok": True,
        "images": images,
        "count": len(images),
        "attom_photos": False,
        "title": title,
        "lat": lat_f,
        "lon": lon_f,
        "phase": "full",
        "note": note,
        "maps": _maps_links(lat_f, lon_f),
        "cached": False,
    }
    _cache_put(cache_key, payload)
    return payload
