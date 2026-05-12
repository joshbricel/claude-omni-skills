"""Build a multi-dashboard Omni migration from a single tile-spec YAML.

This is the production builder for tableau-to-omni: it takes one YAML file
describing N dashboards (each with its tiles, layout, filters, branding) and
emits N import payloads + drives the import + seeds the workbook for each.

Usage:
    python3 build_dashboards.py \
      --spec /path/to/migration-spec.yaml \
      --connection-id <conn> \
      --shared-model-id <shared> \
      --branch-id <branch> \
      [--also-import]   # actually call documents-import + seed_workbook for each
      [--dry-run]       # just write payloads to ./payloads/

The spec YAML grammar is documented in
`reference/tile-spec-grammar.md`.

Supported tile kinds:
  - kpi_strip     One-row spreadsheet of (dimension, measure[, ...measure]) per row
  - bar           Vertical or horizontal bar; optional `color` (stacked); optional sort
  - line          Time series line (date dim x, measure y)
  - area          Filled area (date dim x, measure y); supports overlaid line
  - scatter       Point chart (x measure, y measure); optional `column` for trellis
  - dual_bar      Two parallel bars (e.g. events + new_members) per dimension; supports trellis
  - gender_callout  Two big numbers (Female, Male).  Closest analog to Tableau's gender
                    shape marks; documented as a fidelity gap from the original.
  - markdown      Static markdown / text tile

VisConfig fidelity gaps from Tableau (documented in residual-gaps.md):
  - Custom shape marks (e.g. gendered icons) -> rendered as gender_callout (numbers only).
  - Regression trend lines on scatter -> Omni's omni-spreadsheet supports a calc-based
    trend overlay; documented as manual UI step.
  - Per-dashboard custom hero color band -> rendered via dashboard `themeId`
    or per-tile borderColor; degraded but visually distinct.

Required env: OMNI_API_TOKEN, OMNI_BASE_URL.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from copy import deepcopy
from pathlib import Path

try:
    import yaml as _yaml
except ImportError:
    sys.exit("PyYAML required.  pip3 install pyyaml")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones_to_grid  # noqa: E402  (sibling helper)


def load_ir_dashboard_names(ir_dir: Path | None) -> list[str]:
    """Return the ordered list of Tableau dashboard names from extract.py output.

    Returns [] if --ir-dir was not passed, or the file is missing/empty. Callers
    use this to default a spec entry's `name:` from the source workbook.
    """
    if ir_dir is None:
        return []
    fp = ir_dir / "dashboards.json"
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"--ir-dir/dashboards.json is not valid JSON: {exc}")
    if not isinstance(data, list):
        return []
    return [d["name"] for d in data if isinstance(d, dict) and d.get("name")]


def resolve_dashboard_name(
    dash_spec: dict,
    *,
    name_prefix: str,
    ir_names: list[str],
    spec_index: int,
) -> str:
    """Resolve the Omni document name for one dashboard entry.

    Precedence:
      1. dash_spec["name"]                 (explicit override)
      2. dash_spec["tableau_name"]         (explicit cross-reference into IR)
      3. ir_names[spec_index]              (positional fallback)

    The result is wrapped with `name_prefix` so callers can opt into a
    "Migrated: " or "[Tableau]" tag without losing the source name.

    Fails loud if no name resolves: the dashboard name is the user-visible
    artifact, falling back to the slug would surprise the operator.
    """
    raw = dash_spec.get("name") or dash_spec.get("tableau_name")
    if not raw and 0 <= spec_index < len(ir_names):
        raw = ir_names[spec_index]
    if not raw:
        sys.exit(
            f"Could not resolve a name for dashboard slug={dash_spec.get('slug')!r}. "
            "Set `name:` or `tableau_name:` on the spec entry, or pass --ir-dir "
            "with a dashboards.json that has at least "
            f"{spec_index + 1} entries."
        )
    return f"{name_prefix}{raw}"


OMNI_GRID_COLS = 24
OMNI_GRID_ROWS = 60


def autofill_layouts_from_ir(
    dashboard_spec: dict, *, ir_dir: Path | None, spec_index: int = 0,
) -> None:
    """Mutate dashboard_spec in place: for tiles that omit `layout:`, derive
    (x, y, w, h) from the Tableau zone tree in `ir_dir/dashboards.json`.

    This used to be the spec author's job, and hand-authored layouts were
    routinely wrong (every tile collapsed to a 4-col-wide x 14-row-tall slab
    regardless of the Tableau dashboard's actual proportions). The IR has
    pixel-accurate zone coords; we now use them by default.

    Match strategy: tile is bound to a Tableau worksheet via
    `tile["tableau_name"]` if present, else `tile["name"]`. The matched
    worksheet's zone is converted to a (col, row, w, h) on a 24-col x 60-row
    grid via the existing zones_to_grid algorithm.

    Tiles that already have `layout` are left alone (explicit override wins).
    Tiles whose name doesn't match anything in the IR keep no layout, which
    surfaces as a loud error downstream rather than silent miscentering.
    """
    if ir_dir is None:
        return
    fp = ir_dir / "dashboards.json"
    if not fp.exists():
        return
    dashboards = json.loads(fp.read_text())
    if not isinstance(dashboards, list):
        return

    # Prefer the explicit tableau_name, else fall back to positional match
    # (IR order matches spec order). dashboard_spec["name"] is unreliable here
    # because resolve_dashboard_name has already wrapped it with name_prefix.
    tableau_name = dashboard_spec.get("tableau_name")
    if tableau_name:
        dash_ir = next((d for d in dashboards if d.get("name") == tableau_name), None)
    elif 0 <= spec_index < len(dashboards):
        dash_ir = dashboards[spec_index]
    else:
        dash_ir = None
    if dash_ir is None:
        return

    grid = {
        rec["worksheet"]: rec
        for rec in zones_to_grid.map_dashboard(
            dash_ir, OMNI_GRID_COLS, OMNI_GRID_ROWS
        )
    }
    for i, tile in enumerate(dashboard_spec.get("tiles", []) or []):
        if tile.get("layout"):
            continue
        if tile.get("kind") == "markdown":
            continue
        key = tile.get("tableau_name") or tile.get("name")
        rec = grid.get(key)
        if rec is None:
            continue
        tile["layout"] = {
            "x": rec["col"], "y": rec["row"], "w": rec["w"], "h": rec["h"],
        }


# Mapping from a Tableau period-type-v2 token to the Omni duration unit. Used
# when translating <filter class='relative-date' period-type-v2='month' ...>
# into Omni TIME_FOR_INTERVAL_DURATION left_side/right_side strings.
TABLEAU_PERIOD_TO_OMNI = {
    "year": "years",
    "quarter": "quarters",
    "month": "months",
    "week": "weeks",
    "day": "days",
    "hour": "hours",
    "minute": "minutes",
}


def _tableau_filter_to_omni_default(ir_filter: dict) -> dict | None:
    """Translate one Tableau IR filter record into the partial Omni
    filterConfig fields the spec can otherwise carry by hand.

    Returns None if the IR filter doesn't map cleanly (e.g. a categorical
    filter with a groupfilter expression we don't yet support). The caller
    falls back to the previous string-with-empty-values behavior in that case.

    Specifically supported today:
    - class='relative-date' with period-type-v2 in TABLEAU_PERIOD_TO_OMNI
      -> Omni TIME_FOR_INTERVAL_DURATION (= YAML `time_for_duration`), the
         documented "in the past N units" / "starting from X for Y" filter.
    - class='categorical' with members
      -> Omni EQUALS filter with the member list as values.

    Key Omni date-literal semantics (docs.omni.co/modeling/filters/operators/
    time-for-duration plus empirical SQL inspection):

    - The natural-language `"N units ago"` literal means "the START of the
      period that is (N-1) calendar units back from now" (i.e. truncated and
      inclusive of the current period). So `"12 months ago"` resolves to
      `DATE_TRUNC(MONTH, NOW - INTERVAL '11 month')`, not 12.
    - The "in the past N units" UI picker is the symmetric pattern
      `time_for_duration: [N units ago, N units]`, i.e.
      `left_side: "N units ago", right_side: "N units"`.
    - To get a strict N-units-back start (no current-period inclusion), use
      `"N complete units ago"` which resolves to `INTERVAL '-N unit'`.

    Therefore Tableau `first=-(N-1), last=0, period=unit` (the canonical
    "last N units including current" pattern) maps to Omni
    `left_side: "N units ago", right_side: "N units"`. Both sides use
    `period_count`, not `abs(first)`. Using `abs(first)` on the left
    produces "N-1 units ago" which is the same data window but renders as a
    range picker rather than the "in the past N" picker the user expects.

    Anchor windows that don't end at the current period (e.g. first=-6,
    last=-3 = "6 months ago for 4 months") use the original offset+length
    form: `left_side: "{abs(first)} units ago", right_side: "{period_count} units"`.

    Date-filter `kind` enum surfaced via the API's 400 response (use only
    these values, the planner rejects anything else):
        IS_ON_DAY_OF_WEEK, IS_ON_DAY_OF_QUARTER, IS_IN_MONTH_OF_YEAR,
        IS_ON_DAY_OF_YEAR, IS_AT_HOUR_OF_DAY, IS_IN_QUARTER_OF_YEAR,
        IS_IN_WEEK_OF_YEAR, IS_ON_DAY_OF_MONTH, BETWEEN, ON_OR_AFTER, BEFORE,
        TIME_FOR_INTERVAL_DURATION, TIME_FOR_UNIT_DURATION, QUERY_OFFSET.

    The dashboards-filter PATCH endpoint also accepts TIME_FOR_UNIT_DURATION
    but the query planner rejects it ("Invalid literal value"). Stick to
    TIME_FOR_INTERVAL_DURATION.
    """
    cls = ir_filter.get("class")
    if cls == "relative-date":
        rd = ir_filter.get("relative_date") or {}
        period_type = (rd.get("period_type") or "").lower()
        unit = TABLEAU_PERIOD_TO_OMNI.get(period_type)
        if not unit:
            return None
        try:
            first = int(rd.get("first_period") or 0)
            last = int(rd.get("last_period") or 0)
        except (TypeError, ValueError):
            return None
        # Tableau ranges are inclusive on both ends: first=-11, last=0 means
        # 12 periods total (11 in the past + the current one).
        period_count = abs(last - first) + 1

        if last == 0 and first <= 0:
            # "In the past N units" pattern. Omni renders [N units ago, N units]
            # as the single-input "in the past N" picker.
            return {
                "type": "date",
                "kind": "TIME_FOR_INTERVAL_DURATION",
                "left_side": f"{period_count} {unit} ago",
                "right_side": f"{period_count} {unit}",
            }

        # Offset window not ending at the current period. Anchor at
        # abs(first) units ago, length = period_count.
        return {
            "type": "date",
            "kind": "TIME_FOR_INTERVAL_DURATION",
            "left_side": f"{abs(first)} {unit} ago",
            "right_side": f"{period_count} {unit}",
        }
    if cls == "categorical":
        members = ir_filter.get("members") or []
        cleaned = [m.strip().strip('"') for m in members if m]
        if not cleaned:
            return None
        return {
            "type": "string",
            "kind": "EQUALS",
            "values": cleaned,
        }
    return None


def _column_basename(column_ref: str | None) -> str | None:
    """Strip Tableau's federated/instance wrapping off a column reference.

    Inputs we see in the wild:
        [federated.<id>].[tmn:ATTENDED_DATE:qk]   -> "attended_date"
        [federated.<id>].[none:CATEGORY_NAME:nk]  -> "category_name"
        [ATTENDED_DATE]                           -> "attended_date"
        [tmn:ATTENDED_DATE:qk]                    -> "attended_date"
    """
    if not column_ref:
        return None
    raw = column_ref
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    raw = raw.strip("[]")
    if ":" in raw:
        parts = raw.split(":")
        # tmn:COLNAME:qk -> middle piece
        raw = parts[1] if len(parts) >= 2 else parts[0]
    return raw.lower()


def _tableau_column_to_omni_field(column_ref: str | None, *, view: str) -> str | None:
    """Translate a Tableau column reference to an Omni `<view>.<field>` name.

    The base name comes from `_column_basename` (strips federated wrapping,
    drops the derivation prefix like `none:` / `tmn:` / `sum:`, and lowercases).
    Returns None for refs we can't translate (e.g. references to a
    `Calculation_<hash>` that maps to a view measure under a different name,
    those need an explicit override on the tile).
    """
    base = _column_basename(column_ref)
    if not base:
        return None
    # Tableau column-instance names like "Calculation_2831118125210705" are not
    # view fields; they correspond to calc measures that the spec author has to
    # bind by hand (the IR has the formula in calcs.json but not the target
    # measure name). Skip them.
    if base.startswith("calculation_"):
        return None
    return f"{view}.{base}"


def autofill_tile_encodings_from_ir(
    dashboard_spec: dict, *, ir_dir: Path | None, view: str,
) -> None:
    """Mutate tiles in place: fill `color` (and other encoding-driven fields)
    from the matching Tableau worksheet's encodings shelf.

    Without this, a Tableau bar chart whose `color` shelf was bound to the
    same dimension as the row pill (the "self-color" pattern that gives each
    bar a distinct hue) renders in Omni as a single-color bar chart. The IR
    has the encoding; the script previously ignored it.

    Match strategy: each tile is matched to a worksheet in `worksheets.json`
    by `tile["tableau_name"]` (preferred) or `tile["name"]`. From that
    worksheet, the `encodings` list is scanned for shelves the spec didn't
    set. The translation to a view-prefixed field name uses
    `_tableau_column_to_omni_field`.

    Fields that get filled today:
    - `color` for tiles of kind in {bar, dual_bar, line, area, scatter}, when
      the worksheet has an `encodings[shelf=color]` entry that resolves to a
      view field name.

    Honors explicit nulls: a tile with `color: null` in YAML signals
    "do not color"; auto-fill skips it. A tile that omits `color` entirely
    is the auto-fill path.
    """
    if ir_dir is None:
        return
    fp = ir_dir / "worksheets.json"
    if not fp.exists():
        return
    worksheets = json.loads(fp.read_text())
    if not isinstance(worksheets, list):
        return
    by_name = {w.get("name"): w for w in worksheets if isinstance(w, dict)}

    for tile in dashboard_spec.get("tiles", []) or []:
        if tile.get("kind") == "markdown":
            continue
        ws_key = tile.get("tableau_name") or tile.get("name")
        ws = by_name.get(ws_key)
        if not ws:
            continue

        if "color" not in tile and tile.get("kind") in ("bar", "dual_bar", "line", "area", "scatter"):
            for enc in ws.get("encodings", []) or []:
                if enc.get("shelf") != "color":
                    continue
                resolved = _tableau_column_to_omni_field(enc.get("column"), view=view)
                if resolved:
                    tile["color"] = resolved
                    break


def autofill_filters_from_ir(
    dashboard_spec: dict, *, ir_dir: Path | None,
) -> None:
    """Mutate dashboard_spec in place: for each filter that names a `field:`
    but omits the value config (type/kind/values/left_side/right_side), look
    up the matching Tableau filter in `ir_dir/dashboard_filters.json` and
    fill the defaults.

    Match strategy: extract the column basename from each IR filter's
    `column` (e.g. "ATTENDED_DATE") and compare to the spec field's base
    name (e.g. `vw_events_wide.attended_date[date]` -> "attended_date").
    Case insensitive.

    Without this, every spec filter defaulted to `type: string, values: []`,
    which produced a filter pill with no active default (the 12-month rolling
    window from the source workbook silently disappeared).
    """
    if ir_dir is None:
        return
    fp = ir_dir / "dashboard_filters.json"
    if not fp.exists():
        return
    ir_filters = json.loads(fp.read_text())
    if not isinstance(ir_filters, list) or not ir_filters:
        return

    # Index IR filters by lowercased column basename.
    by_col: dict[str, dict] = {}
    for rec in ir_filters:
        key = _column_basename(rec.get("column"))
        if key and key not in by_col:
            by_col[key] = rec

    for f in dashboard_spec.get("filters", []) or []:
        if not isinstance(f, dict):
            continue
        # Skip if the spec already supplies a non-default config.
        if any(k in f for k in ("type", "kind", "values", "left_side", "right_side")):
            continue
        field_ref = f.get("field") or ""
        # Strip view prefix and [time-frame] suffix.
        base = field_ref.split(".", 1)[-1]
        base = base.split("[", 1)[0].lower()
        ir = by_col.get(base)
        if not ir:
            continue
        translated = _tableau_filter_to_omni_default(ir)
        if translated:
            f.update(translated)


def cli(*args: str, body: str | None = None) -> dict:
    cmd = ["omni"]
    if "OMNI_BASE_URL" in os.environ:
        cmd += ["--base-url", os.environ["OMNI_BASE_URL"]]
    if "OMNI_API_TOKEN" in os.environ:
        cmd += ["--token", os.environ["OMNI_API_TOKEN"]]
    cmd += list(args) + ["--format", "json"]
    if body is not None:
        cmd += ["--body", body]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"omni CLI failed: {' '.join(cmd[:6])}...\n  stderr: {r.stderr}\n  stdout head: {r.stdout[:600]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def new_uuid() -> str:
    return str(uuid.uuid4())


def new_mini() -> str:
    return uuid.uuid4().hex[:8].upper()


def normalize_filters(simple_filters: dict | None) -> dict:
    """Translate the spec's compact filter form into Omni's queryJson filter shape.

    Input:
        {"view.field": {"is": "Y"}}                      -> EQUALS single value
        {"view.field": {"is": "Female,Male"}}            -> EQUALS multi value
        {"view.field": {"is_not": "Y"}}                  -> EQUALS negated
        {"view.field": {"kind": "EQUALS", "values": [...]}} -> passthrough

    Output: Omni's queryJson.filters dict.
    """
    if not simple_filters:
        return {}
    out = {}
    for field, spec in simple_filters.items():
        if not isinstance(spec, dict):
            sys.exit(f"filter for {field!r} must be a dict, got {type(spec).__name__}")
        if "kind" in spec:
            out[field] = spec  # passthrough
            continue
        if "is" in spec:
            v = spec["is"]
            values = [s.strip() for s in v.split(",")] if isinstance(v, str) else (v if isinstance(v, list) else [v])
            out[field] = {"kind": "EQUALS", "values": values, "type": "string", "is_negative": False}
            continue
        if "is_not" in spec:
            v = spec["is_not"]
            values = [s.strip() for s in v.split(",")] if isinstance(v, str) else (v if isinstance(v, list) else [v])
            out[field] = {"kind": "EQUALS", "values": values, "type": "string", "is_negative": True}
            continue
        sys.exit(f"unknown filter shape for {field!r}: {spec!r}")
    return out


# Verified-working queryJson key set: matches Omni's documents-export shape.
def build_query_json(*, model_id: str, table: str, topic: str,
                     fields: list[str], sorts: list[dict] | None = None,
                     filters: dict | None = None, limit: int = 5000) -> dict:
    return {
        "limit": limit,
        "sorts": sorts or [],
        "table": table,
        "fields": fields,
        "pivots": [],
        "dbtMode": False,
        "filters": filters or {},
        "modelId": model_id,
        "version": 8,
        "rewriteSql": True,
        "row_totals": {},
        "fill_fields": [],
        "calculations": [],
        "join_via_map": {},
        "column_totals": {},
        "default_group_by": True,
        "column_limit": 50,
        "metadata": {},
        "userEditedSQL": "",
        "dimensionIndex": 0,
        "custom_summary_types": {},
        "join_paths_from_topic_name": topic,
    }


def build_vis_kpi_strip(tile: dict) -> dict:
    """KPI strip: spreadsheet tile, one row per dimension value, columns = measures."""
    fields = [tile["dimension"]] + tile["measures"]
    return {
        "id": new_uuid(),
        "visType": "omni-spreadsheet",
        "spec": {},
        "fields": fields,
        "version": 0,
    }


def build_vis_bar(tile: dict) -> dict:
    """Vertical or horizontal bar.  Stacked when `color` is provided."""
    horizontal = tile.get("orientation", "vertical") == "horizontal"
    dim = tile["dimension"]
    measures = tile["measures"]
    color_field = tile.get("color")  # optional stacked-by dimension
    column_field = tile.get("column")  # optional trellis column
    sort_field = tile.get("sort_by") or measures[0]
    sort_order = tile.get("sort_order", "descending")

    primary_measure = measures[0]
    series = []
    for m in measures:
        series.append({
            "mark": {"type": "bar"},
            "field": {"name": m},
            "title": {"value": m.split(".")[-1].replace("_", " ").title()},
            ("xAxis" if horizontal else "yAxis"): "x" if horizontal else "y",
        })

    # Stack only when color encodes a split of a single measure (e.g. gender stacks
    # within an age bin). Multi-measure tiles render side-by-side regardless of color.
    stack = bool(color_field) and len(measures) == 1
    spec = {
        "version": 0,
        "configType": "cartesian",
        "mark": {"type": "bar"},
        "series": series,
        "tooltip": [{"field": {"name": f}} for f in [dim] + measures + ([color_field] if color_field else [])],
        "behaviors": {"stackMultiMark": stack},
        "_dependentAxis": "x" if horizontal else "y",
    }
    if horizontal:
        spec["x"] = {"field": {"name": primary_measure}, "axis": {"title": {"value": ""}}}
        spec["y"] = {
            "field": {"name": dim},
            "axis": {
                "title": {"value": ""},
                "sort": {"field": sort_field, "order": sort_order},
            },
        }
    else:
        spec["x"] = {
            "field": {"name": dim},
            "axis": {
                "title": {"value": ""},
                "sort": {"field": sort_field, "order": sort_order} if sort_field != dim else None,
            },
        }
        spec["y"] = {"field": {"name": primary_measure}, "axis": {"title": {"value": ""}}}
    if color_field:
        spec["color"] = {"field": {"name": color_field}}
    if column_field:
        spec["column"] = {"field": {"name": column_field}}

    fields = [dim] + measures + ([color_field] if color_field else []) + ([column_field] if column_field else [])
    return {
        "id": new_uuid(),
        "visType": "basic",
        "chartType": None,
        "spec": spec,
        "fields": list(dict.fromkeys(fields)),
        "version": 0,
    }


def build_vis_line_or_area(tile: dict, mark_type: str) -> dict:
    dim = tile["dimension"]
    measures = tile["measures"]
    color_field = tile.get("color")
    primary_color = tile.get("hero_color", "#298BE5")

    series = []
    for m in measures:
        series.append({
            "mark": {"type": mark_type, "_mark_color": primary_color},
            "field": {"name": m},
            "title": {"value": m.split(".")[-1].replace("_", " ").title()},
            "yAxis": "y",
        })

    spec = {
        "version": 0,
        "configType": "cartesian",
        "mark": {"type": mark_type},
        "x": {
            "field": {"name": dim},
            "axis": {
                "title": {"value": ""},
                "sort": {"field": dim, "order": "ascending"},
            },
        },
        "y": {"field": {"name": measures[0]}, "axis": {"title": {"value": ""}}},
        "series": series,
        "tooltip": [{"field": {"name": f}} for f in [dim] + measures],
        "behaviors": {"stackMultiMark": False},
        "_dependentAxis": "y",
    }
    if color_field:
        spec["color"] = {"field": {"name": color_field}}

    fields = [dim] + measures + ([color_field] if color_field else [])
    return {
        "id": new_uuid(),
        "visType": "basic",
        "chartType": None,
        "spec": spec,
        "fields": list(dict.fromkeys(fields)),
        "version": 0,
    }


def build_vis_scatter(tile: dict) -> dict:
    x_field = tile["x"]
    y_field = tile["y"]
    color_field = tile.get("color")
    column_field = tile.get("column")

    spec = {
        "version": 0,
        "configType": "cartesian",
        "mark": {"type": "point"},
        "x": {"field": {"name": x_field}, "axis": {"title": {"value": x_field.split(".")[-1]}}},
        "y": {"field": {"name": y_field}, "axis": {"title": {"value": y_field.split(".")[-1]}}},
        "series": [{"mark": {"type": "point"}, "field": {"name": y_field}, "yAxis": "y"}],
        "tooltip": [{"field": {"name": x_field}}, {"field": {"name": y_field}}],
        "behaviors": {"stackMultiMark": False},
        "_dependentAxis": "y",
    }
    if color_field:
        spec["color"] = {"field": {"name": color_field}}
    if column_field:
        spec["column"] = {"field": {"name": column_field}}

    fields = [x_field, y_field] + ([color_field] if color_field else []) + ([column_field] if column_field else [])
    # chartType is left null on basic charts in Omni's documents-export shape;
    # the mark.type inside the spec is what drives rendering.
    return {
        "id": new_uuid(),
        "visType": "basic",
        "chartType": None,
        "spec": spec,
        "fields": list(dict.fromkeys(fields)),
        "version": 0,
    }


def build_vis_for_tile(tile: dict) -> dict:
    kind = tile.get("kind", "bar")
    if kind == "kpi_strip":
        return build_vis_kpi_strip(tile)
    if kind == "bar" or kind == "dual_bar":
        return build_vis_bar(tile)
    if kind == "line":
        return build_vis_line_or_area(tile, "line")
    if kind == "area":
        return build_vis_line_or_area(tile, "area")
    if kind == "scatter":
        return build_vis_scatter(tile)
    if kind == "gender_callout":
        # Two-row spreadsheet: gender, measure.  Visual fallback for Tableau shape marks.
        return {
            "id": new_uuid(),
            "visType": "omni-spreadsheet",
            "spec": {},
            "fields": [tile["dimension"], tile["measure"]],
            "version": 0,
        }
    if kind == "markdown":
        return None  # text tiles handled separately
    sys.exit(f"unknown tile kind: {kind!r}")


def fields_for_tile(tile: dict) -> list[str]:
    kind = tile.get("kind")
    if kind == "kpi_strip":
        return [tile["dimension"]] + list(tile["measures"])
    if kind in ("bar", "dual_bar"):
        out = [tile["dimension"]] + list(tile["measures"])
        if tile.get("color"):
            out.append(tile["color"])
        if tile.get("column"):
            out.append(tile["column"])
        return list(dict.fromkeys(out))
    if kind in ("line", "area"):
        out = [tile["dimension"]] + list(tile["measures"])
        if tile.get("color"):
            out.append(tile["color"])
        return list(dict.fromkeys(out))
    if kind == "scatter":
        out = [tile["x"], tile["y"]]
        if tile.get("color"):
            out.append(tile["color"])
        if tile.get("column"):
            out.append(tile["column"])
        # extra_dimensions add implicit GROUP BY granularity (e.g. event_type)
        # without changing the visConfig's x/y/color/column encodings.
        for d in tile.get("extra_dimensions", []) or []:
            out.append(d)
        return list(dict.fromkeys(out))
    if kind == "gender_callout":
        return [tile["dimension"], tile["measure"]]
    return []


def sorts_for_tile(tile: dict) -> list[dict]:
    s = tile.get("sort_by")
    if not s:
        # Default: sort line/area by x ascending, bar by primary measure descending.
        kind = tile.get("kind")
        if kind in ("line", "area"):
            return [{"column_name": tile["dimension"], "sort_descending": False}]
        if kind in ("bar",) and tile.get("orientation", "vertical") == "horizontal":
            return [{"column_name": tile["measures"][0], "sort_descending": True}]
        return []
    return [{"column_name": s, "sort_descending": tile.get("sort_order", "descending") == "descending"}]


def build_query_presentation(tile: dict, *, model_id: str, view: str, topic: str) -> dict:
    qid = new_uuid()
    fields = fields_for_tile(tile)
    sorts = sorts_for_tile(tile)
    qj = build_query_json(
        model_id=model_id, table=view, topic=topic,
        fields=fields, sorts=sorts,
        filters=normalize_filters(tile.get("filters")),
        limit=tile.get("limit", 5000),
    )
    vc = build_vis_for_tile(tile)
    if vc is None:
        sys.exit(f"tile {tile.get('name')!r} is markdown - handle via dashboard.metadata.textTiles, not query presentation")

    return {
        "id": new_uuid(),
        "type": "query",
        "name": tile["name"],
        "subTitle": tile.get("subtitle", ""),
        "description": tile.get("description", ""),
        "queryId": qid,
        "miniUuid": new_mini(),
        "modelId": model_id,
        "fileUploadId": None,
        "prefersChart": vc["visType"] != "omni-spreadsheet",
        "automaticVis": True,
        "visConfigId": vc["id"],
        "topicName": topic,
        "filterOrder": [],
        "isSql": False,
        "resultConfig": {
            "tableType": "spreadsheet",
            "rowBanding": {"enabled": False, "bandSize": 1},
            "expandedRows": {},
            "hideIndexColumn": False,
            "truncateHeaders": True,
            "showDescriptions": True,
            "visColumnDisplay": "hide-view-name",
        },
        "aiConfig": {},
        "query": {"id": qid, "modelId": model_id, "queryJson": qj},
        "visConfig": vc,
    }


def build_dashboard_payload(dashboard_spec: dict, *, connection_id: str,
                            shared_model_id: str, branch_id: str,
                            view: str, topic: str, template: dict) -> dict:
    payload = deepcopy(template)

    qpc_memberships = []
    for tile in dashboard_spec["tiles"]:
        if tile.get("kind") == "markdown":
            continue
        qp = build_query_presentation(tile, model_id=branch_id, view=view, topic=topic)
        qpc_memberships.append({"queryPresentation": qp})

    layouts_lg = []
    layouts_sm = []
    for i, tile in enumerate([t for t in dashboard_spec["tiles"] if t.get("kind") != "markdown"], start=1):
        layout = tile.get("layout", {})
        layouts_lg.append({
            "i": str(i),
            "x": layout.get("x", 0),
            "y": layout.get("y", (i - 1) * 12),
            "w": layout.get("w", 12),
            "h": layout.get("h", 12),
            "moved": False, "static": False,
        })
        layouts_sm.append({
            "i": str(i),
            "x": 0, "y": (i - 1) * 24,
            "w": 1, "h": 24,
            "moved": False, "static": False,
        })

    n_tiles = len(qpc_memberships)
    doc_id = new_uuid()
    dashboard_id = new_uuid()
    payload["document"] = {
        "name": dashboard_spec["name"],
        "connectionId": connection_id,
        "modelId": branch_id,
        "sharedModelId": shared_model_id,
        "documentId": doc_id,
        "stableDocumentId": new_uuid(),
        "dashboardId": dashboard_id,
        "dashboardMiniUuid": new_mini(),
        "hasDashboard": True,
        "ephemeral": ",".join(
            f"{i + 1}:{m['queryPresentation']['miniUuid']}"
            for i, m in enumerate(qpc_memberships)
        ),
        "folder": None,
        "isDocument": True,
        "isDraft": False,
        "scope": "organization",
        "type": "document",
        "description": dashboard_spec.get("description", ""),
        "identifier": None,
        "workbookId": None,
    }

    filter_config = {}
    filter_order = []
    for f in dashboard_spec.get("filters", []) or []:
        field = f["field"]
        ftype = f.get("type", "string")
        label = f.get("label")
        if ftype == "string":
            # Omni's StringFilter deserializer requires `values` to be non-null.
            # An empty list is valid for an "unselected" pill.
            cfg = {
                "kind": f.get("kind", "EQUALS"),
                "type": "string",
                "values": f.get("values", []),
                "is_negative": False,
            }
        elif ftype == "boolean":
            cfg = {
                "type": "boolean",
                "is_negative": False,
                "treat_nulls_as_false": f.get("treat_nulls_as_false", False),
            }
        elif ftype == "date":
            cfg = {
                "kind": f.get("kind", "TIME_FOR_INTERVAL_DURATION"),
                "type": "date",
                "left_side": f.get("left_side", "12 months ago"),
                "right_side": f.get("right_side", "12 months"),
                "is_negative": False,
            }
        else:
            cfg = {
                "kind": f.get("kind", "EQUALS"),
                "type": ftype,
                "values": f.get("values", []),
                "is_negative": False,
            }
        if label:
            cfg["label"] = label
        filter_config[field] = cfg
        filter_order.append(field)

    payload["dashboard"] = {
        "id": dashboard_id,
        "name": dashboard_spec["name"],
        "crossfilterEnabled": dashboard_spec.get("cross_filter", True),
        "facetFilters": False,
        "metadataVersion": 2,
        "metadata": {
            "layouts": {"lg": layouts_lg, "sm": layouts_sm},
            "textTiles": [
                {"i": f"text-{j+1}", **t.get("layout", {}), "content": t.get("content", "")}
                for j, t in enumerate(dashboard_spec.get("tiles", []))
                if t.get("kind") == "markdown"
            ],
            "hiddenTiles": [],
            "tileSettings": {str(i + 1): {"hideBorder": False} for i in range(n_tiles)},
            "tileFilterMap": {str(i + 1): {} for i in range(n_tiles)},
            "tileControlMap": {},
        },
        "queryPresentationCollection": {
            "id": new_uuid(),
            "filterConfig": filter_config,
            "filterConfigVersion": 1,
            "filterOrder": filter_order,
            "queryPresentationCollectionMemberships": qpc_memberships,
        },
    }

    payload["workbookModel"] = {
        "connection_id": connection_id,
        "views": [],
        "relationships": [],
        "model_kind": "WORKBOOK",
        "base_model_id": shared_model_id,
        "topics": [],
        "ignored_schemas": [],
        "ignored_views": [],
        "all_schema_names": [],
        "virtualized_schemas": [],
        "deleted_topics": [],
        "dbt_virtualization_enabled": True,
    }

    payload["queryModels"] = {
        m["queryPresentation"]["query"]["id"]: {
            "id": m["queryPresentation"]["query"]["id"],
            "modelId": branch_id,
            "queryJson": m["queryPresentation"]["query"]["queryJson"],
        }
        for m in qpc_memberships
    }

    payload["exportVersion"] = "0.1"
    payload["fileUploads"] = {}
    payload["baseModelId"] = shared_model_id
    return payload


def import_payload(payload: dict, *, label: str) -> tuple[str, str]:
    print(f"  importing {label!r}...", file=sys.stderr)
    body = json.dumps(payload)
    resp = cli("unstable", "documents-import", body=body)
    workbook_id = resp.get("workbook", {}).get("id")
    identifier = resp.get("workbook", {}).get("identifier")
    if not workbook_id or not identifier:
        sys.exit(f"unexpected import response for {label}: {json.dumps(resp)[:600]}")
    return identifier, workbook_id


def seed_workbook(workbook_id: str, yaml_dir: Path) -> None:
    """Run seed_workbook.py at sibling path for the new workbook."""
    here = Path(__file__).resolve().parent
    seed = here / "seed_workbook.py"
    r = subprocess.run(
        ["python3", str(seed), "--workbook-id", workbook_id, "--yaml-dir", str(yaml_dir), "--also-validate"],
        capture_output=False, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"seed_workbook failed for workbook {workbook_id}")


def main() -> int:
    if shutil.which("omni") is None:
        sys.exit("omni CLI not on PATH.  brew tap exploreomni/tap && brew install omni")

    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", type=Path, required=True, help="migration-spec YAML (1+ dashboards)")
    ap.add_argument("--connection-id", required=True)
    ap.add_argument("--shared-model-id", required=True)
    ap.add_argument("--branch-id", required=True)
    ap.add_argument("--template", type=Path, required=True,
                    help="Working dashboard export JSON (structural skeleton)")
    ap.add_argument("--out-dir", type=Path, default=Path("./payloads"),
                    help="Where to write per-dashboard payload JSON files")
    ap.add_argument("--also-import", action="store_true",
                    help="Actually call documents-import for each dashboard")
    ap.add_argument("--seed-yaml-dir", type=Path,
                    help="If --also-import: directory of view/topic YAML to seed each workbook")
    ap.add_argument("--ir-dir", type=Path, default=None,
                    help=(
                        "Optional extract.py output dir; used to default each "
                        "dashboard's `name` from the source Tableau workbook "
                        "when the spec entry omits it."
                    ))
    ap.add_argument("--name-prefix", default=None,
                    help=(
                        "Prepend this string to every resolved dashboard name "
                        "(e.g. \"Migrated: \"). Overrides spec.name_prefix "
                        "when both are set. Empty by default."
                    ))
    args = ap.parse_args()

    spec = _yaml.safe_load(args.spec.read_text())
    template = json.loads(args.template.read_text())
    args.out_dir.mkdir(parents=True, exist_ok=True)

    view = spec["view"]
    topic = spec["topic"]
    name_prefix = args.name_prefix if args.name_prefix is not None else spec.get("name_prefix", "")
    ir_names = load_ir_dashboard_names(args.ir_dir)

    results = []
    for idx, dash in enumerate(spec["dashboards"]):
        # Default each dashboard's display name from the Tableau workbook unless
        # the spec entry overrides. Mutate the spec so downstream stages
        # (build_dashboard_payload, import_payload) see the resolved value.
        dash["name"] = resolve_dashboard_name(
            dash, name_prefix=name_prefix, ir_names=ir_names, spec_index=idx,
        )
        # IR-driven defaults: fill missing tile layouts from the Tableau zone
        # tree, and missing filter defaults from the Tableau filter config.
        # Explicit values in the spec always win.
        autofill_layouts_from_ir(dash, ir_dir=args.ir_dir, spec_index=idx)
        autofill_filters_from_ir(dash, ir_dir=args.ir_dir)
        autofill_tile_encodings_from_ir(dash, ir_dir=args.ir_dir, view=view)
        payload = build_dashboard_payload(
            dash,
            connection_id=args.connection_id,
            shared_model_id=args.shared_model_id,
            branch_id=args.branch_id,
            view=view, topic=topic,
            template=template,
        )
        out_file = args.out_dir / f"{dash['slug']}.payload.json"
        out_file.write_text(json.dumps(payload, indent=2, default=str))
        print(f"  wrote {out_file} ({len(json.dumps(payload))} chars, {len(dash['tiles'])} tiles)", file=sys.stderr)

        if args.also_import:
            identifier, workbook_id = import_payload(payload, label=dash["name"])
            if args.seed_yaml_dir:
                seed_workbook(workbook_id, args.seed_yaml_dir)
            results.append({
                "name": dash["name"],
                "slug": dash["slug"],
                "identifier": identifier,
                "workbook_id": workbook_id,
                "url": f"{os.environ.get('OMNI_BASE_URL','https://your-org.omniapp.co')}/dashboards/{identifier}",
            })

    if results:
        print(json.dumps({"imported": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
