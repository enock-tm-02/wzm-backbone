"""`wzm status` lists data streams; `wzm ingest <stream>` runs one connector once."""
import argparse
import json

from wzm.connectors import get_connector
from wzm.registry import load_registry, status


def main() -> None:
    p = argparse.ArgumentParser(prog="wzm")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="show which data streams and outputs are configured")
    ing = sub.add_parser("ingest", help="fetch one stream once")
    ing.add_argument("stream")
    args = p.parse_args()

    if args.cmd == "status":
        for r in status():
            mark = "ON " if r["enabled"] else "OFF"
            extra = "" if r["enabled"] else f"  (needs {', '.join(r['missing'])})"
            print(f"[{mark}] {r['section']:<7} {r['name']:<10} {r['priority']:<8} {r['description']}{extra}")
    elif args.cmd == "ingest":
        spec = load_registry()["streams"][args.stream]
        records = get_connector(spec.connector).fetch()
        print(json.dumps({"stream": args.stream, "records": len(records)}))


if __name__ == "__main__":
    main()
