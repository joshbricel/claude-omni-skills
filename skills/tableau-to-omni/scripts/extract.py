"""Comprehensive Tableau .twbx XML mining.

Unpacks a .twbx, then extracts every dimension of the workbook into JSON files
suitable for downstream translation to Omni.

Outputs (all in --out dir):
    inventory.json        High-level counts and asset list.
    datasources.json      Connections, joins, custom SQL, columns, calc fields.
    calcs.json            Every calculated field with formula, LOD detection.
    parameters.json       Parameter definitions and value sets.
    parameter_deps.json   Map of parameter -> calc fields and sheets that reference it.
    worksheets.json       Per-worksheet mark, encodings, filters, datasource refs.
    dashboards.json       Per-dashboard zone tree (layout) and member sheets.
    actions.json          Action graph (filter, highlight, parameter, set, URL actions).
    styles.json           Fonts, colors, borders, number/date formats.
    palettes.json         Inline custom color palettes from <encodings>.
    hidden_sheets.json    Sheets used as tooltip/dashboard sources but not on tabs.
    annotations.json      Mark/area/point annotations with positioning.
    raw_columns.json      Source-column metadata records (with families).

Usage:
    python3 extract.py path/to/workbook.twbx --out ./extract
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

# Tableau XML uses single-quoted attributes and no namespaces in the .twb
# (the on-disk file format).  ElementTree handles both quote styles.

LOD_PATTERN = re.compile(r"\{\s*(FIXED|INCLUDE|EXCLUDE)\s+", re.IGNORECASE)
TABLE_CALC_KEYWORDS = (
    "WINDOW_", "RUNNING_", "INDEX(", "FIRST(", "LAST(",
    "RANK(", "TOTAL(", "LOOKUP(", "PREVIOUS_VALUE(", "SCRIPT_",
)


def unpack_twbx(twbx_path: Path, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(twbx_path, "r") as z:
        z.extractall(work_dir)
        twb_files = [n for n in z.namelist() if n.endswith(".twb")]
    if not twb_files:
        raise RuntimeError("No .twb file found inside the .twbx")
    return work_dir / twb_files[0]


def safe_attrib(elem: ET.Element, key: str, default: str | None = None) -> str | None:
    v = elem.attrib.get(key)
    return v if v is not None else default


def gather_inventory(twb_path: Path, work_dir: Path) -> dict:
    """High-level counts, asset list, and per-folder file inventory."""
    inv: dict = {
        "twb_file": twb_path.name,
        "twb_size_bytes": twb_path.stat().st_size,
        "assets": defaultdict(list),
    }
    for p in work_dir.rglob("*"):
        if p.is_file() and p != twb_path:
            kind = p.parts[len(work_dir.parts)] if len(p.parts) > len(work_dir.parts) else "(root)"
            inv["assets"][kind].append({
                "path": str(p.relative_to(work_dir)),
                "size_bytes": p.stat().st_size,
            })
    inv["assets"] = dict(inv["assets"])
    return inv


def parse_datasources(root: ET.Element) -> tuple[list[dict], list[dict]]:
    """Returns (datasources_list, raw_column_records)."""
    datasources = []
    raw_columns = []

    for ds in root.iterfind(".//datasource"):
        ds_info = {
            "name": safe_attrib(ds, "name"),
            "caption": safe_attrib(ds, "caption"),
            "version": safe_attrib(ds, "version"),
            "inline": safe_attrib(ds, "inline"),
            "has_connection": safe_attrib(ds, "hasconnection") != "false",
            "connections": [],
            "relations": [],
            "custom_sql": [],
        }

        for conn in ds.iterfind(".//connection"):
            ds_info["connections"].append({k: v for k, v in conn.attrib.items()})

        for rel in ds.iterfind(".//relation"):
            r = {k: v for k, v in rel.attrib.items()}
            text = (rel.text or "").strip()
            if text:
                r["sql"] = text
                if rel.attrib.get("type") == "text":
                    ds_info["custom_sql"].append({"name": rel.attrib.get("name"), "sql": text})
            ds_info["relations"].append(r)

        datasources.append(ds_info)

        # Source column metadata records (used for star-schema mapping later)
        for mr in ds.iterfind(".//metadata-record"):
            cls = safe_attrib(mr, "class")
            if cls not in ("column", "measure"):
                continue
            rec: dict = {"datasource": ds_info["name"]}
            for child in mr:
                if not child.text:
                    continue
                rec[child.tag] = child.text.strip()
            raw_columns.append(rec)

    return datasources, raw_columns


def parse_calcs(root: ET.Element) -> list[dict]:
    """Every calculated field with formula.  Handles both XML patterns and dedupes
    by column name (calcs appear in multiple datasource-dependency blocks)."""
    out: list[dict] = []
    seen: set[str] = set()

    # Build the set of column names that belong to the Parameters datasource so we
    # can exclude parameter defaults from the calcs list.
    param_names: set[str] = set()
    for ds in root.iterfind(".//datasource"):
        if ds.attrib.get("name") != "Parameters":
            continue
        for col in ds.iterfind(".//column"):
            if col.attrib.get("name"):
                param_names.add(col.attrib["name"])

    # Pattern A: inline <calculations><calculation column='[name]' formula='...' />
    # (older workbooks).
    for c in root.iterfind(".//calculations/calculation"):
        col = c.attrib.get("column")
        if not col or col in seen or col in param_names:
            continue
        formula = c.attrib.get("formula") or ""
        seen.add(col)
        out.append({
            "pattern": "inline",
            "name": col,
            "caption": col.strip("[]"),
            "formula": formula,
            "is_lod": bool(LOD_PATTERN.search(formula)),
            "is_table_calc": any(k in formula for k in TABLE_CALC_KEYWORDS),
            "param_refs": sorted(set(re.findall(r"\[Parameters\]\.\[([^\]]+)\]", formula))),
        })

    # Pattern B: <column ...><calculation class='tableau' formula='...' /></column>
    for col in root.iterfind(".//column"):
        calc = col.find("calculation")
        if calc is None:
            continue
        formula = calc.attrib.get("formula")
        if not formula:
            continue
        name = col.attrib.get("name")
        if not name or name in seen or name in param_names:
            continue
        seen.add(name)
        out.append({
            "pattern": "column-attached",
            "name": name,
            "caption": col.attrib.get("caption") or name.strip("[]"),
            "datatype": col.attrib.get("datatype"),
            "role": col.attrib.get("role"),
            "type": col.attrib.get("type"),
            "formula": formula,
            "is_lod": bool(LOD_PATTERN.search(formula)),
            "is_table_calc": any(k in formula for k in TABLE_CALC_KEYWORDS),
            "param_refs": sorted(set(re.findall(r"\[Parameters\]\.\[([^\]]+)\]", formula))),
        })
    return out


def parse_parameters(root: ET.Element) -> list[dict]:
    """Parameters live under datasource name='Parameters' as <column> elements
    with an aliases or members block."""
    params: list[dict] = []
    for ds in root.iterfind(".//datasource"):
        if ds.attrib.get("name") != "Parameters":
            continue
        for col in ds.iterfind("column"):
            p: dict = {
                "name": col.attrib.get("name"),
                "caption": col.attrib.get("caption"),
                "datatype": col.attrib.get("datatype"),
                "role": col.attrib.get("role"),
                "param_default": None,
                "value_set": [],
            }
            calc = col.find("calculation")
            if calc is not None and "formula" in calc.attrib:
                p["param_default"] = calc.attrib["formula"]
            for m in col.iterfind(".//member"):
                p["value_set"].append({
                    "value": m.attrib.get("value"),
                    "alias": m.attrib.get("alias"),
                })
            params.append(p)
    return params


def parse_worksheets(root: ET.Element) -> list[dict]:
    """Mine the structural truth from each <worksheet>:
    - `<rows>` / `<cols>` text: the pill strings on the row/column shelves.
      These determine bar orientation (dim on rows -> horizontal) and which
      field is the categorical axis vs the measure axis.
    - `<mark class=...>`: bar / line / area / point / Automatic.
    - `<encodings>/<color column=...>` and siblings: the color/size/shape/
      label/detail/tooltip shelf bindings. The child TAG NAME is the shelf
      name; previous extractor incorrectly looked for `<encoding>` (singular)
      and missed every encoding in the workbook.
    - `<filter>`: filter pills.
    - `<datasource-dependencies>`: worksheet-scoped calc columns AND the
      list of upstream datasources.
    """
    out: list[dict] = []
    for ws in root.iterfind(".//worksheets/worksheet"):
        info: dict = {
            "name": ws.attrib.get("name"),
            "datasources": [],
            "marks": [],
            "encodings": [],
            "rows": None,
            "cols": None,
            "filters": [],
            "field_refs": [],
        }
        for ds_dep in ws.iterfind(".//datasource-dependencies"):
            info["datasources"].append(ds_dep.attrib.get("datasource"))
            for col in ds_dep.iterfind("column"):
                info["field_refs"].append({
                    "name": col.attrib.get("name"),
                    "caption": col.attrib.get("caption"),
                    "role": col.attrib.get("role"),
                    "type": col.attrib.get("type"),
                    "datatype": col.attrib.get("datatype"),
                })
        # Rows / cols shelf strings. Tableau emits these as the text content
        # of <rows> and <cols> under <view><table>. Concatenate any pills.
        for shelf_tag in ("rows", "cols"):
            pieces: list[str] = []
            for el in ws.iterfind(f".//{shelf_tag}"):
                if el.text and el.text.strip():
                    pieces.append(el.text.strip())
            if pieces:
                info[shelf_tag] = " ".join(pieces)
        # Marks: one entry per <mark> element observed (usually one per pane).
        for mark in ws.iterfind(".//mark"):
            info["marks"].append(dict(mark.attrib))
        # Encodings: iterate the CHILDREN of <encodings> elements. The child
        # tag is the shelf name; the column attribute is the bound field.
        for encs in ws.iterfind(".//encodings"):
            for child in encs:
                info["encodings"].append({
                    "shelf": child.tag,
                    **dict(child.attrib),
                })
        for f in ws.iterfind(".//filter"):
            info["filters"].append(_filter_to_dict(f))
        out.append(info)
    return out


def _filter_to_dict(f: ET.Element) -> dict:
    """Capture every attribute on a <filter> element plus its member list.

    The previous extractor only saved class+column+groupfilter-present, which
    silently dropped first-period, last-period, period-type-v2, include-future,
    include-null, and member values. Downstream filter-default migration relies
    on all of these.
    """
    rec: dict = {"_attrs": dict(f.attrib)}
    rec["class"] = f.attrib.get("class")
    rec["column"] = f.attrib.get("column")
    gf = f.find("groupfilter")
    rec["groupfilter"] = gf is not None
    if gf is not None:
        rec["groupfilter_function"] = gf.attrib.get("function")
        members = [m.attrib.get("member") for m in gf.iterfind(".//groupfilter") if m.attrib.get("function") == "member"]
        rec["members"] = [m for m in members if m]
    if f.attrib.get("class") == "relative-date":
        rec["relative_date"] = {
            "first_period": f.attrib.get("first-period"),
            "last_period": f.attrib.get("last-period"),
            "period_type": f.attrib.get("period-type-v2") or f.attrib.get("period-type"),
            "include_future": f.attrib.get("include-future") == "true",
            "include_null": f.attrib.get("include-null") == "true",
        }
    return rec


def parse_shared_view_filters(root: ET.Element) -> list[dict]:
    """Filters declared at federated-datasource scope, applied to every
    worksheet that uses that datasource. These are the source of truth for
    dashboard-level date range pills and category restrictions.
    """
    out: list[dict] = []
    for sv in root.iterfind(".//shared-views/shared-view"):
        ds_name = sv.attrib.get("name")
        for f in sv.iterfind("filter"):
            rec = _filter_to_dict(f)
            rec["scope"] = "shared-view"
            rec["datasource"] = ds_name
            out.append(rec)
    return out


def parse_extract_filters(root: ET.Element) -> list[dict]:
    """Filters declared inside <extract> blocks, applied at the data-source
    extract level. These usually carry user-visible defaults like "last 12
    months" or "exclude internal records".
    """
    out: list[dict] = []
    for ds in root.iterfind(".//datasource"):
        ds_name = ds.attrib.get("name")
        for ext in ds.iterfind(".//extract"):
            for f in ext.iterfind("filter"):
                rec = _filter_to_dict(f)
                rec["scope"] = "extract"
                rec["datasource"] = ds_name
                out.append(rec)
    return out


def parse_dashboards(root: ET.Element) -> list[dict]:
    """Dashboard layout tree.  Walk <zones> recursively, capturing x/y/w/h and the
    parent->child container hierarchy.  This is the bones for layout reconstruction."""

    def walk(z: ET.Element, depth: int = 0) -> dict:
        node: dict = {
            "id": z.attrib.get("id"),
            "name": z.attrib.get("name"),
            "type": z.attrib.get("type-v2") or z.attrib.get("type"),
            "x": int(z.attrib["x"]) if "x" in z.attrib else None,
            "y": int(z.attrib["y"]) if "y" in z.attrib else None,
            "w": int(z.attrib["w"]) if "w" in z.attrib else None,
            "h": int(z.attrib["h"]) if "h" in z.attrib else None,
            "param": z.attrib.get("param"),
            "is_floating": z.attrib.get("floating") == "true",
            "depth": depth,
            "children": [],
        }
        # If this zone references a worksheet, capture it.
        node["worksheet"] = z.attrib.get("name") if z.attrib.get("type") == "layout-flow" else None
        if z.attrib.get("type") in (None, "layout-basic", "layout-flow"):
            ws_name = z.attrib.get("name")
            if ws_name and not node["children"]:
                node["worksheet_ref"] = ws_name
        for child in z.iterfind("zone"):
            node["children"].append(walk(child, depth + 1))
        return node

    out: list[dict] = []
    for d in root.iterfind(".//dashboards/dashboard"):
        info: dict = {
            "name": d.attrib.get("name"),
            "title": d.attrib.get("title"),
            "size": dict(d.find("size").attrib) if d.find("size") is not None else None,
            "zones": [],
        }
        zones = d.find("zones")
        if zones is not None:
            for z in zones.iterfind("zone"):
                info["zones"].append(walk(z))
        out.append(info)
    return out


def parse_actions(root: ET.Element) -> list[dict]:
    """Filter / highlight / parameter / set / URL actions with full source/target
    sheet wiring and field mappings."""
    out: list[dict] = []
    for a in root.iterfind(".//actions/action"):
        info: dict = {
            "name": a.attrib.get("name"),
            "type": a.attrib.get("type"),
            "caption": a.attrib.get("caption"),
            "source_dashboards": [],
            "source_sheets": [],
            "target_sheets": [],
            "field_mappings": [],
            "raw_attrs": dict(a.attrib),
        }
        for src in a.iterfind(".//source-dashboards/source-dashboard"):
            info["source_dashboards"].append(src.text)
        for src in a.iterfind(".//source-sheets/source-sheet"):
            info["source_sheets"].append(src.attrib.get("name") or src.text)
        for tgt in a.iterfind(".//target-sheets/target-sheet"):
            info["target_sheets"].append(tgt.attrib.get("name") or tgt.text)
        for fm in a.iterfind(".//field-mappings/field-mapping"):
            info["field_mappings"].append({
                "source": fm.attrib.get("source"),
                "target": fm.attrib.get("target"),
            })
        out.append(info)
    return out


def parse_styles(root: ET.Element) -> dict:
    """Fonts, colors, borders, banding, conditional formatting, number/date formats."""
    out: dict = {
        "global_styles": [],
        "format_rules": [],
        "conditional_formatting": [],
    }
    for s in root.iterfind(".//style/style-rule"):
        out["global_styles"].append({
            "element": s.attrib.get("element"),
            "format": [{"attr": f.attrib.get("attr"), "value": f.attrib.get("value")} for f in s.iterfind("format")],
        })
    for fmt in root.iterfind(".//format"):
        if "field" in fmt.attrib or "format" in fmt.attrib:
            out["format_rules"].append(dict(fmt.attrib))
    return out


def parse_palettes(root: ET.Element) -> list[dict]:
    """Custom color palettes.

    Two sources:
    1. Workbook-level named palettes under <preferences><color-palette name=...>.
       These are the user's brand palettes. Each <color> child is a hex code.
       Shape: {kind: "workbook", name, type (regular|sequential|diverging), colors: [hex...]}
    2. Per-encoding value maps under <encodings><color column=...><map><bucket>.
       These are per-tile dimension-value-to-color overrides.
       Shape: {kind: "encoding", field, palette_name, values: [{value, color}]}
    """
    out: list[dict] = []
    # Workbook-level brand palettes.
    for cp in root.iterfind(".//preferences/color-palette"):
        colors = [(c.text or "").strip() for c in cp.iterfind("color") if (c.text or "").strip()]
        if not colors:
            continue
        out.append({
            "kind": "workbook",
            "name": cp.attrib.get("name"),
            "type": cp.attrib.get("type", "regular"),
            "colors": colors,
        })
    # Per-encoding value maps.
    for color in root.iterfind(".//encodings/color"):
        m = {
            "kind": "encoding",
            "field": color.attrib.get("column"),
            "palette_name": color.attrib.get("palette"),
            "values": [],
        }
        for entry in color.iterfind(".//map/bucket"):
            m["values"].append({
                "value": entry.attrib.get("value") or (entry.text or "").strip(),
                "color": (entry.text or "").strip(),
            })
        if m["values"]:
            out.append(m)
    return out


def parse_hidden_sheets(root: ET.Element) -> list[str]:
    """Sheets used only as tooltip vizzes or dashboard sources but not on tabs."""
    hidden: list[str] = []
    for w in root.iterfind(".//windows/window"):
        if w.attrib.get("hidden") == "true":
            hidden.append(w.attrib.get("name"))
    return hidden


def build_param_dependency_map(calcs: list[dict], worksheets: list[dict]) -> dict:
    """Reverse map: parameter name -> {calcs: [...], sheets: [...]}."""
    deps: dict = defaultdict(lambda: {"calcs": [], "sheets": []})
    for c in calcs:
        for p in c.get("param_refs", []):
            deps[p]["calcs"].append(c.get("caption") or c.get("name"))
    for ws in worksheets:
        # Sheets reference parameters indirectly via fields, but a quick proxy is
        # name-search across the ws's column refs for "[Parameters]".
        for ref in ws.get("field_refs", []):
            cap = (ref.get("caption") or "")
            name = (ref.get("name") or "")
            for p in re.findall(r"\[Parameters\]\.\[([^\]]+)\]", cap + " " + name):
                deps[p]["sheets"].append(ws["name"])
    return {k: {"calcs": sorted(set(v["calcs"])), "sheets": sorted(set(v["sheets"]))} for k, v in deps.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine a Tableau .twbx into structured JSON.")
    ap.add_argument("twbx", type=Path, help="Path to .twbx file")
    ap.add_argument("--out", type=Path, required=True, help="Output directory for JSON files")
    args = ap.parse_args()

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / "_unpacked"

    print(f"Unpacking {args.twbx} -> {work_dir}", file=sys.stderr)
    twb_path = unpack_twbx(args.twbx, work_dir)
    print(f"  twb: {twb_path.name}", file=sys.stderr)

    inv = gather_inventory(twb_path, work_dir)

    print("Parsing XML...", file=sys.stderr)
    tree = ET.parse(twb_path)
    root = tree.getroot()

    datasources, raw_columns = parse_datasources(root)
    calcs = parse_calcs(root)
    parameters = parse_parameters(root)
    worksheets = parse_worksheets(root)
    dashboards = parse_dashboards(root)
    actions = parse_actions(root)
    styles = parse_styles(root)
    palettes = parse_palettes(root)
    hidden = parse_hidden_sheets(root)
    param_deps = build_param_dependency_map(calcs, worksheets)
    shared_view_filters = parse_shared_view_filters(root)
    extract_filters = parse_extract_filters(root)
    dashboard_filters = shared_view_filters + extract_filters

    inv["counts"] = {
        "datasources": len(datasources),
        "raw_columns": len(raw_columns),
        "calc_fields": len(calcs),
        "lod_calcs": sum(1 for c in calcs if c["is_lod"]),
        "table_calcs": sum(1 for c in calcs if c["is_table_calc"]),
        "parameters": len(parameters),
        "worksheets": len(worksheets),
        "dashboards": len(dashboards),
        "actions": len(actions),
        "palettes": len(palettes),
        "hidden_sheets": len(hidden),
        "dashboard_filters": len(dashboard_filters),
    }

    files = {
        "inventory.json": inv,
        "datasources.json": datasources,
        "raw_columns.json": raw_columns,
        "calcs.json": calcs,
        "parameters.json": parameters,
        "parameter_deps.json": param_deps,
        "worksheets.json": worksheets,
        "dashboards.json": dashboards,
        "actions.json": actions,
        "styles.json": styles,
        "palettes.json": palettes,
        "hidden_sheets.json": hidden,
        "dashboard_filters.json": dashboard_filters,
    }
    for fname, payload in files.items():
        with (out_dir / fname).open("w") as f:
            json.dump(payload, f, indent=2, default=str)

    print(f"\nExtraction complete -> {out_dir}", file=sys.stderr)
    print(json.dumps(inv["counts"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
