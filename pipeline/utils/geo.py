"""Geographic coordinate utilities for FlightPrint."""

import math
import numpy as np

try:
    import pyproj
    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False

try:
    import utm as utm_lib
    HAS_UTM = True
except ImportError:
    HAS_UTM = False


def gps_to_local_enu(gps_points: list[dict], origin: dict | None = None) -> tuple[np.ndarray, dict]:
    """Convert GPS (lat, lon, alt) to local East-North-Up (ENU) coordinates.
    
    Args:
        gps_points: List of dicts with 'lat', 'lon', 'alt' keys.
        origin: Optional origin point. If None, uses first point.
    
    Returns:
        (positions_enu, origin_info) where positions_enu is Nx3 array in meters
        and origin_info contains the reference lat/lon/alt.
    """
    if not gps_points:
        return np.empty((0, 3)), {}

    if origin is None:
        origin = gps_points[0]

    lat0 = math.radians(origin["lat"])
    lon0 = math.radians(origin["lon"])
    alt0 = origin.get("alt", 0.0)

    # WGS84 ellipsoid
    a = 6378137.0  # semi-major axis
    e2 = 0.00669437999014  # eccentricity squared

    sin_lat0 = math.sin(lat0)
    cos_lat0 = math.cos(lat0)
    N0 = a / math.sqrt(1 - e2 * sin_lat0 ** 2)

    positions = np.zeros((len(gps_points), 3))

    for i, pt in enumerate(gps_points):
        lat = math.radians(pt["lat"])
        lon = math.radians(pt["lon"])
        alt = pt.get("alt", 0.0)

        sin_lat = math.sin(lat)
        cos_lat = math.cos(lat)
        sin_lon = math.sin(lon)
        cos_lon = math.cos(lon)

        N = a / math.sqrt(1 - e2 * sin_lat ** 2)

        # ECEF
        x = (N + alt) * cos_lat * cos_lon
        y = (N + alt) * cos_lat * sin_lon
        z = (N * (1 - e2) + alt) * sin_lat

        # Origin ECEF
        x0 = (N0 + alt0) * cos_lat0 * math.cos(lon0)
        y0 = (N0 + alt0) * cos_lat0 * math.sin(lon0)
        z0 = (N0 * (1 - e2) + alt0) * sin_lat0

        # Difference in ECEF
        dx = x - x0
        dy = y - y0
        dz = z - z0

        # Rotation to ENU
        sin_lon0 = math.sin(lon0)
        cos_lon0 = math.cos(lon0)

        e = -sin_lon0 * dx + cos_lon0 * dy
        n = -sin_lat0 * cos_lon0 * dx - sin_lat0 * sin_lon0 * dy + cos_lat0 * dz
        u = cos_lat0 * cos_lon0 * dx + cos_lat0 * sin_lon0 * dy + sin_lat0 * dz

        positions[i] = [e, n, u]

    origin_info = {
        "lat": origin["lat"],
        "lon": origin["lon"],
        "alt": origin.get("alt", 0.0),
    }

    return positions, origin_info


def local_enu_to_gps(positions_enu: np.ndarray, origin: dict) -> list[dict]:
    """Convert local ENU coordinates back to GPS (lat, lon, alt).
    
    Args:
        positions_enu: Nx3 array in meters (East, North, Up).
        origin: Origin dict with 'lat', 'lon', 'alt' keys.
    
    Returns:
        List of dicts with 'lat', 'lon', 'alt' keys.
    """
    lat0 = math.radians(origin["lat"])
    lon0 = math.radians(origin["lon"])
    alt0 = origin.get("alt", 0.0)

    a = 6378137.0
    e2 = 0.00669437999014

    sin_lat0 = math.sin(lat0)
    cos_lat0 = math.cos(lat0)
    sin_lon0 = math.sin(lon0)
    cos_lon0 = math.cos(lon0)

    N0 = a / math.sqrt(1 - e2 * sin_lat0 ** 2)

    # Origin ECEF
    x0 = (N0 + alt0) * cos_lat0 * cos_lon0
    y0 = (N0 + alt0) * cos_lat0 * sin_lon0
    z0 = (N0 * (1 - e2) + alt0) * sin_lat0

    gps_points = []
    for enu in positions_enu:
        e, n, u = enu

        # ENU to ECEF delta (inverse rotation)
        dx = -sin_lon0 * e - sin_lat0 * cos_lon0 * n + cos_lat0 * cos_lon0 * u
        dy = cos_lon0 * e - sin_lat0 * sin_lon0 * n + cos_lat0 * sin_lon0 * u
        dz = cos_lat0 * n + sin_lat0 * u

        x = x0 + dx
        y = y0 + dy
        z = z0 + dz

        # ECEF to geodetic (iterative)
        lon = math.atan2(y, x)
        p = math.sqrt(x ** 2 + y ** 2)
        lat = math.atan2(z, p * (1 - e2))

        for _ in range(5):
            N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
            lat = math.atan2(z + e2 * N * math.sin(lat), p)

        alt = p / math.cos(lat) - N

        gps_points.append({
            "lat": math.degrees(lat),
            "lon": math.degrees(lon),
            "alt": alt,
        })

    return gps_points


def gps_distance(pt1: dict, pt2: dict) -> float:
    """Haversine distance between two GPS points in meters."""
    R = 6371000.0
    lat1, lon1 = math.radians(pt1["lat"]), math.radians(pt1["lon"])
    lat2, lon2 = math.radians(pt2["lat"]), math.radians(pt2["lon"])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    horiz = R * c
    dalt = pt2.get("alt", 0) - pt1.get("alt", 0)

    return math.sqrt(horiz ** 2 + dalt ** 2)


def interpolate_gps(gps_track: list[dict], target_timestamp: float) -> dict:
    """Linearly interpolate GPS position at a given timestamp.
    
    Args:
        gps_track: Sorted list of GPS points with 'timestamp' field.
        target_timestamp: Timestamp to interpolate at.
    
    Returns:
        Interpolated GPS point dict.
    """
    if not gps_track:
        raise ValueError("Empty GPS track")

    # Clamp to bounds
    if target_timestamp <= gps_track[0]["timestamp"]:
        return {k: v for k, v in gps_track[0].items()}
    if target_timestamp >= gps_track[-1]["timestamp"]:
        return {k: v for k, v in gps_track[-1].items()}

    # Binary search for bracket
    lo, hi = 0, len(gps_track) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if gps_track[mid]["timestamp"] <= target_timestamp:
            lo = mid
        else:
            hi = mid

    t0 = gps_track[lo]["timestamp"]
    t1 = gps_track[hi]["timestamp"]
    alpha = (target_timestamp - t0) / (t1 - t0) if t1 != t0 else 0.0

    result = {"timestamp": target_timestamp}
    for key in ("lat", "lon", "alt"):
        if key in gps_track[lo] and key in gps_track[hi]:
            result[key] = gps_track[lo][key] * (1 - alpha) + gps_track[hi][key] * alpha

    return result
