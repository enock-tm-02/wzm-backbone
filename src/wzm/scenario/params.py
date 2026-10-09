"""Loads config/scenario_defaults.yaml and merges per-request overrides."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from wzm.config import get_settings

# Fallback when running from a source checkout outside the repo root
REPO_DEFAULTS = Path(__file__).parents[3] / "config" / "scenario_defaults.yaml"


@lru_cache
def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def merge(base: dict, override: dict | None) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def get_params(override: dict | None = None, path: Path | None = None) -> dict[str, Any]:
    path = path or get_settings().wzm_scenario_file
    if not Path(path).exists():
        path = REPO_DEFAULTS
    return merge(_load(Path(path)), override)
