"""Loop / radar detector volumes, speeds and occupancy."""
from datetime import datetime

from wzm.connectors.base import Connector


class DetectorsConnector(Connector):
    required_env = ("DETECTORS_API_URL", "DETECTORS_API_KEY")

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        # TODO: pull 5-minute detector records from the ATMS or data warehouse.
        raise NotImplementedError("DetectorsConnector.fetch is a placeholder")
