"""Directed road network built from OpenStreetMap data, with shortest paths and detour search.

The graph is plain Python (dicts + heapq) so it runs with no extra dependencies. Load it from
an Overpass JSON response (see osm.py) or from any dict in the same shape.
"""
import heapq
import math
import re
from dataclasses import dataclass, field
from typing import Iterable

from wzm.scenario.geo import M_PER_MILE, haversine_m

# Defaults when OSM tags are missing. Speeds in mph, capacities in veh/h/lane.
DEFAULT_SPEED_MPH = {
    "motorway": 65, "trunk": 55, "primary": 45, "secondary": 40, "tertiary": 35,
    "motorway_link": 40, "trunk_link": 35, "primary_link": 30, "secondary_link": 30,
    "tertiary_link": 25, "unclassified": 30, "residential": 25,
}
DEFAULT_LANES = {"motorway": 2, "trunk": 2, "primary": 2}
LANE_CAPACITY_VPH = {
    "motorway": 2000, "trunk": 1800, "primary": 900, "secondary": 800, "tertiary": 700,
    "motorway_link": 1200, "trunk_link": 1100, "primary_link": 800, "secondary_link": 700,
    "tertiary_link": 600, "unclassified": 600, "residential": 500,
}
FREEWAY_CLASSES = {"motorway", "trunk"}


@dataclass(frozen=True)
class Edge:
    u: int
    v: int
    length_m: float
    speed_mph: float
    lanes: int
    highway: str
    name: str = ""

    @property
    def time_s(self) -> float:
        return self.length_m / (self.speed_mph * M_PER_MILE / 3600)

    @property
    def capacity_vph(self) -> float:
        return self.lanes * LANE_CAPACITY_VPH.get(self.highway, 600)


@dataclass
class Path:
    edges: list[Edge]
    coords: list[tuple[float, float]] = field(default_factory=list)

    @property
    def length_m(self) -> float:
        return sum(e.length_m for e in self.edges)

    @property
    def time_s(self) -> float:
        return sum(e.time_s for e in self.edges)

    @property
    def keys(self) -> set[tuple[int, int]]:
        return {(e.u, e.v) for e in self.edges}

    def road_names(self) -> list[str]:
        """Distinct consecutive road names along the path, e.g. for detour signing."""
        out: list[str] = []
        for e in self.edges:
            label = e.name or ("ramp" if e.highway.endswith("_link") else e.highway)
            if not out or out[-1] != label:
                out.append(label)
        return out


def _parse_speed(tag: str | None) -> float | None:
    if not tag:
        return None
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(mph)?", tag)
    if not m:
        return None
    v = float(m.group(1))
    return v if m.group(2) else v / 1.609344  # OSM default unit is km/h


def _parse_int(tag: str | None) -> int | None:
    try:
        return int(str(tag).split(";")[0])
    except (TypeError, ValueError):
        return None


class RoadNetwork:
    def __init__(self) -> None:
        self.nodes: dict[int, tuple[float, float]] = {}
        self.out: dict[int, list[Edge]] = {}
        self.inc: dict[int, list[Edge]] = {}

    # ---- building -------------------------------------------------------------------
    def add_node(self, nid: int, lon: float, lat: float) -> None:
        self.nodes[nid] = (lon, lat)

    def add_edge(self, e: Edge) -> None:
        self.out.setdefault(e.u, []).append(e)
        self.inc.setdefault(e.v, []).append(e)

    @classmethod
    def from_osm(cls, data: dict) -> "RoadNetwork":
        """Build from an Overpass `out body` JSON response (nodes + ways)."""
        g = cls()
        for el in data.get("elements", []):
            if el.get("type") == "node":
                g.add_node(el["id"], el["lon"], el["lat"])
        for el in data.get("elements", []):
            if el.get("type") != "way":
                continue
            tags = el.get("tags", {})
            hw = tags.get("highway")
            if hw not in DEFAULT_SPEED_MPH:
                continue
            nds = [n for n in el.get("nodes", []) if n in g.nodes]
            oneway = tags.get("oneway", "")
            forward = True
            backward = not (oneway in ("yes", "1", "true", "-1") or tags.get("junction") == "roundabout"
                            or (hw in ("motorway", "motorway_link") and oneway != "no"))
            if oneway == "-1":
                forward, backward = False, True
            speed = _parse_speed(tags.get("maxspeed")) or DEFAULT_SPEED_MPH[hw]
            total_lanes = _parse_int(tags.get("lanes"))
            if total_lanes:
                lanes = total_lanes if not backward else max(1, total_lanes // 2)
            else:
                lanes = DEFAULT_LANES.get(hw, 1)
            name = tags.get("ref") if hw in FREEWAY_CLASSES and tags.get("ref") else tags.get("name", tags.get("ref", ""))
            for a, b in zip(nds, nds[1:]):
                d = haversine_m(g.nodes[a], g.nodes[b])
                if forward:
                    g.add_edge(Edge(a, b, d, speed, lanes, hw, name))
                if backward:
                    g.add_edge(Edge(b, a, d, speed, lanes, hw, name))
        return g

    # ---- queries --------------------------------------------------------------------
    def nearest_nodes(self, pt: tuple[float, float], k: int = 4, max_m: float = 300) -> list[int]:
        routable = (n for n in self.nodes if n in self.out or n in self.inc)
        ranked = sorted(((haversine_m(pt, self.nodes[n]), n) for n in routable))[:k]
        near = [n for d, n in ranked if d <= max_m]
        return near or [n for _, n in ranked[:1]]

    def shortest_path(self, src: int, dst: int, banned: set[tuple[int, int]] | None = None,
                      penalty: dict[tuple[int, int], float] | None = None) -> Path | None:
        """Dijkstra on free-flow travel time. `banned` edges are skipped, `penalty` scales weights."""
        banned, penalty = banned or set(), penalty or {}
        dist: dict[int, float] = {src: 0.0}
        prev: dict[int, Edge] = {}
        heap = [(0.0, src)]
        while heap:
            d, n = heapq.heappop(heap)
            if n == dst:
                break
            if d > dist.get(n, math.inf):
                continue
            for e in self.out.get(n, []):
                if (e.u, e.v) in banned:
                    continue
                nd = d + e.time_s * penalty.get((e.u, e.v), 1.0)
                if nd < dist.get(e.v, math.inf):
                    dist[e.v], prev[e.v] = nd, e
                    heapq.heappush(heap, (nd, e.v))
        if dst not in prev and src != dst:
            return None
        edges: list[Edge] = []
        n = dst
        while n != src:
            e = prev[n]
            edges.append(e)
            n = e.u
        edges.reverse()
        return self._with_coords(edges)

    def _with_coords(self, edges: list[Edge]) -> Path:
        coords = [self.nodes[edges[0].u]] + [self.nodes[e.v] for e in edges] if edges else []
        return Path(edges, coords)

    def route_between(self, start: tuple[float, float], end: tuple[float, float]) -> Path | None:
        """Path along the network between two clicked points. Tries a few snap candidates at each
        end so a click near a divided highway picks the carriageway that runs start -> end."""
        best: Path | None = None
        for s in self.nearest_nodes(start):
            for t in self.nearest_nodes(end):
                if s == t:
                    continue
                p = self.shortest_path(s, t)
                if p and (best is None or p.length_m < best.length_m):
                    best = p
        return best

    def extend(self, node: int, along: Edge, distance_m: float, upstream: bool,
               avoid: set[int] | None = None) -> list[Edge]:
        """Walk the same road up- or downstream from `node` for about `distance_m`, never
        entering `avoid` (the work zone's own nodes). Returns the walked edges in travel order."""
        walked: list[Edge] = []
        seen = {node} | (avoid or set())
        ref, total = along, 0.0
        while total < distance_m:
            options = self.inc.get(node, []) if upstream else self.out.get(node, [])
            options = [e for e in options if (e.u if upstream else e.v) not in seen]
            if not options:
                break
            # Prefer the same road (name, then class)
            e = max(options, key=lambda o: (o.name == ref.name, o.highway == ref.highway, o.lanes))
            walked.append(e)
            total += e.length_m
            node = e.u if upstream else e.v
            seen.add(node)
            ref = e
        return list(reversed(walked)) if upstream else walked

    def alternatives(self, src: int, dst: int, banned: set[tuple[int, int]], k: int = 3,
                     penalty_factor: float = 1.6, max_overlap: float = 0.8,
                     common: set[tuple[int, int]] | None = None) -> list[Path]:
        """Up to k distinct paths avoiding `banned`, using the iterative penalty method.
        `common` links (the mainline up- and downstream of the zone) are shared by every detour, so
        they are neither penalised nor counted when comparing two detours."""
        common = common or set()
        penalty: dict[tuple[int, int], float] = {}
        found: list[Path] = []
        for _ in range(k * 3):
            p = self.shortest_path(src, dst, banned, penalty)
            if p is None:
                break
            if all(_overlap(p, q, common) < max_overlap for q in found):
                found.append(p)
                if len(found) == k:
                    break
            for key in p.keys - common:
                penalty[key] = penalty.get(key, 1.0) * penalty_factor
        return sorted(found, key=lambda q: q.time_s)


def _overlap(a: Path, b: Path, common: set[tuple[int, int]] = frozenset()) -> float:
    """Share of a's length off the `common` links that is also on b."""
    shared = b.keys
    own = [e for e in a.edges if (e.u, e.v) not in common]
    total = sum(e.length_m for e in own) or 1.0
    return sum(e.length_m for e in own if (e.u, e.v) in shared) / total


def edges_not_in(path: Path, others: Iterable[tuple[int, int]]) -> list[Edge]:
    others = set(others)
    return [e for e in path.edges if (e.u, e.v) not in others]
