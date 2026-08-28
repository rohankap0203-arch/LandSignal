"""Compact parcel outlines for View Map — yellow boundary without OOM.

Full GIS rings can be thousands of vertices and previously blew memory when
kept on every nationwide parcel. We keep a tiny outline (≤28 verts) or an
acreage-sized square around the pin so View Map can always draw the land.
"""

from __future__ import annotations

import math
from typing import Any


_MAX_OUTLINE_POINTS = 28


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        n = float(v)
        return n if n == n else None
    except (TypeError, ValueError):
        return None


def acreage_square_polygon(
    lon: float,
    lat: float,
    acres: float | None,
) -> list[list[list[float]]]:
    """Axis-aligned square matching published acreage (fallback outline)."""
    ac = _f(acres)
    if ac is None or ac <= 0:
        ac = 5.0
    # Cap absurd assessor typos so the outline stays on-screen.
    ac = max(0.25, min(ac, 10_000.0))
    m2 = ac * 4046.8564224
    side = math.sqrt(m2)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * max(0.2, math.cos(lat * math.pi / 180.0))
    d_lat = (side / 2.0) / m_per_deg_lat
    d_lon = (side / 2.0) / m_per_deg_lon
    ring = [
        [lon - d_lon, lat - d_lat],
        [lon + d_lon, lat - d_lat],
        [lon + d_lon, lat + d_lat],
        [lon - d_lon, lat + d_lat],
        [lon - d_lon, lat - d_lat],
    ]
    return [ring]


def _close_ring(ring: list[list[float]]) -> list[list[float]]:
    if len(ring) < 3:
        return ring
    if ring[0][0] != ring[-1][0] or ring[0][1] != ring[-1][1]:
        return [*ring, [ring[0][0], ring[0][1]]]
    return ring


def _subsample_ring(ring: list[list[float]], max_points: int) -> list[list[float]]:
    """Evenly keep up to max_points unique vertices (plus closing point)."""
    if len(ring) <= 2:
        return ring
    open_ring = ring[:-1] if ring[0] == ring[-1] else ring
    if len(open_ring) <= max_points - 1:
        return _close_ring([[float(p[0]), float(p[1])] for p in open_ring])
    keep = max_points - 1
    step = (len(open_ring) - 1) / max(1, keep - 1)
    picked: list[list[float]] = []
    for i in range(keep):
        idx = min(len(open_ring) - 1, int(round(i * step)))
        pt = [float(open_ring[idx][0]), float(open_ring[idx][1])]
        if not picked or picked[-1] != pt:
            picked.append(pt)
    return _close_ring(picked)


def compact_polygon(
    polygon: Any,
    *,
    max_points: int = _MAX_OUTLINE_POINTS,
) -> list[list[list[float]]] | None:
    """Return a memory-safe exterior ring for map outline drawing."""
    if not isinstance(polygon, list) or not polygon:
        return None
    # GeoJSON Polygon: [ring, hole, ...] — keep exterior only.
    # MultiPolygon accidentally passed as coords: [ [ring...], [ring...] ]
    ring = polygon[0]
    if not isinstance(ring, list) or not ring:
        return None
    # If first element looks like a ring-of-rings (MultiPolygon mishandle), dive once.
    if ring and isinstance(ring[0], list) and ring[0] and isinstance(ring[0][0], list):
        ring = ring[0]
    cleaned: list[list[float]] = []
    for pt in ring:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        lon, lat = _f(pt[0]), _f(pt[1])
        if lon is None or lat is None:
            continue
        if abs(lat) > 90 or abs(lon) > 180:
            continue
        cleaned.append([lon, lat])
    if len(cleaned) < 3:
        return None
    # Prefer shapely simplify when available for better shape fidelity.
    try:
        from shapely.geometry import Polygon

        poly = Polygon(cleaned)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            return None
        if poly.geom_type == "MultiPolygon" and len(poly.geoms):
            poly = max(poly.geoms, key=lambda g: g.area)
        # Progressive tolerance until under budget.
        tol = 0.0
        for _ in range(8):
            simplified = poly.simplify(tol, preserve_topology=True) if tol > 0 else poly
            coords = list(simplified.exterior.coords)
            if len(coords) <= max_points:
                return [_close_ring([[float(x), float(y)] for x, y in coords])]
            # Grow tolerance in degrees (~111km per deg) — start tiny.
            tol = 0.00002 if tol <= 0 else tol * 2.2
        coords = list(poly.exterior.coords)
        return [_subsample_ring([[float(x), float(y)] for x, y in coords], max_points)]
    except Exception:
        return [_subsample_ring(cleaned, max_points)]


def outline_for_parcel(
    *,
    polygon: Any = None,
    latitude: float | None = None,
    longitude: float | None = None,
    acreage: float | None = None,
) -> list[list[list[float]]] | None:
    """Best available outline: compact real boundary, else acreage square on pin."""
    compact = compact_polygon(polygon)
    if compact:
        return compact
    lat = _f(latitude)
    lon = _f(longitude)
    if lat is None or lon is None:
        return None
    return acreage_square_polygon(lon, lat, acreage)
