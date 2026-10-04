"""Reads config/datastreams.yaml and reports which streams are configured."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from wzm.config import Settings, get_settings


@dataclass
class StreamSpec:
    name: str
    description: str
    connector: str | None
    priority: str = "optional"
    mode: str = "poll"
    interval_minutes: int | None = None
    env: list[str] = field(default_factory=list)

    def missing_env(self, settings: Settings) -> list[str]:
        return [e for e in self.env if not settings.get(e)]

    def enabled(self, settings: Settings) -> bool:
        return not self.missing_env(settings)


def load_registry(path: Path | None = None) -> dict[str, dict[str, StreamSpec]]:
    settings = get_settings()
    path = path or settings.wzm_streams_file
    raw = yaml.safe_load(Path(path).read_text())
    out: dict[str, dict[str, StreamSpec]] = {"streams": {}, "outputs": {}}
    for section in out:
        for name, spec in (raw.get(section) or {}).items():
            out[section][name] = StreamSpec(name=name, connector=spec.get("connector"),
                                            **{k: v for k, v in spec.items() if k != "connector"})
    return out


def status(settings: Settings | None = None, path: Path | None = None) -> list[dict]:
    """One row per stream/output: enabled or which settings are missing."""
    settings = settings or get_settings()
    rows = []
    for section, specs in load_registry(path).items():
        for s in specs.values():
            missing = s.missing_env(settings)
            rows.append({"section": section, "name": s.name, "priority": s.priority,
                         "enabled": not missing, "missing": missing, "description": s.description})
    return rows
