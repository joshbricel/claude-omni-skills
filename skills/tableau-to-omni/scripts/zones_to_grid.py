"""Convert a Tableau dashboard zone tree to a non-overlapping Omni grid layout.

Algorithm (boundary-snapping):

Tableau uses a 100,000-unit coordinate space per dashboard, with nested
containers (`layout-flow` horz/vert) and worksheet leaves. Naive scaling
via floor(x) and ceil(w) produces overlapping integer grid coords when
two tiles share an edge (very common, Tableau's auto layouts are
space-tight, so a 50/50 split has one tile ending at y=49899 and the
next starting at y=49899).

The boundary-snapping algorithm avoids overlap by:

1. Flatten the zone tree to worksheet leaves with absolute (x, y, w, h).
2. Collect every unique boundary coordinate on each axis: the set of all
   x values AND all x+w values (and same for y). These define the
   minimal grid the dashboard can be tiled on without crossing edges.
3. Assign each boundary an integer grid index proportional to its
   position in the Tableau 0..100,000 space, scaled to the Omni target
   (24 cols by default, 60 rows by default).
4. Each tile's grid (col, row, w, h) is computed from the boundary
   indices: col = idx(x), row = idx(y), w = idx(x+w) minus idx(x),
   h = idx(y+h) minus idx(y).

This guarantees adjacent tiles share an edge exactly and no two tiles
overlap. It also preserves relative positioning: a tile that is the
right half of the dashboard always ends up at col 12..23 with the
default 24-col grid.

The grid height target (`--rows`, default 60) controls vertical density.
60 maps the full dashboard to about 2x a MacBook viewport with h=30 tiles;
30 maps it to a single viewport with h=15 tiles. Pick based on how dense
the user wants the migrated dashboard to be.

Usage:
    python3 zones_to_grid.py --ir-dir ir/ --out grid.json
    python3 zones_to_grid.py --ir-dir ir/ --out grid.json --rows 60 --cols 24

Output JSON shape:
    [
        {"worksheet": "Attended by month",
         "dashboard": "Event Dashboard Basic",
         "col": 0, "row": 0, "w": 8, "h": 30,
         "raw": {"x": 800, "y": 1000, "w": 33266, "h": 48899}},
        ...
    ]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


TABLEAU_UNIT = 100_000


def flatten_worksheets(zone: dict, out: list[dict]) -> None:
    """Collect worksheet leaves only; containers are walked through.

    Filter / parameter controls in Tableau live as zones with the same
    `name` as the source worksheet but with the `param` attribute set to
    a field reference. Skip those: they are filter panels (date pickers,
    dropdowns), not worksheet renders, and including them double-counts
    the worksheet AND throws the boundary-snapping grid off.
    """
    if zone.get("worksheet_ref") and not zone.get("param"):
        out.append(zone)
    for child in zone.get("children", []) or []:
        flatten_worksheets(child, out)


def boundary_indices(values: list[int], total: int) -> dict[int, int]:
    """Map each unique raw value to an integer in [0, total] preserving order.

    The smallest raw value lands at index 0, the largest at index `total`.
    Intermediate values are placed proportionally and rounded.
    """
    uniq = sorted(set(values))
    if not uniq:
        return {}
    lo, hi = uniq[0], uniq[-1]
    span = hi - lo
    if span <= 0:
        return {v: 0 for v in uniq}
    return {v: round((v - lo) / span * total) for v in uniq}


def map_dashboard(dash: dict, cols: int, rows: int) -> list[dict[str, Any]]:
    """Map every worksheet zone to a non-overlapping grid cell."""
    worksheets: list[dict] = []
    for top in dash.get("zones", []) or []:
        flatten_worksheets(top, worksheets)
    if not worksheets:
        return []

    # Collect all unique x and y boundaries across the dashboard. Include
    # both starts (x, y) and ends (x+w, y+h) so the grid can tile tightly.
    xs: list[int] = []
    ys: list[int] = []
    for z in worksheets:
        x = z.get("x", 0)
        y = z.get("y", 0)
        w = z.get("w", 0)
        h = z.get("h", 0)
        xs.extend([x, x + w])
        ys.extend([y, y + h])

    x_map = boundary_indices(xs, cols)
    y_map = boundary_indices(ys, rows)

    out: list[dict[str, Any]] = []
    for z in worksheets:
        x = z.get("x", 0)
        y = z.get("y", 0)
        w = z.get("w", 0)
        h = z.get("h", 0)
        col = x_map[x]
        row = y_map[y]
        col_end = x_map[x + w]
        row_end = y_map[y + h]
        out.append({
            "worksheet": z.get("worksheet_ref"),
            "dashboard": dash.get("name"),
            "col": col,
            "row": row,
            "w": max(1, col_end - col),
            "h": max(1, row_end - row),
            "raw": {"x": x, "y": y, "w": w, "h": h},
        })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ir-dir", required=True, type=Path, help="extract.py output directory")
    ap.add_argument("--out", type=Path, default=None, help="Output JSON path (default stdout)")
    ap.add_argument("--dashboard", default=None, help="Only map this dashboard")
    ap.add_argument("--cols", type=int, default=24, help="Omni grid columns (default 24)")
    ap.add_argument("--rows", type=int, default=60, help="Total Omni grid rows for the dashboard (default 60)")
    args = ap.parse_args(argv)

    dashboards_path = args.ir_dir / "dashboards.json"
    if not dashboards_path.exists():
        sys.exit(f"missing {dashboards_path}")

    dashboards: list[dict[str, Any]] = json.loads(dashboards_path.read_text())
    if args.dashboard:
        dashboards = [d for d in dashboards if d.get("name") == args.dashboard]

    all_records: list[dict[str, Any]] = []
    for d in dashboards:
        all_records.extend(map_dashboard(d, args.cols, args.rows))

    output = json.dumps(all_records, indent=2)
    if args.out:
        args.out.write_text(output)
        print(f"wrote {args.out}  ({len(all_records)} tiles)", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
