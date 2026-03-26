---
name: tableau-to-omni
description: >-
  Migrate a Tableau dashboard to Omni by parsing the .twbx workbook,
  translating worksheets to Omni tiles, and deploying via the API.
  Use when migrating dashboards from Tableau to Omni.
disable-model-invocation: true
user-invocable: true
argument-hint: "<path-to-twbx-file>"
---

# Tableau to Omni Migration

Migrate a Tableau dashboard to Omni by parsing the .twbx workbook, translating worksheets to Omni tiles, and deploying via the API.

## Trigger

- "migrate a Tableau dashboard to Omni"
- "convert this .twbx to Omni"
- "move this Tableau dashboard to Omni"
- `/tableau-to-omni path/to/dashboard.twbx`

## Prerequisites

| Requirement | Check |
|-------------|-------|
| `OMNI_API_KEY` env var | `echo $OMNI_API_KEY` |
| `OMNI_BASE_URL` env var | `echo $OMNI_BASE_URL` |
| Python 3.9+ | `python3 --version` |
| `omni-python-sdk` | `pip3 show omni-python-sdk` |
| `requests` library | `pip3 show requests` |
| `.twbx` file path | User provides as argument |

## Workflow

### Step 1: Unpack the .twbx

The `.twbx` is a zip archive. Extract it and locate the `.twb` XML file inside.

```python
import zipfile
import os

twbx_path = "$ARGUMENTS"
extract_dir = os.path.join(os.path.dirname(twbx_path), "tableau-source")
os.makedirs(extract_dir, exist_ok=True)

with zipfile.ZipFile(twbx_path, "r") as z:
    z.extractall(extract_dir)
    twb_files = [f for f in z.namelist() if f.endswith(".twb")]
    twb_path = os.path.join(extract_dir, twb_files[0])
```

### Step 2: Parse the .twb XML

Read the TWB file with `xml.etree.ElementTree`. Extract these components:

1. **Connection details**: server, database, schema, table (under `<datasources><datasource><connection>`)
2. **Columns**: name, datatype, role, aggregation (under `<column>` elements)
3. **Calculated fields**: name, formula, datatype (under `<column caption="..." calculation="...">`)
4. **Worksheets**: fields on rows/columns, filters, mark types, encodings (under `<worksheets><worksheet>`)
5. **Dashboard layout**: zone positions, sizes, worksheet assignments (under `<dashboards><dashboard>`)

Reference: `context/tableau-parsing-guide.md` for full XML structure details.

Also extract the **dashboard name** from `<dashboards><dashboard name="...">` in the XML. This becomes the Omni document name so the migrated dashboard matches the original Tableau workbook title.

Write the analysis to a `tableau-analysis.md` file in the working directory.

### Step 3: Map Tableau Fields to Omni Semantic Layer

Compare the extracted columns against existing Omni views:

1. List views on the target model using `api.list_views(model_id=MODEL_ID)`
2. For each Tableau column, find the matching Omni dimension or measure
3. Note any calculated fields or table calculations that have no Omni equivalent

If views do not exist for the data source, invoke the `omni-semantic-layer-setup` skill first to create them.

### Step 4: Create an Omni Branch

Use the `omni-branch-creator` skill or create directly:

```python
from omni_python_sdk import OmniAPI
from datetime import date

api = OmniAPI(api_key=API_KEY, base_url=BASE_URL)
branch_name = f"tableau-migration-{date.today().isoformat()}"
result = api.create_model(
    connection_id=CONNECTION_ID,
    modelName=branch_name,
    modelKind="BRANCH",
    baseModelId=SHARED_MODEL_ID,
)
branch_id = result["model"]["id"]
```

### Step 5: Build the Dashboard Import Payload

Use the template at `templates/dashboard-payload.json` as the base structure. For each Tableau worksheet, create a tile:

Use the dashboard name extracted in Step 2 for both `dashboard.name` and `document.name` in the payload.

| Tableau Chart Type | Omni Tile Type | visConfig Pattern |
|-------------------|----------------|-------------------|
| KPI strip / text table | `omni-spreadsheet` with `prefersChart: false` | `visType: "omni-spreadsheet"`, `spec: {}` |
| Bar chart | `basic` with `mark.type: "bar"` | Date on `x`, measure on `y`, `_dependentAxis: "y"` |
| Line chart | `basic` with `mark.type: "line"` | Date on `x`, measure on `y`, `_dependentAxis: "y"` |
| Dual-axis | Not directly supported | Create two separate tiles or use single chart |

**Axis mapping (critical):** Date dimensions go on `x`, measures go on `y`, and `_dependentAxis` must be `"y"`. The common mistake is putting the date on `y` and the measure on `x`, which flips the chart horizontally. Omni compiles the visConfig to Vega-Lite where `x.axis.orient` is automatically set to `"bottom"`.

Reference: `context/omni-api-patterns.md` for full visConfig patterns and queryJson requirements.

### Step 6: Configure Dashboard Filters

Translate Tableau worksheet-level filters to Omni dashboard-level `filterConfig`:

- Date filters: use `kind: "TIME_FOR_INTERVAL_DURATION"` with `left_side`/`right_side`
- Boolean filters: use `type: "boolean"` with `is_negative: false`
- String filters: must include a `kind` property (crashes without it)

### Step 7: Set Dashboard Layout

Map Tableau's pixel-based layout to Omni's 12-column grid:

```
Tableau pixel width  ->  Omni grid width
Full width           ->  w: 12
Half width           ->  w: 6
Third width          ->  w: 4
```

Vertical positioning uses `y` values that stack tiles. Height (`h`) is in grid units (roughly 1 unit = ~12px).

### Step 8: Deploy via API

Run the deployment script:

```bash
python3 scripts/create_dashboard.py \
  --base-url "$OMNI_BASE_URL" \
  --api-key "$OMNI_API_KEY" \
  --model-id "$MODEL_ID" \
  --connection-id "$CONNECTION_ID" \
  --payload dashboard-payload.json
```

Or use the API directly:

```python
response = requests.post(
    f"{BASE_URL}/api/unstable/documents/import",
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    json=payload,
)
```

### Step 9: Report Results

After deployment, report to the user:

1. **Dashboard URL**: `{BASE_URL}/dashboards/{dashboard_id}`
2. **Tiles created**: list each tile name and type
3. **Manual adjustments needed**:
   - Convert table tiles to KPI cards if desired
   - Add table calculations (trailing averages, window functions)
   - Set custom sort orders
   - Fine-tune number formatting

## Output

- `tableau-analysis.md`: Structured analysis of the Tableau workbook
- `dashboard-payload.json`: The import payload sent to Omni
- `dashboard-response.json`: The API response
- Live Omni dashboard at the reported URL
- List of manual UI adjustments needed

## Error Handling

| Error | Fix |
|-------|-----|
| `.twbx` is not a valid zip | Verify the file is a `.twbx` (not `.twb` directly). Wrap in zip if needed. |
| No `.twb` found inside zip | Check the archive contents. Some `.twbx` files have nested directories. |
| Model not found | Verify `OMNI_MODEL_ID` in env. Ensure the API key has access to the model. |
| Import API returns 400 | Check `exportVersion` is `"0.1"` (string), `metadataVersion` is `2`, `fileUploads` is `{}` (object). |
| Charts show "No chart available" | Ensure `automaticVis: true`, date dimension on `x`, measure on `y`, and `_dependentAxis: "y"`. |
| Charts render horizontally (flipped) | Date dimension is on `y` instead of `x`. Move date to `x.field`, measure to `y.field`, set `_dependentAxis: "y"`. |
| Dashboard filter crashes page | String filters must include a `kind` property. Date filters need `kind: "TIME_FOR_INTERVAL_DURATION"`. |
| Authentication error | Verify `OMNI_API_KEY` is valid. Keys start with `omni_osk_` or `omni_pat_`. |

## Checklist

- [ ] `.twbx` file unpacked and `.twb` XML parsed
- [ ] All columns, calculated fields, worksheets, and layout extracted
- [ ] Tableau fields mapped to Omni semantic layer views
- [ ] Omni branch created for the migration
- [ ] Import payload built with correct tile definitions
- [ ] Dashboard-level filters configured
- [ ] Layout grid defined (12-column system)
- [ ] Dashboard deployed via document import API
- [ ] Dashboard URL reported to user
- [ ] Manual adjustment list provided

## Context Files

| File | Description |
|------|-------------|
| `context/omni-api-patterns.md` | Omni document import API patterns, visConfig specs, queryJson requirements, and known limitations |
| `context/tableau-parsing-guide.md` | TWB XML structure reference for parsing connections, columns, worksheets, and layout |

## Related Skills

- `omni-branch-creator`: Create Omni model branches (used in Step 4)
- `omni-semantic-layer-setup`: Deploy semantic layer YAML (used in Step 3 if views missing)
