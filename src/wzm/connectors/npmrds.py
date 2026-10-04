"""NPMRDS probe speeds via RITIS (historical, by TMC segment)."""
from datetime import datetime

from wzm.connectors.base import Connector


class NPMRDSConnector(Connector):
    required_env = ("NPMRDS_USERNAME", "NPMRDS_PASSWORD")

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        # TODO: download the RITIS massive data export (or read a CSV export) for the study TMCs.
        raise NotImplementedError("NPMRDSConnector.fetch is a placeholder")
