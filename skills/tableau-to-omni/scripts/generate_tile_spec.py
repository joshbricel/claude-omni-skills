"""Auto tile-spec generator for the Tableau-to-Omni emitter.

Consumes the sibling rules engine's ``decisions.json`` plus the IR JSONs from
``extract.py`` and emits a ``tile-spec.yaml`` that ``build_payload.py`` can eat,
along with a migration report markdown listing what was emitted, flagged for
review, or dropped.

Usage:
    python3 generate_tile_spec.py \
        --decisions decisions.json \
        --ir-dir /path/to/extract-output \
        --out tile-spec.yaml \
        --report migration-report.md \
        [--dry-run] \
        [--strict]

The script switches on ``decisions[].strategy_effective`` to dispatch each
Tableau concept to an emitter function. Decisions are grouped by dashboard
(via the IR's ``dashboards.json`` zone tree). RED-bucket items go into
``omitted[]``, GREY into ``unresolved[]``, YELLOW into ``review_queue[]``,
GREEN into ``tiles[]`` with ``needs_review: false``.

============================================================================
BUILD_PAYLOAD CONTRACT ASSUMED
============================================================================
Source of truth: ``build_payload.py`` in the sister worktree at
skills/tableau-to-omni/scripts/build_payload.py.

build_payload.py reads ``yaml.safe_load(args.tile_spec)["tiles"]``. Each
tile entry is a flat dict with the following keys it consumes:

    name            (required) display name -> queryPresentation.name
    subtitle        optional   -> queryPresentation.subTitle
    description     optional   -> queryPresentation.description
    visType         optional   default "basic"; "omni-spreadsheet" routes to table
    chartType       optional   default "bar"; mapped to mark via chart_mark()
    fields          (required) list[str] field names for queryJson + visConfig
    x               optional   x-axis field name (cartesian only)
    y               optional   list[str] y-series field names
    color           optional   color-encoding field name
    limit           optional   default 5000
    sorts           optional   list[dict]
    filters         optional   dict
    fill_fields     optional   list
    calculations    optional   list
    pos             optional   dict {x, y, w, h} for explicit grid placement

build_payload.py supports any tile kind that resolves to these primitives.
The project memory notes documented kinds: kpi_strip, bar, line, area,
scatter, dual_bar, gender_callout, markdown. Of these, only chart-shaped
ones round-trip through build_payload's visConfig builder. We therefore
emit a SUPERSET tile spec: build_payload's keys live at the top level of
each tile, plus we attach sidecar metadata (``id``, ``kind``, ``title``,
``source_worksheet``, ``query``, ``viz``, ``layout``, ``provenance``,
``needs_review``, ``warnings``) that build_payload ignores but downstream
review tooling consumes.

Additional sidecar collections at the top level (``review_queue``,
``omitted``, ``unresolved``, ``dashboards``) are also ignored by
build_payload but read by the migration report generator. build_payload
only reads ``tiles``; we publish both ``tiles`` (flat list, what
build_payload eats) and ``dashboards`` (grouped, what humans read).
============================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import yaml as _yaml
except ImportError:
    sys.exit("PyYAML required.  pip3 install pyyaml")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DECISIONS_VERSION = "1.0"

BUCKETS = {"GREEN", "YELLOW", "RED", "GREY"}

# Default grid (matches build_payload.build_layout)
GRID_COLS = 24
DEFAULT_TILE_W = 12
DEFAULT_TILE_H = 30


# ---------------------------------------------------------------------------
# IR loading
# ---------------------------------------------------------------------------

IR_FILES = {
    "worksheets": "worksheets.json",
    "dashboards": "dashboards.json",
    "calcs": "calcs.json",
    "palettes": "palettes.json",
    "parameters": "parameters.json",
    "actions": "actions.json",
}


def load_ir(ir_dir: Path) -> dict[str, Any]:
    """Load the IR JSONs that ``extract.py`` produces. Missing files default
    to empty lists so downstream code does not need to None-check."""
    ir: dict[str, Any] = {}
    for key, fname in IR_FILES.items():
        path = ir_dir / fname
        if path.exists():
            ir[key] = json.loads(path.read_text())
        else:
            ir[key] = []
    return ir


def load_decisions(path: Path) -> dict[str, Any]:
    """Load and version-check the decisions JSON produced by apply_rules.py."""
    payload = json.loads(path.read_text())
    version = payload.get("version")
    if version != DECISIONS_VERSION:
        raise ValueError(
            f"decisions.json version {version!r} does not match expected "
            f"{DECISIONS_VERSION!r}"
        )
    if "decisions" not in payload:
        raise ValueError("decisions.json missing required key 'decisions'")
    return payload


# ---------------------------------------------------------------------------
# Worksheet lookup + dashboard grouping
# ---------------------------------------------------------------------------

def index_worksheets(ir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build name -> worksheet IR dict for fast lookup."""
    return {ws.get("name"): ws for ws in ir.get("worksheets", []) if ws.get("name")}


def collect_worksheet_refs_from_zones(zones: list[dict]) -> list[str]:
    """Walk a dashboard zone tree and return worksheet names referenced by
    leaf zones. The IR stores worksheet refs under ``worksheet_ref`` (computed
    in extract.py's parse_dashboards walker)."""
    out: list[str] = []

    def walk(zone: dict) -> None:
        ws_ref = zone.get("worksheet_ref") or zone.get("worksheet")
        if ws_ref:
            out.append(ws_ref)
        for child in zone.get("children") or []:
            walk(child)

    for z in zones or []:
        walk(z)
    return out


def index_dashboards(ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Return list of dashboards with member worksheet names attached."""
    out: list[dict[str, Any]] = []
    for d in ir.get("dashboards", []):
        members = collect_worksheet_refs_from_zones(d.get("zones") or [])
        out.append({
            "name": d.get("name"),
            "title": d.get("title"),
            "size": d.get("size"),
            "zones": d.get("zones") or [],
            "members": members,
        })
    return out


# ---------------------------------------------------------------------------
# Decision typing
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    instance_id: str
    tableau_input: dict[str, Any]
    rule_id: str
    bucket: str
    strategy: str
    emission_target: dict[str, Any]
    needs_review: bool
    omitted: bool
    warnings: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Decision":
        return cls(
            instance_id=d.get("instance_id", ""),
            tableau_input=d.get("tableau_input") or {},
            rule_id=d.get("rule_id", ""),
            bucket=d.get("bucket", "GREY"),
            strategy=d.get("strategy_effective", "manual_review"),
            emission_target=d.get("emission_target") or {},
            needs_review=bool(d.get("needs_review", False)),
            omitted=bool(d.get("omitted", False)),
            warnings=list(d.get("warnings") or []),
            notes=d.get("notes", "") or "",
        )

    @property
    def concept_kind(self) -> str:
        return self.tableau_input.get("concept_kind", "")

    @property
    def name(self) -> str:
        return self.tableau_input.get("name", "")


# ---------------------------------------------------------------------------
# Tile emitters: strategy dispatch
# ---------------------------------------------------------------------------

EmitterCtx = dict[str, Any]  # holds worksheet IR + palettes + counters
Emitter = Callable[[Decision, EmitterCtx], Optional[dict[str, Any]]]


def _worksheet_for(decision: Decision, ctx: EmitterCtx) -> dict[str, Any]:
    """Best-effort lookup of the worksheet IR row backing this decision."""
    ws_index: dict[str, dict[str, Any]] = ctx["ws_index"]
    name = decision.name
    return ws_index.get(name, {})


def _field_names_from_worksheet(ws: dict[str, Any]) -> list[str]:
    """Extract a deterministic list of field names from a worksheet's
    field_refs. Falls back to captions when name is missing."""
    out: list[str] = []
    seen: set[str] = set()
    for ref in ws.get("field_refs", []) or []:
        nm = ref.get("name") or ref.get("caption") or ""
        # Strip Tableau's [bracketed] wrappers for Omni field names.
        nm = nm.strip().strip("[]")
        if nm and nm not in seen:
            seen.add(nm)
            out.append(nm)
    return out


def _chart_kind_from_marks(ws: dict[str, Any]) -> str:
    """Map a Tableau worksheet's mark type to an Omni chart kind."""
    marks = ws.get("marks") or []
    if not marks:
        return "bar"
    mt = (marks[0].get("class") or marks[0].get("type") or "").lower()
    return {
        "bar": "bar",
        "line": "line",
        "area": "area",
        "circle": "scatter",
        "shape": "scatter",
        "square": "scatter",
        "polygon": "scatter",
        "map": "scatter",
        "text": "kpi_strip",
        "automatic": "bar",
    }.get(mt, "bar")


def _next_tile_id(ctx: EmitterCtx) -> str:
    ctx["tile_counter"] = ctx.get("tile_counter", 0) + 1
    return f"tile_{ctx['tile_counter']:03d}"


def _base_tile(
    decision: Decision,
    ctx: EmitterCtx,
    *,
    kind: str,
    needs_review: bool = False,
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Construct the common tile skeleton shared by every emitter.

    This skeleton holds both build_payload.py's flat keys (name, fields,
    visType, chartType, x, y, color, pos) and the sidecar metadata
    (id, kind, title, source_worksheet, query, viz, layout, provenance).
    """
    ws = _worksheet_for(decision, ctx)
    fields = _field_names_from_worksheet(ws)
    if not fields and decision.name:
        # Calculated-field decisions: include the calc name as a field so the
        # tile is still inspectable even if no worksheet was captured.
        fields = [decision.name]
    x_field = fields[0] if fields else None
    y_fields = fields[1:] if len(fields) > 1 else []
    tile_id = _next_tile_id(ctx)
    title = decision.name or decision.instance_id

    tile: dict[str, Any] = {
        # --- build_payload.py keys (flat, top-level) ---
        "name": title,
        "fields": fields,
        "visType": "basic",
        "chartType": kind if kind in {"bar", "line", "area", "scatter"} else "bar",
        "x": x_field,
        "y": y_fields,
        # --- sidecar metadata (build_payload ignores these) ---
        "id": tile_id,
        "kind": kind,
        "title": title,
        "source_worksheet": decision.name,
        "query": {
            "fields": fields,
            "sort": [],
            "limit": 5000,
        },
        "viz": {
            "color": None,
            "axes": {"x": {"scale": "linear"}, "y": {"fixed_range": None}},
        },
        "layout": _layout_for(decision, ctx),
        "provenance": {
            "rule_ids": [decision.rule_id],
            "buckets": [decision.bucket],
            "decisions": [decision.instance_id],
            "strategy": decision.strategy,
        },
        "needs_review": bool(needs_review),
        "warnings": list(warnings or decision.warnings),
    }
    return tile


def _layout_for(decision: Decision, ctx: EmitterCtx) -> dict[str, int]:
    """Return a 24-col grid position for the tile, advancing the cursor in
    ctx. Honors floating zones via the floating-snap strategy when active."""
    cursor = ctx.setdefault("cursor", {"row": 0, "col": 0})
    w = DEFAULT_TILE_W
    h = DEFAULT_TILE_H
    if cursor["col"] + w > GRID_COLS:
        cursor["col"] = 0
        cursor["row"] += h
    pos = {"row": cursor["row"], "col": cursor["col"], "w": w, "h": h}
    cursor["col"] += w
    return pos


# --- GREEN emitters ----------------------------------------------------------

def emit_bar_or_chart(decision: Decision, ctx: EmitterCtx) -> dict[str, Any]:
    """Standard cartesian chart emission. Inspects the worksheet mark type
    to pick bar / line / area / scatter."""
    ws = _worksheet_for(decision, ctx)
    kind = _chart_kind_from_marks(ws)
    return _base_tile(decision, ctx, kind=kind)


def emit_model_layer_measure(decision: Decision, ctx: EmitterCtx) -> None:
    """Calc fields routed to model-layer measures are NOT tiles. They are
    schema-side artifacts emitted by a different writer. Return None so the
    main loop skips appending to tiles[]."""
    return None


def emit_model_layer_dimension(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_snowflake_view(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_precompute_upstream(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_derived_table_cte(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_alias_remap(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_set_dimension_flag(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_bin_native(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_hierarchy_drill_fields(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_palette_theme(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_palette_inline(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_tooltip_omni_native(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_omni_filter(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_omni_control(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_action_filter_native(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_action_url(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_action_navigation(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_format_string_passthrough(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_case_when_dimension(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_dashboard_zone_grid(decision: Decision, ctx: EmitterCtx) -> None:
    """Layout-only decision; consumed implicitly via _layout_for."""
    return None


# --- YELLOW emitters --------------------------------------------------------

def emit_workbook_tile_calc(decision: Decision, ctx: EmitterCtx) -> dict[str, Any]:
    """Calc that did not qualify for the model layer. Emits a tile with the
    calc name in fields, flagged for review."""
    warnings = list(decision.warnings) + [
        "Workbook-tile calc: verify Omni-side calculation correctness."
    ]
    return _base_tile(decision, ctx, kind="bar", needs_review=True, warnings=warnings)


def emit_vega_lite_layered(decision: Decision, ctx: EmitterCtx) -> dict[str, Any]:
    """Dual-axis or otherwise layered viz. Emits a placeholder tile that
    must be replaced with a tuned Vega-Lite spec."""
    warnings = list(decision.warnings) + [
        "Layered Vega-Lite spec emitted as placeholder; tune axes and marks."
    ]
    tile = _base_tile(decision, ctx, kind="bar", needs_review=True, warnings=warnings)
    tile["visType"] = "vega-lite-layered"
    tile["kind"] = "vega_lite_layered"
    return tile


def emit_vega_lite_escape(decision: Decision, ctx: EmitterCtx) -> dict[str, Any]:
    warnings = list(decision.warnings) + [
        "Vega-Lite escape hatch: verify spec renders against Omni's runtime."
    ]
    tile = _base_tile(decision, ctx, kind="bar", needs_review=True, warnings=warnings)
    tile["visType"] = "vega-lite"
    tile["kind"] = "vega_lite_escape"
    return tile


def emit_tile_passthrough(decision: Decision, ctx: EmitterCtx) -> dict[str, Any]:
    """Generic worksheet -> tile passthrough with review flag (unrecognized
    viz that we are best-effort emitting as a bar)."""
    warnings = list(decision.warnings) + [
        "Passthrough emission; verify field mapping and viz config."
    ]
    return _base_tile(decision, ctx, kind="bar", needs_review=True, warnings=warnings)


def emit_format_string_best_effort(decision: Decision, ctx: EmitterCtx) -> None:
    return None


def emit_dashboard_zone_floating_snap(decision: Decision, ctx: EmitterCtx) -> dict[str, Any]:
    """Floating Tableau zone snapped to the nearest grid cell. The tile
    itself is whatever worksheet sat inside the floating zone; we flag for
    review since the snap is heuristic."""
    warnings = list(decision.warnings) + [
        "Floating zone snapped to grid; verify position and overlap."
    ]
    ws = _worksheet_for(decision, ctx)
    kind = _chart_kind_from_marks(ws)
    return _base_tile(decision, ctx, kind=kind, needs_review=True, warnings=warnings)


# --- RED emitters: append to omitted[] --------------------------------------

RED_STRATEGIES = {
    "drop_with_warning",
    "omit_silent",
    "tooltip_drop",
    "action_drop",
    "story_separate_dashboards",
}


# --- GREY emitters: append to unresolved[] ----------------------------------

GREY_STRATEGIES = {"manual_review"}


# --- Dispatch table ---------------------------------------------------------

STRATEGY_DISPATCH: dict[str, Emitter] = {
    # GREEN
    "model_layer_measure": emit_model_layer_measure,
    "model_layer_dimension": emit_model_layer_dimension,
    "snowflake_view": emit_snowflake_view,
    "precompute_upstream": emit_precompute_upstream,
    "derived_table_cte": emit_derived_table_cte,
    "alias_remap": emit_alias_remap,
    "set_dimension_flag": emit_set_dimension_flag,
    "bin_native": emit_bin_native,
    "hierarchy_drill_fields": emit_hierarchy_drill_fields,
    "palette_theme": emit_palette_theme,
    "palette_inline": emit_palette_inline,
    "tooltip_omni_native": emit_tooltip_omni_native,
    "omni_filter": emit_omni_filter,
    "omni_control": emit_omni_control,
    "action_filter_native": emit_action_filter_native,
    "action_url": emit_action_url,
    "action_navigation": emit_action_navigation,
    "format_string_passthrough": emit_format_string_passthrough,
    "case_when_dimension": emit_case_when_dimension,
    "dashboard_zone_grid": emit_dashboard_zone_grid,
    # GREEN viz emitters (these DO produce tiles)
    "tile_passthrough": emit_tile_passthrough,
    # YELLOW
    "workbook_tile_calc": emit_workbook_tile_calc,
    "vega_lite_layered": emit_vega_lite_layered,
    "vega_lite_escape": emit_vega_lite_escape,
    "format_string_best_effort": emit_format_string_best_effort,
    "dashboard_zone_floating_snap": emit_dashboard_zone_floating_snap,
}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_decisions(
    decisions: list[Decision],
    ir: dict[str, Any],
) -> dict[str, Any]:
    """Walk decisions and split them into tiles / review_queue / omitted /
    unresolved. Returns the assembled tile-spec dict."""
    ws_index = index_worksheets(ir)
    dashboards = index_dashboards(ir)

    ctx: EmitterCtx = {
        "ws_index": ws_index,
        "palettes": ir.get("palettes", []),
        "tile_counter": 0,
        "cursor": {"row": 0, "col": 0},
    }

    tiles: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    # Map each worksheet name -> list of decisions touching it. This is how
    # we group decisions into dashboards in the report layer.
    ws_to_decisions: dict[str, list[Decision]] = {}

    for d in decisions:
        # RED strategies always omit, regardless of bucket label.
        if d.strategy in RED_STRATEGIES or d.bucket == "RED" or d.omitted:
            omitted.append({
                "tableau_concept": d.name or d.concept_kind or d.instance_id,
                "rule_id": d.rule_id,
                "bucket": d.bucket,
                "strategy": d.strategy,
                "reason": d.notes or "Dropped by rules engine.",
                "user_action": _user_action_for(d),
            })
            continue

        # GREY strategies route to unresolved.
        if d.strategy in GREY_STRATEGIES or d.bucket == "GREY":
            unresolved.append({
                "tableau_concept": d.name or d.concept_kind or d.instance_id,
                "rule_id": d.rule_id,
                "bucket": d.bucket,
                "strategy": d.strategy,
                "resolution_plan": d.notes or "Manual investigation required.",
            })
            continue

        emitter = STRATEGY_DISPATCH.get(d.strategy)
        if emitter is None:
            # Unknown strategy: treat as unresolved so we never silently lose it.
            unresolved.append({
                "tableau_concept": d.name or d.concept_kind or d.instance_id,
                "rule_id": d.rule_id,
                "bucket": d.bucket,
                "strategy": d.strategy,
                "resolution_plan": (
                    f"Unknown strategy {d.strategy!r}; extend STRATEGY_DISPATCH "
                    f"in generate_tile_spec.py."
                ),
            })
            continue

        tile = emitter(d, ctx)
        if tile is None:
            # Emitter chose not to produce a tile (e.g., model-layer measure).
            continue

        tiles.append(tile)
        ws_name = d.name
        ws_to_decisions.setdefault(ws_name, []).append(d)

        if tile.get("needs_review"):
            review_queue.append({
                "tile_id": tile["id"],
                "reason": (tile["warnings"][0] if tile["warnings"]
                           else "Needs review flag set by emitter."),
                "rule_id": d.rule_id,
                "bucket": d.bucket,
                "strategy": d.strategy,
            })

    # Group tiles by dashboard. Tiles whose source worksheet does not belong
    # to any dashboard land in a synthetic "(orphan)" dashboard.
    dashboard_groups = _group_tiles_by_dashboard(tiles, dashboards)

    return {
        "tiles": tiles,                  # flat list build_payload.py consumes
        "dashboards": dashboard_groups,  # grouped view for humans + report
        "review_queue": review_queue,
        "omitted": omitted,
        "unresolved": unresolved,
    }


def _user_action_for(d: Decision) -> str:
    """Build a short user-actionable string for an omitted concept."""
    if d.strategy == "story_separate_dashboards":
        return "Recreate each story tab as a separate Omni dashboard."
    if d.strategy == "action_drop":
        return "Replace with an Omni cross-filter or accept loss."
    if d.strategy == "tooltip_drop":
        return "Inline the dropped tooltip viz into the parent tile, or accept loss."
    if d.strategy == "drop_with_warning":
        return f"Manually recreate {d.name!r} in Omni if needed."
    return d.notes or "Manual recreation if business-critical."


def _group_tiles_by_dashboard(
    tiles: list[dict[str, Any]],
    dashboards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Walk dashboards and pull out tiles whose source worksheet belongs
    to that dashboard's member list. Tiles not claimed by any dashboard
    land in a synthetic group at the end."""
    groups: list[dict[str, Any]] = []
    claimed_tile_ids: set[str] = set()
    for d in dashboards:
        member_set = set(d["members"])
        d_tiles = [
            t for t in tiles
            if t.get("source_worksheet") in member_set
        ]
        for t in d_tiles:
            claimed_tile_ids.add(t["id"])
        groups.append({
            "name": d["name"],
            "title": d.get("title"),
            "tiles": d_tiles,
        })
    orphans = [t for t in tiles if t["id"] not in claimed_tile_ids]
    if orphans:
        groups.append({"name": "(orphan)", "title": None, "tiles": orphans})
    return groups


# ---------------------------------------------------------------------------
# YAML + report writers
# ---------------------------------------------------------------------------

def dump_yaml(spec: dict[str, Any]) -> str:
    return _yaml.safe_dump(
        spec,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )


def build_report(spec: dict[str, Any], decisions_payload: dict[str, Any]) -> str:
    """Build a markdown migration report summarizing what landed where."""
    tiles = spec["tiles"]
    review_queue = spec["review_queue"]
    omitted = spec["omitted"]
    unresolved = spec["unresolved"]
    dashboards = spec["dashboards"]

    lines: list[str] = []
    lines.append("# Tableau-to-Omni Migration Report")
    lines.append("")
    lines.append("## TL;DR")
    lines.append("")
    lines.append(f"- Emitted tiles: {len(tiles)}")
    lines.append(f"- Needs review (YELLOW): {len(review_queue)}")
    lines.append(f"- Omitted (RED): {len(omitted)}")
    lines.append(f"- Unresolved (GREY): {len(unresolved)}")
    lines.append("")

    summary = decisions_payload.get("summary") or {}
    if summary:
        lines.append("## Upstream decisions summary")
        lines.append("")
        total = summary.get("total_instances", "?")
        lines.append(f"- Total Tableau instances seen: {total}")
        by_bucket = summary.get("by_bucket") or {}
        for bucket in ("GREEN", "YELLOW", "RED", "GREY"):
            if bucket in by_bucket:
                lines.append(f"- {bucket}: {by_bucket[bucket]}")
        lines.append("")

    lines.append("## Per-dashboard tile counts")
    lines.append("")
    lines.append("| Dashboard | Tiles | Needs review |")
    lines.append("|-----------|-------|--------------|")
    for d in dashboards:
        d_tiles = d["tiles"]
        d_review = sum(1 for t in d_tiles if t.get("needs_review"))
        lines.append(f"| {d['name']} | {len(d_tiles)} | {d_review} |")
    lines.append("")

    if review_queue:
        lines.append("## Review queue (YELLOW)")
        lines.append("")
        for r in review_queue:
            lines.append(
                f"- {r['tile_id']} ({r['rule_id']}, strategy {r['strategy']}): "
                f"{r['reason']}"
            )
        lines.append("")

    if omitted:
        lines.append("## Omitted (RED)")
        lines.append("")
        for o in omitted:
            lines.append(
                f"- {o['tableau_concept']} ({o['rule_id']}): {o['reason']} "
                f"Action: {o['user_action']}"
            )
        lines.append("")

    if unresolved:
        lines.append("## Unresolved (GREY)")
        lines.append("")
        for u in unresolved:
            lines.append(
                f"- {u['tableau_concept']} ({u['rule_id']}, strategy "
                f"{u['strategy']}): {u['resolution_plan']}"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate tile-spec.yaml from decisions.json + extract IR.",
    )
    ap.add_argument("--decisions", type=Path, required=True,
                    help="Path to decisions.json from apply_rules.py.")
    ap.add_argument("--ir-dir", type=Path, required=True,
                    help="Directory holding extract.py IR JSONs.")
    ap.add_argument("--out", type=Path, required=True,
                    help="Output tile-spec.yaml path.")
    ap.add_argument("--report", type=Path, required=True,
                    help="Output migration report markdown path.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Write outputs to stdout instead of files.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit nonzero if any RED-omitted or GREY-unresolved present.")
    args = ap.parse_args(argv)

    decisions_payload = load_decisions(args.decisions)
    decisions = [Decision.from_dict(d) for d in decisions_payload["decisions"]]
    ir = load_ir(args.ir_dir)

    spec = process_decisions(decisions, ir)
    yaml_text = dump_yaml(spec)
    report_text = build_report(spec, decisions_payload)

    if args.dry_run:
        print("=== tile-spec.yaml ===")
        print(yaml_text)
        print("=== migration-report.md ===")
        print(report_text)
    else:
        args.out.write_text(yaml_text)
        args.report.write_text(report_text)
        print(f"wrote tile-spec: {args.out}", file=sys.stderr)
        print(f"wrote report:    {args.report}", file=sys.stderr)

    if args.strict and (spec["omitted"] or spec["unresolved"]):
        print(
            f"strict mode: {len(spec['omitted'])} omitted, "
            f"{len(spec['unresolved'])} unresolved",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
