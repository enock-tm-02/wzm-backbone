"""Base class every data stream connector implements."""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from wzm.config import Settings, get_settings


class ConnectorNotConfigured(RuntimeError):
    """Raised when a connector's credentials or endpoint are not set in .env."""


class Connector(ABC):
    #: settings this connector needs; must match the stream's `env` in datastreams.yaml
    required_env: tuple[str, ...] = ()

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def check(self) -> None:
        missing = [e for e in self.required_env if not self.settings.get(e)]
        if missing:
            raise ConnectorNotConfigured(f"{type(self).__name__} needs {', '.join(missing)} in .env")

    @abstractmethod
    def fetch(self, since: datetime | None = None) -> list[dict[str, Any]]:
        """Pull records from the source and return them in the source's own shape."""

    def normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        """Map one source record to the canonical schema (db/schema.sql). Override per source."""
        return record
