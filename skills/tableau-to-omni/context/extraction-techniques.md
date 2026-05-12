# Creative TWBX Extraction Techniques

A `.twbx` is just a zip. Rename to `.zip`, unzip, and the workbook surrenders most of its secrets. This file documents the techniques that go beyond "open it in Tableau Desktop" and let you mine a workbook programmatically.

## The minimal toolkit

| Tool | Purpose |
|------|---------|
| `unzip` (system) | Crack open the .twbx zip |
| `xmllint` (system) | XPath the .twb on the command line |
| `python3` + `xml.etree.ElementTree` | Parse and walk the .twb tree (stdlib only) |
| `tableauhyperapi` (Python) | Read .hyper extracts as a Postgres-like DB |
| `tableaudocumentapi` (Python, optional) | Higher-level workbook reads/edits |
| `jq` (system) | Filter and reshape the JSON our `extract.py` produces |

Most workflows below need only `unzip` and the JSON output of our `extract.py`.

## File-level structure (after unzip)

```
{Workbook}.twbx
├── {Workbook}.twb                XML workbook definition. The goldmine.
├── Data/
│   └── {Workbook}.twb Files/
│       └── *.hyper / *.tde       Embedded data extracts.
├── Image/                        Embedded backgrounds, logos, dashboard images.
├── Shapes/                       Custom mark shapes (PNG).
├── Thumbnails/                   Sheet/dashboard preview PNGs.
├── Custom Geocoding/             Custom geographic role definitions.
└── TwbxExternalCache/            Tableau's per-viz cache (binary, mostly skip).
```

## XML mining cheatsheet

Run `extract.py` first, then use `jq` to filter the JSON outputs. Below are the same XPaths if you prefer raw `xmllint`.

### Connections, joins, custom SQL

```bash
xmllint --xpath '//datasource/connection' workbook.twb
xmllint --xpath '//relation[@type="text"]' workbook.twb       # custom SQL
xmllint --xpath '//relation[@type="join"]' workbook.twb       # multi-table joins
```

Or:

```bash
jq '.[] | {name, connections, custom_sql, relations}' extract/datasources.json
```

### Calculated fields with formulas

```bash
xmllint --xpath '//column[calculation]' workbook.twb
```

Or filter for LODs and table calcs:

```bash
jq '.[] | select(.is_lod or .is_table_calc) | {caption, formula}' extract/calcs.json
```

### Parameter definitions and value sets

```bash
jq '.[] | {name, caption, datatype, default: .param_default, values: .value_set}' extract/parameters.json
```

### Marks card configuration

```bash
jq '.[] | {name, marks, encodings, filters}' extract/worksheets.json
```

### Dashboard layout (zone tree)

The `<zones>` tree is a literal hierarchy of containers with `x`, `y`, `w`, `h` plus `floating` flags. You can walk it to rebuild the dashboard layout in any tool (Figma, HTML/CSS, Omni `gridConfig`).

```bash
jq '.[] | {name, size, zones}' extract/dashboards.json
```

### Action graph

Filter actions, highlight actions, parameter actions, set actions, URL actions, with full source-to-target wiring and field mappings.

```bash
jq '[.[] | {name, type, source: .source_sheets, target: .target_sheets, fields: .field_mappings}]' extract/actions.json
```

Build a directed graph (DOT format) for visualization:

```bash
echo "digraph G {"; jq -r '.[] | .source_sheets[] as $s | .target_sheets[] as $t | "  \"\($s)\" -> \"\($t)\" [label=\"\(.type)\"];"' extract/actions.json; echo "}"
```

Pipe to `dot -Tpng > actions.png` for a visual.

### Custom color palettes

Inline hardcoded `<encodings><color><map>` entries reveal palettes the user built without saving to `Preferences.tps`. Lift them for reuse:

```bash
jq '.[] | {field, palette_name, values}' extract/palettes.json
```

### Hidden sheets

Sheets used as tooltip vizzes, dashboard sources, or just orphaned but kept in the workbook. They show up as `<window hidden='true'>`.

```bash
cat extract/hidden_sheets.json
```

These are landmines during migration: they often duplicate logic from visible sheets. Always audit.

### Tooltip markup with embedded vizzes

Tableau lets you embed a viz inside another sheet's tooltip. Look for `<formatted-text>` nodes with `<sheet>` children:

```bash
xmllint --xpath '//tooltip[contains(., "<sheet")]' workbook.twb
```

These almost never translate to Omni cleanly. Document and rebuild.

### Annotations

Mark / area / point annotations with positioning:

```bash
xmllint --xpath '//annotation' workbook.twb
```

### Story points sequence

```bash
xmllint --xpath '//story' workbook.twb
```

Stories are Tableau-specific. Omni has no direct equivalent. Treat each story point as a separate dashboard or a sequence of bookmarks.

## Hyper extract -> SQL

```python
from tableauhyperapi import HyperProcess, Connection, Telemetry

with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
    with Connection(endpoint=hyper.endpoint, database="path/to/extract.hyper") as conn:
        for tn in conn.catalog.get_table_names(schema="Extract"):
            print(conn.execute_list_query(f"SELECT * FROM {tn} LIMIT 10"))
```

We provide `scripts/read_hyper.py` as a thin wrapper. Lets you treat the embedded data as a read-only Postgres-like DB.

## Diffing two TWBX versions

Reveal every change someone made between v1 and v2 of a workbook:

```bash
python3 scripts/diff_twbx.py before.twbx after.twbx --mode summary
```

Reports added / removed / modified calc fields, sheets, dashboards, actions. Use `--mode raw` for line-by-line XML diff.

Great for migration QA: build the Omni dashboard, then compare the freshly-saved Tableau workbook (after unintentional drift) to your baseline to make sure the source-of-truth is what you expected.

## Bulk grep across a library of workbooks

When you have N workbooks and want to find every reference to a field or formula:

```bash
find . -name '*.twbx' -exec sh -c 'unzip -p "$1" "*.twb" 2>/dev/null | grep -l "your_field"' _ {} \;
```

Or expand to grep + filename:

```bash
for f in *.twbx; do
  unzip -p "$f" "*.twb" 2>/dev/null | grep -q "your_field" && echo "$f"
done
```

Useful for impact analysis ("which workbooks use this column?") before retiring a source.

## Strip the extract, keep the shell

To share viz logic without data:

1. Unzip the .twbx.
2. Replace `Data/*/extract.hyper` with an empty file or remove and add an empty `.tdsx`.
3. Re-zip into a new `.twbx`.

Recipient sees the dashboard structure, no data. Useful for support requests where you don't want to leak production rows.

## Extract embedded images

```bash
mkdir -p extracted_images
cp _unpacked/Image/*.png extracted_images/
cp _unpacked/Shapes/*.png extracted_images/
```

Custom marks, logos, and background images are raw assets. Reuse them in Omni dashboards directly.

## What our `extract.py` does for you

The single command `python3 scripts/extract.py workbook.twbx --out ./extract` runs all the XPaths above and produces 12 JSON files. Use it as the first step in every migration. Drop down to `xmllint` only when you need something the extractor doesn't capture (extending the script is preferred to one-off XPath scripts).
