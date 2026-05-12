"""Translate Tableau IR (from extract.py output) into an Omni `documents-import`
payload, ready for `omni unstable documents-import --body -`.

Strategy: take a working Omni dashboard export as a structural template, then
mutate it: replace IDs, swap in our Tableau-derived queries and visConfigs,
update layout, point at our branch model.

Usage:
    python3 build_payload.py \
      --dashboard-name "Events overview" \
      --topic acme_events \
      --view vw_events_wide \
      --base-model-id <branch-id> \
      --connection-id <conn-id> \
      --shared-model-id <shared-id> \
      --template /path/to/working_export.json \
      --tile-spec /path/to/tile_spec.yaml \
      --out payload.json

The tile-spec is a small YAML file that maps each Tableau worksheet name to
an Omni tile definition (query fields, visType, chartType).  This is the
human-curated translation step the skill calls out: not every Tableau viz
maps cleanly, so the user provides the mapping table.

CRITICAL POST-IMPORT STEPS (do not skip):

1. After import, write the migration view + topic YAML files to the WORKBOOK
   model the import creates.  Use `scripts/seed_workbook.py`.  The workbook
   extends SHARED (the import API rejects branch baseModelId), so it does
   NOT see the branch's view/topic.

2. seed_workbook performs a delete-then-recreate dance for each view to
   suppress Omni's automatic schema-prefix on the view name (a view at
   `<SCHEMA>/<view>.view` registers as `<schema>__<view>`, but query bodies
   reference the un-prefixed `<view>`).  See seed_workbook docstring.

Without (1) and (2) the dashboard 500s with "Could not convert to OmniQuery"
on every documents get / documents-export / UI render, even though
`omni query run` resolves fine (runtime infers the topic from the view; the
document-load conversion path does not).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

try:
    import yaml as _yaml
except ImportError:
    sys.exit("PyYAML required.  pip3 install pyyaml")


def new_uuid() -> str:
    return str(uuid.uuid4())


def new_mini() -> str:
    """Omni's miniUuid is an 8-char ID."""
    return uuid.uuid4().hex[:8].upper()


def normalize_sorts(sorts: list) -> list:
    """Convert author-friendly sort shape to the server-required shape.

    Tile authors write either `{field, direction}` (Tableau-style, also what
    the v1 documents-get endpoint returns) or `{column_name, sort_descending}`
    (what the Omni runtime ModelQueryJobRequest deserializer requires).

    The runtime multi-job batch fails all-or-nothing when ANY sort uses the
    wrong shape, even on tiles without sorts. Symptom: every tile renders as
    an empty placeholder. Error class: `Sort["column_name"]` deserialization
    failure on `ModelQueryJobRequest["sorts"]`.

    This normalizer guarantees the persisted queryJson uses the runtime
    schema regardless of which shape the tile-spec author used.
    """
    out = []
    for s in sorts or []:
        if not isinstance(s, dict):
            out.append(s)
            continue
        col = s.get("column_name") or s.get("field")
        if "sort_descending" in s:
            desc = bool(s["sort_descending"])
        else:
            desc = (s.get("direction", "asc") or "asc").lower().startswith("desc")
        if col is None:
            # Keep the unknown shape so the failure is loud, not silent.
            out.append(s)
            continue
        out.append({"column_name": col, "sort_descending": desc})
    return out


def build_query_json(tile_spec: dict, model_id: str, table: str, topic: str) -> dict:
    """Build the queryJson for a single tile.

    Critical: `join_paths_from_topic_name` MUST be set. Without it, the saved
    queries on the dashboard fail to convert at document-load time and every
    `documents get` / `documents-export` / UI render returns 500
    "Could not convert to OmniQuery", even though `omni query run` resolves
    fine. Runtime infers the topic from the view; document-load conversion
    does not.

    Critical: `sorts` MUST use `{column_name, sort_descending}`. The v1
    documents-get endpoint reports sorts as `{field, direction}` but the
    runtime ModelQueryJobRequest deserializer rejects that shape. See
    `normalize_sorts`.

    Match the field set of a known-working Omni dashboard's queryJson:
    include `userEditedSQL` and `dimensionIndex`; do NOT include
    `controls`, `manualSort`, `context_metadata`, `query_references` (those
    fields are produced by other Omni surfaces, not the dashboard load path,
    and including them caused conversion to fail in our migration tests).
    """
    return {
        "limit": tile_spec.get("limit", 5000),
        "sorts": normalize_sorts(tile_spec.get("sorts", [])),
        "table": table,
        "fields": tile_spec["fields"],
        "pivots": [],
        "dbtMode": False,
        "filters": tile_spec.get("filters", {}),
        "modelId": model_id,
        "version": 8,
        "rewriteSql": True,
        "row_totals": {},
        "fill_fields": tile_spec.get("fill_fields", []),
        "calculations": tile_spec.get("calculations", []),
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


def build_vis_config(tile_spec: dict) -> dict:
    """Build visConfig.  Defaults to a sensible bar/line based on tile_spec.

    Orientation:
        Tile authors set `orientation: horizontal` for charts where the
        Tableau worksheet has a dimension on `<rows>` and a measure on
        `<cols>` (the classic "bars grow rightward" layout). When
        horizontal, x and y are swapped: the dimension becomes the
        Y-axis category, the measure series renders along X, and
        `_dependentAxis` switches to "x".

    Color:
        `color` can be either a string (legacy: field name) or a dict
        with `{dimension, palette}`. The dict form lands as
        `spec.color.field.name = dimension`. Palette is currently
        decorative; Omni picks the default categorical palette unless
        an explicit theme is wired.
    """
    vis_type = tile_spec.get("visType", "basic")
    chart_type = tile_spec.get("chartType", "bar")
    orientation = (tile_spec.get("orientation") or "vertical").lower()
    horizontal = orientation == "horizontal"
    x_field = tile_spec.get("x")
    y_fields = tile_spec.get("y", [])
    color = tile_spec.get("color")

    spec: dict = {"configType": "cartesian"}
    if vis_type == "omni-spreadsheet":
        return {
            "id": new_uuid(),
            "visType": "omni-spreadsheet",
            "spec": {},
            "fields": tile_spec["fields"],
            "version": 0,
        }

    # Build the two axes. For vertical (default): dim on x, measure series on y.
    # For horizontal: measure series on x, dim on y.
    if horizontal:
        spec["x"] = {}
        if x_field:
            spec["y"] = {"field": {"name": x_field}}
        else:
            spec["y"] = {}
        spec["series"] = [{"field": {"name": f}, "xAxis": "x"} for f in y_fields]
        spec["_dependentAxis"] = "x"
    else:
        if x_field:
            spec["x"] = {"field": {"name": x_field}}
        spec["y"] = {}
        spec["series"] = [{"field": {"name": f}, "yAxis": "y"} for f in y_fields]
        spec["_dependentAxis"] = "y"

    spec["y2"] = {}
    spec["mark"] = {"type": chart_mark(chart_type)}

    # Color: accept a bare field name (legacy) or {dimension, palette, values}.
    # `palette` is an ordered list of hex codes; `values` (optional) is the
    # ordered list of dimension values used to build an explicit value->color
    # map.
    #
    # KNOWN GOTCHA: Omni's organization-default color palette
    # OVERRIDES the visConfig palette keys when categorical color encoding
    # is used with `automaticVis: true`. Observed during trials: the
    # dashboard rendered with the org default even though scale.range,
    # colors, colorMap, valueColors were all populated. To get the
    # workbook palette through, one of the following must happen:
    #   1. The org default palette must be unset (org-admin action), OR
    #   2. The dashboard must use `visType: vegalite` (escape hatch, no
    #      drill capability), OR
    #   3. The visConfig must explicitly disable the org default (path
    #      currently undocumented in the Omni API).
    # We continue to write every plausible key so that as soon as the
    # override path is resolved, the existing visConfigs carry the right
    # palette without a redeploy.
    if isinstance(color, dict):
        dim = color.get("dimension") or color.get("field")
        palette = color.get("palette") or []
        values = color.get("values") or []
        if dim:
            spec["color"] = {"field": {"name": dim}}
            if palette:
                spec["color"]["scale"] = {"range": list(palette)}
                spec["color"]["colors"] = list(palette)
                spec["colors"] = list(palette)
                if values:
                    # value -> color map. Each documented Omni shape we have
                    # seen for category-color uses some flavor of this.
                    color_map = {v: palette[i % len(palette)] for i, v in enumerate(values)}
                    spec["color"]["colorMap"] = color_map
                    spec["color"]["valueColors"] = color_map
                    spec["color"]["scale"]["domain"] = list(values)
        if palette:
            for idx, s in enumerate(spec.get("series") or []):
                s.setdefault("mark", {})["_mark_color"] = palette[idx % len(palette)]
    elif isinstance(color, str):
        spec["color"] = {"field": {"name": color}}

    return {
        "id": new_uuid(),
        "visType": vis_type,
        "chartType": chart_type,
        "spec": spec,
        "fields": tile_spec["fields"],
        "version": 0,
    }


def chart_mark(chart_type: str) -> str:
    return {
        "bar": "bar",
        "stackedBar": "bar",
        "line": "line",
        "lineColor": "line",
        "area": "area",
        "scatter": "point",
    }.get(chart_type, "bar")


def build_query_presentation(tile_spec: dict, model_id: str, table: str, topic: str) -> dict:
    qid = new_uuid()
    vc = build_vis_config(tile_spec)
    qj = build_query_json(tile_spec, model_id, table, topic)
    return {
        "id": new_uuid(),
        "type": "query",
        "name": tile_spec["name"],
        "subTitle": tile_spec.get("subtitle", ""),
        "description": tile_spec.get("description", ""),
        "queryId": qid,
        "miniUuid": new_mini(),
        "modelId": model_id,
        "fileUploadId": None,
        "prefersChart": tile_spec.get("visType", "basic") != "omni-spreadsheet",
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
            "visColumnDisplay": "hide",
        },
        "aiConfig": {},
        "query": {
            "id": qid,
            "modelId": model_id,
            "queryJson": qj,
        },
        "visConfig": vc,
    }


def build_layout(tile_specs: list[dict]) -> dict:
    """Build a 24-col grid layout placing tiles in a 2-col flow.

    Per-tile `pos` accepts either Omni-native keys `{x, y, w, h}` or the
    friendlier alias `{col, row, w, h}` (matching `zones_to_grid.py` output).
    When a `pos` is supplied, BOTH coordinates and dimensions land in the
    layout AND the cursor advances past it so the next tile without `pos`
    flows correctly.

    Earlier behavior: a tile with `pos: {row, col}` got `pos.x = cur_x` /
    `pos.y = cur_y` (alias not recognized) AND the cursor didn't advance
    (the `pos == {}` guard kept it pinned at 0,0). Result: every tile
    collapsed onto the same grid cell.
    """
    layouts = {"lg": [], "sm": []}
    cols = 24
    default_w = 12
    default_h = 15  # matches Omni's working-template tile height
    cur_x = 0
    cur_y = 0
    for i, spec in enumerate(tile_specs, start=1):
        pos = spec.get("pos") or {}
        # Accept row/col aliases for y/x.
        pos_x = pos.get("x") if "x" in pos else pos.get("col")
        pos_y = pos.get("y") if "y" in pos else pos.get("row")
        w = pos.get("w", default_w)
        h = pos.get("h", default_h)
        if pos_x is None:
            pos_x = cur_x
            pos_y = cur_y if pos_y is None else pos_y
            if cur_x + w > cols:
                cur_x = 0
                cur_y += default_h
                pos_x, pos_y = cur_x, cur_y
            # auto-flow: advance cursor by tile width, wrap if needed
            cur_x += w
            if cur_x >= cols:
                cur_x = 0
                cur_y += h
        else:
            # explicit pos: respect it and bump the cursor past it so a
            # later tile without pos doesn't collide
            if pos_y is None:
                pos_y = cur_y
            cur_x = max(cur_x, pos_x + w)
            cur_y = max(cur_y, pos_y)
            if cur_x >= cols:
                cur_x = 0
                cur_y = pos_y + h
        layouts["lg"].append({"i": str(i), "w": w, "h": h, "x": pos_x, "y": pos_y, "moved": False, "static": False})
        layouts["sm"].append({"i": str(i), "w": 1, "h": h * 2, "x": 0, "y": (i - 1) * default_h * 2, "moved": False, "static": False})
    return layouts


def resolve_dashboard_name(
    explicit: str | None,
    name_prefix: str,
    tile_yaml: dict,
    ir_dir: Path | None,
) -> str:
    """Decide the Omni document/dashboard name, in order of precedence.

    1. --dashboard-name passed explicitly on the command line.
    2. tile-spec.yaml top-level `dashboard_name`.
    3. The first `dashboards[].name` in the tile-spec (emitted by
       generate_tile_spec.py from the IR).
    4. The first `dashboards[].name` in <ir_dir>/dashboards.json (extract.py output).

    Result is prefixed with --name-prefix (defaults to "") so callers can opt
    into a "Migrated: " or "[Tableau]" tag without losing the source name.

    Fails loud if no name can be resolved. The Tableau dashboard name is the
    user-visible artifact, so falling back to a generic stub would be wrong.
    """
    if explicit:
        return f"{name_prefix}{explicit}"

    spec_name = tile_yaml.get("dashboard_name")
    if spec_name:
        return f"{name_prefix}{spec_name}"

    spec_dashboards = tile_yaml.get("dashboards") or []
    for entry in spec_dashboards:
        if isinstance(entry, dict) and entry.get("name"):
            return f"{name_prefix}{entry['name']}"

    if ir_dir is not None:
        ir_dash = ir_dir / "dashboards.json"
        if ir_dash.exists():
            try:
                data = json.loads(ir_dash.read_text())
            except json.JSONDecodeError as exc:
                sys.exit(f"--ir-dir/dashboards.json is not valid JSON: {exc}")
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict) and entry.get("name"):
                        return f"{name_prefix}{entry['name']}"

    sys.exit(
        "Could not resolve dashboard name. Pass --dashboard-name, set "
        "`dashboard_name` (or a `dashboards[].name`) in the tile-spec, or "
        "pass --ir-dir pointing at an extract.py output directory."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dashboard-name",
        default=None,
        help=(
            "Display name for the migrated dashboard. Optional: if omitted, "
            "the name is taken from the Tableau workbook (via tile-spec or "
            "--ir-dir/dashboards.json). Pass an explicit value here to override."
        ),
    )
    ap.add_argument(
        "--name-prefix",
        default="",
        help=(
            "String to prepend to the resolved dashboard name (e.g. "
            "\"Migrated: \"). Default is empty: the Omni document name is "
            "identical to the Tableau dashboard name."
        ),
    )
    ap.add_argument(
        "--ir-dir",
        type=Path,
        default=None,
        help="Optional extract.py output dir; used to default --dashboard-name from dashboards.json.",
    )
    ap.add_argument("--topic", required=True, help="Omni topic name (e.g. acme_events). Goes into queryJson.join_paths_from_topic_name and queryPresentation.topicName.")
    ap.add_argument("--view", required=True, help="Omni view name backing the topic (e.g. vw_events_wide). Goes into queryJson.table and field prefixes.")
    ap.add_argument("--base-model-id", required=True, help="Branch model ID where the dashboard lands")
    ap.add_argument("--connection-id", required=True, help="Omni connection ID")
    ap.add_argument("--shared-model-id", required=True, help="Parent SHARED model ID of the branch")
    ap.add_argument("--template", type=Path, required=True, help="Path to a working Omni dashboard export JSON to use as structural template")
    ap.add_argument("--tile-spec", type=Path, required=True, help="YAML defining the tile mapping (one entry per worksheet)")
    ap.add_argument("--out", type=Path, required=True, help="Output payload JSON path")
    ap.add_argument("--branch-name", default=None,
                    help="Optional human-readable branch name; if set, the script prints the "
                         "branch-scoped test URL pattern after generation")
    args = ap.parse_args()

    template = json.loads(args.template.read_text())
    tile_yaml = _yaml.safe_load(args.tile_spec.read_text())
    tiles = tile_yaml["tiles"]

    resolved_name = resolve_dashboard_name(
        args.dashboard_name, args.name_prefix, tile_yaml, args.ir_dir,
    )
    args.dashboard_name = resolved_name

    # Build queryPresentations from tile specs.
    qpc_memberships = []
    for spec in tiles:
        qp = build_query_presentation(spec, args.base_model_id, args.view, args.topic)
        qpc_memberships.append({"queryPresentation": qp})

    # Mutate the template to be our payload.
    payload = template

    # Document
    doc = payload["document"]
    doc["name"] = args.dashboard_name
    doc["connectionId"] = args.connection_id
    doc["modelId"] = args.base_model_id
    doc["sharedModelId"] = args.shared_model_id
    doc["workbookId"] = args.base_model_id
    doc["dashboardId"] = new_uuid()
    doc["identifier"] = None  # let server assign
    doc["stableDocumentId"] = new_uuid()
    doc["documentId"] = new_uuid()
    doc["folder"] = None
    if "baseModel" in doc and isinstance(doc["baseModel"], dict):
        doc["baseModel"]["baseModelId"] = args.shared_model_id
    # `ephemeral` maps layout tile ids (1, 2, ...) to qpcM miniUuids.
    # Format: "1:miniUuid1,2:miniUuid2,..."
    doc["ephemeral"] = ",".join(
        f"{i + 1}:{qpcm['queryPresentation']['miniUuid']}"
        for i, qpcm in enumerate(qpc_memberships)
    )

    # Dashboard
    dash = payload["dashboard"]
    dash["id"] = doc["dashboardId"]
    dash["name"] = args.dashboard_name
    dash["queryPresentationCollection"] = {
        "id": new_uuid(),
        "filterConfig": {},
        "filterConfigVersion": 1,
        "filterOrder": [],
        "queryPresentationCollectionMemberships": qpc_memberships,
    }
    dash["facetFilters"] = False
    dash["metadata"] = {
        "layouts": build_layout(tiles),
        "textTiles": [],
        "hiddenTiles": [],
        "tileSettings": {str(i): {"hideBorder": False} for i in range(1, len(tiles) + 1)},
        "tileFilterMap": {str(i): {} for i in range(1, len(tiles) + 1)},
        "tileControlMap": {},
    }
    dash["metadataVersion"] = 2

    # workbookModel: the WORKBOOK Omni creates for the imported document.  It must
    # base on the BRANCH model so it inherits our migrated views and topics, NOT
    # on the shared model directly (that doesn't have the migrated topic yet).
    payload["workbookModel"] = {
        "id": args.base_model_id,
        "connection_id": args.connection_id,
        "base_model_id": args.base_model_id,
        "model_kind": "WORKBOOK",
        "views": [],
        "topics": [],
        "relationships": [],
        "ignored_schemas": [],
        "ignored_views": [],
        "all_schema_names": [],
        "virtualized_schemas": [],
        "deleted_topics": [],
        "dbt_virtualization_enabled": False,
    }

    # queryModels: build per-tile entries keyed by query id
    payload["queryModels"] = {}
    for qpcm in qpc_memberships:
        qp = qpcm["queryPresentation"]
        qid = qp["query"]["id"]
        payload["queryModels"][qid] = {
            "id": qid,
            "modelId": args.base_model_id,
            "queryJson": qp["query"]["queryJson"],
        }

    # exportVersion stays "0.1"
    payload["exportVersion"] = "0.1"
    payload["fileUploads"] = {}
    # baseModelId at the top level must be a SHARED or SHARED_EXTENSION model
    # (the import API rejects branches here).  We pair this with
    # workbookModel.base_model_id = branch so the new workbook extends the branch
    # and inherits its migrated views/topics.
    payload["baseModelId"] = args.shared_model_id

    args.out.write_text(json.dumps(payload, indent=2, default=str))
    print(f"wrote payload: {args.out} ({len(json.dumps(payload))} chars, {len(tiles)} tiles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
