"""Accurate parcel outlines for View Map — real GIS rings only (never invented).

Full cadastral rings can be thousands of vertices and previously OOM'd nationwide
inventory. We keep a compact exterior (≤64 verts) that still follows the true
boundary. If GIS never gave a ring (point-only layers), polygon stays None —
View Map shows the pin, not a fake lot square.
"""

from __future__ import annotations

from typing import Any

_MAX_OUTLINE_POINTS = 64


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
    """Return a memory-safe exterior ring that still follows the real GIS boundary."""
    if is_synthetic_square(polygon):
        return None
    if not isinstance(polygon, list) or not polygon:
        return None
    ring = polygon[0]
    if not isinstance(ring, list) or not ring:
        return None
    # MultiPolygon mishandle: dive once.
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
        for _ in range(10):
            simplified = poly.simplify(tol, preserve_topology=True) if tol > 0 else poly
            coords = list(simplified.exterior.coords)
            if len(coords) <= max_points:
                return [_close_ring([[float(x), float(y)] for x, y in coords])]
            tol = 0.00001 if tol <= 0 else tol * 2.0
        coords = list(poly.exterior.coords)
        return [_subsample_ring([[float(x), float(y)] for x, y in coords], max_points)]
    except Exception:
        return [_subsample_ring(cleaned, max_points)]


def outline_for_parcel(
    *,
    polygon: Any = None,
    latitude: float | None = None,  # noqa: ARG001 — kept for call-site compat
    longitude: float | None = None,  # noqa: ARG001
    acreage: float | None = None,  # noqa: ARG001
) -> list[list[list[float]]] | None:
    """Real compact GIS outline only. Never invents acreage squares."""
    return compact_polygon(polygon)
