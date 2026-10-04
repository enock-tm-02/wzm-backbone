"""HERE Traffic flow API (alternative live speed source)."""
from datetime import datetime

from wzm.connectors.base import Connector


class HEREConnector(Connector):
    required_env = ("HERE_API_KEY",)

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        # TODO: call HERE Traffic API v7 /flow with a corridor bounding box.
        raise NotImplementedError("HEREConnector.fetch is a placeholder")
