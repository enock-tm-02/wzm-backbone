from pathlib import Path

from fastapi.testclient import TestClient

from wzm.api.main import app
from wzm.config import Settings
from wzm.connectors import CONNECTORS
from wzm.registry import load_registry, status

STREAMS = Path(__file__).parents[1] / "config" / "datastreams.yaml"


def test_every_stream_has_a_connector_with_matching_env():
    for spec in load_registry(STREAMS)["streams"].values():
        cls = CONNECTORS[spec.connector]
        assert set(cls.required_env) == set(spec.env), spec.name


def test_streams_disabled_until_configured():
    rows = status(Settings(_env_file=None), STREAMS)
    wzdx = next(r for r in rows if r["name"] == "wzdx")
    assert not wzdx["enabled"] and wzdx["missing"] == ["WZDX_FEED_URL"]
    rows = status(Settings(_env_file=None, wzdx_feed_url="https://example.org/wzdx"), STREAMS)
    assert next(r for r in rows if r["name"] == "wzdx")["enabled"]


def test_baseline_endpoint():
    client = TestClient(app)
    r = client.post("/predict/baseline",
                    json={"normal_lanes": 3, "open_lanes": 1, "demand_vph": [3000, 3000, 1500, 1000]})
    assert r.status_code == 200
    body = r.json()
    assert body["max_queue_miles"] > 0
    assert len(body["intervals"]) == 4
