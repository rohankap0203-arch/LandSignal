from __future__ import annotations

import math

EARTH_RADIUS_M = 6371008.8


def to_radians(deg: float) -> float:
    return deg * math.pi / 180.0


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    φ1, φ2 = to_radians(lat1), to_radians(lat2)
    Δφ = to_radians(lat2 - lat1)
    Δλ = to_radians(lon2 - lon1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def ring_area_square_meters(ring: list[list[float]]) -> float:
    if len(ring) < 4:
        return 0.0
    lat0 = sum(p[1] for p in ring) / len(ring)
    cos_lat = math.cos(to_radians(lat0))
    m_per_deg_lat = (math.pi / 180.0) * EARTH_RADIUS_M
    m_per_deg_lon = m_per_deg_lat * cos_lat
    total = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0] * m_per_deg_lon, ring[i][1] * m_per_deg_lat
        x2, y2 = ring[i + 1][0] * m_per_deg_lon, ring[i + 1][1] * m_per_deg_lat
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def acres_from_square_meters(m2: float) -> float:
    return m2 / 4046.8564224


def interior_pin_lat_lon(geom) -> tuple[float, float]:
    """Lat/lon guaranteed on the land — never a lake-hole geometric centroid.

    Prefer centroid when it lies inside the polygon; otherwise use Shapely's
    representative_point (always interior). For MultiPolygon, pin the largest part.
    """
    from shapely.ops import unary_union

    g = unary_union(geom)
    if g.is_empty:
        raise ValueError("empty geometry")
    if g.geom_type == "MultiPolygon" and len(g.geoms):
        g = max(g.geoms, key=lambda p: p.area)
    elif g.geom_type == "GeometryCollection":
        polys = [p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon") and not p.is_empty]
        if not polys:
            c = g.centroid
            return float(c.y), float(c.x)
        g = unary_union(polys)
        if g.geom_type == "MultiPolygon" and len(g.geoms):
            g = max(g.geoms, key=lambda p: p.area)
    c = g.centroid
    try:
        if g.contains(c) or g.covers(c):
            return float(c.y), float(c.x)
    except Exception:
        pass
    rp = g.representative_point()
    return float(rp.y), float(rp.x)


def buildable_acreage_estimate(
    acreage: float,
    wetland_pct: float | None,
    flood_pct: float | None,
    extreme_slope_pct: float | None,
) -> float | None:
    if acreage <= 0:
        return None
    if wetland_pct is None or flood_pct is None:
        return None
    constrained = min(100.0, wetland_pct + flood_pct * 0.5 + (extreme_slope_pct or 0.0))
    return acreage * (1 - constrained / 100.0)


def usable_ag_acreage_estimate(
    acreage: float,
    wetland_pct: float | None,
    prime_farmland_pct: float | None,
    max_slope_pct: float | None,
) -> float | None:
    if acreage <= 0 or wetland_pct is None:
        return None
    usable = 1 - wetland_pct / 100.0
    if max_slope_pct is not None and max_slope_pct > 15:
        usable *= 0.7
    if prime_farmland_pct is not None:
        usable = min(usable, 0.2 + (prime_farmland_pct / 100.0) * 0.8)
    return max(0.0, acreage * usable)
