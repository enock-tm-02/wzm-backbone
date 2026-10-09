"""Miami-Dade test case: I-95 northbound between the NW 62nd and NW 79th Street interchanges.

Runs the full map flow (snap the work zone, search detours, analyze) on the hand-built network in
tests/fixtures/miami_dade_i95.json, so it needs no internet. Traffic is an assumed 220,000 AADT
(two-way) for this stretch of I-95; the other inputs use config/scenario_defaults.yaml.
"""
import pytest
from fastapi.testclient import TestClient

from tests.fixtures.miami_dade_i95 import FIXTURE
from wzm.api import scenario as scenario_api
from wzm.api.main import app
from wzm.config import Settings
from wzm.scenario.osm import fetch_network, load_network_file

# Clicks on the northbound carriageway: just past the NW 62nd St on-ramp, just before the NW 79th St off-ramp
START, END = [-80.2063, 25.8340], [-80.2063, 25.8440]
I95 = dict(coordinates=[START, END], facility="freeway", normal_lanes=4, free_flow_speed_mph=55,
           aadt=220_000, heavy_vehicle_pct=6)


@pytest.fixture
def client(monkeypatch):
    net = load_network_file(str(FIXTURE))
    monkeypatch.setattr(scenario_api, "fetch_network", lambda coords, **kw: net)
    return TestClient(app)


def analyze(client, **kw) -> dict:
    r = client.post("/scenario/analyze", json=I95 | kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_network_file_setting_loads_the_fixture():
    g = fetch_network([START, END], settings=Settings(_env_file=None, wzm_network_file=str(FIXTURE)))
    assert len(g.nodes) > 100


def test_segment_snaps_to_i95_northbound(client):
    seg = client.post("/scenario/segment", json={"start": START, "end": END}).json()
    assert seg["road"] == "I 95" and seg["facility"] == "freeway"
    assert seg["lanes"] == 4 and seg["speed_mph"] == 55
    lats = [lat for _, lat in seg["geometry"]["coordinates"]]
    assert lats == sorted(lats)                                   # travels north
    assert all(lon == pytest.approx(-80.2062) for lon, _ in seg["geometry"]["coordinates"])
    assert 0.5 < seg["length_mi"] < 0.8


def test_midday_two_lane_closure_diverts_via_nw_7th_avenue(client):
    out = analyze(client, lanes_closed=2, work_zone_speed_mph=45, start_hour=9, end_hour=15)
    roads = [d["roads"] for d in out["detours"]]
    assert len(roads) == 3
    best = out["detours"][0]
    assert best["roads"][1:4] == ["NW 62nd Street", "NW 7th Avenue", "NW 79th Street"]
    assert ["NW 62nd Street", "NW 2nd Avenue", "NW 79th Street"] in [r[1:4] for r in roads]
    rec, base = out["recommended"], out["without_diversion"]
    assert "NW 7th Avenue" in out["recommendation"] and rec["diversion_share"] > 0
    assert base["operations"]["max_queue_miles"] > 1
    assert rec["operations"]["max_queue_miles"] < base["operations"]["max_queue_miles"]
    assert rec["user_cost"]["total_usd"] < base["user_cost"]["total_usd"]
    assert base["safety"]["crash_risk_ratio"] > 1
    assert 0 < base["safety"]["probability_any_crash"] < 1


def test_night_two_lane_closure_needs_no_detour(client):
    out = analyze(client, lanes_closed=2, work_zone_speed_mph=45, start_hour=22, end_hour=5, days=10)
    assert out["without_diversion"]["operations"]["max_queue_miles"] == 0
    assert out["recommendation"].startswith("Keep traffic")
    assert out["recommended"]["operations"]["total_delay_veh_hours"] > 0   # reduced speed still costs time


def test_night_full_closure_overloads_the_detour(client):
    out = analyze(client, lanes_closed=4, start_hour=23, end_hour=5)
    assert out["recommendation"].startswith("Full closure: route traffic via NW 62nd Street / NW 7th Avenue")
    assert out["recommended"]["diversion_share"] == 1.0
    assert any("above its estimated spare capacity" in w for w in out["warnings"])
    assert out["recommended"]["operations"]["max_detour_queued_vehicles"] > 0  # overflow queues at the ramp


def test_shoulder_closure_is_mild(client):
    out = analyze(client, shoulder_closed=True, work_zone_speed_mph=50, start_hour=9, end_hour=15)
    base = out["without_diversion"]
    assert base["operations"]["max_queue_miles"] == 0
    assert out["capacity"]["work_zone_vph"] < out["capacity"]["normal_vph"]
    assert 1 < base["safety"]["crash_risk_ratio"] < 2
