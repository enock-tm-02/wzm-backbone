"""Builds a hand-drawn Miami-Dade test network around I-95 between NW 54th and NW 95th Street.

Writes miami_dade_i95.json next to this file in Overpass (`out body`) shape, so it loads through
the same RoadNetwork.from_osm path as live OpenStreetMap data. Run it to regenerate:

    python tests/fixtures/miami_dade_i95.py

Geometry is approximate (traced from the street grid, not surveyed) and tags are typical values:
I-95 with 4 lanes each way at 55 mph, NW 7th Avenue (US 441) and NW 2nd Avenue as the parallel
arterials, and the NW 54th / 62nd / 79th / 95th Street interchanges. Good enough to exercise
snapping, detour search and the scenario math on a realistic layout; not for real decisions.
"""
import json
from pathlib import Path

LAT = {"south": 25.8150, "NW 54th Street": 25.8235, "NW 62nd Street": 25.8305,
       "NW 79th Street": 25.8475, "NW 95th Street": 25.8625, "north": 25.8700}
LON = {"NW 7th Avenue": -80.2100, "sb_ramps": -80.2080, "I-95 SB": -80.2070, "I-95 NB": -80.2062,
       "nb_ramps": -80.2052, "NW 2nd Avenue": -80.1990}
INTERCHANGES = ["NW 54th Street", "NW 62nd Street", "NW 79th Street", "NW 95th Street"]
RAMP_OFFSET = 0.0035          # ramps leave / join the freeway this far (deg lat) from the cross street
STEP = 0.002                  # node spacing along long roads


class Builder:
    def __init__(self) -> None:
        self.ids: dict[tuple[float, float], int] = {}
        self.ways: list[dict] = []

    def node(self, lon: float, lat: float) -> int:
        key = (round(lon, 6), round(lat, 6))
        return self.ids.setdefault(key, 100_000 + len(self.ids))

    def way(self, pts: list[tuple[float, float]], **tags) -> None:
        self.ways.append({"type": "way", "id": 900_000 + len(self.ways),
                          "nodes": [self.node(*p) for p in pts], "tags": tags})

    def osm(self) -> dict:
        nodes = [{"type": "node", "id": i, "lon": lon, "lat": lat} for (lon, lat), i in self.ids.items()]
        return {"version": 0.6, "generator": "wzm test fixture", "elements": nodes + self.ways}


def _densify(fixed: list[float], lo: float, hi: float) -> list[float]:
    pts = set(round(v, 6) for v in fixed if lo <= v <= hi)
    v = lo
    while v < hi:
        pts.add(round(v, 6))
        v += STEP
    pts.add(round(hi, 6))
    return sorted(pts)


def build() -> dict:
    b = Builder()
    lo, hi = LAT["south"], LAT["north"]
    street_lats = [LAT[s] for s in INTERCHANGES]
    nb_ramp_lats = [l + d for l in street_lats for d in (-RAMP_OFFSET, RAMP_OFFSET)]

    i95 = dict(highway="motorway", ref="I 95", name="Interstate 95", lanes="4", maxspeed="55 mph", oneway="yes")
    nb = [(LON["I-95 NB"], lat) for lat in _densify(nb_ramp_lats, lo, hi)]
    sb = [(LON["I-95 SB"], lat) for lat in reversed(_densify(nb_ramp_lats, lo, hi))]
    b.way(nb, **i95)
    b.way(sb, **i95)

    for name, tags in [("NW 7th Avenue", dict(highway="primary", ref="US 441", lanes="6", maxspeed="40 mph")),
                       ("NW 2nd Avenue", dict(highway="secondary", lanes="4", maxspeed="35 mph"))]:
        b.way([(LON[name], lat) for lat in _densify(street_lats, lo, hi)], name=name, **tags)

    street_tags = {"NW 54th Street": ("primary", "4"), "NW 62nd Street": ("primary", "4"),
                   "NW 79th Street": ("primary", "6"), "NW 95th Street": ("secondary", "4")}
    for street in INTERCHANGES:
        lat = LAT[street]
        hw, lanes = street_tags[street]
        # West half and east half meet only at the ramp terminals: the street bridges over I-95
        b.way([(LON["NW 7th Avenue"], lat), (LON["sb_ramps"], lat), (LON["nb_ramps"], lat), (LON["NW 2nd Avenue"], lat)],
              highway=hw, name=street, lanes=lanes, maxspeed="35 mph")
        ramp = dict(highway="motorway_link", oneway="yes", lanes="1", maxspeed="35 mph")
        # Northbound: off-ramp before the street, on-ramp after it (east side)
        b.way([(LON["I-95 NB"], lat - RAMP_OFFSET), (LON["nb_ramps"], lat)], **ramp)
        b.way([(LON["nb_ramps"], lat), (LON["I-95 NB"], lat + RAMP_OFFSET)], **ramp)
        # Southbound: off-ramp north of the street, on-ramp south of it (west side)
        b.way([(LON["I-95 SB"], lat + RAMP_OFFSET), (LON["sb_ramps"], lat)], **ramp)
        b.way([(LON["sb_ramps"], lat), (LON["I-95 SB"], lat - RAMP_OFFSET)], **ramp)
    return b.osm()


FIXTURE = Path(__file__).with_suffix(".json")

if __name__ == "__main__":
    FIXTURE.write_text(json.dumps(build(), indent=0))
    print(f"wrote {FIXTURE}")
