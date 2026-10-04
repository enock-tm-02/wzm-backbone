"""WZDx work zone feed (GeoJSON FeatureCollection, spec v4.x)."""
from datetime import datetime

import httpx

from wzm.connectors.base import Connector


class WZDxConnector(Connector):
    required_env = ("WZDX_FEED_URL",)

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        headers = {}
        if self.settings.wzdx_api_key:
            headers["Authorization"] = f"Bearer {self.settings.wzdx_api_key}"  # TODO: confirm your feed's auth scheme
        resp = httpx.get(self.settings.wzdx_feed_url, headers=headers, timeout=30)
        resp.raise_for_status()
        return [self.normalize(f) for f in resp.json().get("features", [])]

    def normalize(self, feature: dict) -> dict:
        core = feature.get("properties", {}).get("core_details", {})
        props = feature.get("properties", {})
        return {
            "source": "wzdx",
            "source_id": feature.get("id"),
            "road_name": (core.get("road_names") or [None])[0],
            "direction": core.get("direction"),
            "start_time": props.get("start_date"),
            "end_time": props.get("end_date"),
            "vehicle_impact": props.get("vehicle_impact"),
            "lanes": props.get("lanes", []),
            "reduced_speed_limit_kph": props.get("reduced_speed_limit_kph"),
            "geometry": feature.get("geometry"),
        }
