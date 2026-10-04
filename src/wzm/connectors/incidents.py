"""TMC incident log / 511 incidents."""
from datetime import datetime

from wzm.connectors.base import Connector


class IncidentsConnector(Connector):
    required_env = ("INCIDENTS_API_URL", "INCIDENTS_API_KEY")

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        # TODO: pull incidents with location, type, lanes blocked, start and clear times.
        raise NotImplementedError("IncidentsConnector.fetch is a placeholder")
