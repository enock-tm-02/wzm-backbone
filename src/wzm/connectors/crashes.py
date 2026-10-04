"""State crash records."""
from datetime import datetime

from wzm.connectors.base import Connector


class CrashesConnector(Connector):
    required_env = ("CRASHES_DB_URL",)

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        # TODO: query the crash database (or load an export) for the study corridors.
        raise NotImplementedError("CrashesConnector.fetch is a placeholder")
