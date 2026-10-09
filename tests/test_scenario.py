"""Scenario analysis on a small synthetic network (no internet needed).

Layout (lon grows east, lat north):

    lat 0.02   secondary "Far Rd"   o----------------------o            (via connectors at 0.03 / 0.07)
    lat 0.01   primary "Main St"  o--------------------------------o
                                   \\ exit ramp            entry ramp /
    lat 0.00   I-1 eastbound  o-----o------[ work zone 0.04-0.06 ]-----o-----o
    lat -0.0005 I-1 westbound (separate carriageway)
"""
import pytest
from fastapi.testclient import TestClient

from wzm.api import scenario as scenario_api
from wzm.api.main import app
from wzm.scenario.analyze import analyze, find_detours
from wzm.scenario.impacts import DetourOption, Scenario, capacities, simulate, summarize
from wzm.scenario.network import RoadNetwork
from wzm.scenario.params import get_params

_ids = iter(range(1, 10_000))


def _line(lat: float, lon0: float, lon1: float, step: float = 0.005) -> list[tuple[int, float, float]]:
    n = round((lon1 - lon0) / step)
    return [(next(_ids), lon0 + i * step, lat) for i in range(n + 1)]


def build_osm() -> dict:
    nodes, ways = [], []

    def way(pts, **tags):
        ways.append({"type": "way", "id": next(_ids), "nodes": [p[0] for p in pts], "tags": tags})

    eb = _line(0.0, 0.0, 0.1)
    wb = list(reversed(_line(-0.0005, 0.0, 0.1)))
    main = _line(0.01, 0.0, 0.1)
    far = _line(0.02, 0.03, 0.07)
    nodes += eb + wb + main + far
    way(eb, highway="motorway", ref="I-1", lanes="3", maxspeed="65 mph")
    way(wb, highway="motorway", ref="I-1", lanes="3", maxspeed="65 mph")
    way(main, highway="primary", name="Main St", lanes="4", maxspeed="40 mph")
    way(far, highway="secondary", name="Far Rd", lanes="2", maxspeed="40 mph")
    by_lon = lambda line, lon: next(p for p in line if abs(p[1] - lon) < 1e-9)
    way([by_lon(eb, 0.02), by_lon(main, 0.025)], highway="motorway_link", oneway="yes")
    way([by_lon(main, 0.075), by_lon(eb, 0.08)], highway="motorway_link", oneway="yes")
    way([by_lon(main, 0.03), by_lon(far, 0.03)], highway="tertiary", name="North Ave")
    way([by_lon(far, 0.07), by_lon(main, 0.07)], highway="tertiary", name="South Ave")
    elements = [{"type": "node", "id": i, "lon": lon, "lat": lat} for i, lon, lat in nodes]
    return {"elements": elements + ways}


@pytest.fixture(scope="module")
def net() -> RoadNetwork:
    return RoadNetwork.from_osm(build_osm())


def scenario(**kw) -> Scenario:
    base = dict(normal_lanes=3, lanes_closed=1, length_mi=1.4, aadt=100_000, start_hour=9, end_hour=15,
                params=get_params())
    return Scenario(**(base | kw))


def test_segment_follows_clicked_direction(net):
    zone = net.route_between((0.04, 0.0001), (0.06, 0.0001))
    assert zone and all(e.highway == "motorway" for e in zone.edges)
    assert zone.coords[0][0] < zone.coords[-1][0]          # eastbound carriageway
    assert 2000 < zone.length_m < 2400


def test_detours_leave_the_freeway_and_rejoin(net):
    zone = net.route_between((0.04, 0.0), (0.06, 0.0))
    detours = find_detours(net, zone, get_params())
    assert detours
    best = detours[0]
    assert "Main St" in best["roads"]
    assert best["option"].extra_time_min > 0
    coords = best["geometry"]["coordinates"]
    assert any(lat > 0.005 for _, lat in coords)            # actually leaves I-1


def test_capacity_order_shoulder_lane_full():
    open_ = capacities(scenario(lanes_closed=0), night=False)["work_zone_vph"]
    shoulder = capacities(scenario(lanes_closed=0, shoulder_closed=True), night=False)["work_zone_vph"]
    one = capacities(scenario(lanes_closed=1), night=False)["work_zone_vph"]
    two = capacities(scenario(lanes_closed=2), night=False)["work_zone_vph"]
    assert open_ > shoulder > one > two > 0


def test_lower_work_zone_speed_adds_delay_and_closures_add_crashes():
    light = dict(aadt=30_000)
    fast = summarize(s := scenario(work_zone_speed_mph=60, **light), simulate(s))
    slow = summarize(s := scenario(work_zone_speed_mph=40, **light), simulate(s))
    assert slow["operations"]["delay_breakdown_veh_hours"]["reduced_speed"] > \
        fast["operations"]["delay_breakdown_veh_hours"]["reduced_speed"]
    one = summarize(s := scenario(lanes_closed=1, **light), simulate(s))["safety"]
    two = summarize(s := scenario(lanes_closed=2, **light), simulate(s))["safety"]
    assert two["expected_crashes"] > one["expected_crashes"] > one["expected_crashes_without_work_zone"]
    assert 0 < one["probability_any_crash"] < 1


def test_diversion_recommended_only_when_queue_is_costly():
    detour = DetourOption(extra_time_min=5, extra_miles=1.5, spare_capacity_vph=900, length_mi=4)
    heavy = analyze(scenario(lanes_closed=2), manual_detours=[detour])
    assert heavy["recommended"]["diversion_share"] > 0
    assert "divert" in heavy["recommendation"]
    assert heavy["recommended"]["operations"]["max_queue_miles"] < heavy["without_diversion"]["operations"]["max_queue_miles"]
    night = analyze(scenario(lanes_closed=1, start_hour=22, end_hour=5), manual_detours=[detour])
    assert night["without_diversion"]["operations"]["max_queue_miles"] == 0
    assert "Keep traffic" in night["recommendation"]


def test_full_closure_sends_all_traffic_to_the_detour():
    detour = DetourOption(extra_time_min=4, extra_miles=1, spare_capacity_vph=5000, length_mi=3)
    r = analyze(scenario(lanes_closed=3, aadt=40_000, start_hour=0, end_hour=4), manual_detours=[detour])
    assert r["recommended"]["diversion_share"] == 1.0
    assert r["recommended"]["operations"]["max_queue_miles"] == 0
    assert r["recommendation"].startswith("Full closure")


def test_analyze_endpoint_with_network(monkeypatch, net):
    monkeypatch.setattr(scenario_api, "fetch_network", lambda coords, **kw: net)
    client = TestClient(app)
    body = {"coordinates": [[0.04, 0.0], [0.05, 0.0], [0.06, 0.0]], "normal_lanes": 3, "lanes_closed": 2,
            "aadt": 110000, "start_hour": 7, "end_hour": 12, "days": 5}
    r = client.post("/scenario/analyze", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["detours"] and out["detours"][0]["rank"] == 1
    assert out["detours"][0]["geometry"]["type"] == "LineString"
    assert out["work_zone"]["length_mi"] == pytest.approx(1.38, abs=0.1)
    assert out["recommended"]["user_cost"]["total_usd"] > 0

    seg = client.post("/scenario/segment", json={"start": [0.04, 0.0], "end": [0.06, 0.0]})
    assert seg.status_code == 200 and seg.json()["lanes"] == 3 and seg.json()["facility"] == "freeway"


def test_analyze_without_network_and_map_served(monkeypatch):
    def offline(coords, **kw):
        raise scenario_api.NetworkUnavailable("offline")
    monkeypatch.setattr(scenario_api, "fetch_network", offline)
    client = TestClient(app)
    r = client.post("/scenario/analyze", json={"coordinates": [[0.04, 0.0], [0.06, 0.0]], "normal_lanes": 2,
                                               "shoulder_closed": True, "aadt": 50000})
    assert r.status_code == 200
    assert r.json()["detours"] == [] and r.json()["warnings"]
    assert client.post("/scenario/analyze", json={"normal_lanes": 2, "lanes_closed": 3, "aadt": 1,
                                                  "length_mi": 1}).status_code == 422
    page = client.get("/map/")
    assert page.status_code == 200 and "leaflet" in page.text.lower()
