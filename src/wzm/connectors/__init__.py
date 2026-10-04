"""Connector registry: class name in datastreams.yaml -> class."""
from wzm.connectors.base import Connector, ConnectorNotConfigured
from wzm.connectors.crashes import CrashesConnector
from wzm.connectors.detectors import DetectorsConnector
from wzm.connectors.events import EventsConnector
from wzm.connectors.here import HEREConnector
from wzm.connectors.incidents import IncidentsConnector
from wzm.connectors.inrix import INRIXConnector
from wzm.connectors.npmrds import NPMRDSConnector
from wzm.connectors.permits import PermitsConnector
from wzm.connectors.weather import WeatherConnector
from wzm.connectors.wzdx import WZDxConnector

CONNECTORS: dict[str, type[Connector]] = {c.__name__: c for c in (
    WZDxConnector, PermitsConnector, NPMRDSConnector, INRIXConnector, HEREConnector,
    DetectorsConnector, CrashesConnector, WeatherConnector, EventsConnector, IncidentsConnector,
)}


def get_connector(name: str) -> Connector:
    return CONNECTORS[name]()


__all__ = ["CONNECTORS", "Connector", "ConnectorNotConfigured", "get_connector"]
