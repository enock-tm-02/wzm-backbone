"""Fetches the OpenStreetMap road network around a work zone from an Overpass API.

Responses are cached under $WZM_DATA_DIR/raw/osm so repeat runs on a corridor work offline.
Set WZM_NETWORK_FILE to a saved Overpass JSON to skip the download entirely.
"""
import hashlib
import json
import math
from pathlib import Path

import httpx

from wzm.config import Settings, get_settings
from wzm.scenario.geo import bbox
from wzm.scenario.network import RoadNetwork

ROUTABLE = ("motorway|trunk|primary|secondary|tertiary|unclassified|"
            "motorway_link|trunk_link|primary_link|secondary_link|tertiary_link")


_MEMORY: dict[str, RoadNetwork] = {}   # parsed networks for the life of the API process


class NetworkUnavailable(RuntimeError):
    """The road network could not be fetched (no network access, Overpass down, empty area)."""


def overpass_query(south: float, west: float, north: float, east: float, residential: bool = False) -> str:
    classes = ROUTABLE + ("|residential" if residential else "")
    return (f'[out:json][timeout:90];way["highway"~"^({classes})$"]'
            f"({south:.5f},{west:.5f},{north:.5f},{east:.5f});(._;>;);out body;")


def fetch_network(coords: list[tuple[float, float]], pad_m: float = 6000, residential: bool = False,
                  settings: Settings | None = None) -> RoadNetwork:
    settings = settings or get_settings()
    if settings.wzm_network_file:
        return load_network_file(settings.wzm_network_file)
    s, w, n, e = bbox(coords, pad_m)
    # Round outward to a 0.02 degree grid so nearby requests share one download
    s, w = (math.floor(v / 0.02) * 0.02 for v in (s, w))
    n, e = (math.ceil(v / 0.02) * 0.02 for v in (n, e))
    q = overpass_query(s, w, n, e, residential=residential)
    if q in _MEMORY:
        return _MEMORY[q]
    cache_dir = Path(settings.wzm_data_dir) / "raw" / "osm"
    cache = cache_dir / f"{hashlib.sha1(q.encode()).hexdigest()[:16]}.json"
    if cache.exists():
        data = json.loads(cache.read_text())
    else:
        try:
            r = httpx.post(settings.overpass_url, data={"data": q}, timeout=120,
                           headers={"User-Agent": "wzm-scenario/0.1"})
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NetworkUnavailable(f"Overpass request to {settings.overpass_url} failed: {exc}") from exc
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
    g = RoadNetwork.from_osm(data)
    if not g.out:
        raise NetworkUnavailable("No routable roads found around the work zone")
    if len(_MEMORY) >= 8:
        _MEMORY.pop(next(iter(_MEMORY)))
    _MEMORY[q] = g
    return g


def load_network_file(path: str) -> RoadNetwork:
    key = f"file:{path}"
    if key not in _MEMORY:
        try:
            _MEMORY[key] = RoadNetwork.from_osm(json.loads(Path(path).read_text()))
        except (OSError, ValueError) as exc:
            raise NetworkUnavailable(f"Could not read WZM_NETWORK_FILE {path}: {exc}") from exc
    return _MEMORY[key]
