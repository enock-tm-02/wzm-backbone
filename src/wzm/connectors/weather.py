"""NOAA weather via api.weather.gov (no key; requires a User-Agent with contact)."""
from datetime import datetime

import httpx

from wzm.connectors.base import Connector


class WeatherConnector(Connector):
    required_env = ("NOAA_USER_AGENT",)
    stations: tuple[str, ...] = ()  # TODO: ICAO station ids near your corridors, e.g. ("KBWI",)

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        headers = {"User-Agent": self.settings.noaa_user_agent, "Accept": "application/geo+json"}
        out = []
        for station in self.stations:
            r = httpx.get(f"https://api.weather.gov/stations/{station}/observations/latest",
                          headers=headers, timeout=30)
            r.raise_for_status()
            out.append(self.normalize({"station": station, **r.json().get("properties", {})}))
        return out

    def normalize(self, rec: dict) -> dict:
        return {
            "source": "noaa",
            "station": rec.get("station"),
            "observed_at": rec.get("timestamp"),
            "precip_last_hour_mm": (rec.get("precipitationLastHour") or {}).get("value"),
            "visibility_m": (rec.get("visibility") or {}).get("value"),
            "text": rec.get("textDescription"),
        }
