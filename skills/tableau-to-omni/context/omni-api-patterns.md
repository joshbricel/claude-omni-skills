# Omni API Patterns for Dashboard Import

Reference for the Omni document import API, covering payload structure, visualization configuration, query requirements, filter formats, and known limitations.

## Import Endpoint

```
POST {BASE_URL}/api/unstable/documents/import
Authorization: Bearer {API_KEY}
Content-Type: application/json
```

## Payload Structure

```json
{
  "baseModelId": "uuid-of-shared-model",
  "exportVersion": "0.1",
  "fileUploads": {},
  "queryModels": {},
  "dashboard": { ... },
  "document": { ... },
  "workbookModel": { ... }
}
```

### Critical Requirements

| Field | Required Value | Notes |
|-------|---------------|-------|
| `exportVersion` | `"0.1"` (string) | Must be a string, not a number |
| `metadataVersion` | `2` (integer) | Inside `dashboard` object |
| `baseModelId` | UUID string | Must be at root level |
| `fileUploads` | `{}` (object) | Must be empty object, NOT empty array `[]` |

## Dashboard Object

```json
{
  "dashboard": {
    "crossfilterEnabled": false,
    "facetFilters": false,
    "name": "Dashboard Name",
    "metadata": {
      "layouts": { "lg": [...] },
      "textTiles": [],
      "hiddenTiles": [],
      "tileSettings": {},
      "tileFilterMap": {},
      "tileControlMap": {}
    },
    "metadataVersion": 2,
    "queryPresentationCollection": {
      "filterConfig": { ... },
      "filterConfigVersion": 0,
      "filterOrder": [...],
      "queryPresentationCollectionMemberships": [...]
    }
  }
}
```

## Tile Definitions (queryPresentation)

Each tile lives inside `queryPresentationCollectionMemberships` as:

```json
{
  "queryPresentation": {
    "type": "query",
    "name": "Tile Name",
    "subTitle": "",
    "description": "",
    "prefersChart": true,
    "automaticVis": true,
    "topicName": "topic_name",
    "isSql": false,
    "filterOrder": [...],
    "resultConfig": { ... },
    "aiConfig": {},
    "query": { "queryJson": { ... } },
    "visConfig": { ... }
  }
}
```

### Key Properties

| Property | Type | Effect |
|----------|------|--------|
| `prefersChart` | boolean | `true` = chart, `false` = table/spreadsheet |
| `automaticVis` | boolean | **Must be `true`**. `false` breaks rendering. |
| `topicName` | string | Links to the semantic layer topic |
| `isSql` | boolean | `false` for model-based queries |

## visConfig Patterns

### Valid visTypes

`vegalite`, `basic`, `omni-kpi`, `omni-table`, `omni-spreadsheet`, `spreadsheet-tab`, `summary-value`, `omni-markdown`, `omni-ai-summary-markdown`, `map`, `svg-map`, `funnel`, `sankey`, `single-record`

### Table / Spreadsheet

```json
{
  "visType": "omni-spreadsheet",
  "spec": {},
  "fields": ["view.field1", "view.field2"],
  "version": 0
}
```

Set `prefersChart: false` on the queryPresentation.

### Line Chart (Vertical Orientation)

For a standard vertical chart (dates horizontal, values vertical), assign axes like standard Vega-Lite:

- **`x`** = date/time dimension (temporal, horizontal)
- **`y`** = measure (quantitative, vertical)
- **`_dependentAxis: "y"`** tells Omni the measure (dependent variable) is on y

The generated Vega-Lite will have `x.axis.orient: "bottom"` automatically.

```json
{
  "visType": "basic",
  "spec": {
    "version": 0,
    "configType": "cartesian",
    "mark": {"type": "line"},
    "x": {
      "field": {"name": "view.date_field[month]"},
      "axis": {
        "title": {"value": ""},
        "sort": {
          "field": "view.date_field[month]",
          "order": "ascending"
        }
      }
    },
    "y": {
      "field": {"name": "view.measure_field"},
      "axis": {"title": {"value": "Chart Title"}}
    },
    "series": [{
      "mark": {"type": "line", "_mark_color": "#298BE5"},
      "field": {"name": "view.measure_field"},
      "title": {"value": "Series Name", "format": "USDCURRENCY"},
      "yAxis": "y"
    }],
    "tooltip": [
      {"field": {"name": "view.date_field[month]"}},
      {"field": {"name": "view.measure_field"}}
    ],
    "behaviors": {"stackMultiMark": false},
    "_dependentAxis": "y"
  },
  "fields": ["view.date_field[month]", "view.measure_field"],
  "version": 0
}
```

### Bar Chart

Same as line chart but with `"mark": {"type": "bar"}` in both the top-level `mark` and the series `mark`.

## Axis Mapping: Tableau to Omni

The mapping is straightforward once you know it:

| Tableau Axis | Omni visConfig Key | Vega-Lite Output | Content |
|-------------|-------------------|-----------------|---------|
| Columns shelf (x-axis) | `x` | `x` with `axis.orient: "bottom"` | Date/time dimension |
| Rows shelf (y-axis) | `y` | `y` | Measure values |

Set `_dependentAxis: "y"` for standard vertical charts. The common mistake is putting the date on `y` and the measure on `x`, which flips the chart horizontally.

## Known Rendering Constraints

1. **Date dimension goes on `x`, measure goes on `y`.** Swapping them (date on `y`, measure on `x`) renders the chart horizontally (dates on the left axis, values along the bottom). Use `x` for dates + `_dependentAxis: "y"` for standard vertical orientation.

2. **`automaticVis` must be `true`**. Setting to `false` with a custom spec causes "No chart available" in most cases.

3. **Empty `spec: {}` with `automaticVis: true`** also shows "No chart available" since there's no axis mapping. Only works with `prefersChart: false` (table rendering).

4. **`omni-kpi` visType** with `spec: {}` does not render. Use `omni-spreadsheet` as a fallback for KPI data.

## queryJson Requirements

```json
{
  "limit": 500,
  "sorts": [...],
  "table": "view_name",
  "fields": ["view.field1", "view.field2"],
  "pivots": [],
  "dbtMode": false,
  "filters": { ... },
  "version": 8,
  "metadata": {},
  "rewriteSql": true,
  "row_totals": {},
  "fill_fields": [],
  "calculations": [],
  "column_limit": 50,
  "join_via_map": {},
  "column_totals": {},
  "userEditedSQL": "",
  "dimensionIndex": 0,
  "default_group_by": true,
  "custom_summary_types": {},
  "join_paths_from_topic_name": "topic_name"
}
```

### Sort Format

```json
{
  "null_sort": "OMNI_DEFAULT",
  "column_name": "view.field_name",
  "is_column_sort": false,
  "sort_descending": false
}
```

`null_sort: "OMNI_DEFAULT"` is required on every sort entry.

### Date Field Granularity

Use bracket suffixes for date granularity: `view.date_field[month]`, `view.date_field[year]`, `view.date_field[week]`, `view.date_field[day]`.

### Filter Formats

**Date filter (relative range):**
```json
{
  "sf_opportunities.closedate": {
    "kind": "TIME_FOR_INTERVAL_DURATION",
    "type": "date",
    "left_side": "27 months ago",
    "right_side": "27 months",
    "is_negative": false
  }
}
```

**Boolean filter:**
```json
{
  "sf_opportunities.iswon": {
    "type": "boolean",
    "is_negative": false,
    "treat_nulls_as_false": false
  }
}
```

**String filter (important: `kind` is required):**
```json
{
  "sf_opportunities.stagename": {
    "kind": "STRING_IS",
    "type": "string",
    "values": ["Closed Won"],
    "is_negative": false
  }
}
```

String filters without a `kind` property will crash the dashboard page.

## Dashboard Filters (filterConfig)

Dashboard-level filters go in `queryPresentationCollection.filterConfig`:

```json
{
  "filterConfig": {
    "view.date_field": {
      "type": "date",
      "label": "Display Label",
      "kind": "TIME_FOR_INTERVAL_DURATION",
      "hidden": false,
      "fieldName": "view.date_field",
      "left_side": "27 months ago",
      "right_side": "27 months"
    }
  },
  "filterOrder": ["view.date_field"]
}
```

## Layout Grid

Omni uses a 12-column grid system. Layout is defined in `dashboard.metadata.layouts.lg`:

```json
[
  {"i": "1", "x": 0, "y": 0, "w": 12, "h": 15},
  {"i": "2", "x": 0, "y": 15, "w": 6, "h": 42},
  {"i": "3", "x": 6, "y": 15, "w": 6, "h": 42}
]
```

| Property | Description |
|----------|-------------|
| `i` | Tile index (string, 1-based, matches tile order) |
| `x` | Column position (0-11) |
| `y` | Row position (stacks vertically) |
| `w` | Width in columns (1-12) |
| `h` | Height in grid units (~12px per unit) |

## Document and Workbook Model

```json
{
  "document": {
    "connectionId": "uuid",
    "name": "Dashboard Name",
    "description": "Description text",
    "scope": "organization",
    "type": "document"
  },
  "workbookModel": {
    "connection_id": "uuid",
    "views": [],
    "relationships": [],
    "model_kind": "WORKBOOK",
    "base_model_id": "uuid",
    "topics": [],
    "ignored_schemas": [],
    "ignored_views": [],
    "all_schema_names": [],
    "virtualized_schemas": [],
    "deleted_topics": [],
    "dbt_virtualization_enabled": true
  }
}
```
