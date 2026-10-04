"""INRIX real-time segment speeds."""
from datetime import datetime

from wzm.connectors.base import Connector


class INRIXConnector(Connector):
    required_env = ("INRIX_APP_ID", "INRIX_HASH_TOKEN")

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        # TODO: get an auth token from the INRIX UAS endpoint, then request segment speeds for the corridor.
        raise NotImplementedError("INRIXConnector.fetch is a placeholder")
