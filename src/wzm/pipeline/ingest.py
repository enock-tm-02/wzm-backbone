"""Run every enabled connector and write raw records to data/raw/<stream>/."""
import json
from datetime import datetime, timezone

from wzm.config import get_settings
from wzm.connectors import get_connector
from wzm.registry import load_registry


def ingest_all() -> dict[str, int | str]:
    settings = get_settings()
    results: dict[str, int | str] = {}
    for name, spec in load_registry()["streams"].items():
        if not spec.enabled(settings):
            results[name] = "skipped: not configured"
            continue
        try:
            records = get_connector(spec.connector).fetch()
        except NotImplementedError:
            results[name] = "skipped: connector is a placeholder"
            continue
        out_dir = settings.wzm_data_dir / "raw" / name
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (out_dir / f"{stamp}.jsonl").write_text("\n".join(json.dumps(r) for r in records))
        results[name] = len(records)
    return results
