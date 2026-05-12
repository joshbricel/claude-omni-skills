"""Render a Tableau dashboard's zone tree as an HTML visual.

Reads `dashboards.json` from an `extract.py` IR directory and emits a standalone
HTML file that mirrors the original Tableau layout. Worksheet zones become
labeled boxes; containers are translucent overlays so you can see the hierarchy.

Purpose: a visual tracker that a human can open in a browser to verify the
Omni-side layout matches the Tableau-side intent. Pair with `zone_to_grid.py`
to confirm the grid mapping is correct.

Usage:
    python3 render_layout.py --ir-dir /path/to/extract-output --out layout.html
    python3 render_layout.py --ir-dir /path/to/extract-output --out layout.html --dashboard "Event Dashboard Basic"

The 100,000-unit coordinate space used by Tableau gets scaled to a fixed pixel
canvas so the output fits a standard browser window.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any


CANVAS_W = 960
CANVAS_H = 720


def walk(zone: dict, depth: int = 0) -> list[dict]:
    """Flatten the zone tree to (zone, depth) records preserving order."""
    out = [{"zone": zone, "depth": depth}]
    for child in zone.get("children", []) or []:
        out.extend(walk(child, depth + 1))
    return out


def render_dashboard(dash: dict) -> str:
    """Render one dashboard as an HTML <section>."""
    name = html.escape(dash.get("name") or "(unnamed)")
    size = dash.get("size") or {}
    maxw = size.get("maxwidth") or "auto"
    maxh = size.get("maxheight") or "auto"

    nodes: list[dict] = []
    for top in dash.get("zones", []) or []:
        nodes.extend(walk(top, depth=0))

    def to_px(v: int, total: int) -> int:
        return int(round(v / 100_000 * total))

    boxes: list[str] = []
    for n in nodes:
        z = n["zone"]
        d = n["depth"]
        is_worksheet = bool(z.get("worksheet_ref"))
        ztype = z.get("type") or ("worksheet" if is_worksheet else "?")
        label = z.get("worksheet_ref") or ztype
        x = to_px(z.get("x", 0), CANVAS_W)
        y = to_px(z.get("y", 0), CANVAS_H)
        w = to_px(z.get("w", 0), CANVAS_W)
        h = to_px(z.get("h", 0), CANVAS_H)
        klass = "worksheet" if is_worksheet else "container"
        param = z.get("param") or ""
        title = f"{label} (depth={d}, type={ztype}, param={param}, raw=x{z.get('x')} y{z.get('y')} w{z.get('w')} h{z.get('h')})"
        boxes.append(
            f'<div class="zone {klass}" '
            f'style="left:{x}px;top:{y}px;width:{w}px;height:{h}px" '
            f'title="{html.escape(title)}">'
            f'<span class="label">{html.escape(label)}</span>'
            f'</div>'
        )

    return f"""
<section class="dash">
  <h2>{name}</h2>
  <p class="meta">Tableau size: maxwidth={maxw}, maxheight={maxh}. Canvas scaled to {CANVAS_W}x{CANVAS_H}px.</p>
  <div class="canvas" style="width:{CANVAS_W}px;height:{CANVAS_H}px">
    {''.join(boxes)}
  </div>
</section>
"""


HTML_TMPL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tableau dashboard layout</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #1e1e22; color: #eee; margin: 24px; }}
  h1 {{ font-size: 18px; margin: 0 0 16px 0; }}
  h2 {{ font-size: 14px; margin: 24px 0 8px 0; color: #ffb84d; }}
  .meta {{ font-size: 12px; color: #888; margin: 0 0 12px 0; }}
  .canvas {{ position: relative; background: #2a2a30; border: 1px solid #444; }}
  .zone {{ position: absolute; box-sizing: border-box; }}
  .zone.container {{ border: 1px dashed #888; background: transparent; }}
  .zone.worksheet {{ border: 1px solid #3a7; background: rgba(58, 200, 122, 0.08); }}
  .label {{ position: absolute; top: 4px; left: 6px; font-size: 11px; color: #cdd; background: rgba(0,0,0,0.5); padding: 2px 4px; border-radius: 3px; }}
  .legend {{ font-size: 11px; color: #aaa; margin-top: 8px; }}
  .legend .swatch {{ display: inline-block; width: 10px; height: 10px; vertical-align: middle; margin: 0 4px 0 12px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="legend">
  <span class="swatch" style="background:rgba(58,200,122,0.4);border:1px solid #3a7"></span> worksheet zone
  <span class="swatch" style="border:1px dashed #888"></span> container (horz/vert flow)
</p>
{sections}
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ir-dir", required=True, type=Path, help="extract.py output directory")
    ap.add_argument("--out", required=True, type=Path, help="HTML file to write")
    ap.add_argument("--dashboard", default=None, help="Only render this dashboard (default: all)")
    args = ap.parse_args(argv)

    dashboards_path = args.ir_dir / "dashboards.json"
    if not dashboards_path.exists():
        sys.exit(f"missing {dashboards_path}")

    dashboards: list[dict[str, Any]] = json.loads(dashboards_path.read_text())
    if args.dashboard:
        dashboards = [d for d in dashboards if d.get("name") == args.dashboard]
        if not dashboards:
            sys.exit(f"no dashboard named {args.dashboard!r}")

    sections = "\n".join(render_dashboard(d) for d in dashboards)
    title = f"Tableau layout from {args.ir_dir}"
    args.out.write_text(HTML_TMPL.format(title=html.escape(title), sections=sections))
    print(f"wrote {args.out}  ({len(dashboards)} dashboard(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
