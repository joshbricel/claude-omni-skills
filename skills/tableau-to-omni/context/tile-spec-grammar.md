# Tile-spec grammar (`build_dashboards.py`)

The migration spec YAML drives the production builder. One YAML file describes
N dashboards, each with its tiles, layout, filters, and branding. The builder
emits one Omni `documents-import` payload per dashboard and (with `--also-import`)
imports + seeds each.

## Top-level shape

```yaml
view: <view_name>           # e.g. vw_events_wide. The base view all tiles query against.
topic: <topic_name>         # e.g. acme_events. Every tile gets join_paths_from_topic_name = this.

dashboards:
  - slug: <kebab-slug>      # used for output filenames
    name: <display name>
    description: <text>
    cross_filter: true|false   # enables click-any-tile -> filter-everything-else (Omni crossfilterEnabled)
    filters:                # dashboard-level filters surfaced as pills at the top
      - field: <view>.<field>
        type: string|date|number    # default "string"
        kind: EQUALS|...            # default "EQUALS"
    tiles:
      - <tile-spec>
```

## Tile-spec grammar (per tile)

Common to every tile:

```yaml
- name: <display name>
  kind: kpi_strip | bar | line | area | scatter | dual_bar | gender_callout | markdown
  layout: { x: 0, y: 0, w: 12, h: 14 }   # 12-col grid, h in row units
  filters:                                # tile-level always-on filters
    "<view>.<field>": { is: "Y" }         # EQUALS single value
    "<view>.<field>": { is: "Female,Male" } # EQUALS multi-value (comma -> array)
    "<view>.<field>": { is_not: "Other" } # NOT EQUALS
    "<view>.<field>": { kind: ..., values: [...] } # passthrough Omni shape
  limit: 5000     # optional
```

### `kind: kpi_strip`

Spreadsheet-style row of dimension + measure(s). Closest analog to Tableau's
KPI header strips (e.g. "BREAKDOWN BY GEO: APAC | EMEA | NA").

```yaml
- name: "Events by Geo"
  kind: kpi_strip
  dimension: <view>.<dim>
  measures: [<view>.<measure>, ...]      # 1+ measures, rendered as columns
  sort_by: <view>.<measure>              # optional, default first measure
  sort_order: descending|ascending       # default descending
```

### `kind: bar`

Vertical or horizontal bar. Stacked by `color` if provided. Trellised by `column` if provided.

```yaml
- name: "Events by Category"
  kind: bar
  orientation: horizontal | vertical    # default vertical
  dimension: <view>.<dim>
  measures: [<view>.<m1>, <view>.<m2>]  # multi-measure -> grouped or stacked depending on color
  color: <view>.<dim>                    # optional. Stacked bars when set.
  column: <view>.<dim>                   # optional. Trellis (small multiples) when set.
  sort_by: <view>.<measure-or-dim>
  sort_order: descending|ascending
```

### `kind: line` / `kind: area`

Time series. `dimension` is the time-frame field (e.g. `vw_events_wide.startdate[month]`).

```yaml
- name: "Events Trend"
  kind: line                             # or area
  dimension: vw_events_wide.startdate[date]
  measures: [<view>.<m1>, ...]
  color: <view>.<dim>                    # optional, splits into multiple lines/areas
  hero_color: "#dc3545"                  # optional, overrides default Omni blue
```

### `kind: scatter`

X/Y point chart. Trellis via `column`, color-encode via `color`.

```yaml
- name: "Events vs new members"
  kind: scatter
  x: <view>.<measure-or-dim>
  y: <view>.<measure>
  color: <view>.<dim>                    # optional
  column: <view>.<dim>                   # optional, trellis
```

Note: Omni does not natively render regression / trend-line overlays on
scatter. Tableau's "show trend line" is a manual step in the Omni UI today.
Documented in `residual-gaps.md`.

### `kind: dual_bar`

Two parallel-bar measures per category (events + new_members style). Same
shape as `bar` with two measures; the renderer auto-detects multi-measure as
side-by-side bars unless `color` is set, in which case it stacks.

```yaml
- name: "Category breakdown by geo"
  kind: dual_bar
  orientation: horizontal
  dimension: <view>.<dim>
  measures: [<view>.<m1>, <view>.<m2>]
  column: <view>.<dim>                   # optional, trellis
```

### `kind: gender_callout`

Two-row spreadsheet (Female / Male, with measure beside). Closest analog to
Tableau's gender-shape-mark icons. Numbers only; the iconography itself is
documented as a fidelity gap.

```yaml
- name: "Members by gender"
  kind: gender_callout
  dimension: <view>.<gender-field>
  measure: <view>.<measure>
  filters:
    "<view>.<gender-field>": { is: "Female,Male" }   # exclude null/Other
```

### `kind: markdown`

Static text tile (notes, dashboard descriptions, footers). Becomes a
`textTile` in `dashboard.metadata.textTiles` rather than a query
presentation.

```yaml
- name: "Footer"
  kind: markdown
  content: "Migrated from Tableau ..."
  layout: { x: 0, y: 80, w: 12, h: 4 }
```

## Filter normalization

The builder accepts compact filter forms and translates to Omni's verbose
queryJson filter shape:

| Spec form | Omni form |
|-----------|-----------|
| `{ is: "Y" }` | `{ kind: "EQUALS", values: ["Y"], type: "string", is_negative: false }` |
| `{ is: "Female,Male" }` | `{ kind: "EQUALS", values: ["Female", "Male"], type: "string", is_negative: false }` |
| `{ is_not: "Other" }` | `{ kind: "EQUALS", values: ["Other"], type: "string", is_negative: true }` |
| `{ kind: ..., values: [...] }` | passthrough |

## Cross-filter behavior (`cross_filter`)

When `cross_filter: true`, the dashboard sets `crossfilterEnabled: true` and
`tileFilterMap: {}` (every tile receives every filter). This mirrors
Tableau's "click on any chart, filter all others" UX.

For per-tile filter scoping (some tiles ignore some dashboard filters), set
`cross_filter: false` and populate `tileFilterMap` directly via a future
extension, or post-edit in the Omni UI. Most migrations should use the
default and post-tune in UI.

## Layout grid

Dashboards use Omni's standard 12-col grid. Y is in row units (~12px each).

| Tableau pixel zone | Omni grid |
|--------------------|-----------|
| Full width (~960px) | w: 12 |
| Half width | w: 6 |
| Third width | w: 4 |

Heights are tile-content-driven; start with 12-16 for charts, 6-8 for KPI
strips, then adjust in UI.

## Example: full migration spec

See `templates/acme-events-spec.yaml` for the worked example used in the
demo migration. It defines 4 dashboards, ~17 tiles, with bar / line / scatter
/ kpi_strip / gender_callout, dashboard filters, and tile-level always-on
filters (e.g. `new_account = Y` to scope the New Members dashboards).
