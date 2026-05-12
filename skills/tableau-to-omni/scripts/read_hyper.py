"""Read a .hyper extract from inside an unpacked .twbx and dump rows / schema.

The .twbx packages its data in `Data/<workbook>.twb Files/*.hyper` (or
`*.tde` for pre-2020 workbooks).  Hyper files are read-only Postgres-like
databases that the tableauhyperapi Python package can SELECT against.

Usage:
    python3 read_hyper.py path/to/extract.hyper [--limit 100] [--out rows.csv]

If tableauhyperapi is not installed, prints install instructions and exits.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("hyper", type=Path)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    try:
        from tableauhyperapi import HyperProcess, Connection, Telemetry
    except ImportError:
        sys.exit(
            "tableauhyperapi not installed.\n"
            "  pip3 install tableauhyperapi\n"
            "Note: Tableau ships an x86_64-only build, so on Apple Silicon you may need:\n"
            "  arch -x86_64 pip3 install tableauhyperapi"
        )

    if not args.hyper.exists():
        sys.exit(f"hyper file not found: {args.hyper}")

    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(endpoint=hyper.endpoint, database=str(args.hyper)) as conn:
            schemas = [s.name.unescaped for s in conn.catalog.get_schema_names()]
            print(f"# Schemas: {schemas}", file=sys.stderr)
            for s in schemas:
                tables = conn.catalog.get_table_names(schema=s)
                for tn in tables:
                    columns = conn.catalog.get_table_definition(tn).columns
                    print(f"\n## {tn}", file=sys.stderr)
                    for c in columns:
                        print(f"  {c.name.unescaped:30s}  {c.type}", file=sys.stderr)
                    rows = conn.execute_list_query(f"SELECT * FROM {tn} LIMIT {args.limit}")
                    if args.out:
                        with args.out.open("w", newline="") as f:
                            w = csv.writer(f)
                            w.writerow([c.name.unescaped for c in columns])
                            w.writerows(rows)
                        print(f"  wrote {len(rows)} rows -> {args.out}", file=sys.stderr)
                    else:
                        for row in rows[:5]:
                            print(f"  {row}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
