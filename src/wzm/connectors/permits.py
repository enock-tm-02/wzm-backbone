"""Lane closure permit system (planned closures)."""
from datetime import datetime

from wzm.connectors.base import Connector


class PermitsConnector(Connector):
    required_env = ("PERMITS_API_URL", "PERMITS_API_KEY")

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        # TODO: call the permit system API and return planned closures with lanes, start and end times.
        raise NotImplementedError("PermitsConnector.fetch is a placeholder")
