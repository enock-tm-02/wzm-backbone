"""Small geometry helpers on WGS84 [lon, lat] coordinates."""
import math

EARTH_R_M = 6_371_000.0
M_PER_MILE = 1609.344


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R_M * math.asin(math.sqrt(h))


def line_length_m(coords: list[tuple[float, float]]) -> float:
    return sum(haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def bbox(coords: list[tuple[float, float]], pad_m: float = 0) -> tuple[float, float, float, float]:
    """(south, west, north, east) padded by pad_m metres."""
    lons, lats = [c[0] for c in coords], [c[1] for c in coords]
    dlat = pad_m / 111_320
    dlon = pad_m / (111_320 * max(math.cos(math.radians(sum(lats) / len(lats))), 0.1))
    return min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon
