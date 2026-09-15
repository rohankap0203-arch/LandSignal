"""Closest-landmark lookup for Land Viewer — server-side Overpass with hard deadlines.

Browser-direct Overpass is flaky (CORS, mirrors, encoding, geom timeouts). This module
owns Closest chip results so every kind returns quickly with legitimate OSM hits or a
clear empty/unavailable status — never an endless spinner.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Any, Literal

import httpx
import structlog

log = structlog.get_logger()

NearbyKind = Literal[
    # Existing Closest chips
    "flood",
    "wetland",
    "water",
    "road",
    "power",
    "town",
    "school",
    "hospital",
    # Access
    "highway",
    "airport",
    "railroad",
    # Utilities
    "electric",
    "transmission",
    "water_main",
    "sewer",
    "gas",
    "fiber",
    "substation",
    "cell",
    # Environment
    "wildfire",
    "conservation",
    # Services / context
    "grocery",
    "fire",
    "police",
    "park",
    "employer",
    "landfill",
    "mine",
    "prison",
    "hazmat",
]

OVERPASS_ENDPOINTS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Whole chip budget — API must answer inside this window.
SEARCH_DEADLINE_S = 10.0
MIRROR_TIMEOUT_S = 5.5
CACHE_TTL_S = 6 * 3600
RESULT_LIMIT = 3

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

KIND_META: dict[str, dict[str, Any]] = {
    "flood": {
        "label": "Flood zone",
        "max_miles": 15.0,
        "radii_m": [12000, 22000],
        "out": "center",
        "parts": ['way["waterway"~"^(river|stream|canal)$"]'],
        "fallback_parts": [
            'nwr["flood_prone"="yes"]',
            'nwr["hazard"="flood"]',
            'nwr["floodplain"="yes"]',
        ],
        "photon": [
            {"q": "stream", "osm_tag": "waterway:stream"},
            {"q": "river", "osm_tag": "waterway:river"},
            {"q": "canal", "osm_tag": "waterway:canal"},
        ],
    },
    "wetland": {
        "label": "Wetland",
        "max_miles": 18.0,
        "radii_m": [16000, 28000],
        "out": "center",
        "parts": ['nwr["natural"="wetland"]', 'nwr["wetland"]'],
        "photon": [
            {"q": "wetland", "osm_tag": "natural:wetland"},
            {"q": "marsh", "osm_tag": "wetland:marsh"},
        ],
    },
    "water": {
        "label": "Water body",
        "max_miles": 18.0,
        "radii_m": [16000, 28000],
        "out": "center",
        "parts": [
            'nwr["natural"="water"]',
            'nwr["water"~"^(lake|pond|reservoir|basin|lagoon)$"]',
            'nwr["landuse"="reservoir"]',
        ],
        "photon": [
            {"q": "lake", "osm_tag": "natural:water"},
            {"q": "reservoir", "osm_tag": "water:reservoir"},
            {"q": "pond", "osm_tag": "water:pond"},
        ],
    },
    "power": {
        "label": "Power line",
        "max_miles": 18.0,
        "radii_m": [8000, 16000, 28000],
        "out": "center",
        # Backward-compatible: major + distribution + substations.
        "parts": [
            'node["power"="tower"]',
            'node["power"="pole"]',
            'way["power"="line"]',
            'way["power"="minor_line"]',
            'node["power"="substation"]',
        ],
        "photon": [
            {"q": "power tower", "osm_tag": "power:tower"},
            {"q": "power pole", "osm_tag": "power:pole"},
            {"q": "substation", "osm_tag": "power:substation"},
        ],
    },
    "road": {
        "label": "Paved road",
        "max_miles": 12.0,
        "radii_m": [8000, 16000, 25000],
        "out": "center",
        "parts": [
            'way["highway"~"^(primary|secondary|tertiary|residential|unclassified|trunk)$"]',
        ],
        "photon": [
            {"q": "road", "osm_tag": "highway:primary"},
            {"q": "road", "osm_tag": "highway:secondary"},
            {"q": "road", "osm_tag": "highway:residential"},
        ],
    },
    "town": {
        "label": "Town / services",
        "max_miles": 35.0,
        "radii_m": [28000, 50000],
        "out": "center",
        "parts": ['node["place"~"^(city|town|village|hamlet)$"]'],
        "photon": [
            {"q": "town", "osm_tag": "place:town"},
            {"q": "city", "osm_tag": "place:city"},
            {"q": "village", "osm_tag": "place:village"},
        ],
    },
    "school": {
        "label": "School",
        "max_miles": 25.0,
        "radii_m": [20000, 35000],
        "out": "center",
        "parts": [
            'node["amenity"="school"]',
            'way["amenity"="school"]',
            'node["amenity"="kindergarten"]',
        ],
        "photon": [
            {"q": "school", "osm_tag": "amenity:school"},
            {"q": "school", "osm_tag": "building:school"},
        ],
    },
    "hospital": {
        "label": "Hospital",
        "max_miles": 50.0,
        "radii_m": [50000, 80000],
        "out": "center",
        "parts": [
            'node["amenity"="hospital"]',
            'way["amenity"="hospital"]',
            'node["healthcare"="hospital"]',
        ],
        "fallback_parts": [
            'node["amenity"="clinic"]',
            'way["amenity"="clinic"]',
        ],
        "photon": [
            {"q": "hospital", "osm_tag": "amenity:hospital"},
            {"q": "clinic", "osm_tag": "amenity:clinic"},
        ],
    },
    # --- Access ---
    "highway": {
        "label": "Highway",
        "max_miles": 25.0,
        "radii_m": [16000, 32000, 50000],
        "out": "center",
        "parts": [
            'way["highway"~"^(motorway|motorway_link|trunk|trunk_link)$"]',
        ],
        "photon": [
            {"q": "highway", "osm_tag": "highway:motorway"},
            {"q": "freeway", "osm_tag": "highway:trunk"},
        ],
    },
    "airport": {
        "label": "Airport",
        "max_miles": 60.0,
        "radii_m": [50000, 90000],
        "out": "center",
        "parts": [
            'nwr["aeroway"="aerodrome"]',
            'nwr["aeroway"="airport"]',
            'node["aeroway"="helipad"]',
        ],
        "photon": [
            {"q": "airport", "osm_tag": "aeroway:aerodrome"},
            {"q": "airport", "osm_tag": "aeroway:airport"},
        ],
    },
    "railroad": {
        "label": "Railroad",
        "max_miles": 20.0,
        "radii_m": [12000, 24000, 40000],
        "out": "center",
        "parts": [
            'way["railway"~"^(rail|light_rail|subway|tram)$"]',
            'node["railway"="station"]',
        ],
        "photon": [
            {"q": "railroad", "osm_tag": "railway:rail"},
            {"q": "train station", "osm_tag": "railway:station"},
        ],
    },
    # --- Utilities ---
    "transmission": {
        "label": "Transmission line",
        "max_miles": 18.0,
        "radii_m": [8000, 16000, 28000],
        "out": "center",
        # Major HV lines / towers (alias of the "power" major-line intent).
        "parts": [
            'node["power"="tower"]',
            'way["power"="line"]',
        ],
        "photon": [
            {"q": "power tower", "osm_tag": "power:tower"},
            {"q": "power line", "osm_tag": "power:line"},
        ],
    },
    "electric": {
        "label": "Electric distribution",
        "max_miles": 12.0,
        "radii_m": [6000, 12000, 20000],
        "out": "center",
        "parts": [
            'node["power"="pole"]',
            'way["power"="minor_line"]',
        ],
        "photon": [
            {"q": "power pole", "osm_tag": "power:pole"},
            {"q": "power line", "osm_tag": "power:minor_line"},
        ],
    },
    "water_main": {
        "label": "Public water",
        "max_miles": 20.0,
        "radii_m": [12000, 24000, 40000],
        "out": "center",
        "parts": [
            'nwr["man_made"="water_works"]',
            'nwr["office"="water_utility"]',
            'way["pipeline"="water"]',
            'nwr["man_made"="water_tower"]',
        ],
        "photon": [
            {"q": "water works", "osm_tag": "man_made:water_works"},
            {"q": "water utility", "osm_tag": "office:water_utility"},
            {"q": "water tower", "osm_tag": "man_made:water_tower"},
        ],
    },
    "sewer": {
        "label": "Sewer / wastewater",
        "max_miles": 20.0,
        "radii_m": [12000, 24000, 40000],
        "out": "center",
        "parts": [
            'nwr["man_made"="wastewater_plant"]',
            'nwr["man_made"="sewage_works"]',
            'way["pipeline"="sewage"]',
            'nwr["utility"="sewerage"]',
        ],
        "photon": [
            {"q": "wastewater plant", "osm_tag": "man_made:wastewater_plant"},
            {"q": "sewage", "osm_tag": "man_made:sewage_works"},
        ],
    },
    "gas": {
        "label": "Gas utility",
        "max_miles": 20.0,
        "radii_m": [12000, 24000, 40000],
        "out": "center",
        "parts": [
            'way["pipeline"="gas"]',
            'nwr["man_made"="gasometer"]',
            'nwr["office"="gas_utility"]',
            'node["utility"="gas"]',
        ],
        "photon": [
            {"q": "gas pipeline", "osm_tag": "pipeline:gas"},
            {"q": "gas utility", "osm_tag": "office:gas_utility"},
        ],
    },
    "fiber": {
        "label": "Fiber / telecom",
        "max_miles": 20.0,
        "radii_m": [12000, 24000, 40000],
        "out": "center",
        "parts": [
            'way["communication"="line"]',
            'way["cable"="fiber"]',
            'nwr["office"="telecommunication"]',
            'nwr["telecom"="exchange"]',
        ],
        "photon": [
            {"q": "telecom", "osm_tag": "office:telecommunication"},
            {"q": "fiber", "osm_tag": "cable:fiber"},
        ],
    },
    "substation": {
        "label": "Substation",
        "max_miles": 25.0,
        "radii_m": [16000, 32000, 50000],
        "out": "center",
        "parts": [
            'nwr["power"="substation"]',
            'node["power"="transformer"]',
        ],
        "photon": [
            {"q": "substation", "osm_tag": "power:substation"},
        ],
    },
    "cell": {
        "label": "Cell tower",
        "max_miles": 20.0,
        "radii_m": [12000, 24000, 40000],
        "out": "center",
        "parts": [
            'nwr["man_made"="mast"]',
            'nwr["man_made"="tower"]["tower:type"="communication"]',
            'nwr["tower:type"="communication"]',
            'nwr["communication:mobile_phone"="yes"]',
        ],
        "photon": [
            {"q": "cell tower", "osm_tag": "man_made:mast"},
            {"q": "communication tower", "osm_tag": "man_made:tower"},
        ],
    },
    # --- Environment ---
    "wildfire": {
        "label": "Wildfire hazard",
        "max_miles": 25.0,
        "radii_m": [16000, 32000, 50000],
        "out": "center",
        "parts": [
            'nwr["hazard"="fire"]',
            'nwr["hazard"="wildfire"]',
            'nwr["fire_hazard"]',
            'nwr["hazard:fire"]',
        ],
        "photon": [
            {"q": "fire hazard", "osm_tag": "hazard:fire"},
            {"q": "wildfire", "osm_tag": "hazard:wildfire"},
        ],
    },
    "conservation": {
        "label": "Conservation land",
        "max_miles": 30.0,
        "radii_m": [20000, 40000, 60000],
        "out": "center",
        "parts": [
            'nwr["boundary"="protected_area"]',
            'nwr["leisure"="nature_reserve"]',
            'nwr["landuse"="conservation"]',
            'nwr["protect_class"]',
        ],
        "photon": [
            {"q": "nature reserve", "osm_tag": "leisure:nature_reserve"},
            {"q": "protected area", "osm_tag": "boundary:protected_area"},
        ],
    },
    # --- Services / context ---
    "grocery": {
        "label": "Grocery",
        "max_miles": 25.0,
        "radii_m": [16000, 32000, 50000],
        "out": "center",
        "parts": [
            'nwr["shop"="supermarket"]',
            'nwr["shop"="grocery"]',
            'nwr["shop"="convenience"]',
        ],
        "photon": [
            {"q": "supermarket", "osm_tag": "shop:supermarket"},
            {"q": "grocery", "osm_tag": "shop:grocery"},
        ],
    },
    "fire": {
        "label": "Fire station",
        "max_miles": 30.0,
        "radii_m": [20000, 40000, 60000],
        "out": "center",
        "parts": [
            'nwr["amenity"="fire_station"]',
        ],
        "photon": [
            {"q": "fire station", "osm_tag": "amenity:fire_station"},
        ],
    },
    "police": {
        "label": "Police",
        "max_miles": 30.0,
        "radii_m": [20000, 40000, 60000],
        "out": "center",
        "parts": [
            'nwr["amenity"="police"]',
        ],
        "photon": [
            {"q": "police", "osm_tag": "amenity:police"},
        ],
    },
    "park": {
        "label": "Park",
        "max_miles": 20.0,
        "radii_m": [12000, 24000, 40000],
        "out": "center",
        "parts": [
            'nwr["leisure"="park"]',
            'nwr["leisure"="nature_reserve"]',
        ],
        "photon": [
            {"q": "park", "osm_tag": "leisure:park"},
            {"q": "nature reserve", "osm_tag": "leisure:nature_reserve"},
        ],
    },
    "employer": {
        "label": "Major employer",
        "max_miles": 30.0,
        "radii_m": [20000, 40000, 60000],
        "out": "center",
        "parts": [
            'nwr["landuse"="industrial"]',
            'nwr["industrial"]',
            'nwr["office"="company"]',
        ],
        "photon": [
            {"q": "industrial", "osm_tag": "landuse:industrial"},
            {"q": "factory", "osm_tag": "building:industrial"},
        ],
    },
    "landfill": {
        "label": "Landfill",
        "max_miles": 30.0,
        "radii_m": [20000, 40000, 60000],
        "out": "center",
        "parts": [
            'nwr["landuse"="landfill"]',
            'nwr["amenity"="waste_transfer_station"]',
        ],
        "photon": [
            {"q": "landfill", "osm_tag": "landuse:landfill"},
        ],
    },
    "mine": {
        "label": "Mine / quarry",
        "max_miles": 30.0,
        "radii_m": [20000, 40000, 60000],
        "out": "center",
        "parts": [
            'nwr["landuse"="quarry"]',
            'nwr["landuse"="mine"]',
            'nwr["man_made"="mineshaft"]',
            'nwr["industrial"="mine"]',
        ],
        "photon": [
            {"q": "quarry", "osm_tag": "landuse:quarry"},
            {"q": "mine", "osm_tag": "landuse:mine"},
        ],
    },
    "prison": {
        "label": "Prison",
        "max_miles": 40.0,
        "radii_m": [30000, 50000, 80000],
        "out": "center",
        "parts": [
            'nwr["amenity"="prison"]',
        ],
        "photon": [
            {"q": "prison", "osm_tag": "amenity:prison"},
        ],
    },
    "hazmat": {
        "label": "Hazmat / industrial risk",
        "max_miles": 25.0,
        "radii_m": [16000, 32000, 50000],
        "out": "center",
        "parts": [
            'nwr["hazard"="contamination"]',
            'nwr["hazard"="nuclear"]',
            'nwr["industrial"="oil"]',
            'nwr["hazmat"]',
            'nwr["industrial"="refinery"]',
        ],
        "photon": [
            {"q": "refinery", "osm_tag": "industrial:oil"},
            {"q": "contamination", "osm_tag": "hazard:contamination"},
        ],
    },
}




def _haversine_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlmb = math.radians(b_lon - a_lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _closest_on_segment(
    p_lat: float, p_lon: float, a_lat: float, a_lon: float, b_lat: float, b_lon: float
) -> tuple[float, float, float]:
    m_lat = 111320.0
    m_lon = 111320.0 * max(0.2, math.cos(math.radians(p_lat)))
    px = (p_lon - a_lon) * m_lon
    py = (p_lat - a_lat) * m_lat
    bx = (b_lon - a_lon) * m_lon
    by = (b_lat - a_lat) * m_lat
    denom = bx * bx + by * by
    t = 0.0 if denom <= 1e-9 else max(0.0, min(1.0, (px * bx + py * by) / denom))
    lon = a_lon + (t * bx) / m_lon
    lat = a_lat + (t * by) / m_lat
    return lat, lon, _haversine_m(p_lat, p_lon, lat, lon)


def _title(v: str) -> str:
    return v.replace("_", " ").strip().title()


def _is_flood(tags: dict[str, str]) -> bool:
    return bool(
        tags.get("flood_prone") == "yes"
        or tags.get("hazard") == "flood"
        or tags.get("flood:zone")
        or tags.get("floodplain") == "yes"
    )


def _matches(kind: str, el: dict[str, Any]) -> bool:
    tags = {str(k): str(v) for k, v in (el.get("tags") or {}).items()}
    if kind == "flood":
        ww = tags.get("waterway", "")
        return _is_flood(tags) or ww in {"river", "stream", "canal"}
    if kind == "wetland":
        return tags.get("natural") == "wetland" or bool(tags.get("wetland") and tags.get("wetland") != "no")
    if kind == "water":
        water = tags.get("water", "")
        if water in {
            "river",
            "stream",
            "canal",
            "drain",
            "ditch",
            "swimming_pool",
            "reflecting_pool",
            "fountain",
            "moat",
        }:
            return False
        if tags.get("leisure") == "swimming_pool":
            return False
        if tags.get("landuse") == "basin" and tags.get("basin") == "detention":
            return False
        return (
            tags.get("natural") == "water"
            or water in {"lake", "pond", "reservoir", "basin", "lagoon"}
            or tags.get("landuse") == "reservoir"
        )
    if kind == "road":
        hw = tags.get("highway", "")
        surface = tags.get("surface", "")
        if surface in {
            "unpaved",
            "gravel",
            "dirt",
            "earth",
            "grass",
            "sand",
            "mud",
            "ground",
            "fine_gravel",
            "pebblestone",
            "wood",
            "metal",
        }:
            return False
        return hw in {
            "motorway",
            "motorway_link",
            "trunk",
            "trunk_link",
            "primary",
            "primary_link",
            "secondary",
            "secondary_link",
            "tertiary",
            "tertiary_link",
            "residential",
            "unclassified",
        }
    if kind == "highway":
        return tags.get("highway") in {"motorway", "motorway_link", "trunk", "trunk_link"}
    if kind == "airport":
        return tags.get("aeroway") in {"aerodrome", "airport", "helipad"}
    if kind == "railroad":
        return tags.get("railway") in {"rail", "light_rail", "subway", "tram", "station"}
    if kind == "power":
        return tags.get("power") in {"line", "minor_line", "tower", "pole", "substation"}
    if kind == "transmission":
        return tags.get("power") in {"line", "tower"}
    if kind == "electric":
        return tags.get("power") in {"pole", "minor_line"}
    if kind == "water_main":
        return (
            tags.get("man_made") in {"water_works", "water_tower"}
            or tags.get("office") == "water_utility"
            or tags.get("pipeline") == "water"
        )
    if kind == "sewer":
        return (
            tags.get("man_made") in {"wastewater_plant", "sewage_works"}
            or tags.get("pipeline") == "sewage"
            or tags.get("utility") == "sewerage"
        )
    if kind == "gas":
        return (
            tags.get("pipeline") == "gas"
            or tags.get("man_made") == "gasometer"
            or tags.get("office") == "gas_utility"
            or tags.get("utility") == "gas"
        )
    if kind == "fiber":
        return (
            tags.get("communication") == "line"
            or tags.get("cable") == "fiber"
            or tags.get("office") == "telecommunication"
            or tags.get("telecom") == "exchange"
        )
    if kind == "substation":
        return tags.get("power") in {"substation", "transformer"}
    if kind == "cell":
        return (
            tags.get("man_made") == "mast"
            or tags.get("tower:type") == "communication"
            or tags.get("communication:mobile_phone") == "yes"
            or (tags.get("man_made") == "tower" and tags.get("tower:type") == "communication")
        )
    if kind == "wildfire":
        return (
            tags.get("hazard") in {"fire", "wildfire"}
            or bool(tags.get("fire_hazard") and tags.get("fire_hazard") != "no")
            or bool(tags.get("hazard:fire") and tags.get("hazard:fire") != "no")
        )
    if kind == "conservation":
        return (
            tags.get("boundary") == "protected_area"
            or tags.get("leisure") == "nature_reserve"
            or tags.get("landuse") == "conservation"
            or bool(tags.get("protect_class"))
        )
    if kind == "grocery":
        return tags.get("shop") in {"supermarket", "grocery", "convenience"}
    if kind == "fire":
        return tags.get("amenity") == "fire_station"
    if kind == "police":
        return tags.get("amenity") == "police"
    if kind == "park":
        return tags.get("leisure") in {"park", "nature_reserve"}
    if kind == "employer":
        return (
            tags.get("landuse") == "industrial"
            or bool(tags.get("industrial") and tags.get("industrial") != "no")
            or tags.get("office") == "company"
            or tags.get("building") == "industrial"
        )
    if kind == "landfill":
        return tags.get("landuse") == "landfill" or tags.get("amenity") == "waste_transfer_station"
    if kind == "mine":
        return (
            tags.get("landuse") in {"quarry", "mine"}
            or tags.get("man_made") == "mineshaft"
            or tags.get("industrial") == "mine"
        )
    if kind == "prison":
        return tags.get("amenity") == "prison"
    if kind == "hazmat":
        return (
            tags.get("hazard") in {"contamination", "nuclear"}
            or tags.get("industrial") in {"oil", "refinery"}
            or bool(tags.get("hazmat") and tags.get("hazmat") != "no")
        )
    if kind == "town":
        return tags.get("place") in {"city", "town", "village", "hamlet"}
    if kind == "school":
        return (
            tags.get("amenity") in {"school", "kindergarten"}
            or tags.get("building") == "school"
        )
    if kind == "hospital":
        return (
            tags.get("amenity") == "hospital"
            or tags.get("healthcare") == "hospital"
            or tags.get("amenity") == "clinic"
        )
    return False


def _point_for(el: dict[str, Any], origin: tuple[float, float]) -> tuple[float, float, float] | None:
    o_lat, o_lon = origin
    geom = el.get("geometry") or []
    if isinstance(geom, list) and len(geom) >= 2:
        best: tuple[float, float, float] | None = None
        for i in range(len(geom) - 1):
            a, b = geom[i], geom[i + 1]
            try:
                a_lat, a_lon = float(a["lat"]), float(a["lon"])
                b_lat, b_lon = float(b["lat"]), float(b["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            hit = _closest_on_segment(o_lat, o_lon, a_lat, a_lon, b_lat, b_lon)
            if best is None or hit[2] < best[2]:
                best = hit
        if best:
            return best
    if isinstance(geom, list) and len(geom) == 1:
        try:
            lat, lon = float(geom[0]["lat"]), float(geom[0]["lon"])
            return lat, lon, _haversine_m(o_lat, o_lon, lat, lon)
        except (KeyError, TypeError, ValueError):
            pass
    center = el.get("center") or {}
    lat = el.get("lat", center.get("lat"))
    lon = el.get("lon", center.get("lon"))
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if abs(lat_f) > 90 or abs(lon_f) > 180:
        return None
    return lat_f, lon_f, _haversine_m(o_lat, o_lon, lat_f, lon_f)


def _name(kind: str, el: dict[str, Any], fallback: str) -> str:
    tags = {str(k): str(v) for k, v in (el.get("tags") or {}).items()}
    named = tags.get("name") or tags.get("name:en") or tags.get("brand")
    if named:
        return named
    if kind == "flood":
        if _is_flood(tags):
            zone = tags.get("flood:zone")
            return f"Flood zone {zone}" if zone else "Mapped flood hazard"
        if tags.get("waterway"):
            return f"{_title(tags['waterway'])} (flood-adjacency)"
    if kind == "wetland":
        w = tags.get("wetland")
        return f"{_title(w)} wetland" if w and w not in {"yes", "no"} else "Wetland"
    if kind == "water":
        if tags.get("water"):
            return _title(tags["water"])
        if tags.get("landuse") == "reservoir":
            return "Reservoir"
        return "Water body"
    if kind == "road":
        if tags.get("ref"):
            return tags["ref"]
        if tags.get("highway"):
            return f"{_title(tags['highway'])} road"
        return "Paved road"
    if kind == "highway":
        if tags.get("ref"):
            return tags["ref"]
        hw = tags.get("highway", "")
        return f"{_title(hw.replace('_link', ''))} highway" if hw else "Highway"
    if kind == "airport":
        return "Helipad" if tags.get("aeroway") == "helipad" else "Airport"
    if kind == "railroad":
        if tags.get("railway") == "station":
            return "Rail station"
        return "Railroad"
    if kind == "power":
        if tags.get("power") in {"tower", "pole"}:
            return "Transmission / distribution support (power corridor)"
        op = tags.get("operator")
        return f"{op} power line" if op else "Power line"
    if kind == "transmission":
        op = tags.get("operator")
        if tags.get("power") == "tower":
            return "Transmission tower"
        return f"{op} transmission line" if op else "Transmission line"
    if kind == "electric":
        return "Distribution pole" if tags.get("power") == "pole" else "Distribution line"
    if kind == "water_main":
        if tags.get("man_made") == "water_tower":
            return "Water tower"
        if tags.get("man_made") == "water_works":
            return "Water works"
        return "Public water facility"
    if kind == "sewer":
        return "Wastewater plant" if tags.get("man_made") else "Sewer infrastructure"
    if kind == "gas":
        return "Gas pipeline" if tags.get("pipeline") == "gas" else "Gas utility"
    if kind == "fiber":
        return "Telecom facility" if tags.get("office") == "telecommunication" else "Fiber / telecom line"
    if kind == "substation":
        return "Electrical substation"
    if kind == "cell":
        return "Cell / communication tower"
    if kind == "wildfire":
        return "Mapped wildfire hazard"
    if kind == "conservation":
        return "Nature reserve" if tags.get("leisure") == "nature_reserve" else "Protected area"
    if kind == "grocery":
        return _title(tags.get("shop") or "grocery")
    if kind == "fire":
        return "Fire station"
    if kind == "police":
        return "Police station"
    if kind == "park":
        return "Nature reserve" if tags.get("leisure") == "nature_reserve" else "Park"
    if kind == "employer":
        return "Industrial site"
    if kind == "landfill":
        return "Landfill"
    if kind == "mine":
        return "Quarry" if tags.get("landuse") == "quarry" else "Mine"
    if kind == "prison":
        return "Prison"
    if kind == "hazmat":
        if tags.get("industrial") in {"oil", "refinery"}:
            return "Oil / refinery site"
        return "Hazmat / contamination site"
    if kind == "town":
        return _title(tags["place"]) if tags.get("place") else "Town"
    if kind == "school":
        return "School"
    if kind == "hospital":
        return "Emergency clinic" if tags.get("amenity") == "clinic" else "Hospital"
    return fallback


_UTILITY_KINDS = frozenset(
    {
        "power",
        "transmission",
        "electric",
        "water_main",
        "sewer",
        "gas",
        "fiber",
        "substation",
        "cell",
    }
)
_HAZARD_AREA_KINDS = frozenset(
    {
        "flood",
        "wetland",
        "water",
        "wildfire",
        "hazmat",
        "conservation",
        "landfill",
        "mine",
        "sewer",
        "gas",
        "highway",
        "railroad",
        "transmission",
        "electric",
        "power",
    }
)
_FRONTAGE_KINDS = frozenset({"road", "water", "highway"})


def _facility_type(kind: str, el: dict[str, Any]) -> str:
    tags = {str(k): str(v) for k, v in (el.get("tags") or {}).items()}
    for key in (
        "power",
        "highway",
        "railway",
        "aeroway",
        "waterway",
        "natural",
        "wetland",
        "water",
        "shop",
        "amenity",
        "leisure",
        "landuse",
        "industrial",
        "man_made",
        "office",
        "pipeline",
        "hazard",
        "boundary",
        "place",
        "healthcare",
        "tower:type",
        "telecom",
        "cable",
        "communication",
    ):
        val = tags.get(key)
        if val and val not in {"yes", "no"}:
            return f"{key}={val}"
    return kind


def _hit_source(el: dict[str, Any]) -> str:
    tags = {str(k): str(v) for k, v in (el.get("tags") or {}).items()}
    if tags.get("source") == "osrm_nearest":
        return "OSRM"
    return "OpenStreetMap"


def _hit_confidence(kind: str, el: dict[str, Any]) -> str:
    tags = {str(k): str(v) for k, v in (el.get("tags") or {}).items()}
    if kind == "flood" and _is_flood(tags):
        return "mapped"
    return "estimated"


def _hit_relation(kind: str, meters: float) -> str:
    if kind in _FRONTAGE_KINDS and meters < 30:
        return "frontage_possible"
    if kind in _HAZARD_AREA_KINDS and meters < 35:
        return "intersects_likely"
    if meters < 1609.344:
        return "nearby"
    return "distant"


def _hit_disclaimer(kind: str) -> str | None:
    if kind == "flood":
        return "OSM flood-adjacency proxy — not FEMA SFHA"
    if kind == "wetland":
        return "OSM wetland mapping — coverage and boundaries vary by region"
    if kind in _UTILITY_KINDS:
        return "Proximity ≠ confirmed service availability"
    if kind == "road":
        return "Proximity ≠ confirmed legal access"
    return None


def _detail(kind: str, el: dict[str, Any], meters: float | None = None) -> str | None:
    tags = {str(k): str(v) for k, v in (el.get("tags") or {}).items()}
    if kind == "flood":
        if meters is not None and meters < 50:
            return "Adjacent or overlapping mapped flood-related feature (OSM proxy)"
        return (
            "Mapped flood hazard tag"
            if _is_flood(tags)
            else "Nearest mapped waterway (flood-adjacency proxy)"
        )
    if kind == "hospital" and tags.get("amenity") == "clinic":
        return (
            "Emergency clinic (no hospital mapped closer)"
            if tags.get("emergency") == "yes"
            else "Clinic (no hospital mapped closer)"
        )
    if kind == "town" and tags.get("place"):
        return f"OSM place={tags['place']}"
    if kind == "water" and tags.get("water"):
        return f"OSM water={tags['water']}"
    if kind == "road" and tags.get("source") == "osrm_nearest":
        return "Nearest drivable road (OSRM)"
    if kind == "power":
        p = tags.get("power")
        if p in {"tower", "pole"}:
            return "Nearest mapped power tower/pole (line corridor proxy)"
    if kind == "transmission" and tags.get("power") == "tower":
        return "Nearest mapped transmission tower (line corridor proxy)"
    if kind == "electric" and tags.get("power") == "pole":
        return "Nearest mapped distribution pole"
    if kind == "wildfire":
        return "OSM wildfire/hazard tag — coverage is limited"
    return None


def _rank_boost(kind: str, el: dict[str, Any]) -> int:
    tags = {str(k): str(v) for k, v in (el.get("tags") or {}).items()}
    if kind == "hospital" and tags.get("amenity") == "clinic":
        return 1
    if kind == "flood" and not _is_flood(tags):
        return 1
    if kind == "airport" and tags.get("aeroway") == "helipad":
        return 1
    if kind == "grocery" and tags.get("shop") == "convenience":
        return 1
    return 0


def _element_key(el: dict[str, Any]) -> str:
    t = el.get("type")
    i = el.get("id")
    if t and i is not None:
        return f"{t}/{i}"
    center = el.get("center") or {}
    lat = el.get("lat", center.get("lat"))
    lon = el.get("lon", center.get("lon"))
    return f"pt:{lat}:{lon}"


def _pick_hits(
    kind: str,
    label: str,
    origin: tuple[float, float],
    elements: list[dict[str, Any]],
    *,
    max_miles: float,
    radius_m: float,
    limit: int = RESULT_LIMIT,
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    max_m = min(max_miles * 1609.344, radius_m * 1.2)
    for el in elements:
        if not _matches(kind, el):
            continue
        pt = _point_for(el, origin)
        if not pt:
            continue
        lat, lon, meters = pt
        if meters < 0 or meters > max_m:
            continue
        key = _element_key(el)
        hit = {
            "kind": kind,
            "label": label,
            "name": _name(kind, el, label),
            "lat": lat,
            "lon": lon,
            "meters": meters,
            "detail": _detail(kind, el, meters),
            "osm_key": key,
            "relation": _hit_relation(kind, meters),
            "measurement": "boundary_distance_m",
            "source": _hit_source(el),
            "confidence": _hit_confidence(kind, el),
            "facility_type": _facility_type(kind, el),
            "disclaimer": _hit_disclaimer(kind),
            "_boost": _rank_boost(kind, el),
        }
        prev = by_key.get(key)
        if prev is None or meters < prev["meters"]:
            by_key[key] = hit
    ranked = sorted(by_key.values(), key=lambda h: (h["_boost"], h["meters"]))
    out: list[dict[str, Any]] = []
    for raw in ranked:
        near_dup = any(
            _haversine_m(o["lat"], o["lon"], raw["lat"], raw["lon"]) < 55
            and o["name"].strip().lower() == raw["name"].strip().lower()
            for o in out
        )
        if near_dup:
            continue
        clean = {k: v for k, v in raw.items() if k != "_boost"}
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _build_query(parts: list[str], lat: float, lon: float, radius_m: int, out_mode: str, timeout_s: int) -> str:
    union = "\n".join(f"  {part}(around:{radius_m},{lat:.6f},{lon:.6f});" for part in parts)
    out_clause = "out center tags qt;" if out_mode == "center" else "out geom qt;"
    return f"[out:json][timeout:{timeout_s}];\n(\n{union}\n);\n{out_clause}"


async def _overpass_once(client: httpx.AsyncClient, query: str, endpoint: str) -> list[dict[str, Any]]:
    res = await client.post(
        endpoint,
        data={"data": query},
        headers={"User-Agent": "LandSignal/0.1 (closest-landmarks; server)"},
    )
    if res.status_code != 200:
        raise RuntimeError(f"Overpass {res.status_code}")
    payload = res.json()
    return list(payload.get("elements") or [])


async def _overpass_race(query: str, budget_s: float) -> tuple[list[dict[str, Any]], bool]:
    """Query mirrors in parallel. Returns (elements, upstream_succeeded)."""
    if budget_s <= 0.4:
        return [], False
    timeout = httpx.Timeout(max(0.5, min(budget_s, MIRROR_TIMEOUT_S)))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        tasks = [asyncio.create_task(_overpass_once(client, query, ep)) for ep in OVERPASS_ENDPOINTS]
        empty_ok = False
        try:
            while tasks:
                remaining = budget_s
                if remaining <= 0:
                    break
                finished, pending = await asyncio.wait(
                    tasks, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
                )
                tasks = list(pending)
                for fut in finished:
                    try:
                        els = fut.result()
                    except Exception:
                        continue
                    empty_ok = True
                    if els:
                        for p in tasks:
                            p.cancel()
                        return els, True
                if not finished:
                    break
        finally:
            for t in tasks:
                t.cancel()
        return [], empty_ok


async def _osrm_nearest_roads(lat: float, lon: float, budget_s: float) -> list[dict[str, Any]]:
    """Nearest drivable roads via OSRM — works for every geocoded listing nationwide."""
    if budget_s <= 0.4:
        return []
    timeout = httpx.Timeout(max(0.5, min(budget_s, 4.0)))
    url = f"https://router.project-osrm.org/nearest/v1/driving/{lon:.6f},{lat:.6f}"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            res = await client.get(
                url,
                params={"number": "5"},
                headers={"User-Agent": "LandSignal/0.1 (closest-landmarks; server)"},
            )
            if res.status_code != 200:
                return []
            payload = res.json()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for i, wp in enumerate(payload.get("waypoints") or []):
        loc = wp.get("location") or []
        if len(loc) < 2:
            continue
        try:
            r_lon, r_lat = float(loc[0]), float(loc[1])
        except (TypeError, ValueError):
            continue
        name = str(wp.get("name") or "").strip() or "Drivable road"
        out.append(
            {
                "type": "node",
                "id": f"osrm-{i}",
                "lat": r_lat,
                "lon": r_lon,
                "tags": {
                    "name": name,
                    "highway": "secondary",
                    "source": "osrm_nearest",
                },
            }
        )
    return out


async def _photon_pois(
    lat: float,
    lon: float,
    queries: list[dict[str, str]],
    budget_s: float,
) -> list[dict[str, Any]]:
    """Photon (Komoot) locality search — fast nationwide POI lookup for any lat/lon."""
    if budget_s <= 0.3 or not queries:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    timeout = httpx.Timeout(max(0.5, min(budget_s, 3.5)))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for spec in queries:
            if budget_s <= 0.25:
                break
            t0 = time.monotonic()
            params = {
                "q": spec["q"],
                "lat": f"{lat:.6f}",
                "lon": f"{lon:.6f}",
                "limit": "8",
                "osm_tag": spec["osm_tag"],
            }
            try:
                res = await client.get(
                    "https://photon.komoot.io/api/",
                    params=params,
                    headers={"User-Agent": "LandSignal/0.1 (closest-landmarks; server)"},
                )
                if res.status_code != 200:
                    continue
                feats = (res.json() or {}).get("features") or []
            except Exception:
                continue
            finally:
                budget_s -= time.monotonic() - t0
            for feat in feats:
                props = feat.get("properties") or {}
                geom = feat.get("geometry") or {}
                coords = geom.get("coordinates") or []
                if len(coords) < 2:
                    continue
                try:
                    r_lon, r_lat = float(coords[0]), float(coords[1])
                except (TypeError, ValueError):
                    continue
                osm_key = str(props.get("osm_key") or "")
                osm_value = str(props.get("osm_value") or "")
                osm_type = str(props.get("osm_type") or "n")
                osm_id = props.get("osm_id")
                key = f"{osm_type}/{osm_id}" if osm_id is not None else f"pt:{r_lat:.5f}:{r_lon:.5f}"
                if key in seen:
                    continue
                seen.add(key)
                tags: dict[str, str] = {"name": str(props.get("name") or props.get("street") or "").strip()}
                if osm_key and osm_value:
                    tags[osm_key] = osm_value
                # Normalize common Photon keys into our matcher tags.
                if osm_key == "amenity":
                    tags["amenity"] = osm_value
                if osm_key == "healthcare":
                    tags["healthcare"] = osm_value
                if osm_key == "place":
                    tags["place"] = osm_value
                if osm_key == "natural":
                    tags["natural"] = osm_value
                if osm_key == "water":
                    tags["water"] = osm_value
                if osm_key == "waterway":
                    tags["waterway"] = osm_value
                if osm_key == "wetland":
                    tags["wetland"] = osm_value
                if osm_key == "power":
                    tags["power"] = osm_value
                if osm_key == "building" and osm_value == "school":
                    tags["building"] = "school"
                    tags["amenity"] = tags.get("amenity") or "school"
                if not tags.get("name"):
                    tags["name"] = _title(osm_value or spec["q"])
                typ = {"N": "node", "W": "way", "R": "relation"}.get(osm_type.upper()[:1], "node")
                out.append({"type": typ, "id": osm_id, "lat": r_lat, "lon": r_lon, "tags": tags})
    return out


async def _nominatim_towns(lat: float, lon: float, radius_m: int, budget_s: float) -> list[dict[str, Any]]:
    if budget_s <= 0.4:
        return []
    lat_d = radius_m / 111_320
    lon_d = radius_m / (111_320 * max(0.2, math.cos(math.radians(lat))))
    viewbox = f"{lon - lon_d},{lat + lat_d},{lon + lon_d},{lat - lat_d}"
    out: list[dict[str, Any]] = []
    timeout = httpx.Timeout(max(0.5, min(budget_s, 3.5)))
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for q in ("city", "town", "village"):
            if budget_s <= 0.3:
                break
            t0 = time.monotonic()
            try:
                res = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "format": "jsonv2",
                        "limit": "6",
                        "dedupe": "1",
                        "bounded": "1",
                        "q": q,
                        "featuretype": "settlement",
                        "viewbox": viewbox,
                    },
                    headers={
                        "User-Agent": "LandSignal/0.1 (closest-landmarks; server)",
                        "Accept": "application/json",
                    },
                )
                if res.status_code != 200:
                    continue
                rows = res.json()
            except Exception:
                continue
            finally:
                budget_s -= time.monotonic() - t0
            for row in rows if isinstance(rows, list) else []:
                place = str(row.get("type") or "").lower()
                if place not in {"city", "town", "village"}:
                    continue
                if row.get("class") and row.get("class") != "place":
                    continue
                try:
                    r_lat = float(row["lat"])
                    r_lon = float(row["lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                if _haversine_m(lat, lon, r_lat, r_lon) > radius_m * 1.05:
                    continue
                osm_type = row.get("osm_type") or "node"
                osm_id = row.get("osm_id")
                out.append(
                    {
                        "type": osm_type if osm_type in {"node", "way", "relation"} else "node",
                        "id": osm_id,
                        "lat": r_lat,
                        "lon": r_lon,
                        "tags": {
                            "name": row.get("name")
                            or str(row.get("display_name") or "").split(",")[0]
                            or _title(place),
                            "place": place,
                        },
                    }
                )
    return out


def _cache_key(kind: str, lat: float, lon: float) -> str:
    return f"v4:{kind}:{lat:.3f}:{lon:.3f}"


async def find_nearby(lat: float, lon: float, kind: str) -> dict[str, Any]:
    """Resolve Closest chips for any listing pin worldwide."""
    meta = KIND_META.get(kind)
    if not meta:
        return {
            "kind": kind,
            "label": kind,
            "hits": [],
            "status": "invalid_kind",
            "message": f"Unknown Closest kind: {kind}",
            "max_miles": None,
        }

    key = _cache_key(kind, lat, lon)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < CACHE_TTL_S and cached[1].get("hits"):
        return {**cached[1], "cached": True}

    label = meta["label"]
    max_miles = float(meta["max_miles"])
    origin = (lat, lon)
    started = time.monotonic()
    best: list[dict[str, Any]] = []
    upstream_ok = False
    searched_radius = int(meta["radii_m"][-1])

    def remaining() -> float:
        return SEARCH_DEADLINE_S - (time.monotonic() - started)

    # --- Primary: kind-specific fast nationwide sources ---
    elements: list[dict[str, Any]] = []
    try:
        if kind == "road":
            osrm_els = await _osrm_nearest_roads(lat, lon, min(4.0, remaining()))
            if osrm_els:
                upstream_ok = True
                elements.extend(osrm_els)
        else:
            photon_specs = list(meta.get("photon") or [])
            if photon_specs and remaining() > 0.5:
                photon_els = await _photon_pois(lat, lon, photon_specs, min(4.5, remaining()))
                if photon_els:
                    upstream_ok = True
                    elements.extend(photon_els)
            if kind == "town" and remaining() > 0.8:
                nom = await _nominatim_towns(lat, lon, searched_radius, min(3.0, remaining()))
                if nom:
                    upstream_ok = True
                    elements.extend(nom)
    except Exception as exc:  # noqa: BLE001
        log.warning("nearby_primary_failed", kind=kind, error=str(exc))

    best = _pick_hits(
        kind, label, origin, elements, max_miles=max_miles, radius_m=float(searched_radius)
    )

    # --- Secondary: Overpass only if still short on hits ---
    if len(best) < RESULT_LIMIT and remaining() > 1.2:
        for radius in meta["radii_m"]:
            if remaining() < 1.0:
                break
            searched_radius = int(radius)
            timeout_s = max(5, min(10, int(remaining())))
            query = _build_query(meta["parts"], lat, lon, int(radius), meta["out"], timeout_s)
            try:
                ov_els, ov_ok = await _overpass_race(query, remaining() - 0.2)
                if ov_ok:
                    upstream_ok = True
                hits = _pick_hits(
                    kind, label, origin, ov_els, max_miles=max_miles, radius_m=float(radius)
                )
                if (
                    not hits
                    and meta.get("fallback_parts")
                    and remaining() > 1.0
                ):
                    fb_query = _build_query(
                        meta["fallback_parts"],
                        lat,
                        lon,
                        int(radius),
                        meta["out"],
                        max(5, int(remaining())),
                    )
                    fb_els, fb_ok = await _overpass_race(fb_query, remaining() - 0.2)
                    if fb_ok:
                        upstream_ok = True
                    hits = _pick_hits(
                        kind, label, origin, fb_els, max_miles=max_miles, radius_m=float(radius)
                    )
                if hits:
                    merged: dict[str, dict[str, Any]] = {}
                    for h in best + hits:
                        k = h.get("osm_key") or f"{h['lat']:.5f},{h['lon']:.5f}"
                        prev = merged.get(k)
                        if prev is None or h["meters"] < prev["meters"]:
                            merged[k] = h
                    best = sorted(merged.values(), key=lambda x: x["meters"])[:RESULT_LIMIT]
                    if len(best) >= RESULT_LIMIT:
                        break
            except Exception as exc:  # noqa: BLE001
                log.warning("nearby_overpass_failed", kind=kind, radius=radius, error=str(exc))

    if best:
        payload = {
            "kind": kind,
            "label": label,
            "hits": best,
            "status": "ok",
            "message": None,
            "max_miles": max_miles,
            "searched_radius_m": searched_radius,
            "cached": False,
        }
        _CACHE[key] = (time.time(), payload)
        return payload

    if upstream_ok:
        message = f"No mapped {label.lower()} within ~{max_miles:g} mi"
        status = "empty"
    else:
        message = f"Map data temporarily unavailable for {label.lower()} — tap again to retry"
        status = "unavailable"

    return {
        "kind": kind,
        "label": label,
        "hits": [],
        "status": status,
        "message": message,
        "max_miles": max_miles,
        "searched_radius_m": searched_radius,
        "cached": False,
    }
