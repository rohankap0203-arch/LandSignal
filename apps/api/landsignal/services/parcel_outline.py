"""Accurate parcel outlines for View Map — real GIS rings only (never invented).

Nationwide inventory cannot keep every full cadastral ring in RAM (OOM history).
- Inventory/persist: compact rings for memory.
- View Map /geometry: exact GIS exterior (cleaned, not simplified) so the yellow
  outline matches the true land edge, acreage, and dimensions.
"""

from __future__ import annotations

import math
from typing import Any

# Inventory-scale budget (discover / disk snapshot) — not for View Map.
_MAX_INVENTORY_POINTS = 128
# Hard safety cap for a single viewed parcel (pathological rings only).
_MAX_VIEWER_POINTS = 2500


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        n = float(v)
        return n if n == n else None
    except (TypeError, ValueError):
        return None


def is_synthetic_square(polygon: Any) -> bool:
    """True for the old acreage-square / demo placeholder — not a real parcel edge."""
    if not isinstance(polygon, list) or not polygon:
        return False
    ring = polygon[0]
    if not isinstance(ring, list) or len(ring) != 5:
        return False
    try:
        pts = [(float(p[0]), float(p[1])) for p in ring[:4]]
    except (TypeError, ValueError, IndexError):
        return False
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return len(set(round(x, 6) for x in lons)) == 2 and len(set(round(y, 6) for y in lats)) == 2


def _close_ring(ring: list[list[float]]) -> list[list[float]]:
    if len(ring) < 3:
        return ring
    if ring[0][0] != ring[-1][0] or ring[0][1] != ring[-1][1]:
        return [*ring, [ring[0][0], ring[0][1]]]
    return ring


def _subsample_ring(ring: list[list[float]], max_points: int) -> list[list[float]]:
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


def _clean_exterior(polygon: Any) -> list[list[float]] | None:
    if is_synthetic_square(polygon):
        return None
    if not isinstance(polygon, list) or not polygon:
        return None
    ring = polygon[0]
    if not isinstance(ring, list) or not ring:
        return None
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
        if cleaned and cleaned[-1][0] == lon and cleaned[-1][1] == lat:
            continue
        cleaned.append([lon, lat])
    if len(cleaned) < 3:
        return None
    return _close_ring(cleaned)


def ring_area_acres(ring: list[list[float]]) -> float | None:
    """Shoelace area on lon/lat ring → acres (local equirectangular)."""
    if not ring or len(ring) < 4:
        return None
    open_ring = ring[:-1] if ring[0] == ring[-1] else ring
    if len(open_ring) < 3:
        return None
    lat0 = sum(p[1] for p in open_ring) / len(open_ring)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * max(0.2, math.cos(lat0 * math.pi / 180.0))
    area = 0.0
    for i in range(len(open_ring)):
        x1 = open_ring[i][0] * m_per_deg_lon
        y1 = open_ring[i][1] * m_per_deg_lat
        x2 = open_ring[(i + 1) % len(open_ring)][0] * m_per_deg_lon
        y2 = open_ring[(i + 1) % len(open_ring)][1] * m_per_deg_lat
        area += x1 * y2 - x2 * y1
    m2 = abs(area) / 2.0
    return m2 / 4046.8564224


def outline_matches_acreage(
    polygon: list[list[list[float]]] | None,
    acres: float | None,
    *,
    lo: float = 0.45,
    hi: float = 2.25,
) -> bool:
    """Reject a GIS hit that is clearly the wrong neighboring parcel."""
    if not polygon or not polygon[0]:
        return False
    published = _f(acres)
    if published is None or published <= 0:
        return True
    measured = ring_area_acres(polygon[0])
    if measured is None or measured <= 0:
        return True
    ratio = measured / published
    return lo <= ratio <= hi


def exact_polygon(
    polygon: Any,
    *,
    max_points: int = _MAX_VIEWER_POINTS,
) -> list[list[list[float]]] | None:
    """Full GIS exterior for View Map — clean/close only; do not simplify the land edge."""
    cleaned = _clean_exterior(polygon)
    if not cleaned:
        return None
    # Prefer shapely fix for self-intersections without simplifying shape.
    try:
        from shapely.geometry import Polygon

        poly = Polygon(cleaned)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            return None
        if poly.geom_type == "MultiPolygon" and len(poly.geoms):
            poly = max(poly.geoms, key=lambda g: g.area)
        coords = [[float(x), float(y)] for x, y in poly.exterior.coords]
        if len(coords) > max_points:
            # Pathological only — last resort subsample, still high fidelity.
            coords = _subsample_ring(coords, max_points)
        return [_close_ring(coords)]
    except Exception:
        if len(cleaned) > max_points:
            return [_subsample_ring(cleaned, max_points)]
        return [cleaned]


def compact_polygon(
    polygon: Any,
    *,
    max_points: int = _MAX_INVENTORY_POINTS,
) -> list[list[list[float]]] | None:
    """Memory-safe ring for nationwide inventory / disk — still from real GIS only."""
    cleaned = _clean_exterior(polygon)
    if not cleaned:
        return None
    if len(cleaned) <= max_points:
        return [cleaned]
    try:
        from shapely.geometry import Polygon

        poly = Polygon(cleaned)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            return None
        if poly.geom_type == "MultiPolygon" and len(poly.geoms):
            poly = max(poly.geoms, key=lambda g: g.area)
        tol = 0.0
        for _ in range(12):
            simplified = poly.simplify(tol, preserve_topology=True) if tol > 0 else poly
            coords = list(simplified.exterior.coords)
            if len(coords) <= max_points:
                return [_close_ring([[float(x), float(y)] for x, y in coords])]
            tol = 0.000008 if tol <= 0 else tol * 1.9
        coords = list(poly.exterior.coords)
        return [_subsample_ring([[float(x), float(y)] for x, y in coords], max_points)]
    except Exception:
        return [_subsample_ring(cleaned, max_points)]


def outline_for_parcel(
    *,
    polygon: Any = None,
    latitude: float | None = None,  # noqa: ARG001
    longitude: float | None = None,  # noqa: ARG001
    acreage: float | None = None,  # noqa: ARG001
) -> list[list[list[float]]] | None:
    """Real GIS outline only. Never invents acreage squares."""
    return exact_polygon(polygon) or compact_polygon(polygon)
