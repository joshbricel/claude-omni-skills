---
title: Tableau to Omni Mapping Rules
version: 1.0
last_updated: 2026-05-11
source_specs:
  - path: tableau-twbx-format-spec.md
    words: 10527
    lines: 2034
  - path: omni-cli-format-spec.md
    words: 7268
    lines: 1630
  - path: tableau-omni-parity-audit.md
    words: 11093
    lines: 1409
---

# Tableau to Omni Mapping Rules

Single authoritative mapping document. Two layers: a machine-driven defaults layer (rules R-* below, addressed by stable ID) and a user-editable guardrails layer (YAML at the top). Guardrails win over defaults. The emitter parses the guardrail block, resolves each rule by ID, applies any guardrails that name that rule, then falls back to the default mapping. The decisions ledger at the bottom records every guardrail change with rationale.

Each rule cites a TWBX section (audit input), an Omni section (audit output), and the parity audit row that classified the bucket. Trust the audit's bucket classifications. This file does not re-derive them.

---

## USER GUARDRAILS

```yaml
# USER GUARDRAILS - EDIT THIS BLOCK
# These keys override rule defaults. Comments name the rule IDs each key influences.

# === Calculation placement ===
# Affects rules R-CALC-04, R-CALC-05, R-CALC-06
lod_placement: model_layer
# valid: model_layer | workbook_layer | snowflake_view
# Where Tableau LOD expressions land. model_layer = Omni derived_table or measure SQL.

# Affects rules R-CALC-01, R-CALC-02, R-CALC-03
calculated_field_placement: model_layer
# valid: model_layer | workbook_layer
# Where ordinary calc fields land. model_layer keeps reuse high; workbook_layer is single-tile only.

# Affects rules R-CALC-07 through R-CALC-12
table_calc_placement: omni_table_calc
# valid: omni_table_calc | snowflake_window | workbook_layer
# omni_table_calc when Omni supports the calc natively, snowflake_window otherwise.

# === Visualization strategy ===
# Affects rules R-VIZ-10, R-VIZ-11
dual_axis_strategy: vega_lite_layered
# valid: vega_lite_layered | two_tiles_stacked | reject
# Tableau dual-axis behavior. Vega-Lite handles synced and independent; two_tiles loses overlap.

# === Dashboard layout ===
# Affects rules R-DASH-02, R-DASH-03
floating_zone_handling: snap_to_grid
# valid: snap_to_grid | reject_with_warning | best_effort_layered
# Tableau floating layout has no Omni equivalent; choose how to land it.

# Affects rules R-DASH-09, R-DASH-10
multi_tab_handling: separate_dashboards
# valid: separate_dashboards | single_dashboard_with_anchor | wait_for_omni_tabs
# Tableau stories or multi-sheet dashboards. separate_dashboards is the safest until Omni tabs are stable.

# === Parameters and derived dimensions ===
# Affects rules R-PARAM-01, R-PARAM-02, R-PARAM-03, R-PARAM-04
parameter_handling: omni_control
# valid: omni_control | snowflake_session_var | reject
# Tableau parameters. omni_control = templated filter + dashboard control.

# Affects rules R-DERIVED-01, R-DERIVED-02, R-DERIVED-03
set_handling: dimension_flag
# valid: dimension_flag | filter_preset | reject
# Tableau sets. dimension_flag = CASE WHEN boolean dimension.

# Affects rules R-DERIVED-04
group_handling: case_when_dimension
# valid: case_when_dimension | alias_only | reject
# Tableau groups (categorical-bin).

# Affects rules R-DERIVED-05
bin_handling: omni_bin
# valid: omni_bin | case_when_dimension
# Numeric bin: arithmetic FLOOR vs CASE ranges. omni_bin emits FLOOR.

# Affects rules R-DERIVED-06
hierarchy_handling: omni_drill_fields
# valid: omni_drill_fields | flatten | reject
# Tableau drill-paths.

# === Color and formatting ===
# Affects rules R-COLOR-01, R-COLOR-02, R-COLOR-03
custom_palette_handling: emit_brand_theme
# valid: emit_brand_theme | inline_per_tile | reject
# emit_brand_theme writes one palette in model AI settings, then references per tile.

# Affects rules R-VIZ-20, R-FORMAT-08
tooltip_handling: omni_tooltip
# valid: omni_tooltip | drop_with_warning
# Tableau tooltip text with field tokens.

# === Drop and reject thresholds ===
# Affects rules R-VIZ-15, R-VIZ-16, R-CALC-13
forecast_cluster_handling: drop_with_warning
# valid: precompute_snowflake | drop_with_warning | reject
# Tableau forecast / cluster analytics objects. Precompute is heavy; drop is honest.

# Affects rules R-ACTION-06
set_action_handling: drop_with_warning
# valid: drop_with_warning | reject_workbook
# Tableau set actions have no Omni equivalent.

# Affects rules R-ACTION-02
highlight_action_handling: drop_with_warning
# valid: drop_with_warning | crossfilter_substitute
# Tableau highlight actions.

# === Formats and conventions ===
# Affects rules R-FORMAT-01, R-FORMAT-02, R-FORMAT-03
format_string_dialect: best_effort
# valid: omni_native | passthrough_excel | best_effort
# best_effort uses Omni named formats when available, falls back to Excel-style strings.

# Affects rules R-FIELD-04
null_handling: preserve
# valid: preserve | replace_with_zero | drop
# Default null treatment for numeric measures.

# Affects rules R-FIELD-02, R-FIELD-03
default_aggregation_strategy: respect_tableau
# valid: respect_tableau | force_explicit_in_omni
# respect_tableau copies the TWBX default-aggregation enum onto the Omni measure.

# Affects rules R-CONN-01, R-MODEL-01
view_naming_convention: root_path_no_schema_prefix
# valid: root_path_no_schema_prefix | schema_prefixed | both
# PUBLIC views go at views/<view>.view; non-PUBLIC get schema__view filename.

# Affects rules R-MODEL-05
topic_naming_convention: snake_case_clean
# valid: from_tableau_datasource_caption | snake_case_clean | manual
# How to name the Omni topic. snake_case_clean strips Tableau adornments.

# === Emission threshold ===
# Affects every rule (global gate)
fidelity_threshold_for_rejection: 0.6
# valid: float 0.0 - 1.0
# Per-tile fidelity score. Below this the emitter raises instead of emitting low-quality output.
```

---

## Mapping Rules

### R-CONN: Connections and datasources

#### R-CONN-01: Live SQL connection
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.2): `<connection class='...' dbname='...' schema='...' server='...' warehouse='...'>`
- **Omni target** (Omni 1.1, 2): view file `schema:` + `sql_table_name:`; connection itself created out-of-band
- **Default mapping**: emit one view file per Tableau `<column>` group. `dbname.schema.table` reconstructs `sql_table_name`. Omni connection must exist on target instance by name; emitter validates via `omni connections list`.
```yaml
view: orders
schema: PUBLIC
sql_table_name: ANALYTICS.PUBLIC.ORDERS
```
- **Guardrails that override this**: `view_naming_convention`
- **Failure mode**: connection not found on target Omni instance. Emit error, list candidate connections, halt.
- **Verification**: `omni connections list` shows the target connection; row count of view matches Tableau extract row count.

#### R-CONN-02: Embedded Hyper extract
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 1.3, 3.12, 10): `<extract enabled='true'>` plus `Data/*.hyper` file in TWBX zip
- **Omni target**: none native (Omni 2)
- **Default mapping**: re-point to the live underlying connection. If the underlying connection is unknown or inaccessible, materialize the .hyper as a warehouse table upstream (out-of-band) and target that table.
- **Guardrails that override this**: none
- **Failure mode**: hyper file present but underlying connection unrecoverable. Emit warning, include hyper extraction script in migration report.
- **Verification**: row count of resulting Omni view matches hyper extract.

#### R-CONN-03: Legacy TDE extract
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 1.1): `.tde` file
- **Omni target**: none native
- **Default mapping**: upgrade .tde to .hyper using Tableau's `tdsutil` before migration, then apply R-CONN-02.
- **Guardrails that override this**: none
- **Failure mode**: .tde upgrade fails. Halt with explicit message naming the workbook.
- **Verification**: hyper file produced before migration proceeds.

#### R-CONN-04: Federated multi-connection
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.2): multiple `<connection>` siblings under one `<datasource>`
- **Omni target**: multiple model connections or upstream UNION view (Omni 2, 4)
- **Default mapping**: emit one Omni topic per connection plus a warning recommending an upstream join view. Do not attempt cross-connection join in Omni.
- **Guardrails that override this**: none
- **Failure mode**: workbook has cross-connection joins in worksheets. Demote to R-CONN-05 (cross-database) and reject the affected worksheets.
- **Verification**: each topic queries independently; cross-connection worksheets land in the warnings report.

#### R-CONN-05: Cross-database join (federated 10.0+)
- **Bucket** (audit 3.1): RED
- **Tableau source** (TWBX 1.5, 3.2): `<relation type='join'>` across connections
- **Omni target**: none (Omni 4, 5 single-connection only)
- **Default mapping**: emit a warning naming the source connections and the join predicate. Suggested message: "Pre-join these sources in your warehouse and re-point Omni at the joined table." Do not attempt to emit Omni YAML for these joins.
- **Guardrails that override this**: none (RED is absolute)
- **Failure mode**: this IS the failure mode. The emitter writes to the warnings report and continues with other worksheets.
- **Verification**: warning appears in the migration report for every affected worksheet.

#### R-CONN-06: Data blending
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.14): `<datasource-dependencies>` linking primary and secondary
- **Omni target**: single-connection topic with joins, or pre-blended SQL view (Omni 4, 5)
- **Default mapping**: emit a derived_table view that performs the blend in SQL, then reference it. Treat the linking field as the join key.
- **Guardrails that override this**: none
- **Failure mode**: linking field is calculated on the fly in the worksheet. Emit warning, recommend manual SQL.
- **Verification**: row count of blended view equals row count of Tableau-blended worksheet.

#### R-CONN-07: Published-on-server datasource (sqlproxy)
- **Bucket** (audit 3.1): GREY
- **Tableau source** (TWBX 3.2): `<connection class='sqlproxy' server='...' username='...'/>`
- **Omni target**: existing Omni model via `extends:` (Omni 2)
- **Default mapping**: if a corresponding Omni shared model exists, emit `extends: <model_id>` in the workbook model file. If not, emit a warning.
- **Guardrails that override this**: none
- **Failure mode**: no matching shared model on Omni instance. Emit warning, halt unless `--allow-orphan-extends` flag passed.
- **Verification**: workbook opens and inherits fields from the shared model.

#### R-CONN-08: Extract refresh schedule
- **Bucket** (audit 3.1): RED
- **Tableau source** (TWBX 3.12): `<extract><refresh-schedule>`
- **Omni target**: none (refresh runs in the warehouse)
- **Default mapping**: emit a warning that refresh logic must move to dbt or the warehouse scheduler. Include the original Tableau schedule string in the warning for reference.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears in migration report.

### R-MODEL: Semantic model

#### R-MODEL-01: Physical inner / left / right / full join
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.3): `<relation type='join' join='inner|left|right|full'>`
- **Omni target** (Omni 5): `relationships.yaml` entry with `join_type: always_inner|always_left|always_right|always_full`
- **Default mapping**: map join enum directly; serialize `<expression>` tree to `on_sql:` Mustache string.
```yaml
- join_from_view: orders
  join_to_view: customers
  join_type: always_left
  on_sql: ${orders.customer_id} = ${customers.id}
  relationship_type: many_to_one
```
- **Guardrails that override this**: none
- **Failure mode**: expression tree contains a function Omni cannot represent in `on_sql:`. Emit warning, materialize as a derived_table.
- **Verification**: relationship resolves; sample joined query returns expected row count.

#### R-MODEL-02: Multi-clause / calc-based join
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.3): `<clause>` with multi-`<expression>` body
- **Omni target** (Omni 5): single `on_sql:` string with `AND`-joined conditions
- **Default mapping**: walk every clause, render as `${left} = ${right}`, join with ` AND `.
- **Guardrails that override this**: none
- **Failure mode**: clause uses Tableau-specific operator. Fall back to literal SQL with warning.
- **Verification**: relationship validates in Omni; join cardinality holds.

#### R-MODEL-03: Logical relationship (noodle)
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.4): `<relationship>` with `<first-end-point>` and `<second-end-point>` cardinality attrs
- **Omni target** (Omni 5): `relationships.yaml` with `relationship_type:` derived from cardinality
- **Default mapping**: `many` + `one` to `many_to_one`; `one` + `one` to `one_to_one`; `many` + `many` to `many_to_many`. `join_type` defaults to `always_left`.
- **Guardrails that override this**: none
- **Failure mode**: cardinality unspecified. Default to `many_to_one` with warning.
- **Verification**: relationship validates; row count post-join does not inflate.

#### R-MODEL-04: Custom SQL relation
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.3): `<relation type='text'>...SELECT...</relation>`
- **Omni target** (Omni 3): view `sql:` or `derived_table.sql:`
- **Default mapping**: XML-unescape body (TWBX 0.3), paste into view's `sql:` block, run a SQL formatter pass.
```yaml
view: custom_orders
sql: |
  SELECT o.id, o.amount
  FROM orders o
  WHERE o.created_at > '2024-01-01'
```
- **Guardrails that override this**: none
- **Failure mode**: SQL references a Tableau-only function. Emit warning, replace with `/* TODO: rewrite for warehouse */`.
- **Verification**: derived_table compiles in Omni; row count matches Tableau extract.

#### R-MODEL-05: Topic naming and creation
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.1): `<datasource caption='...' name='...'>`
- **Omni target** (Omni 4): one topic file per datasource
- **Default mapping**: emit `<snake_case_clean caption>.topic` with `base_view:` set to the primary table. Strip Tableau adornments (federated, sqlproxy prefixes).
- **Guardrails that override this**: `topic_naming_convention`
- **Failure mode**: caption empty or contains only special characters. Fall back to `name` attribute.
- **Verification**: topic loads in Omni IDE.

#### R-MODEL-06: Union relation
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.3): `<relation type='union'>`
- **Omni target** (Omni 3): upstream `UNION ALL` SQL view
- **Default mapping**: materialize as a derived_table with explicit `UNION ALL` between source tables, then reference.
- **Guardrails that override this**: none
- **Failure mode**: union sources have different schemas. Emit warning naming the diverging columns.
- **Verification**: derived_table row count equals sum of source row counts.

### R-FIELD: Columns, dimensions, measures

#### R-FIELD-01: Column data type
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.5): `<column datatype='string|integer|real|date|datetime|boolean'>`
- **Omni target** (Omni 3.3): `dimension.type:` enum
- **Default mapping**: lookup table:
```yaml
# Tableau -> Omni
string:   string
integer:  number
real:     number
date:     date
datetime: timestamp
boolean:  yesno
```
- **Guardrails that override this**: none
- **Failure mode**: datatype `geometry` or `spatial`. Demote to R-FIELD-07.
- **Verification**: Omni view loads; dimension type matches.

#### R-FIELD-02: Dimension vs measure role
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.5): `<column role='dimension|measure'>`
- **Omni target** (Omni 3): `dimensions:` vs `measures:` section
- **Default mapping**: place the field under the named section in the view YAML.
- **Guardrails that override this**: `default_aggregation_strategy`
- **Failure mode**: role missing. Default to dimension for string/date, measure for numeric, with warning.
- **Verification**: field appears in Omni's correct shelf.

#### R-FIELD-03: Default aggregation
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.5): `<column aggregation='Sum|Avg|Count|CountD|Min|Max|Median|...'>`
- **Omni target** (Omni 3.2): `measure.aggregate_type:`
- **Default mapping**:
```yaml
# Tableau -> Omni
Sum:         sum
Avg:         average
Count:       count
CountD:      count_distinct
Min:         min
Max:         max
Median:      median
Percentile:  percentile
```
- **Guardrails that override this**: `default_aggregation_strategy`
- **Failure mode**: aggregation `AttributeOf` (no Omni equivalent). Demote to R-FIELD-05.
- **Verification**: aggregated measure value matches Tableau extract sum/avg/etc.

#### R-FIELD-04: Default format
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.5, 8.4): `default-format='c0'`, `'p1%'`, `'#,##0.00'`
- **Omni target** (Omni 3.4): `format:` or `value_format:` on measure/dimension
- **Default mapping**: translate Tableau shortcuts to Excel-style strings via lookup. See R-FORMAT-02 for shortcut table.
- **Guardrails that override this**: `format_string_dialect`, `null_handling`
- **Failure mode**: format shortcut not in lookup table. Emit `format: "$#,##0"` (or `0%`) with warning naming the original.
- **Verification**: rendered cell value matches Tableau worksheet output.

#### R-FIELD-05: AttributeOf aggregation
- **Bucket** (audit 3.2): YELLOW
- **Tableau source** (TWBX 3.5, 4.1): `aggregation='AttributeOf'`
- **Omni target** (Omni 3.2): SQL-driven measure with disagreement CASE
- **Default mapping**:
```yaml
measures:
  region_attr:
    sql: |
      CASE WHEN MIN(${TABLE}.region) = MAX(${TABLE}.region)
           THEN MIN(${TABLE}.region) END
    type: string
```
- **Guardrails that override this**: none
- **Failure mode**: none; the SQL is mechanical.
- **Verification**: rows that disagree return NULL, as in Tableau.

#### R-FIELD-06: Aliases (display-value remapping)
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.7): `<aliases><alias key='...' value='...'/>`
- **Omni target** (Omni 3): dimension SQL with `CASE WHEN`
- **Default mapping**:
```yaml
dimensions:
  status_label:
    sql: |
      CASE ${TABLE}.STATUS
        WHEN 'A' THEN 'Active'
        WHEN 'I' THEN 'Inactive'
        ELSE ${TABLE}.STATUS
      END
    type: string
```
- **Guardrails that override this**: `group_handling` (because aliases interact with groups)
- **Failure mode**: alias key not present in source data. CASE WHEN ELSE branch preserves the raw value.
- **Verification**: distinct labels in Omni view match Tableau-displayed labels.

#### R-FIELD-07: Geometry / spatial data type
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.5): `datatype='geometry'`
- **Omni target**: none native
- **Default mapping**: pass through as `type: string`. If a Vega-Lite map tile (R-VIZ-09) consumes the field, use the field as the lookup key against a public TopoJSON.
- **Guardrails that override this**: none
- **Failure mode**: field is a `MAKEPOINT` result with x/y components only. Drop or rewrite as separate lat/lng columns.
- **Verification**: shape renders in Vega-Lite or appears as text in tables.

### R-CALC: Calculated fields, LOD, table calcs

#### R-CALC-01: Arithmetic and math functions
- **Bucket** (audit 3.2): GREEN
- **Tableau source** (TWBX 4.1): `<calculation class='tableau' formula='...'>`
- **Omni target** (Omni 3.1): SQL operators in dimension/measure `sql:`
- **Default mapping**: direct paste of formula body after token translation. `[Field]` to `${TABLE}.field` or `${view.field}` depending on cross-view reference.
- **Guardrails that override this**: `calculated_field_placement`
- **Failure mode**: formula references undefined token. Halt with explicit message.
- **Verification**: computed value matches Tableau extract for sample rows.

#### R-CALC-02: Logical (IF, IIF, CASE)
- **Bucket** (audit 3.2): GREEN
- **Tableau source** (TWBX 4.2): `IF ... THEN ... ELSEIF ... ELSE ... END`
- **Omni target** (Omni 3.1): SQL `CASE WHEN ... THEN ... ELSE ... END`
- **Default mapping**: mechanical rewrite. `IIF(a,b,c,d)` requires `WHEN a IS NULL THEN d` branch.
- **Guardrails that override this**: `calculated_field_placement`
- **Failure mode**: nested IF deeper than 8 levels. Emit warning (legibility) but proceed.
- **Verification**: branch coverage tested against representative rows.

#### R-CALC-03: String / date / type functions
- **Bucket** (audit 3.2): GREEN (most) / YELLOW (dialect-specific)
- **Tableau source** (TWBX 4.1): `LEN`, `LEFT`, `UPPER`, `DATEPART`, `DATETRUNC`, etc.
- **Omni target** (Omni 3.1, 7.2): warehouse SQL function or Omni dimension group `timeframes:`
- **Default mapping**: lookup table per warehouse dialect. Truncation prefers Omni timeframes:
```yaml
# Tableau DATETRUNC('month', d) -> Omni dimension group
dimension_group: order
type: time
timeframes: [date, week, month, quarter, year]
sql: ${TABLE}.order_date
```
- **Guardrails that override this**: `calculated_field_placement`
- **Failure mode**: function has no warehouse equivalent (e.g., `ISOWEEK` on a warehouse without ISO support). Emit warning.
- **Verification**: sample value comparison.

#### R-CALC-04: LOD FIXED
- **Bucket** (audit 3.2): YELLOW
- **Tableau source** (TWBX 3.6, 4.3): `<calculation formula='{ FIXED [dim] : SUM([m]) }'>`
- **Omni target** (Omni 3): derived_table CTE plus relationship
- **Default mapping**: emit one view per unique (dim-list, agg-expr) pair:
```yaml
views:
  customer_total_sales:
    derived_table:
      sql: |
        SELECT customer_id AS customer, SUM(sales) AS customer_total_sales
        FROM orders
        GROUP BY customer_id
relationships:
  - join_from_view: orders
    join_to_view: customer_total_sales
    join_type: always_left
    on_sql: ${orders.customer_id} = ${customer_total_sales.customer}
    relationship_type: many_to_one
```
- **Guardrails that override this**: `lod_placement`
- **Failure mode**: fixed-dim list includes a calc field that depends on the row. Emit warning, recommend SQL window fallback.
- **Verification**: aggregated value at the fixed grain matches Tableau's worksheet output.

#### R-CALC-05: LOD INCLUDE
- **Bucket** (audit 3.2): YELLOW
- **Tableau source** (TWBX 4.3): `{ INCLUDE [dim] : ... }`
- **Omni target** (Omni 3.2): SQL window with extended partition
- **Default mapping**: `SUM(...) OVER (PARTITION BY <viz_dims>, <include_dim>)`. Since a static measure cannot know the viz dims, materialize at the most granular meaningful level:
```yaml
measures:
  avg_profit_include_region:
    sql: |
      AVG(${TABLE}.profit) OVER (
        PARTITION BY ${TABLE}.region
      )
    type: number
```
- **Guardrails that override this**: `lod_placement`
- **Failure mode**: include dim is calculated. Emit warning, fall back to derived_table.
- **Verification**: aggregated value matches Tableau output at the intended grain.

#### R-CALC-06: LOD EXCLUDE
- **Bucket** (audit 3.2): YELLOW
- **Tableau source** (TWBX 4.3): `{ EXCLUDE [dim] : ... }`
- **Omni target** (Omni 3.2): SQL window with reduced partition
- **Default mapping**: `SUM(...) OVER (PARTITION BY <viz_dims minus excluded_dim>)`. Same caveat as R-CALC-05 about viz-dim awareness.
- **Guardrails that override this**: `lod_placement`
- **Failure mode**: same as R-CALC-05.
- **Verification**: same as R-CALC-05.

#### R-CALC-07: Table calc RUNNING_*
- **Bucket** (audit 3.2): YELLOW
- **Tableau source** (TWBX 4.5): `<table-calc agg-type='Sum' ordering-type='Rows'>`
- **Omni target** (Omni 3.2): SQL window with `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`
- **Default mapping**:
```yaml
measures:
  running_total_sales:
    sql: |
      SUM(${TABLE}.sales) OVER (
        PARTITION BY {{ partition_field }}
        ORDER BY {{ order_field }}
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
      )
    type: number
```
- **Guardrails that override this**: `table_calc_placement`
- **Failure mode**: addressing reads from a pivot that does not exist in the Omni tile. Emit warning.
- **Verification**: cumulative sum at last row matches Tableau worksheet last-row value.

#### R-CALC-08: Table calc WINDOW_*
- **Bucket** (audit 3.2): YELLOW
- **Tableau source** (TWBX 4.5): `WINDOW_AVG(SUM([m]), -11, 0)`
- **Omni target** (Omni 3.2): SQL window with explicit bounds `ROWS BETWEEN N PRECEDING AND M FOLLOWING`
- **Default mapping**: map `from` and `to` integer attrs onto `ROWS BETWEEN N PRECEDING AND M FOLLOWING`.
- **Guardrails that override this**: `table_calc_placement`
- **Failure mode**: window bounds reference Tableau "First" / "Last" tokens. Translate using offsets relative to FIRST_VALUE / LAST_VALUE.
- **Verification**: spot-check at boundary rows.

#### R-CALC-09: Table calc RANK family
- **Bucket** (audit 3.2): GREEN
- **Tableau source** (TWBX 4.1, 4.5): `RANK`, `RANK_DENSE`, `RANK_MODIFIED`, `RANK_PERCENTILE`, `RANK_UNIQUE`
- **Omni target** (Omni 3.2): `RANK()`, `DENSE_RANK()`, `PERCENT_RANK()`, `ROW_NUMBER()`
- **Default mapping**:
```yaml
# RANK            -> RANK() OVER (...)
# RANK_DENSE      -> DENSE_RANK() OVER (...)
# RANK_PERCENTILE -> PERCENT_RANK() OVER (...)
# RANK_UNIQUE     -> ROW_NUMBER() OVER (...)
# RANK_MODIFIED   -> custom: COUNT(*) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
```
- **Guardrails that override this**: `table_calc_placement`
- **Failure mode**: RANK_MODIFIED across nulls. Emit warning, hand-roll the SQL.
- **Verification**: top-10 ranks match Tableau worksheet.

#### R-CALC-10: Table calc INDEX / FIRST / LAST / SIZE / LOOKUP / TOTAL
- **Bucket** (audit 3.2): YELLOW (INDEX, FIRST, LAST, SIZE) / GREEN (LOOKUP, TOTAL)
- **Tableau source** (TWBX 4.5): `INDEX()`, `FIRST()`, `LAST()`, `SIZE()`, `LOOKUP(expr, n)`, `TOTAL`
- **Omni target** (Omni 3.2): `ROW_NUMBER`, `FIRST_VALUE`, `LAST_VALUE`, `COUNT(*) OVER`, `LAG/LEAD`, `SUM() OVER ()`
- **Default mapping**: direct SQL translation. `FIRST()` becomes negative offset to `FIRST_VALUE`; `LAST()` becomes positive offset to `LAST_VALUE`.
- **Guardrails that override this**: `table_calc_placement`
- **Failure mode**: addressing not enumerable. Emit warning.
- **Verification**: spot-check at first, middle, last row.

#### R-CALC-11: Quick table calcs (% of total, difference, % difference, moving avg)
- **Bucket** (audit 3.2): YELLOW
- **Tableau source** (TWBX 4.5): `<calculation derivation='PercentOfTotal|Difference|...'>`
- **Omni target** (Omni 3.2 or Omni 7.1 pivot totals)
- **Default mapping**: prefer Omni native pivot `row_totals` for % of total; SQL window for everything else.
```yaml
measures:
  pct_of_total_sales:
    sql: |
      SUM(${TABLE}.sales)
      / NULLIF(SUM(SUM(${TABLE}.sales)) OVER (PARTITION BY {{ partition_field }}), 0)
    type: number
```
- **Guardrails that override this**: `table_calc_placement`
- **Failure mode**: division by zero where SUM is null. NULLIF prevents.
- **Verification**: column percentages sum to 100 percent per partition.

#### R-CALC-12: Custom table calc
- **Bucket** (audit 3.2): YELLOW
- **Tableau source** (TWBX 4.5): `<calculation derivation='Custom' formula='...'>`
- **Omni target** (Omni 3.2): SQL window function
- **Default mapping**: parse inner formula, rewrite arithmetic into window SQL.
- **Guardrails that override this**: `table_calc_placement`
- **Failure mode**: formula references R/Python via SCRIPT_*. Demote to R-CALC-13.
- **Verification**: sample value match.

#### R-CALC-13: SCRIPT_* (R / Python integration)
- **Bucket** (audit 3.2): RED
- **Tableau source** (TWBX 4.5): `SCRIPT_REAL/INT/STR/BOOL`
- **Omni target**: none
- **Default mapping**: emit warning naming the script body. Recommend dbt + Python or pre-compute upstream.
- **Guardrails that override this**: `forecast_cluster_handling` (precompute_snowflake)
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears in migration report.

#### R-CALC-14: Predictive (MODEL_PERCENTILE, MODEL_QUANTILE)
- **Bucket** (audit 3.2): RED
- **Tableau source** (TWBX 4.1): `MODEL_PERCENTILE(expr1, expr2)`
- **Omni target**: none
- **Default mapping**: emit warning. Recommend `SNOWFLAKE.ML.FORECAST` or BigQuery ML upstream.
- **Guardrails that override this**: `forecast_cluster_handling`
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-CALC-15: Spatial functions (MAKEPOINT, MAKELINE, DISTANCE, BUFFER, AREA)
- **Bucket** (audit 3.2): YELLOW
- **Tableau source** (TWBX 4.1): `MAKEPOINT(lat, lng)`, etc.
- **Omni target** (Omni 3.1): warehouse spatial functions (Snowflake `ST_MAKEPOINT`, etc.)
- **Default mapping**: dialect lookup, prefer `ST_*` (Snowflake / BigQuery / PostGIS).
- **Guardrails that override this**: none
- **Failure mode**: warehouse lacks spatial extension. Emit warning.
- **Verification**: distance / area values match a manual SQL query.

#### R-CALC-16: HEXBINX / HEXBINY
- **Bucket** (audit 3.2): RED
- **Tableau source** (TWBX 4.1): `HEXBINX(x, y, size)`
- **Omni target**: none
- **Default mapping**: emit warning. Pre-compute hex coordinates upstream.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-CALC-17: Forward references between calcs
- **Bucket** (audit 3.2): GREEN
- **Tableau source** (TWBX 4.4): `[CaptionA]` referenced inside `Calc B` defined earlier
- **Omni target** (Omni 3.2): Omni resolves `${field}` lazily
- **Default mapping**: build a DAG, but emit fields in any order. Omni's compile-time resolution handles forward refs.
- **Guardrails that override this**: none
- **Failure mode**: circular reference. Halt with explicit cycle path.
- **Verification**: Omni view compiles.

### R-DERIVED: Groups, sets, bins, hierarchies

#### R-DERIVED-01: Set (manual list)
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.9): `<set><member><value>...</value></member></set>`
- **Omni target** (Omni 3): boolean `yesno` dimension with `IN (...)`
- **Default mapping**:
```yaml
dimensions:
  is_in_top_customers:
    sql: |
      CASE WHEN ${TABLE}.customer_name IN ('Acme Inc','Globex') THEN true ELSE false END
    type: yesno
```
- **Guardrails that override this**: `set_handling`
- **Failure mode**: set member list exceeds 1000 entries. Emit warning, recommend a derived_table lookup.
- **Verification**: dimension boolean count matches Tableau set membership count.

#### R-DERIVED-02: Set (condition-based)
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.9): `<set><condition><expression>...</expression></condition></set>`
- **Omni target** (Omni 3): boolean dimension with `CASE WHEN <expr>`
- **Default mapping**:
```yaml
dimensions:
  high_value:
    sql: |
      CASE WHEN ${TABLE}.amount > 10000 THEN true ELSE false END
    type: yesno
```
- **Guardrails that override this**: `set_handling`
- **Failure mode**: expression references an aggregated field. Promote to a measure-level filter or demote to R-DERIVED-03.
- **Verification**: boolean count matches Tableau set.

#### R-DERIVED-03: Set (top-N)
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.9): `<set><top n='10' by='[m]' direction='TOP'>`
- **Omni target** (Omni 3): pre-rank in SQL, filter by rank
- **Default mapping**: emit a hidden rank dimension and a `LESS_THAN_OR_EQUAL_TO` filter at the topic level. See R-FILTER-06 for filter shape.
- **Guardrails that override this**: `set_handling`
- **Failure mode**: top-N references an aggregation that requires viz-dim awareness. Emit warning.
- **Verification**: top-10 rows in Omni match Tableau set members.

#### R-DERIVED-04: Group (categorical-bin)
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.7): `<calculation class='categorical-bin'>` with `<bin><value>...</value></bin>`
- **Omni target** (Omni 3): dimension SQL with `CASE WHEN ... IN (...) THEN`
- **Default mapping**:
```yaml
dimensions:
  product_group:
    sql: |
      CASE
        WHEN ${TABLE}.PRODUCT_NAME IN ('Acme Widget','Acme Sprocket') THEN 'Acme Group'
        WHEN ${TABLE}.PRODUCT_NAME IN ('Globex Foo','Globex Bar') THEN 'Globex Group'
        ELSE ${TABLE}.PRODUCT_NAME
      END
    type: string
```
- **Guardrails that override this**: `group_handling`
- **Failure mode**: group references an aliased value. Resolve aliases first (R-FIELD-06), then group.
- **Verification**: distinct group labels match Tableau worksheet.

#### R-DERIVED-05: Numeric bin
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.8): `<calculation class='bin' column='[x]' size='1000'>`
- **Omni target** (Omni 3): dimension `FLOOR(x/size)*size`
- **Default mapping**:
```yaml
dimensions:
  amount_bin:
    sql: FLOOR(${TABLE}.AMOUNT / 1000) * 1000
    type: number
```
- **Guardrails that override this**: `bin_handling`
- **Failure mode**: size is 0 or null. Halt with explicit message.
- **Verification**: bin counts match Tableau histogram.

#### R-DERIVED-06: Hierarchy / drill-paths
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.11): `<drill-paths><drill-path><field>...</field></drill-path></drill-paths>`
- **Omni target** (Omni 3, 12): `drill_fields:` on measure plus `ai_context:` mention
- **Default mapping**:
```yaml
measures:
  total_sales:
    aggregate_type: sum
    sql: ${TABLE}.amount
    drill_fields: [country, state, city, postal_code]
```
- **Guardrails that override this**: `hierarchy_handling`
- **Failure mode**: hierarchy includes a calculated dim that does not exist as an Omni dimension. Promote that calc to a real dimension first.
- **Verification**: drill click in Omni cycles through the hierarchy.

### R-PARAM: Parameters

#### R-PARAM-01: Parameter list domain
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.10): `<parameter><domain type='list'><members><member value='...' alias='...'/>`
- **Omni target** (Omni 9.6): topic-level templated filter with `suggestion_list`
- **Default mapping**:
```yaml
filters:
  region_param:
    type: string
    default_filter: West
    suggestion_list: [West, East, Central, South]
    display_order: 1
```
- **Guardrails that override this**: `parameter_handling`
- **Failure mode**: member list dynamically computed from a field. Demote to a free-form `type: string`.
- **Verification**: Omni dashboard control shows the same options.

#### R-PARAM-02: Parameter range domain
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.10): `<domain type='range' min='...' max='...' granularity='...'>`
- **Omni target** (Omni 9.6): templated filter `type: number` or `type: timestamp`
- **Default mapping**: emit filter without min/max constraint and note the constraint in `description:`. Omni UI does not enforce numeric bounds.
- **Guardrails that override this**: `parameter_handling`
- **Failure mode**: granularity required for date stepping. Emit warning.
- **Verification**: user can enter values inside the documented range.

#### R-PARAM-03: Parameter any domain
- **Bucket** (audit 3.1): GREEN
- **Tableau source** (TWBX 3.10): `<domain type='any'>`
- **Omni target** (Omni 9.6): templated filter `type: string` with no suggestion list
- **Default mapping**:
```yaml
filters:
  search_text:
    type: string
    display_order: 2
```
- **Guardrails that override this**: `parameter_handling`
- **Failure mode**: none.
- **Verification**: free-form input accepted.

#### R-PARAM-04: Parameter referenced in a calc
- **Bucket** (audit 3.1): YELLOW
- **Tableau source** (TWBX 3.10, 4): `[Parameter 1]` token inside `<calculation formula='...'>`
- **Omni target** (Omni 9.6): `{{ filters.<view>.<field>.value }}` inside templated SQL
- **Default mapping**: replace every `[Parameter X]` reference with the Mustache filter token. Convert the calc to templated SQL.
- **Guardrails that override this**: `parameter_handling`
- **Failure mode**: parameter referenced inside a string literal. Escape carefully; emit warning.
- **Verification**: changing the control value re-renders the tile with new SQL.

### R-VIZ: Visualizations, marks, encodings, axes

#### R-VIZ-01: Bar mark
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.6): `<mark class='Bar'/>`
- **Omni target** (Omni 8.5): `visType: basic`, `mark.type: bar`
- **Default mapping**: Omni renders horizontal bars by default (Omni 11.7). Swap rows/columns vs Tableau: category on y, measure on series.
- **Guardrails that override this**: none
- **Failure mode**: too many categories for horizontal rendering. Emit warning, suggest vertical with `behaviors.rotated: true`.
- **Verification**: bar count and order match Tableau worksheet.

#### R-VIZ-02: Line mark
- **Bucket** (audit 3.3): GREEN
- **Tableau source** (TWBX 5.6): `<mark class='Line'/>`
- **Omni target** (Omni 8.4): `visType: basic`, `mark.type: line`
- **Default mapping**: x temporal, y quantitative. Direct map.
- **Guardrails that override this**: none
- **Failure mode**: non-temporal x with line mark. Emit warning (often a Tableau accident).
- **Verification**: line shape matches Tableau worksheet.

#### R-VIZ-03: Area mark
- **Bucket** (audit 3.3): GREEN
- **Tableau source** (TWBX 5.6): `<mark class='Area'/>`
- **Omni target** (Omni 8.1): `visType: basic`, `mark.type: area`
- **Default mapping**: direct.
- **Guardrails that override this**: none
- **Failure mode**: none.
- **Verification**: filled area matches Tableau.

#### R-VIZ-04: Circle / scatter mark
- **Bucket** (audit 3.3): GREEN
- **Tableau source** (TWBX 5.6): `<mark class='Circle'/>`
- **Omni target** (Omni 8.6): `visType: basic`, `mark.type: circle`
- **Default mapping**: direct.
- **Guardrails that override this**: none
- **Failure mode**: none.
- **Verification**: point count matches.

#### R-VIZ-05: Square / shape mark
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.6): `<mark class='Square'/>` or `<mark class='Shape'/>`
- **Omni target** (Omni 8.6, 8.11): basic `circle` with shape override, or Vega-Lite point with `shape` channel
- **Default mapping**: emit Vega-Lite with shape channel set to a unicode glyph if custom PNGs were used.
- **Guardrails that override this**: none
- **Failure mode**: custom PNG shapes from `<external><shapes>` cannot upload. Demote to R-VIZ-06.
- **Verification**: visual review of one tile.

#### R-VIZ-06: Custom shape PNG
- **Bucket** (audit 3.3): RED
- **Tableau source** (TWBX 2.4, 5.7): `<external><shapes>` referencing PNG file
- **Omni target**: none
- **Default mapping**: drop shape encoding; substitute Unicode glyph or default shape with warning.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning lists every dropped PNG.

#### R-VIZ-07: Text table
- **Bucket** (audit 3.3): GREEN
- **Tableau source** (TWBX 5.6): `<mark class='Text'/>`
- **Omni target** (Omni 8.7): `visType: omni-spreadsheet` or `omni-table`
- **Default mapping**: emit spreadsheet visType with columns from the encoding shelves.
- **Guardrails that override this**: none
- **Failure mode**: none.
- **Verification**: row count and column order match.

#### R-VIZ-08: Pie / donut
- **Bucket** (audit 3.3): GREEN
- **Tableau source** (TWBX 5.6): `<mark class='Pie'/>`
- **Omni target** (Omni 8.1): `visType: basic`, `configType: arc`
- **Default mapping**: direct. Donut uses same configType with inner radius.
- **Guardrails that override this**: none
- **Failure mode**: too many slices (>12) renders poorly. Emit warning.
- **Verification**: slice angles sum to 360.

#### R-VIZ-09: Map (filled / symbol)
- **Bucket** (audit 3.3): YELLOW (filled) / GREY (symbol)
- **Tableau source** (TWBX 5.6): `<mark class='Map'/>`
- **Omni target** (Omni 8.1, 8.11): `visType: map` or `vegalite` geoshape
- **Default mapping**: Vega-Lite geoshape against `https://vega.github.io/vega-datasets/data/us-10m.json` (or world TopoJSON). Use the bound dimension as the lookup key.
- **Guardrails that override this**: none
- **Failure mode**: geo encoding ambiguous (state vs county vs ZIP). Emit warning naming candidate lookups.
- **Verification**: shape count matches Tableau.

#### R-VIZ-10: Dual axis (synchronized)
- **Bucket** (audit 3.3): GREY
- **Tableau source** (TWBX 5.10): `<panes synchronized='true'>` with two `<pane>` children
- **Omni target** (Omni 8.4): `y2` axis (thin docs) or Vega-Lite layered
- **Default mapping**: Vega-Lite layered spec, `resolve.scale.y: 'shared'`.
- **Guardrails that override this**: `dual_axis_strategy`
- **Failure mode**: more than 2 panes. Emit warning.
- **Verification**: both series render on the same axis with matching scale.

#### R-VIZ-11: Dual axis (independent)
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.10): `<panes synchronized='false'>`
- **Omni target** (Omni 8.11): Vega-Lite layered with `resolve.scale.y: 'independent'`
- **Default mapping**: layered spec with independent y scales.
- **Guardrails that override this**: `dual_axis_strategy`
- **Failure mode**: same as R-VIZ-10.
- **Verification**: each series has its own y axis.

#### R-VIZ-12: Combined axis (Measure Names / Values)
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.4): `<rows>` or `<cols>` containing `[Multiple Values]`
- **Omni target** (Omni 8.4): multiple `series[]` entries on shared y axis
- **Default mapping**: one `series` per measure, same `yAxis: y`.
- **Guardrails that override this**: none
- **Failure mode**: measures have incompatible scales. Demote to R-VIZ-11.
- **Verification**: legend shows all measures.

#### R-VIZ-13: Trellis / small multiples
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.5): multi-pill rows/columns producing facet
- **Omni target** (Omni 8.11, 6.1): Vega-Lite `facet` or multiple tiles
- **Default mapping**: Vega-Lite facet for single-tile, or N tiles for dashboard-level static repetition. Static repetition loses cross-facet reactivity.
- **Guardrails that override this**: none
- **Failure mode**: facet dimension has >50 distinct values. Emit warning.
- **Verification**: facet count matches Tableau.

#### R-VIZ-14: Density / heatmap
- **Bucket** (audit 3.3): GREEN
- **Tableau source** (TWBX 5.6): `<mark class='Density'/>`
- **Omni target** (Omni 8.1): basic heatmap
- **Default mapping**: direct.
- **Guardrails that override this**: none
- **Failure mode**: none.
- **Verification**: cell color gradient matches.

#### R-VIZ-15: Forecast (analytics object)
- **Bucket** (audit 3.3): RED
- **Tableau source** (TWBX 5.12): `<forecast>` element with model parameters
- **Omni target**: none
- **Default mapping**: emit warning. If `forecast_cluster_handling: precompute_snowflake`, generate a stub dbt model spec.
- **Guardrails that override this**: `forecast_cluster_handling`
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-VIZ-16: Cluster analysis
- **Bucket** (audit 3.3): RED
- **Tableau source** (TWBX 5.12): `<cluster k='...'>` element
- **Omni target**: none
- **Default mapping**: emit warning. If `forecast_cluster_handling: precompute_snowflake`, recommend a clustering dbt model.
- **Guardrails that override this**: `forecast_cluster_handling`
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-VIZ-17: Reference line / band / distribution
- **Bucket** (audit 3.3): GREY (native) / YELLOW (Vega-Lite fallback)
- **Tableau source** (TWBX 5.12): `<reference-line>`, `<reference-band>`, `<reference-distribution>`
- **Omni target** (Omni 8.12): `visConfig.referenceLines[]` (thin docs) or Vega-Lite `rule`/`rect`
- **Default mapping**: Vega-Lite `rule` mark for line; `rect` mark for band.
- **Guardrails that override this**: none
- **Failure mode**: reference line type `forecast` lands here. Demote to R-VIZ-15.
- **Verification**: line position matches Tableau value.

#### R-VIZ-18: Trend line
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.12): `<trend-line model='linear|log|exp|polynomial|power'>`
- **Omni target** (Omni 8.11): Vega-Lite `transform: [{regression: ..., method: ...}]`
- **Default mapping**: Vega-Lite regression transform. Method values: linear, log, exp, pow, quad, poly.
- **Guardrails that override this**: none
- **Failure mode**: trend confidence band requested. Emit warning, drop the band.
- **Verification**: regression slope sign matches Tableau.

#### R-VIZ-19: Sort (manual, computed, alphabetic, nested)
- **Bucket** (audit 3.3): GREEN (computed, alpha) / YELLOW (manual, nested)
- **Tableau source** (TWBX 5.11): `<sort class='manual|computed|alphabetic'>`
- **Omni target** (Omni 7.1): `queryJson.sorts[]`
- **Default mapping**: computed and alphabetic map directly. Manual sort emits a hidden ordering dimension with `CASE WHEN`.
```json
{"sorts": [{
  "null_sort": "OMNI_DEFAULT",
  "column_name": "view.total_sales",
  "is_column_sort": false,
  "sort_descending": true
}]}
```
- **Guardrails that override this**: none
- **Failure mode**: manual sort dictionary contains values not present in source data. CASE WHEN ELSE branch handles.
- **Verification**: row order matches Tableau worksheet.

#### R-VIZ-20: Tooltip with formatted text
- **Bucket** (audit 3.3): GREEN (basic) / YELLOW (styled runs)
- **Tableau source** (TWBX 5.7, 5.8): `<tooltip column='...'>` and `<formatted-text><run>...</run></formatted-text>`
- **Omni target** (Omni 8.4): `visConfig.tooltip[]` array
- **Default mapping**: one tooltip entry per `<tooltip>`. Collapse `<run>` formatting to plain text.
```json
"tooltip": [{"field": {"name": "view.notes"}}]
```
- **Guardrails that override this**: `tooltip_handling`
- **Failure mode**: tooltip references a measure not in the query. Add it to `queryJson.fields[]`.
- **Verification**: hover shows expected fields.

#### R-VIZ-21: Stacked / grouped / 100% stacked bars
- **Bucket** (audit 3.3): GREEN (stacked, grouped) / GREY (100% stacked)
- **Tableau source** (TWBX 5.6): `<mark class='Bar'/>` with `<encodings>` including color
- **Omni target** (Omni 8.5): `behaviors.stackMultiMark: true|false`
- **Default mapping**: stacked is the default; grouped sets `stackMultiMark: false`; 100% stacked uses `stack %` (key unverified, GREY).
- **Guardrails that override this**: none
- **Failure mode**: 100% stacked emits with placeholder key and warning.
- **Verification**: stack semantics match Tableau (visual).

#### R-VIZ-22: Gantt bar / waterfall / pareto
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.6, 5.10, 4.5): combinations of bar + running sum + dual axis
- **Omni target** (Omni 8.11): Vega-Lite layered
- **Default mapping**: composable templates. Gantt uses `x` plus `x2`. Waterfall uses bar with `y` plus `y2`. Pareto layers bar plus running-sum line.
- **Guardrails that override this**: none
- **Failure mode**: composability fails when source data lacks an explicit start/end pair. Emit warning.
- **Verification**: chart shape matches reference image.

#### R-VIZ-23: Box-and-whisker
- **Bucket** (audit 3.3): GREEN
- **Tableau source** (TWBX 5.6): `<mark class='Box Plot'/>`
- **Omni target** (Omni 8.1): `visType: basic`, `mark.type: boxplot`
- **Default mapping**: direct.
- **Guardrails that override this**: none
- **Failure mode**: none.
- **Verification**: quartile boundaries match.

#### R-VIZ-24: Histogram (Show Me)
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 3.8, 5.6): bin dimension plus bar
- **Omni target** (Omni 3, 8.5): emit a binned dimension via R-DERIVED-05, then bar tile
- **Default mapping**: two-stage emission.
- **Guardrails that override this**: none
- **Failure mode**: bin size 0. Demote to R-DERIVED-05.
- **Verification**: bin counts match Tableau histogram.

#### R-VIZ-25: Sparkline
- **Bucket** (audit 3.3): GREEN
- **Tableau source** (TWBX 5.6): line mark in a small cell context
- **Omni target** (Omni 8.8, 8.10): `omni-kpi` chart row OR markdown `<Sparkline>`
- **Default mapping**: KPI chart row is the cleaner path.
```json
{
  "visType": "omni-kpi",
  "spec": {"rows": [
    {"type": "number", "field": "view.sales", "format": "USDCURRENCY"},
    {"type": "chart", "field": "view.sales", "x": "view.month", "shape": "line", "height": 30}
  ]}
}
```
- **Guardrails that override this**: none
- **Failure mode**: time field missing. Emit warning.
- **Verification**: sparkline renders inside KPI tile.

#### R-VIZ-26: Bullet chart
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.6, Show Me): not enumerated in TWBX spec; standard combination of bar + reference + comparison
- **Omni target** (Omni 8.8): `omni-kpi` progress row
- **Default mapping**: KPI progress with `field` and `target`; lose comparison-band fidelity.
- **Guardrails that override this**: none
- **Failure mode**: comparison band required for the use case. Emit warning.
- **Verification**: target line appears.

#### R-VIZ-27: Polygon (custom spatial)
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.6): `<mark class='Polygon'/>` with `<encoding shelf='path'>`
- **Omni target** (Omni 8.11): Vega-Lite `geoshape`
- **Default mapping**: Vega-Lite spec with `mark: 'geoshape'` and bound spatial field.
- **Guardrails that override this**: none
- **Failure mode**: source data is point pairs, not GeoJSON. Emit warning.
- **Verification**: polygon renders.

#### R-VIZ-28: Mark Automatic
- **Bucket** (audit 3.3): YELLOW
- **Tableau source** (TWBX 5.6): `<mark class='Automatic'/>`
- **Omni target** (Omni 7, 11.6): `automaticVis: true` plus a concrete `visType: basic`
- **Default mapping**: emit `automaticVis: true` AND a concrete fallback `visType` matching what Tableau's auto-picker would have chosen, so the user sees the same chart.
- **Guardrails that override this**: none
- **Failure mode**: Tableau auto-pick rules differ from Omni. Emit warning.
- **Verification**: user reviews mark choice.

#### R-VIZ-29: Color encoding (discrete / continuous / diverging / stepped)
- **Bucket** (audit 3.3): YELLOW (discrete) / GREY (continuous, diverging, stepped)
- **Tableau source** (TWBX 5.7, 5.13): `<encoding shelf='color'>` plus `<map-color-discrete>` or `<map-color-continuous>`
- **Omni target** (Omni 8.13, 8.14): `visConfig.colors[]` / `seriesColors` / `colorScale`
- **Default mapping**: discrete walks `<map-color-discrete>` and emits `colors[]`. Continuous uses Vega-Lite color scale when Omni key is unverified.
- **Guardrails that override this**: `custom_palette_handling`
- **Failure mode**: palette referenced by name (e.g., "Tableau 20") with no inline colors. Look up from `tableau-20.xml` defaults; emit hardcoded hex.
- **Verification**: series colors match Tableau worksheet.

### R-FILTER: Filters

#### R-FILTER-01: Categorical multi-select / single-select / exclude
- **Bucket** (audit 3.4): GREEN
- **Tableau source** (TWBX 5.3, 9.1): `<filter class='categorical'>` with `<groupfilter function='union|exclude'>`
- **Omni target** (Omni 9.1, 9.2): `kind: STRING_IS` plus `values: []` plus optional `is_negative: true`
- **Default mapping**:
```json
{
  "sf_opportunities.stage_name": {
    "kind": "STRING_IS",
    "type": "string",
    "values": ["Closed Won", "Negotiation"],
    "is_negative": false
  }
}
```
- **Guardrails that override this**: none
- **Failure mode**: values exceed wire size limit. Emit warning, recommend a server-side filter view.
- **Verification**: filtered row count matches Tableau worksheet.

#### R-FILTER-02: Wildcard (contains, starts, ends, regex)
- **Bucket** (audit 3.4): GREEN (contains, starts, ends, exactly) / YELLOW (regex)
- **Tableau source** (TWBX 5.3): `<filter class='wildcard' match-pattern='...'>` with `<criteria match-type='Contains|StartsWith|EndsWith|RegEx'>`
- **Omni target** (Omni 9.2): `kind: STRING_CONTAINS|STRING_STARTS_WITH|STRING_ENDS_WITH`; regex uses YAML `matches_regex` operator
- **Default mapping**: direct enum map. Regex `kind` on JSON wire side is GREY; verify via export.
- **Guardrails that override this**: none
- **Failure mode**: regex pattern contains Tableau-specific syntax. Emit warning.
- **Verification**: pattern match count matches Tableau.

#### R-FILTER-03: Quantitative range
- **Bucket** (audit 3.4): GREEN
- **Tableau source** (TWBX 5.3): `<filter class='quantitative' include-values='in-range'><min>...<max>...`
- **Omni target** (Omni 9.2): `kind: BETWEEN` (inclusive) or `WITHIN_RANGE`
- **Default mapping**:
```json
{
  "view.amount": {
    "kind": "BETWEEN",
    "type": "number",
    "values": [1000, 50000],
    "is_negative": false
  }
}
```
- **Guardrails that override this**: none
- **Failure mode**: open-ended range. Use `GREATER_THAN_OR_EQUAL_TO` or `LESS_THAN_OR_EQUAL_TO`.
- **Verification**: filtered row count matches.

#### R-FILTER-04: Date range (calendar)
- **Bucket** (audit 3.4): GREEN
- **Tableau source** (TWBX 5.3): `<filter class='quantitative' column='[d]'><min>2024-01-01<max>2024-12-31`
- **Omni target** (Omni 9.2): `kind: WITHIN_RANGE`, `type: date`
- **Default mapping**: direct.
- **Guardrails that override this**: none
- **Failure mode**: time zone ambiguity. Default to warehouse-local; emit warning if Tableau-set TZ differs.
- **Verification**: row count matches.

#### R-FILTER-05: Relative date
- **Bucket** (audit 3.4): GREEN
- **Tableau source** (TWBX 5.3): `<filter class='relative-date' first-period='-3' last-period='0' period-type='month'>`
- **Omni target** (Omni 9.2): `kind: TIME_FOR_INTERVAL_DURATION` (the JSON form of YAML `time_for_duration`). The UI picker rendered is chosen by Omni from the shape of `left_side` / `right_side`, not from a separate kind. The symmetric form `[N units ago, N units]` renders as the "in the past N units" picker; the asymmetric form renders as the offset+duration range picker.
- **Default mapping** (the common "last N including current" pattern, Tableau `first=-(N-1), last=0`):
```json
{
  "view.closedate": {
    "kind": "TIME_FOR_INTERVAL_DURATION",
    "type": "date",
    "left_side": "4 months ago",
    "right_side": "4 months",
    "is_negative": false
  }
}
```
- **Alternate mapping** (true offset window, e.g. `first-period=-6, last-period=-3`):
```json
{
  "view.closedate": {
    "kind": "TIME_FOR_INTERVAL_DURATION",
    "type": "date",
    "left_side": "6 months ago",
    "right_side": "4 months",
    "is_negative": false
  }
}
```
- **Guardrails that override this**: none
- **Failure mode**: `TIME_FOR_UNIT_DURATION` is in the API's accepted kind enum but the query planner rejects it with "Invalid literal value". Do not emit it. Off-by-one bug: using `abs(first)` on the left_side (e.g. `"11 months ago"` for `first=-11, last=0`) gives the SAME data window but renders as a range picker rather than "in the past N", because Omni only picks the latter UI when the two sides match symmetrically.
- **Verification**: relative window updates as expected; UI picker matches the Tableau "Relative dates" dialog's intended shape (single-input "in the past N" vs. offset range).
- **Date-literal semantics**: `"N units ago"` resolves to `INTERVAL '-(N-1) unit'` truncated to the unit. `"N complete units ago"` resolves to `INTERVAL '-N unit'`. So `[12 months ago, 12 months]` covers 12 calendar months ending at the current month; `[12 complete months ago, 12 months]` covers 12 calendar months ending at the prior month.

#### R-FILTER-06: Top-N filter
- **Bucket** (audit 3.4): YELLOW
- **Tableau source** (TWBX 5.3): `<groupfilter function='end' direction='TOP' n='10'>`
- **Omni target** (Omni 7.1, 9): pre-rank in SQL plus `LESS_THAN_OR_EQUAL_TO`
- **Default mapping**: emit a hidden rank dimension (R-CALC-09) plus a numeric filter:
```yaml
dimensions:
  customer_sales_rank:
    sql: RANK() OVER (ORDER BY ${TABLE}.total_sales DESC)
    type: number
    hidden: true
```
```json
"filters": {
  "view.customer_sales_rank": {
    "kind": "LESS_THAN_OR_EQUAL_TO",
    "type": "number",
    "values": [10]
  }
}
```
- **Guardrails that override this**: none
- **Failure mode**: ranking field is a calculated measure. Materialize via derived_table.
- **Verification**: result has exactly 10 rows.

#### R-FILTER-07: Conditional filter (formula-based)
- **Bucket** (audit 3.4): YELLOW
- **Tableau source** (TWBX 5.3): `<filter class='condition'><condition><expression>`
- **Omni target** (Omni 9.6): templated filter with `bind_to` plus SQL OR HAVING clause via measure filter
- **Default mapping**: rewrite expression as SQL on a hidden boolean dimension; filter on that dimension.
- **Guardrails that override this**: none
- **Failure mode**: expression references an aggregation. Use Omni measure-level `filters:`.
- **Verification**: filtered count matches Tableau.

#### R-FILTER-08: Context filter
- **Bucket** (audit 3.4): RED
- **Tableau source** (TWBX 5.3): `<filter context='true'>`
- **Omni target**: none (concept evaporates)
- **Default mapping**: drop with note. Because FIXED LODs are materialized as derived tables (R-CALC-04), context filter's purpose disappears.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: filter not present in Omni output; row counts still correct.

#### R-FILTER-09: Cross-datasource filter
- **Bucket** (audit 3.4): YELLOW
- **Tableau source** (TWBX 5.3): per-target field references in `<filters-with-target>`
- **Omni target** (Omni 9.3): dashboard `filterConfig` with same field name across topics
- **Default mapping**: works only when both topics expose a shared dimension name. Use topic `joins:` aliases to enforce naming.
- **Guardrails that override this**: none
- **Failure mode**: shared field name not enforceable. Emit warning.
- **Verification**: filter applies to both tiles.

#### R-FILTER-10: Only relevant values / cascading
- **Bucket** (audit 3.4): RED
- **Tableau source** (TWBX 5.3): `user:ui-marker='cascade'`
- **Omni target**: none automatic
- **Default mapping**: drop. Manual scope of filter options requires per-filter query and is heavy.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-FILTER-11: Show apply button
- **Bucket** (audit 3.4): RED
- **Tableau source** (TWBX UI): `<window>` flag
- **Omni target**: none (Omni applies live)
- **Default mapping**: drop silently.
- **Guardrails that override this**: none
- **Failure mode**: none.
- **Verification**: filter behavior is reactive.

#### R-FILTER-12: Datasource filter
- **Bucket** (audit 3.4): GREEN
- **Tableau source** (TWBX 9.1): `<datasource><filter>` at datasource level
- **Omni target** (Omni 4.3): `always_where_filters:` on topic
- **Default mapping**:
```yaml
always_where_filters:
  view.is_deleted:
    is: false
```
- **Guardrails that override this**: none
- **Failure mode**: filter references a calc that does not exist as a dimension yet. Emit warning, recommend explicit dimension.
- **Verification**: topic queries exclude filtered rows.

#### R-FILTER-13: Extract filter
- **Bucket** (audit 3.4): YELLOW
- **Tableau source** (TWBX 3.12): `<extract><filter>`
- **Omni target**: dbt or upstream materialization
- **Default mapping**: emit warning recommending the filter be moved into a warehouse view or dbt model.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

### R-COLOR: Palettes and color encoding

#### R-COLOR-01: Custom categorical palette
- **Bucket** (audit 3.8): GREEN
- **Tableau source** (TWBX 2.2): `<color-palette type='regular' name='...'><color>#xxxxxx</color>`
- **Omni target** (Omni 8.14): `visConfig.colors[]` array of hex strings
- **Default mapping**: walk colors in order, emit hex array. If `custom_palette_handling: emit_brand_theme`, write once to model `ai_settings` and reference per tile.
- **Guardrails that override this**: `custom_palette_handling`
- **Failure mode**: palette has fewer colors than series. Cycle.
- **Verification**: tile colors match Tableau worksheet.

#### R-COLOR-02: Custom sequential / diverging palette
- **Bucket** (audit 3.8): GREY
- **Tableau source** (TWBX 2.2): `<color-palette type='ordered-sequential|ordered-diverging'>`
- **Omni target** (Omni 8.14): `visConfig.colorScale` (thin docs)
- **Default mapping**: emit Vega-Lite color scale with explicit start/end hex when Omni key unverified.
- **Guardrails that override this**: `custom_palette_handling`
- **Failure mode**: gradient with >3 stops. Emit warning.
- **Verification**: gradient shape matches.

#### R-COLOR-03: Workbook-level theme (org-level)
- **Bucket** (audit 3.8): RED
- **Tableau source** (TWBX 2.3): `<style>` block
- **Omni target**: none at model level
- **Default mapping**: drop with warning. Roadmap candidate.
- **Guardrails that override this**: `custom_palette_handling`
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-COLOR-04: Conditional formatting on text table
- **Bucket** (audit 3.3): YELLOW (static) / GREY (per-row logic)
- **Tableau source** (TWBX 8.3): `<style-rule><condition>`
- **Omni target** (Omni 8.7): `resultConfig.columnFormats`
- **Default mapping**: static per-column color emits directly. Per-row conditional logic (positive green, negative red) requires either an explicit SQL helper column or a heavy Vega-Lite spreadsheet workaround.
```json
"resultConfig": {
  "columnFormats": {
    "view.profit": {"format": "$#,##0", "color": "#1b5e20"}
  }
}
```
- **Guardrails that override this**: none
- **Failure mode**: condition references aggregations. Emit warning.
- **Verification**: cell color matches Tableau.

### R-DASH: Dashboards (layout, zones, sizing, multi-tab)

#### R-DASH-01: Tiled layout (root)
- **Bucket** (audit 3.6): GREEN
- **Tableau source** (TWBX 6.1, 6.2): root `<dashboard>` with `<zones>` tree
- **Omni target** (Omni 6.3): `metadata.layouts.lg` 12-column grid
- **Default mapping**: flatten zone tree to grid cells via the algorithm in audit 5.19.
- **Guardrails that override this**: none
- **Failure mode**: zone tree contains overlapping or zero-area zones. Skip with warning.
- **Verification**: every tile fits inside 12 columns and does not overlap.

#### R-DASH-02: Floating layout (absolute pixels)
- **Bucket** (audit 3.6): RED
- **Tableau source** (TWBX 6.4): `<zone floating='true' x='...' y='...' w='...' h='...'>`
- **Omni target**: none (grid-only)
- **Default mapping**: snap to nearest grid cell using R-DASH-01 algorithm.
- **Guardrails that override this**: `floating_zone_handling`
- **Failure mode**: floating zone overlaps a tiled zone. Emit warning, keep tiled.
- **Verification**: tile lands at expected grid position.

#### R-DASH-03: Container (horizontal / vertical flow)
- **Bucket** (audit 3.6): YELLOW
- **Tableau source** (TWBX 6.2): `<zone container-type='horizontal|vertical'>`
- **Omni target** (Omni 6.3): tiles laid in matching x/y bands
- **Default mapping**: flatten flow into explicit grid positions. Loses dynamic re-flow.
- **Guardrails that override this**: `floating_zone_handling`
- **Failure mode**: nested containers > 3 deep. Emit warning.
- **Verification**: visual review.

#### R-DASH-04: Sizing (fixed / automatic / range)
- **Bucket** (audit 3.6): GREEN (auto) / YELLOW (fixed) / RED (range)
- **Tableau source** (TWBX 6.1): `<size value='800,600'>` or `<size sizing-mode='automatic'>`
- **Omni target** (Omni 6.3): always responsive
- **Default mapping**: drop pixel dimensions; rely on Omni responsive grid.
- **Guardrails that override this**: none
- **Failure mode**: workbook designed for specific aspect ratio. Emit warning.
- **Verification**: dashboard fits on screen at standard sizes.

#### R-DASH-05: Worksheet zone
- **Bucket** (audit 3.6): GREEN
- **Tableau source** (TWBX 6.2): `<zone type-v2='worksheet' name='SheetName'>`
- **Omni target** (Omni 6.2, 7): `queryPresentation` tile in `metadata.layouts.lg`
- **Default mapping**: one worksheet to one tile. Worksheet definition feeds `queryJson` and `visConfig`.
- **Guardrails that override this**: none
- **Failure mode**: worksheet uses unsupported mark (e.g., custom shape only). Demote tile with warning.
- **Verification**: tile renders.

#### R-DASH-06: Text / image / web / blank zones
- **Bucket** (audit 3.6): GREEN (text, blank) / YELLOW (image, web)
- **Tableau source** (TWBX 6.2): `<zone type-v2='text|image|web|blank'>`
- **Omni target** (Omni 6.6): `metadata.textTiles[]` markdown tile
- **Default mapping**: text emits markdown directly. Image must be externally hosted; emit `<img src='...'>`. Web emits `<iframe>` (JS stripped). Blank just leaves a gap.
```json
{"i": "1", "spec": {"markdown": "# Sales Overview"}}
```
- **Guardrails that override this**: none
- **Failure mode**: image is TWBX-embedded only (Image/ folder). Upload externally first; emit warning if external URL not provided.
- **Verification**: tile renders.

#### R-DASH-07: Extension zone (.trex)
- **Bucket** (audit 3.6): RED
- **Tableau source** (TWBX 6.2): `<zone type-v2='extension'>` plus `.trex` config
- **Omni target**: none
- **Default mapping**: drop with explicit warning naming the extension.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-DASH-08: Show / hide containers
- **Bucket** (audit 3.6): RED
- **Tableau source** (TWBX 6.2, UI only): show/hide button widget
- **Omni target**: none
- **Default mapping**: drop with warning.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-DASH-09: Dashboard filter applied to multiple sheets
- **Bucket** (audit 3.6): GREEN
- **Tableau source** (TWBX 6.5): `<filters-with-target>`
- **Omni target** (Omni 9.3, 9.5): dashboard-level `filterConfig` with default scope
- **Default mapping**: emit a single `filterConfig` entry; let Omni auto-apply to tiles using that field.
- **Guardrails that override this**: none
- **Failure mode**: target field name differs across topics. Use R-FILTER-09 fix.
- **Verification**: all targeted tiles filter together.

#### R-DASH-10: Multi-tab (from stories or multi-sheet dashboards)
- **Bucket** (audit 3.6, 3.7): GREY
- **Tableau source** (TWBX 7): `<story><story-points>` or workbook with multiple dashboards
- **Omni target** (Omni 6.4): multi-tab dashboard JSON (thin docs)
- **Default mapping**: with `multi_tab_handling: separate_dashboards`, emit one dashboard per story point or sheet, plus cross-dashboard navigation buttons.
- **Guardrails that override this**: `multi_tab_handling`
- **Failure mode**: story has frozen filter state per point. Per-tab default filters are GREY.
- **Verification**: each dashboard renders independently.

#### R-DASH-11: Device-specific layouts (phone, tablet)
- **Bucket** (audit 3.6): RED
- **Tableau source** (TWBX 6.1): `<device-layouts><device-layout device='phone'>`
- **Omni target**: none device-conditioned
- **Default mapping**: drop device layouts, keep only desktop. Rely on Omni responsive grid.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: dashboard renders on mobile via Omni's responsive grid (visual review).

### R-ACTION: Dashboard actions

#### R-ACTION-01: Filter action (click to filter)
- **Bucket** (audit 3.6): YELLOW
- **Tableau source** (TWBX 6.6): `<filter-action>`
- **Omni target** (Omni 6.5): `dashboard.crossfilterEnabled: true`
- **Default mapping**: enable crossfilter at dashboard level. Per-tile filter override (`tileFilterMap`) is GREY.
- **Guardrails that override this**: none
- **Failure mode**: action requires specific source-to-target field mapping. Document only.
- **Verification**: clicking in one tile filters another (manual).

#### R-ACTION-02: Highlight action
- **Bucket** (audit 3.6): RED
- **Tableau source** (TWBX 6.6): `<highlight-action>`
- **Omni target**: none
- **Default mapping**: drop with warning, or substitute crossfilter if `highlight_action_handling: crossfilter_substitute`.
- **Guardrails that override this**: `highlight_action_handling`
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-ACTION-03: URL action
- **Bucket** (audit 3.6): YELLOW
- **Tableau source** (TWBX 6.6): `<url-action><url>https://...<FIELD></url>`
- **Omni target** (Omni 3.2, 6.6): dimension `link:` or markdown tile link
- **Default mapping**: dimension `link:` is the cleaner path:
```yaml
dimensions:
  region:
    sql: ${TABLE}.REGION
    link:
      url: "https://my.salesforce.com/{{ value }}"
      label: "Open in Salesforce"
```
- **Guardrails that override this**: none
- **Failure mode**: URL references a field not bound to this row. Use `{{ row.<view.field> }}` template.
- **Verification**: link opens with expected URL.

#### R-ACTION-04: Navigation action (go to dashboard)
- **Bucket** (audit 3.6): YELLOW
- **Tableau source** (TWBX 6.6): `<navigation-action target-dashboard='...'>`
- **Omni target** (Omni 6.5, 6.6): cross-dashboard markdown link
- **Default mapping**: emit a markdown tile with a button-styled link. JSON shape is GREY.
- **Guardrails that override this**: none
- **Failure mode**: target dashboard ID not resolvable at emit time. Emit warning with placeholder.
- **Verification**: link navigates.

#### R-ACTION-05: Parameter action
- **Bucket** (audit 3.6): RED
- **Tableau source** (TWBX 6.6): `<parameter-action>`
- **Omni target**: none direct (Omni 9.5 is GREY)
- **Default mapping**: drop with warning. Suggest manual filter as substitute.
- **Guardrails that override this**: `parameter_handling`
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-ACTION-06: Set action
- **Bucket** (audit 3.6): RED
- **Tableau source** (TWBX 6.6): `<set-action>`
- **Omni target**: none
- **Default mapping**: drop with warning.
- **Guardrails that override this**: `set_action_handling`
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

### R-STORY: Stories

#### R-STORY-01: Story container
- **Bucket** (audit 3.7): YELLOW
- **Tableau source** (TWBX 7): `<story>`
- **Omni target** (Omni 6.4): multi-tab dashboard or sequence of linked dashboards
- **Default mapping**: see R-DASH-10. Default to separate dashboards.
- **Guardrails that override this**: `multi_tab_handling`
- **Failure mode**: story has dependencies between points. Emit warning.
- **Verification**: navigation path matches Tableau story.

#### R-STORY-02: Story point
- **Bucket** (audit 3.7): GREY
- **Tableau source** (TWBX 7): `<story-points><story-point>`
- **Omni target** (Omni 6.4): one tab in a multi-tab dashboard (GREY)
- **Default mapping**: under `multi_tab_handling: separate_dashboards`, one story point becomes one dashboard. Resolution plan: build a 2-tab dashboard in Omni UI, export, copy the structure (audit 7.1).
- **Guardrails that override this**: `multi_tab_handling`
- **Failure mode**: per-point frozen filter state not preserved.
- **Verification**: each point renders.

#### R-STORY-03: Frozen filter state per story point
- **Bucket** (audit 3.7): YELLOW
- **Tableau source** (TWBX 7): point-level `<filter>` overrides
- **Omni target** (Omni 9.3): per-tab default filter values
- **Default mapping**: under `multi_tab_handling: separate_dashboards`, encode filter state in each dashboard's default `filterConfig`.
- **Guardrails that override this**: `multi_tab_handling`
- **Failure mode**: filter references story-only field. Emit warning.
- **Verification**: dashboard opens with expected filters applied.

#### R-STORY-04: Navigator style
- **Bucket** (audit 3.7): GREY (dot, caption) / RED (number, arrows-only)
- **Tableau source** (TWBX 7): `<story navigator-style='dot|caption|number|arrows-only'>`
- **Omni target**: Omni tab UI variants not enumerated
- **Default mapping**: drop style preference; use Omni default tab UI.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode for `number` and `arrows-only`.
- **Verification**: warning appears for unsupported styles.

#### R-STORY-05: Annotations on story points
- **Bucket** (audit 3.7): YELLOW
- **Tableau source** (TWBX 7): `<story-point><caption>` plus `<formatted-text>`
- **Omni target** (Omni 6.6): markdown tile per tab / dashboard
- **Default mapping**: emit a markdown tile at top of each tab/dashboard with the caption as the title.
- **Guardrails that override this**: none
- **Failure mode**: caption contains rich formatting. Collapse to plain text.
- **Verification**: caption appears.

### R-FORMAT: Numbers, dates, fonts, banding

#### R-FORMAT-01: Number format strings (Excel-like)
- **Bucket** (audit 3.8): GREEN
- **Tableau source** (TWBX 8.4): `<format format='#,##0.00;-#,##0'>` or `default-format` attribute
- **Omni target** (Omni 3.4, 8.13): `format:` or `value_format:` field
- **Default mapping**: direct paste, Excel-compatible.
- **Guardrails that override this**: `format_string_dialect`
- **Failure mode**: format uses Tableau-specific tokens (e.g., `[Custom]:c0`). Translate via R-FORMAT-02.
- **Verification**: rendered cell matches Tableau.

#### R-FORMAT-02: Format string shortcuts
- **Bucket** (audit 3.8): YELLOW
- **Tableau source** (TWBX 8.4): `default-format='c0'`, `'p1%'`, `'n2'`, `'s'`
- **Omni target** (Omni 3.4): long-form Excel string OR named format
- **Default mapping**: lookup table:
```yaml
# Tableau -> Omni format
c0:   "$#,##0"
c2:   "$#,##0.00"
n0:   "#,##0"
n2:   "#,##0.00"
p0%:  "0%"
p1%:  "0.0%"
p2%:  "0.00%"
s:    "0.00E+00"
```
- **Guardrails that override this**: `format_string_dialect`
- **Failure mode**: shortcut not in table. Emit best-guess plus warning.
- **Verification**: rendered cell matches Tableau.

#### R-FORMAT-03: Date format strings
- **Bucket** (audit 3.8): GREEN
- **Tableau source** (TWBX 8.4): `format='yyyy-MM-dd'`
- **Omni target** (Omni 3.4): direct paste
- **Default mapping**: pass through.
- **Guardrails that override this**: `format_string_dialect`
- **Failure mode**: locale-specific tokens (e.g., `MMM` for short month name). Document.
- **Verification**: rendered date matches.

#### R-FORMAT-04: Custom format with conditional sections
- **Bucket** (audit 3.8): GREEN
- **Tableau source** (TWBX 8.4): `format='[Red]<0;[Green]>=0'`
- **Omni target** (Omni 3.4): `value_format:` same syntax
- **Default mapping**: pass through.
- **Guardrails that override this**: `format_string_dialect`
- **Failure mode**: condition references aggregation. Demote to R-COLOR-04.
- **Verification**: positive vs negative colors match.

#### R-FORMAT-05: Fonts and per-mark font sizing
- **Bucket** (audit 3.8): RED
- **Tableau source** (TWBX 8.6): `<font name='...' size='...'>`
- **Omni target**: dashboard-level only via spec
- **Default mapping**: drop per-mark fonts with warning. Keep workbook-level theme if present (also RED, see R-COLOR-03).
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning lists every dropped font.

#### R-FORMAT-06: Row / column banding
- **Bucket** (audit 3.8): GREEN
- **Tableau source** (TWBX 8.5): `<band>` element on table view
- **Omni target** (Omni 8.7): `resultConfig.rowBanding: true`
- **Default mapping**: direct.
- **Guardrails that override this**: none
- **Failure mode**: custom band color. Emit warning, drop the custom color.
- **Verification**: alternating rows render.

#### R-FORMAT-07: Borders and gridlines
- **Bucket** (audit 3.8): GREY
- **Tableau source** (TWBX 5.5, 8.5): `<border>` styling
- **Omni target** (Omni 8.7): spreadsheet rendering defaults
- **Default mapping**: drop; emit warning only if borders are load-bearing for the tile.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-FORMAT-08: Dashboard background color / image
- **Bucket** (audit 3.8): GREY (color) / YELLOW (image)
- **Tableau source** (TWBX 2.3, 8.5): `<style><format attr='dashboard-bg-color'>`
- **Omni target** (Omni 6.6): markdown tile or per-tile (GREY for dashboard-level)
- **Default mapping**: emit a full-width markdown tile with `<div>` background if background-image is required. Otherwise drop.
- **Guardrails that override this**: none
- **Failure mode**: image referenced by file path inside TWBX zip. Externalize first.
- **Verification**: visual review.

### R-OTHER: Misc

#### R-OTHER-01: Mark annotations
- **Bucket** (audit 3.9): RED
- **Tableau source**: annotation XML element (not enumerated in TWBX spec sections shown)
- **Omni target**: none
- **Default mapping**: drop with warning.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-OTHER-02: Viz-in-tooltip
- **Bucket** (audit 3.9): RED
- **Tableau source**: Tableau interactive feature, not in TWBX spec sections
- **Omni target**: none
- **Default mapping**: drop with warning.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

#### R-OTHER-03: Subscriptions / email alerts
- **Bucket** (audit 3.9): YELLOW
- **Tableau source**: Tableau Server feature (not in TWBX)
- **Omni target** (Omni 10): `omni schedules` CLI
- **Default mapping**: re-create on Omni side, not migrated automatically. Emit a planning note.
- **Guardrails that override this**: none
- **Failure mode**: subscription config not visible from TWBX. Document only.
- **Verification**: manual.

#### R-OTHER-04: Permissions
- **Bucket** (audit 3.9): YELLOW
- **Tableau source**: Tableau Server feature (not in TWBX)
- **Omni target** (Omni 2, 3, 4): `access_grants`, `access_filters`, `required_access_grants`
- **Default mapping**: re-create on Omni side, not migrated.
- **Guardrails that override this**: none
- **Failure mode**: permission scope unknown. Document only.
- **Verification**: manual.

#### R-OTHER-05: Workbook-level actions
- **Bucket** (audit 3.9): RED
- **Tableau source** (TWBX 2.1): `<workbook><actions>`
- **Omni target**: none
- **Default mapping**: drop. Rare in practice.
- **Guardrails that override this**: none
- **Failure mode**: this IS the failure mode.
- **Verification**: warning appears.

---

## Decisions ledger

| date | rule_id(s) | decision | rationale | who |
|---|---|---|---|---|
| YYYY-MM-DD | R-CALC-04, R-CALC-05, R-CALC-06 | lod_placement: model_layer | LOD belongs in the model so downstream tiles inherit it and stay consistent | (owner) |
|  |  |  |  |  |
|  |  |  |  |  |
|  |  |  |  |  |
|  |  |  |  |  |

---

## Emitter contract

The eventual format-emitter tool consumes this file as runtime config. Contract:

1. **Parse YAML guardrails block** at the top of this file into a typed dict. Reject unknown keys (typo guard). Validate enum values against the inline comments.
2. **For each rule referenced by emitter code**, look up the rule by its stable ID (`R-FAMILY-NN`). Rule IDs survive forever. Deprecated rules are marked DEPRECATED, never renumbered.
3. **Apply guardrails before defaults.** If a guardrail names a rule and assigns a non-default value, the emitter follows the guardrail's branch in the rule body. Where the rule body has no branch for that value, the emitter raises a configuration error pointing at this file.
4. **Bucket=RED with no override**: write a structured warning to the migration report (file: `migration-warnings.md`) naming the rule ID, the TWBX section, the affected workbook entity (datasource / worksheet / dashboard / tile), and the recommended manual action. Continue.
5. **Bucket=GREY**: emit the default mapping plus a `# TODO: verify against Omni instance export` comment in the output YAML/JSON. Continue.
6. **Fidelity threshold**: each emitted tile carries a fidelity score (1.0 minus 0.1 per YELLOW rule applied, minus 0.3 per RED rule dropped). If `fidelity_threshold_for_rejection` is exceeded (score falls below the threshold), the emitter raises rather than emits.
7. **Decisions ledger**: every guardrail change must be appended as a row before the change ships. The ledger is the audit trail for why the emitter behaves the way it does.
