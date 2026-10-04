"""Special events calendar."""
from datetime import datetime

from wzm.connectors.base import Connector


class EventsConnector(Connector):
    required_env = ("EVENTS_API_URL",)

    def fetch(self, since: datetime | None = None) -> list[dict]:
        self.check()
        # TODO: load events with venue location, start and end times, expected attendance.
        raise NotImplementedError("EventsConnector.fetch is a placeholder")
