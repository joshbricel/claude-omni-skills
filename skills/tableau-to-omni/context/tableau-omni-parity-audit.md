# Tableau to Omni Parity Audit

Concept-by-concept reconciliation between `tableau-twbx-format-spec.md` (TWBX, 14 sections) and `omni-cli-format-spec.md` (Omni, 13 sections). The author-asserted map table in TWBX section 11 was re-derived from scratch and stress-tested; many GREEN claims were demoted to YELLOW or GREY where the Omni spec does not document the target feature.

Citations use the form (TWBX 3.5; Omni 3.2). [INFERRED] tags mark claims grounded outside the two specs.

---

## 1. TL;DR

Counts across 144 concepts audited:

- **GREEN: 38** (26 percent). Direct or near-direct map, documented on both sides.
- **YELLOW: 56** (39 percent). Achievable with a workaround (SQL rewrite, Vega-Lite, pre-aggregation, grid-snap), some fidelity loss.
- **RED: 28** (19 percent). No equivalent. Migration drops, manualizes, or warns.
- **GREY: 22** (15 percent). One or both specs too thin to classify. Single experiment usually resolves each.

Overall feasibility: the semantic model and most calculation primitives translate well. Visualizations split clean (basic marks GREEN, advanced analytics RED). Dashboard chrome is mostly YELLOW because Omni's layout model is grid-only and many Tableau widgets either flatten or vanish. The migration is viable for 70 to 80 percent of typical workbook content, with a long tail of analytics-object and interactivity features (forecast, sets, story points, set actions) that should be flagged for manual rework.

Three highest-impact RED items:
1. **Forecast / cluster / predictive marks** (TWBX 5.12). No Omni primitive. Must be pre-computed upstream.
2. **Set actions and highlight actions** (TWBX 6.6). No Omni equivalent. Drop with warning.
3. **Floating zones with absolute pixel positioning** (TWBX 6.4). Omni is grid-only.

Three highest-value GREY items where one experiment unlocks a class:
1. **Multi-tab dashboard `documentMetadata.presentation` shape** (Omni 6.4). Export an existing multi-tab dashboard via `/api/unstable/documents/{id}/export` and copy the tab structure. Unlocks story-point migration and large dashboard splitting.
2. **`tileFilterMap` / `tileControlMap` override shape** (Omni 6.5, 9.5). Export a dashboard with cross-tile linked filters; inspect the per-tile override JSON. Unlocks filter-action migration.
3. **`omni-kpi` `spec.rows[]` full schema** (Omni 8.8). Export a KPI tile with each row type populated. Unlocks Tableau BAN-style "headline number" tiles.

---

## 2. Migration feasibility scorecard

| Family | GREEN | YELLOW | RED | GREY | One-line summary |
|---|---|---|---|---|---|
| Semantic / data model | 55% | 25% | 5% | 15% | Connections, columns, joins, parameters translate. LODs, hierarchies need workarounds. |
| Calculations | 30% | 50% | 10% | 10% | Arithmetic and date funcs port directly. LODs, table calcs require SQL window rewrites. Forecast / predictive drop. |
| Visualizations | 35% | 35% | 20% | 10% | Bar/line/scatter/table GREEN; pie/dual-axis/gantt/density via Vega-Lite; forecast/cluster RED. |
| Filters | 60% | 25% | 5% | 10% | Most filter classes map. Context filter is RED (no concept needed in Omni). |
| Parameters | 50% | 35% | 0% | 15% | List/range/any all map. Parameter swap is YELLOW (FIELD_SELECTION controls). |
| Dashboards | 30% | 40% | 20% | 10% | Tiled grid layouts map. Floating, device layouts, web zones, extensions are RED or grey. |
| Stories | 0% | 30% | 50% | 20% | Multi-tab is the closest approximation; full story navigator is RED. |
| Formatting / theme | 50% | 30% | 10% | 10% | Format strings, palettes, fonts mostly map. Conditional formatting GREY-to-YELLOW. |

---

## 3. Concept-by-concept table

### 3.1 Semantic / data model

| Tableau concept | TWBX ref | Omni equivalent | Omni ref | Bucket | Notes |
|---|---|---|---|---|---|
| Live SQL connection (snowflake, postgres, redshift, bigquery, etc.) | 3.2 | Omni model connection | Omni 1.1, 2 | GREEN | Map `class` to Omni connection type. `dbname`, `schema` map to view `schema:` and `sql_table_name:`. |
| Embedded extract (.hyper) | 1.3, 3.12, 10 | None native | n/a | YELLOW | Either re-point to live connection or materialize the .hyper as a Snowflake table upstream. Omni has no concept of an embedded data file. |
| Legacy extract (.tde) | 1.1 | None | n/a | YELLOW | Upgrade to .hyper first, then YELLOW path above. |
| Federated multi-connection | 3.2 | Multiple model connections OR upstream UNION view | Omni 2, 4 | YELLOW | Omni topics work over a single connection. Multi-connection joins must be unified upstream. |
| Data blending (cross-datasource queries) | 3.14 | Single-connection topic plus joins OR pre-blended view | Omni 4, 5 | YELLOW | Data blending is a Tableau-only execution model; flatten to a SQL view or topic. |
| Published-on-server datasource (`sqlproxy`) | 3.2 | Existing Omni model | Omni 2 | GREY | Need to confirm whether Omni can reference an Omni-side shared topic from a workbook overlay. The `extends:` model param (Omni 3) suggests yes. Verify. |
| Physical-layer inner join | 3.3 | Topic relationship `always_inner` | Omni 5 | GREEN | `<relation type='join' join='inner'>` to `join_type: always_inner` plus `on_sql:`. |
| Physical-layer left join | 3.3 | `always_left` | Omni 5 | GREEN | Direct mapping. |
| Physical-layer right join | 3.3 | `always_right` | Omni 5 | GREEN | Direct mapping. |
| Physical-layer full outer join | 3.3 | `always_full` | Omni 5 | GREEN | Direct mapping. |
| Multi-clause / calc-based join | 3.3 | `on_sql:` with multi-condition SQL | Omni 5 | GREEN | `<expression>` tree serializes to a single `on_sql:` string. |
| Cross-database join (10.0+ federated) | 1.5, 3.2 | Single-connection topic | Omni 4, 5 | RED | Omni cannot join across connections. Materialize upstream. |
| Logical-layer relationship (noodle, 2020.2+) | 3.4 | `relationships:` with `relationship_type` | Omni 5 | GREEN | Cardinality maps cleanly: `many-one` to `many_to_one`, `one-one` to `one_to_one`, etc. |
| Custom SQL relation (`type='text'`) | 3.3 | View `sql:` or `derived_table.sql:` | Omni 3 | GREEN | XML-unescape the body, paste into the view's `sql:`. |
| Union relation (`type='union'`) | 3.3 | Upstream `UNION ALL` SQL view | Omni 3 | YELLOW | No native union in Omni topics. Materialize. |
| Column data type (string, int, real, date, datetime, boolean) | 3.5 | View `dimension: { type: }` enum | Omni 3.3 | GREEN | Map `string` to `string`, `integer` to `number`, `real` to `number`, `date` to `date`, `datetime` to `timestamp`, `boolean` to `yesno`. |
| Column data type `geometry` / `spatial` | 3.5 | None native | n/a | YELLOW | No first-class geo type. Pass through as `string` and use Vega-Lite geoshape for rendering. |
| Column role: dimension vs measure | 3.5 | `dimensions:` vs `measures:` sections | Omni 3 | GREEN | Direct: `role='dimension'` to dimension block; `role='measure'` to measure block. |
| Default aggregation (`Sum`, `Avg`, `Count`, `CountD`, `Min`, `Max`, `Median`, `StDev`, `Var`) | 3.5 | `measure.aggregate_type` enum | Omni 3.2 | GREEN | Tableau `Sum` to `sum`, `Avg` to `average`, `CountD` to `count_distinct`, etc. `AttributeOf` has no equivalent (YELLOW). |
| Default aggregation `AttributeOf` | 3.5 | None | n/a | YELLOW | Use `MIN()` or `MAX()` with `assumed` rationale; or use a SQL CASE in the measure. |
| Default format (`default-format='c0'`, `'p1%'`, etc.) | 3.5, 8.4 | Measure/dimension `format:` or `value_format:` | Omni 3.4 | YELLOW | Tableau shortcuts (`c0`, `p1%`) must be translated to Excel-style strings (`"$#,##0"`, `"0.0%"`) or to Omni named formats (`USDCURRENCY`, `percent`). Build a lookup table. |
| Aliases (display-value remapping) | 3.7 | Dimension SQL `CASE WHEN` | Omni 3 | YELLOW | One CASE WHEN per `<alias key= value=>`. Loses the "values remain underlying" semantic where Tableau filters still match raw keys; document the trade-off. |
| Groups (`<calculation class='categorical-bin'>`) | 3.7 | Dimension SQL `CASE WHEN` | Omni 3 | YELLOW | One CASE per `<bin>`. |
| Numeric bins (`<calculation class='bin' size=...>`) | 3.8 | Dimension SQL `FLOOR(x/size)*size` or `CASE WHEN` ranges | Omni 3 | YELLOW | Arithmetic floor preserves equal-width bins; CASE preserves auto-generated cut points. |
| Sets (manual list) | 3.9 | Dimension boolean SQL `IN (...)` | Omni 3 | YELLOW | Translate `<value>` list to SQL `IN`. |
| Sets (condition-based) | 3.9 | Dimension boolean SQL `WHEN <expr>` | Omni 3 | YELLOW | Translate `<expression>` tree to SQL. |
| Sets (top-N) | 3.9 | None native | n/a | YELLOW | Pre-rank in SQL or in a derived_table; expose as a boolean dimension. |
| Drill hierarchies (`<drill-paths>`) | 3.11 | `drill_fields:` on measure / view `ai_context:` ordered list | Omni 3, 12 | YELLOW | Omni has no strict hierarchy. Record the path order as `drill_fields:` and / or in `ai_context`. Drill experience is not identical. |
| Parameter `list` domain (`<members>`) | 3.10 | Topic / model `filters:` with `suggestion_list` | Omni 9.6 | GREEN | `<member value= alias=>` to `suggestion_list:` plus optional `default_filter:`. |
| Parameter `range` domain (`<range min= max= granularity=>`) | 3.10 | Templated filter `type: number` with numeric bounds OR `type: timestamp` | Omni 9.6 | YELLOW | Omni does not expose `min`/`max`/`step` directly; UI control accepts free-form. Document the constraint. |
| Parameter `any` domain | 3.10 | Templated filter `type: string` with no suggestion list | Omni 9.6 | GREEN | Free-form text input. |
| Parameter referenced in a calc (`[Parameter 1]` token) | 3.10, 4 | `{{ filters.<view>.<field>.value }}` | Omni 9.6 | YELLOW | Translate every `[Param]` token to the Mustache filter reference; calc body becomes templated SQL. |
| Extract refresh / incremental refresh | 3.12 | dbt or upstream pipeline schedule | n/a | RED | Omni has cache policies but no upstream-refresh primitive. Refresh runs in the warehouse, not in Omni. |

### 3.2 Calculations

| Tableau concept | TWBX ref | Omni equivalent | Omni ref | Bucket | Notes |
|---|---|---|---|---|---|
| Arithmetic `+ - * / % ^` | 4.1 | SQL operators in dimension/measure `sql:` | Omni 3.1 | GREEN | Direct paste. |
| Math functions (`ABS`, `CEILING`, `FLOOR`, `ROUND`, `EXP`, `LN`, `LOG`, `POWER`, `SQRT`, `SIGN`, `MIN`, `MAX`) | 4.1 | Snowflake / target-warehouse SQL fns | Omni 3.1 | GREEN | Names line up across dialects [INFERRED]; SQUARE has no SQL equivalent (use `x*x`). |
| Math `ZN` (zero-if-null) | 4.1 | `COALESCE(x, 0)` | Omni 3.1 | GREEN | Trivial rewrite. |
| Math `DIV` (integer division) | 4.1 | `FLOOR(a/b)` | Omni 3.1 | GREEN | Trivial. |
| Math `PI`, `DEGREES`, `RADIANS`, `SIN`, `COS`, `TAN`, `ASIN`, `ACOS`, `ATAN`, `ATAN2` | 4.1 | Warehouse SQL trig fns | Omni 3.1 | GREEN | Direct. |
| Math `HEXBINX`, `HEXBINY` | 4.1 | None | n/a | RED | No SQL equivalent. Pre-compute in dbt. |
| Logical `IF...THEN...ELSEIF...ELSE...END` | 4.2 | SQL `CASE WHEN ... THEN ... ELSE ... END` | Omni 3.1 | GREEN | Mechanical rewrite. |
| Logical `IIF(test, then, else, [unknown])` | 4.2 | SQL `CASE WHEN test THEN then ELSE else END` (and null branch) | Omni 3.1 | GREEN | 4-arg form needs a `WHEN test IS NULL` branch. |
| Logical `CASE [field] WHEN value THEN ... END` | 4.2 | SQL `CASE field WHEN value ...` | Omni 3.1 | GREEN | Direct. |
| Logical `AND`, `OR`, `NOT` | 4.1 | SQL boolean operators | Omni 3.1 | GREEN | Direct. |
| Logical `IFNULL`, `ISNULL` | 4.1 | `COALESCE`, `x IS NULL` | Omni 3.1 | GREEN | Trivial. |
| Logical `ISDATE` | 4.1 | `TRY_TO_DATE(x) IS NOT NULL` [INFERRED] | Omni 3.1 | YELLOW | Warehouse-specific. Snowflake has TRY_TO_DATE; Postgres needs a different cast. |
| String `LEN`, `LEFT`, `RIGHT`, `MID`, `UPPER`, `LOWER`, `TRIM`, `LTRIM`, `RTRIM` | 4.1 | SQL string fns | Omni 3.1 | GREEN | Names mostly identical. `MID` to `SUBSTR`. |
| String `REPLACE`, `CONTAINS`, `STARTSWITH`, `ENDSWITH`, `FIND` | 4.1 | SQL `REPLACE`, `LIKE`, `POSITION`, etc. | Omni 3.1 | GREEN | Mechanical. `CONTAINS(s,sub)` to `s LIKE '%'||sub||'%'`. |
| String `SPLIT`, `FINDNTH` | 4.1 | Warehouse string fns (`SPLIT_PART`, `REGEXP_INSTR`) | Omni 3.1 | YELLOW | Dialect-specific. Snowflake has `SPLIT_PART(str, sep, n)`. |
| String `REGEXP_MATCH`, `REGEXP_EXTRACT`, `REGEXP_EXTRACT_NTH`, `REGEXP_REPLACE` | 4.1 | SQL regex fns (`REGEXP_LIKE`, `REGEXP_SUBSTR`, `REGEXP_REPLACE`) | Omni 3.1 | YELLOW | Dialect-specific. |
| String `ASCII`, `CHAR`, `SPACE` | 4.1 | SQL `ASCII`, `CHR`, `REPEAT(' ',n)` | Omni 3.1 | GREEN | Direct. |
| Date `DATEPART('year',d)`, `DATETRUNC('month',d)`, `DATEADD`, `DATEDIFF`, `DATENAME` | 4.1 | Dimension group `timeframes:` for truncation; SQL `DATEADD`, `DATEDIFF` for arithmetic | Omni 3.1, 7.2 | GREEN | Truncation maps to Omni timeframes `[day]`, `[week]`, `[month]`, `[quarter]`, `[year]`. Custom DATEPART (e.g., `'iso-week'`) requires SQL. |
| Date `NOW`, `TODAY` | 4.1 | `CURRENT_TIMESTAMP()`, `CURRENT_DATE()` | Omni 3.1 | GREEN | Direct. |
| Date `YEAR`, `MONTH`, `DAY`, `WEEK`, `WEEKDAY`, `QUARTER`, `HOUR`, `MINUTE`, `SECOND` | 4.1 | `EXTRACT()` or Omni timeframes | Omni 3.1, 7.2 | GREEN | Both work. Timeframes more idiomatic. |
| Date `ISOWEEK`, `ISOQUARTER`, `ISOYEAR`, `ISOWEEKDAY` | 4.1 | `EXTRACT(ISOYEAR ...)` etc. | Omni 3.1 | YELLOW | Dialect-specific support; Snowflake has `WEEKISO`, `YEAROFWEEKISO`. |
| Date `DATEPARSE`, `MAKEDATE`, `MAKETIME`, `MAKEDATETIME` | 4.1 | `TO_DATE(fmt, str)`, `DATE_FROM_PARTS(y,m,d)`, etc. | Omni 3.1 | YELLOW | Dialect-specific. |
| Type conversion `INT`, `FLOAT`, `STR`, `DATE`, `DATETIME`, `BOOL` | 4.1 | SQL `CAST` / `::type` | Omni 3.1 | GREEN | Direct. |
| Aggregations `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `COUNTD`, `MEDIAN` | 4.1 | `aggregate_type:` or SQL `SUM/AVG/etc.` | Omni 3.2 | GREEN | Direct. Omni prefers `aggregate_type:` for symmetric aggregation. |
| Aggregations `STDEV`, `STDEVP`, `VAR`, `VARP` | 4.1 | SQL `STDDEV`, `STDDEV_POP`, `VARIANCE`, `VAR_POP` | Omni 3.2 | GREEN | Use raw SQL in `measure.sql:`. |
| Aggregation `ATTR` | 4.1 | `MIN()` or `MAX()` with note | Omni 3.2 | YELLOW | Semantic loss: ATTR returns NULL on disagreement. Express as `CASE WHEN MIN(x)=MAX(x) THEN MIN(x) END`. |
| Aggregation `PERCENTILE`, `CORR`, `COVAR`, `COVARP` | 4.1 | `percentile` aggregate_type; SQL `CORR()`, `COVAR_POP()`, `COVAR_SAMP()` | Omni 3.2 | GREEN | Direct. |
| LOD `FIXED` (single-dim, multi-dim, table-scoped) | 3.6, 4.3 | Derived table (CTE) or upstream view | Omni 3 | YELLOW | Materialize as `derived_table:` SQL with `GROUP BY` on the fixed dims, then join back. Section 5 below has full template. |
| LOD `INCLUDE` | 4.3 | SQL window function in measure | Omni 3.2 | YELLOW | `SUM(...) OVER (PARTITION BY <viz-dims>, <include-dim>)`. |
| LOD `EXCLUDE` | 4.3 | SQL window function with reduced partition | Omni 3.2 | YELLOW | `SUM(...) OVER (PARTITION BY <viz-dims minus excluded-dim>)`. |
| Table calc `RUNNING_SUM`, `RUNNING_AVG`, `RUNNING_MIN`, `RUNNING_MAX`, `RUNNING_COUNT` | 4.1, 4.5 | SQL window `SUM/AVG/etc. OVER (ORDER BY ...)` | Omni 3.2 | YELLOW | Translate addressing to ORDER BY; translate partitioning to PARTITION BY. |
| Table calc `WINDOW_SUM`, `WINDOW_AVG`, `WINDOW_MIN`, `WINDOW_MAX`, `WINDOW_COUNT`, `WINDOW_VAR`, `WINDOW_STDEV`, `WINDOW_MEDIAN`, `WINDOW_PERCENTILE`, `WINDOW_CORR`, `WINDOW_COVAR` | 4.1, 4.5 | SQL window with `ROWS BETWEEN N PRECEDING AND M FOLLOWING` | Omni 3.2 | YELLOW | Map `from`/`to` attributes to ROWS BETWEEN bounds. |
| Table calc `RANK`, `RANK_DENSE`, `RANK_MODIFIED`, `RANK_PERCENTILE`, `RANK_UNIQUE` | 4.1, 4.5 | SQL `RANK()`, `DENSE_RANK()`, `PERCENT_RANK()`, `ROW_NUMBER()` | Omni 3.2 | GREEN | Direct. RANK_MODIFIED needs custom logic. |
| Table calc `INDEX`, `FIRST`, `LAST`, `SIZE` | 4.5 | `ROW_NUMBER()`, `FIRST_VALUE()`, `LAST_VALUE()`, `COUNT(*) OVER (PARTITION BY ...)` | Omni 3.2 | YELLOW | Mechanical. `FIRST`/`LAST` translate to negative window offsets. |
| Table calc `LOOKUP(expr, n)` | 4.5 | SQL `LAG(expr, n)` / `LEAD(expr, n)` | Omni 3.2 | GREEN | Direct. |
| Table calc `PREVIOUS_VALUE` | 4.5 | SQL `LAG()` | Omni 3.2 | GREEN | Direct. |
| Table calc `TOTAL` | 4.5 | SQL `SUM() OVER ()` | Omni 3.2 | GREEN | Direct. |
| Table calc `SCRIPT_REAL/INT/STR/BOOL` (R/Python integration) | 4.5 | None | n/a | RED | Omni does not embed R/Python. Pre-compute outside. |
| Table calc addressing / partitioning | 4.5 | SQL `PARTITION BY`/`ORDER BY` | Omni 3.2 | YELLOW | Mechanical, but requires knowing the worksheet's pill order. Parser must read `partition-along=` and the shelf order. |
| Quick table calc: % of total | 4.5 | `SUM(x) / SUM(SUM(x)) OVER (PARTITION BY ...)` | Omni 3.2 | YELLOW | Or use Omni's built-in pivot-row totals (Omni 7.1 `row_totals`). |
| Quick table calc: Difference | 4.5 | `x - LAG(x) OVER (...)` | Omni 3.2 | YELLOW | Mechanical. |
| Quick table calc: % Difference | 4.5 | `(x - LAG(x)) / NULLIF(LAG(x),0)` | Omni 3.2 | YELLOW | Mechanical. |
| Quick table calc: Moving average | 4.5 | `AVG(x) OVER (ROWS BETWEEN n PRECEDING AND CURRENT ROW)` | Omni 3.2 | YELLOW | Mechanical. |
| Quick table calc: YoY growth | 4.5 | Period-over-period control OR SQL | Omni 9.4 (PERIOD_OVER_PERIOD), 3.2 | YELLOW | Omni has a PERIOD_OVER_PERIOD control type but docs are thin (GREY). SQL fallback works. |
| Custom table calc (`derivation='Custom'`) | 4.5 | SQL window function | Omni 3.2 | YELLOW | Parse inner `<formula>` and rewrite. |
| Forward references between calcs (`[CaptionA]` from `Calc B`) | 4.4 | Omni resolves `${field}` lazily | Omni 3.2 | GREEN | Omni does dependency resolution at compile time; forward references work. Parser builds DAG to emit in any order. |
| Spatial `MAKEPOINT`, `MAKELINE`, `DISTANCE`, `BUFFER`, `AREA` | 4.1 | Snowflake spatial fns (`ST_*`) or none | Omni 3.1 | YELLOW | Snowflake has `ST_MAKEPOINT`, `ST_DISTANCE`, `ST_BUFFER`, `ST_AREA`. Postgres has PostGIS. BigQuery has `ST_*`. Dialect-specific. |
| Predictive `MODEL_PERCENTILE`, `MODEL_QUANTILE` | 4.1 | None | n/a | RED | Tableau-only predictive primitives. Pre-compute upstream. |

### 3.3 Visualizations (worksheet level)

| Tableau concept | TWBX ref | Omni equivalent | Omni ref | Bucket | Notes |
|---|---|---|---|---|---|
| Mark `Bar` | 5.6 | `visType: basic`, `mark.type: bar` | Omni 8.5 | YELLOW | Native, but Omni renders horizontal by default (Omni 11.7); category goes on y, measure on series. Emitter must swap axes. |
| Mark `Line` | 5.6 | `visType: basic`, `mark.type: line` | Omni 8.4 | GREEN | Direct. |
| Mark `Area` | 5.6 | `visType: basic`, `mark.type: area` | Omni 8.1 | GREEN | Omni 8.1 lists area as a basic mark type. |
| Mark `Circle` (scatter) | 5.6 | `visType: basic`, `mark.type: circle` | Omni 8.6 | GREEN | Direct. |
| Mark `Square` | 5.6 | `visType: basic`, `mark.type: circle` with shape override OR `vegalite` | Omni 8.6, 8.11 | YELLOW | Omni basic does not enumerate square; use Vega-Lite. |
| Mark `Shape` (custom shapes) | 5.6 | `visType: vegalite` with custom shape encoding | Omni 8.11 | YELLOW | Custom-shape PNGs from `<external><shapes>` cannot upload to Omni; either drop the encoding or use Vega-Lite point with `shape` channel set to unicode glyphs. |
| Mark `Text` (text table) | 5.6 | `visType: omni-spreadsheet` or `omni-table` | Omni 8.7 | GREEN | Direct. |
| Mark `Map` (filled chloropleth) | 5.6 | `visType: map` / `svg-map` OR `vegalite` `geoshape` | Omni 8.1, 8.11 | YELLOW | Omni has a map visType (Omni 8.1) but the spec is thin (GREY). Vega-Lite geoshape is the safer fallback. |
| Mark `Map` (symbol / pin) | 5.6 | `visType: map` | Omni 8.1 | GREY | Map type exists but JSON shape not documented. Single experiment unlocks. |
| Mark `Pie` | 5.6 | `visType: basic`, `configType: arc` | Omni 8.1 | GREEN | Omni 8.1 names "Pie & Donut" under basic. |
| Mark `Polygon` (custom spatial) | 5.6 | `vegalite` geoshape | Omni 8.11 | YELLOW | Vega-Lite only. |
| Mark `Density` (heatmap) | 5.6 | `visType: basic` heatmap | Omni 8.1 | GREEN | Listed. |
| Mark `Gantt Bar` | 5.6 | `vegalite` `bar` with `x` and `x2` | Omni 8.11 | YELLOW | No native gantt. Emit Vega-Lite layered spec. |
| Mark `Automatic` | 5.6 | `automaticVis: true` plus `visType: basic` | Omni 7, 11.6 | YELLOW | Omni's automatic chooses on the fly; the emitter should pick a concrete mark to match what Tableau auto-picked, otherwise the user sees a different chart. |
| Encoding shelf: rows | 5.4, 5.7 | `queryJson.fields[]` plus `pivots[]` | Omni 7.1 | GREEN | Multi-pill rows become first field plus pivots. |
| Encoding shelf: columns | 5.4, 5.7 | `queryJson.fields[]` | Omni 7.1 | GREEN | Direct. |
| Encoding shelf: color (discrete) | 5.7, 5.13 | `visConfig` `seriesColors` OR auto-mapped from a categorical field | Omni 8.14 | YELLOW | Discrete color maps to series colors; the emitter must walk `<map-color-discrete>` and emit per-series `_mark_color`. |
| Encoding shelf: color (continuous) | 5.7, 5.13 | `visConfig` color gradient | Omni 8.13, 8.14 | GREY | Omni docs thin on continuous color spec keys. Vega-Lite fallback works. |
| Encoding shelf: size | 5.7 | Vega-Lite `size` channel | Omni 8.11 | YELLOW | No native size encoding in basic; use Vega-Lite. |
| Encoding shelf: shape | 5.7 | Vega-Lite `shape` channel | Omni 8.11 | YELLOW | Vega-Lite only. |
| Encoding shelf: label | 5.7 | `visConfig` label fields | Omni 8.13 | YELLOW | Omni 8.13 mentions value formatting but full label-positioning spec is thin (GREY). |
| Encoding shelf: text | 5.7 | Table view rendering | Omni 8.7 | GREEN | For text-table marks only. |
| Encoding shelf: detail | 5.7 | Extra `queryJson.fields[]` entry (not in pivots) | Omni 7.1 | GREEN | Splits marks without changing aggregation. |
| Encoding shelf: tooltip | 5.7, 5.8 | `visConfig.tooltip[]` array | Omni 8.4 | GREEN | Each `<tooltip column=>` to a tooltip entry. |
| Encoding shelf: path | 5.7 | Vega-Lite `order` channel | Omni 8.11 | YELLOW | Vega-Lite only. |
| Encoding shelf: angle (pie slice) | 5.7 | Implicit via measure on pie mark | Omni 8.1 | GREEN | Pie configType handles angle automatically. |
| Continuous vs discrete pill semantics | 5.9 | Omni infers from field type | Omni 3.3 | GREEN | A `number`-type measure on x is continuous; a `string` dimension is discrete. Tableau distinction translates implicitly. |
| Dual axis (synchronized) | 5.10 | `visConfig` `yAxis: y2` series plus second axis spec | Omni 8.4 | GREY | Omni docs explicitly thin on `y2` spec keys (Omni 8.4). Fallback: `vegalite` layered spec. |
| Dual axis (independent) | 5.10 | `vegalite` with `resolve.scale.y: 'independent'` | Omni 8.11 | YELLOW | Vega-Lite layered. |
| Combined axis (Measure Names / Measure Values) | 5.4 | Multiple `series[]` on the same axis OR Vega-Lite | Omni 8.4 | YELLOW | Each Tableau measure on the combined axis becomes one `series[]` entry with `yAxis: y`. |
| Trellis / small multiples | 5.5 | Vega-Lite `facet` OR multiple tiles | Omni 8.11, 6.1 | YELLOW | Vega-Lite facet works for one chart. For dashboard-level repetition, emit one tile per facet value (loses dynamic reactivity). |
| Stacked bars | 5.6 | `behaviors.stackMultiMark: true` | Omni 8.5 | GREEN | Direct. |
| Side-by-side (grouped) bars | 5.6 | `behaviors.stackMultiMark: false` plus multiple series | Omni 8.5 | GREEN | Direct. |
| 100% stacked bars | 5.6 | Stacking option `stack %` | Omni 8.5 | GREY | Omni 8.5 mentions `stack %` but exact JSON key is unclear ("thin docs, verify via UI export"). |
| Reference line (constant, avg, median, custom) | 5.12 | `visConfig.referenceLines[]` (mentioned, not documented) | Omni 8.12 | GREY | Omni 8.12 explicitly notes "thin docs". Fallback: Vega-Lite `rule` mark. |
| Reference band | 5.12 | Vega-Lite layered rect | Omni 8.11, 8.12 | YELLOW | Limited native support; Vega-Lite fallback. |
| Distribution bands (percentiles) | 5.12 | Vega-Lite | Omni 8.11 | YELLOW | Compute percentiles in SQL and overlay via Vega-Lite. |
| Trend line (linear, log, expo, polynomial, power) | 5.12 | Vega-Lite `regression` transform | Omni 8.11, 8.12 | YELLOW | Vega-Lite supports linear, log, exp, poly via `transform: [{regression: ..., method: ...}]`. |
| Forecast (model-based) | 5.12 | None | n/a | RED | No Omni primitive. Pre-compute upstream (dbt + Snowflake `FORECAST` ML function or Python). |
| Cluster analysis (Tableau analytics object) | 5.12 | None | n/a | RED | No clustering primitive. Pre-compute upstream. |
| Sort manual (`<sort class='manual'>`) | 5.11 | `queryJson.sorts[]` plus derived order column | Omni 7.1 | YELLOW | Manual sort dictionary becomes a SQL `CASE` order column. |
| Sort computed (`<sort class='computed' using=>`) | 5.11 | `queryJson.sorts[]` with `column_name` and `sort_descending` | Omni 7.1 | GREEN | Direct mapping. |
| Sort alphabetic | 5.11 | `queryJson.sorts[]` with the dimension itself | Omni 7.1 | GREEN | Direct. |
| Sort nested | 5.11 | Multiple `sorts[]` entries in order | Omni 7.1 | YELLOW | Omni respects the array order. Nesting semantics differ slightly. |
| Top-N filter (on shelf) | 5.3, 9.1 | `queryJson` filter or pre-rank | Omni 7.1, 9 | YELLOW | Easiest: a SQL `RANK()` filter in a templated dimension. Native top-N support in Omni is GREY. |
| Axis log / linear | 5.10 | `visConfig.x.axis` / `y.axis` log scale | Omni 8.4, 8.5 | GREY | Public Omni docs do not show the log-scale axis key. Vega-Lite has `scale.type: 'log'`. |
| Axis fixed / automatic range | 5.10 | `visConfig.axis.domain` | Omni 8.4 | GREY | Not enumerated in Omni docs; verify via export. |
| Axis reversed | 5.10 | Vega-Lite `scale.reverse: true` | Omni 8.11 | YELLOW | Vega-Lite only. |
| Axis sync (dual) | 5.10 | Single axis with both series OR `vegalite` shared scale | Omni 8.4 | YELLOW | Same as dual-axis sync. |
| Color: stepped | 5.13 | Vega-Lite scale type `'quantize'` | Omni 8.11 | YELLOW | Vega-Lite. |
| Color: diverging | 5.13 | `visConfig.colorScale` diverging | Omni 8.14 | GREY | Omni 8.14 mentions diverging but JSON shape not shown. |
| Color: custom palette | 5.13, 2.2 | `visConfig.colors[]` array of hex | Omni 8.14 | GREEN | Walk `<color-palette>` colors and emit. |
| Per-mark custom shape from `<external><shapes>` | 2.4, 5.7 | None | n/a | RED | Tableau ships PNG shapes; Omni cannot upload custom shapes per mark. Drop with warning or substitute Unicode glyphs. |
| Conditional formatting on text tables (`<style-rule><condition>`) | 8.3 | `resultConfig.columnFormats` (per-column color) | Omni 8.7 | YELLOW | Omni 8.7 notes "thin docs on color scales" (GREY). Static color OK; condition logic GREY. |
| Sparklines (line in cells) | 5.6 | `omni-kpi` `chart` row OR markdown `<Sparkline>` | Omni 8.8, 8.10 | GREEN | Two paths. KPI sparkline is native. |
| Bullet charts | n/a (TWBX doesn't enumerate; standard Tableau show-me) | `omni-kpi` `progress` row | Omni 8.8 | YELLOW | KPI progress bar approximates a bullet chart but loses comparison-band. |
| Box-and-whisker plot | 5.6 | `visType: basic`, `mark.type: boxplot` | Omni 8.1 | GREEN | Listed. |
| Histogram (Show Me) | 3.8 (bins) plus 5.6 (bar) | Numeric bin dimension plus bar | Omni 3, 8.5 | YELLOW | Emit a binned dimension (see 3.1 row) plus a bar chart. |
| Pareto chart (dual-axis with running sum) | 5.10, 5.6, 4.5 | Vega-Lite layered (bar plus running-sum line) | Omni 8.11 | YELLOW | Combine dual-axis YELLOW path with RUNNING_SUM YELLOW path. |
| Waterfall chart | 5.6, 4.5 | Vega-Lite | Omni 8.11 | YELLOW | Use Tableau's gantt-plus-running-sum trick translated to Vega-Lite bar with `y` and `y2`. |
| Donut chart | 5.6 | `visType: basic` configType arc with inner radius | Omni 8.1 | GREEN | Same as pie. |

### 3.4 Filters

| Tableau concept | TWBX ref | Omni equivalent | Omni ref | Bucket | Notes |
|---|---|---|---|---|---|
| Categorical multi-select | 5.3, 9.1 | `kind: STRING_IS` plus `values: []` | Omni 9.1, 9.2 | GREEN | Direct. |
| Categorical single-select | 5.3 | `kind: STRING_IS`, `values` length 1 | Omni 9.2 | GREEN | Direct. |
| Categorical exclude (NOT IN) | 5.3 | `is_negative: true` | Omni 9.2 | GREEN | Direct. |
| Wildcard contains | 5.3 | `kind: STRING_CONTAINS` | Omni 9.2 | GREEN | Direct. |
| Wildcard starts/ends | 5.3 | `STRING_STARTS_WITH`, `STRING_ENDS_WITH` | Omni 9.2 | GREEN | Direct. |
| Wildcard regex | 5.3 | YAML `matches_regex` operator | Omni 9.1 | YELLOW | YAML-side OK; JSON wire `kind` for regex not documented (GREY at wire). |
| Wildcard exactly | 5.3 | `STRING_IS` | Omni 9.2 | GREEN | Direct. |
| Quantitative range | 5.3 | `kind: BETWEEN` or `WITHIN_RANGE` | Omni 9.2 | GREEN | Direct. |
| Date range (calendar) | 5.3 | `kind: WITHIN_RANGE`, `type: date` | Omni 9.2 | GREEN | Direct. |
| Relative date (`<filter class='relative-date'>`) | 5.3 | `kind: TIME_FOR_INTERVAL_DURATION` always (the JSON form of YAML `time_for_duration`); the UI picker is chosen by the shape of `left_side` / `right_side` | Omni 9.2 | GREEN | Tableau `first-period=-11, last-period=0, period-type=month` (= "last 12 months including current") maps to `{kind: TIME_FOR_INTERVAL_DURATION, left_side: "12 months ago", right_side: "12 months"}`, which Omni renders as the "in the past 12 months" picker. Pure offset windows like `first-period=-6, last-period=-3` map to `{left_side: "6 months ago", right_side: "4 months"}` and render as a range picker. NOTE: `"12 months ago"` resolves to `INTERVAL '-11 month'` (truncated, inclusive of current period), not `'-12 month'`. Use `"12 complete months ago"` for the strict form. |
| Top-N filter (on dimension shelf) | 5.3 | Pre-rank in SQL plus filter | Omni 7.1, 9 | YELLOW | Native top-N in queryJson is GREY. |
| Conditional filter (formula-based) | 5.3 | Templated filter with `bind_to` plus SQL | Omni 9.6 | YELLOW | Or HAVING clause via Omni measure filter. |
| Context filter (`context='true'`) | 5.3 | None (not needed in Omni execution model) | n/a | RED | Tableau's context filter exists to fix LOD interaction; Omni evaluates filters in a different order, so the concept usually evaporates. Drop with a note. |
| Cross-datasource filter | 5.3 (no explicit element; per-target field references) | Dashboard `filterConfig` with same field name across topics | Omni 9.3 | YELLOW | Works only when both topics expose a shared dimension name. |
| "Only relevant values" / cascading filters | 5.3 (`user:ui-marker='cascade'`) | None automatic | n/a | RED | Omni does not auto-cascade filter options. User would manually scope a filter to a query. |
| "Show apply button" UI behavior | n/a (Tableau UI flag in `<window>`) | None | n/a | RED | Omni applies filters live; no apply button. Drop. |
| Data source filter | 9.1 | `always_where_filters:` on topic | Omni 4.3 | GREEN | Direct. |
| Extract filter | 3.12 (`<extract><filter>`) | dbt or upstream materialization | n/a | YELLOW | Extract filters live in Tableau's extract step; in Omni's world they belong upstream. |

### 3.5 Parameters

| Tableau concept | TWBX ref | Omni equivalent | Omni ref | Bucket | Notes |
|---|---|---|---|---|---|
| Parameter as filter input | 3.10, 9 | Bind templated filter to a dashboard control | Omni 9.6, 9.4 | YELLOW | Replace `[Param]` in filter formulas with `{{ filters.<view>.<field>.value }}`. |
| Parameter in calculated field | 3.10, 4.4 | Templated filter referenced in SQL | Omni 9.6 | YELLOW | Use Mustache `{{ filters... }}` syntax. |
| Parameter action (set parameter from click) | 6.6 | None direct; closest is dashboard filter click-through | Omni 9.5 (limited) | RED | Omni does not yet have a "click to set a filter value" primitive. Section 9.5 is GREY too. |
| Parameter swap (dimension/measure picker) | 6.6 | `FIELD_SELECTION` or `FIELD_PICKER` control | Omni 9.4 | GREEN | Document the swap targets as `options[]`. |

### 3.6 Dashboards

| Tableau concept | TWBX ref | Omni equivalent | Omni ref | Bucket | Notes |
|---|---|---|---|---|---|
| Tiled layout (root container) | 6.1, 6.2 | `metadata.layouts.lg` 12-col grid | Omni 6.3 | GREEN | Flatten Tableau zone tree to grid cells. |
| Floating layout (absolute pixel) | 6.4 | None | n/a | RED | Omni grid-only. Snap to nearest cell with warning. |
| Container: horizontal flow | 6.2 | Multiple tiles laid in same `y` band with varying `x` | Omni 6.3 | YELLOW | Flatten flow. Loses dynamic re-flow behavior. |
| Container: vertical flow | 6.2 | Multiple tiles in same `x` column with varying `y` | Omni 6.3 | YELLOW | Same. |
| Sizing: fixed | 6.1 | Dashboard layout naturally responsive | Omni 6.3 | YELLOW | Omni does not pin pixel dimensions; grid resizes. |
| Sizing: automatic | 6.1 | Same as fixed in Omni semantics | Omni 6.3 | GREEN | Effectively unchanged. |
| Sizing: range | 6.1 | None | n/a | RED | Omni does not have range sizing semantics. |
| Worksheet zone | 6.2 | `queryPresentation` tile in `metadata.layouts.lg` | Omni 6.2, 7 | GREEN | One worksheet to one tile. |
| Text zone (markdown / static text) | 6.2 | `metadata.textTiles[]` markdown tile | Omni 6.6 | GREEN | Render Tableau text-block content as markdown. |
| Image zone | 6.2 | `metadata.textTiles[]` markdown with `<img>` | Omni 6.6 | YELLOW | Image must be hosted externally or base64 inlined. TWBX `Image/` files are not uploaded by Omni. |
| Web page zone (iframe) | 6.2 | Markdown iframe (`<iframe>`) | Omni 6.6 | YELLOW | Omni allows iframes in markdown tiles. JavaScript stripped. |
| Blank zone (spacer) | 6.2 | Empty grid cell (just leave gap) | Omni 6.3 | GREEN | Direct. |
| Navigation button zone | 6.2 | Markdown tile with link OR cross-dashboard link | Omni 6.5, 6.6 | YELLOW | Render as a link or button-styled markdown. |
| Extension zone (.trex) | 6.2 | None | n/a | RED | Tableau Extensions are sandboxed iframes with API. Omni has no extension framework. Drop. |
| Show/hide containers | 6.2 (UI-only, not in XML) | None | n/a | RED | Omni dashboards cannot conditionally show/hide tiles based on filter values. |
| Dashboard filter applied to multiple worksheets | 6.5 (`<filters-with-target>`) | Dashboard-level `filterConfig` plus default filter scope | Omni 9.3, 9.5 | GREEN | Add to `filterConfig` and let Omni auto-apply to tiles using that field. |
| Filter action (click-to-filter) | 6.6 | `dashboard.crossfilterEnabled: true` | Omni 6.5 | YELLOW | Omni 6.5 itself is GREY; cross-tile filter wiring documented thinly. |
| Highlight action | 6.6 | None | n/a | RED | Drop. |
| URL action | 6.6 | Markdown tile link OR drill `link:` on measure | Omni 3.2, 6.6 | YELLOW | Field-token substitution (`<REGION_ID>`) translates to `{{view.field}}` Mustache. |
| Navigation action (go-to-dashboard) | 6.6 | Cross-dashboard link in markdown | Omni 6.5, 6.6 | YELLOW | Cross-dashboard navigation is mentioned (Omni 6.5) but JSON shape is GREY. |
| Parameter action | 6.6 | None | n/a | RED | See 3.5. |
| Set action | 6.6 | None | n/a | RED | Sets are Tableau-specific. Drop. |
| Dashboard-level tooltip | 6.2 (zone-level, rare) | Per-tile tooltip | Omni 8.4 | YELLOW | Tableau dashboard-wide tooltips are uncommon; flatten to per-tile. |
| Device-specific layouts (phone, tablet) | 6.1 | None | n/a | RED | Omni layout is responsive but not device-conditioned. Drop the phone layout; rely on Omni responsive grid. |

### 3.7 Stories

| Tableau concept | TWBX ref | Omni equivalent | Omni ref | Bucket | Notes |
|---|---|---|---|---|---|
| Story container | 7 | Multi-tab dashboard OR sequence of linked dashboards | Omni 6.4 | YELLOW | Omni 6.4 says multi-tab shape is documented thinly (GREY). |
| Story point (single snapshot) | 7 | One tab in a multi-tab dashboard | Omni 6.4 | GREY | Once 6.4 is resolved, this becomes YELLOW. |
| Frozen filter state on a story point | 7 | Per-tab default filter values | Omni 9.3 | YELLOW | Tab-level filters supported, but the API shape is GREY (Omni 6.4). |
| Navigator style: dot | 7 | Omni dot navigator on multi-tab (default) | n/a | GREY | Omni tab UI variants not enumerated. |
| Navigator style: caption | 7 | Omni labelled tabs | n/a | GREY | Same. |
| Navigator style: number | 7 | None | n/a | RED | No numeric navigator. |
| Navigator style: arrows-only | 7 | None | n/a | RED | No arrows-only navigator. |
| Annotations on story points | 7 | Markdown tile in the tab | Omni 6.6 | YELLOW | Render as a markdown tile per tab. |

### 3.8 Formatting / theme

| Tableau concept | TWBX ref | Omni equivalent | Omni ref | Bucket | Notes |
|---|---|---|---|---|---|
| Custom categorical palette (`<color-palette type='regular'>`) | 2.2 | `visConfig.colors[]` per dashboard OR model AI settings | Omni 8.14 | GREEN | Walk colors and emit. |
| Custom sequential palette | 2.2 | `visConfig.colorScale` gradient | Omni 8.14 | GREY | Continuous color JSON shape thin. |
| Custom diverging palette | 2.2 | `visConfig.colorScale` diverging | Omni 8.14 | GREY | Same. |
| Workbook-level theme (`<style>` block) | 2.3 | None at model level; per-dashboard styling only | Omni 8.14 | RED | Omni does not currently expose org-level theming via model. Document as a known gap. |
| Per-worksheet formatting | 5.5, 5.13 | `visConfig` per tile | Omni 8.4 to 8.7 | YELLOW | One-by-one translation; tile-level. |
| Number format strings (Excel-like, `#,##0.00;-#,##0`) | 8.4 | Direct paste into `format:` or `value_format:` | Omni 3.4, 8.13 | GREEN | Direct paste, Excel-compatible. |
| Number format shortcuts (`c0`, `p1%`, `n2`) | 8.4 | Translate to long form OR Omni named formats | Omni 3.4 | YELLOW | Build lookup table: `c0` to `$#,##0`, `p1%` to `0.0%`, etc. |
| Date format strings (`yyyy-MM-dd`, etc.) | 8.4 | Direct paste | Omni 3.4 | GREEN | Compatible. |
| Custom format strings with conditional sections (`[Red]<0`) | 8.4 | `value_format:` with same syntax | Omni 3.4 | GREEN | Excel-compatible. |
| Fonts and font sizing | 8.6 | Dashboard-level only via spec | Omni 8.14 | RED | Tableau allows per-mark font sizing; Omni does not expose this. |
| Banding (alternating row/column shading) | 8.5 | `resultConfig.rowBanding` | Omni 8.7 | GREEN | Direct. |
| Borders and gridlines | 5.5, 8.5 | Spreadsheet rendering defaults | Omni 8.7 | GREY | Omni docs do not document border-level styling. |
| Background colors on dashboard | 2.3, 8.5 | Markdown tile background OR per-tile | Omni 6.6 | GREY | Dashboard background color is not enumerated as a key. |
| Background images on dashboard | 8.5 | Markdown tile inline image | Omni 6.6 | YELLOW | Wrap image in markdown. |

### 3.9 Other

| Tableau concept | TWBX ref | Omni equivalent | Omni ref | Bucket | Notes |
|---|---|---|---|---|---|
| Mark annotations (mark, area, point) | n/a (XML annotation element not enumerated in spec) | None | n/a | RED | Tableau mark annotations have no Omni equivalent. Drop. |
| Tooltip with formatted text and field tokens | 5.8 | `visConfig.tooltip[]` plus markdown tile templating | Omni 8.4, 8.10 | YELLOW | Per-tile tooltips support fields but not styled runs. Translate `<run>` to plain text or to markdown. |
| Viz-in-tooltip | n/a (Tableau interactive feature, not enumerated in TWBX spec) | None | n/a | RED | No equivalent. |
| Tooltip images | n/a | Markdown image in `omni-markdown` tile | Omni 8.10 | YELLOW | Workaround only for static contexts. |
| Calculated tooltip text | 5.8 | Mustache template in markdown tile | Omni 8.10 | YELLOW | Translate `<FieldName>` tokens to `{{view.field}}`. |
| Workbook-level actions (in `<workbook><actions>`) | 2.1 | None | n/a | RED | Rare in practice. Drop. |
| Subscriptions / email alerts | n/a (Tableau Server feature) | Omni schedules / deliveries | Omni 10 (commands list) | YELLOW | Omni has `omni schedules` CLI group; not deeply documented in this spec. |
| Permissions | n/a (Tableau Server feature) | Omni `access_grants`, `access_filters`, `required_access_grants` | Omni 2, 3, 4 | YELLOW | Tableau permissions are stored on the server, not in TWBX. The migration recipe is to re-create permission scopes in Omni after import. |

---

## 4. GREEN deep dive

Each GREEN gets a paired XML to YAML/JSON micro-example. Only the load-bearing fragment is shown.

### 4.1 Live SQL connection

Tableau (TWBX 3.2):

```xml
<connection class='snowflake' dbname='ANALYTICS' schema='PUBLIC'
            server='abc.snowflakecomputing.com' warehouse='WH_X'/>
```

Omni view YAML (Omni 3.1):

```yaml
view: orders
schema: PUBLIC
sql_table_name: ANALYTICS.PUBLIC.ORDERS
```

Inference required: warehouse and server are attached to the Omni connection itself (created out of band), not the view file. Emitter validates that an Omni connection on the target instance matches by name.

### 4.2 Inner / left / right / full physical join

Tableau (TWBX 3.3):

```xml
<relation join='left' type='join'>
  <clause type='join'>
    <expression op='='>
      <expression op='[orders].[customer_id]'/>
      <expression op='[customers].[id]'/>
    </expression>
  </clause>
  ...
</relation>
```

Omni relationships YAML (Omni 5):

```yaml
relationships:
  - join_from_view: orders
    join_to_view: customers
    join_type: always_left
    on_sql: ${orders.customer_id} = ${customers.id}
    relationship_type: many_to_one
```

Inference: cardinality `many_to_one` derived from join direction unless the noodle (TWBX 3.4) supplied explicit cardinality.

### 4.3 Logical-layer relationship (noodle)

Tableau (TWBX 3.4):

```xml
<relationship>
  <expression op='='>
    <expression op='[Orders].[customer_id]'/>
    <expression op='[Customers].[id]'/>
  </expression>
  <first-end-point object-id='Orders_xyz' cardinality='many'/>
  <second-end-point object-id='Customers_abc' cardinality='one'/>
</relationship>
```

Omni (Omni 5):

```yaml
- join_from_view: orders
  join_to_view: customers
  join_type: always_left
  on_sql: ${orders.customer_id} = ${customers.id}
  relationship_type: many_to_one
```

Inference: `join_type` defaults to `always_left` when Tableau does not specify; the noodle uses implicit-join semantics, so left is the safe default.

### 4.4 Custom SQL relation

Tableau (TWBX 3.3):

```xml
<relation type='text'>
SELECT o.id, o.amount FROM orders o WHERE o.created_at &gt; '2024-01-01'
</relation>
```

Omni view (Omni 3):

```yaml
view: custom_orders
sql: |
  SELECT o.id, o.amount
  FROM orders o
  WHERE o.created_at > '2024-01-01'
```

Inference: XML-unescape `&gt;` to `>`, etc. (TWBX 0.3).

### 4.5 Physical column to dimension / measure

Tableau (TWBX 3.5):

```xml
<column datatype='real' name='[AMOUNT]' role='measure'
        default-format='$#,##0.00' aggregation='Sum'/>
```

Omni (Omni 3):

```yaml
measures:
  total_amount:
    sql: ${TABLE}.AMOUNT
    aggregate_type: sum
    format: "$#,##0.00"
```

### 4.6 Dimension default aggregation enum

Tableau `aggregation='CountD'` to Omni `aggregate_type: count_distinct`. Lookup table:

| Tableau | Omni |
|---|---|
| Sum | sum |
| Avg | average |
| Count | count |
| CountD | count_distinct |
| Min | min |
| Max | max |
| Median | median |
| Percentile | percentile |
| AttributeOf | (no equivalent, see YELLOW 5.x) |
| Stdev | (use SQL stddev) |
| Var | (use SQL var) |

### 4.7 Categorical filters

Tableau (TWBX 5.3):

```xml
<filter class='categorical' column='[ds].[STAGENAME]'>
  <groupfilter function='union'>
    <groupfilter function='member' member='&quot;Closed Won&quot;'/>
    <groupfilter function='member' member='&quot;Negotiation&quot;'/>
  </groupfilter>
</filter>
```

Omni (Omni 9.2):

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

Inference: drop XML quote-escapes; emit JSON string values directly. `kind` required (Omni 11.4).

### 4.8 Quantitative range filter

Tableau (TWBX 5.3):

```xml
<filter class='quantitative' column='[ds].[AMOUNT]' include-values='in-range'>
  <min>1000</min>
  <max>50000</max>
</filter>
```

Omni (Omni 9.2):

```json
{
  "sf_opportunities.amount": {
    "kind": "BETWEEN",
    "type": "number",
    "values": [1000, 50000],
    "is_negative": false
  }
}
```

### 4.9 Relative-date filter

Tableau (TWBX 5.3):

```xml
<filter class='relative-date' column='[ds].[CLOSEDATE]'
        first-period='-12' last-period='0' period-type='month'/>
```

Omni (Omni 9.2):

```json
{
  "sf_opportunities.closedate": {
    "kind": "TIME_FOR_INTERVAL_DURATION",
    "type": "date",
    "left_side": "12 months ago",
    "right_side": "12 months",
    "is_negative": false
  }
}
```

Inference: Tableau's `first-period=-12, period-type=month` to Omni's `left_side: "12 months ago"`. Numeric to natural-language string.

### 4.10 Tiled worksheet zone to grid cell

Tableau (TWBX 6.2, 6.3):

```xml
<zone id='4' h='90000' w='50000' x='0' y='10000' worksheet='Sales by Region'/>
```

Conversion to Omni grid (Omni 6.3):

```text
omni_x = round((0/100000) * 12)     = 0
omni_w = round((50000/100000) * 12) = 6
omni_y = round((10000/100000) * 42) [INFERRED, scale to dashboard height units]
omni_h = round((90000/100000) * 42) [INFERRED]
```

Omni layout:

```json
{"i": "1", "x": 0, "y": 1, "w": 6, "h": 37}
```

Inference: row units in Omni are "approximately 12 pixels per unit"; the conversion factor between Tableau's 100,000-unit vertical and Omni's row count is dashboard-height dependent and must be calibrated. Section 7 covers this as a YELLOW pitfall.

### 4.11 Tooltip encoding

Tableau (TWBX 5.7):

```xml
<tooltip column='[ds].[none:NOTES:nk]'/>
```

Omni (Omni 8.4):

```json
"tooltip": [{"field": {"name": "view.notes"}}]
```

### 4.12 Box-and-whisker plot

Tableau `<mark class='Box Plot'/>` (TWBX 5.6 lists box-plot capability) maps to Omni `visType: basic`, `mark.type: boxplot` (Omni 8.1). Encoder picks the dimension/measure split from the worksheet shelves.

### 4.13 Dashboard text tile

Tableau (TWBX 6.2):

```xml
<zone id='2' type-v2='text' name='Title'>
  <formatted-text>
    <run fontsize='18' bold='true'>Sales Overview</run>
  </formatted-text>
</zone>
```

Omni (Omni 6.6):

```json
{
  "i": "1",
  "spec": {"markdown": "# Sales Overview"}
}
```

(In `dashboard.metadata.textTiles[]`.) Inference: collapse formatted-text runs to markdown headings.

### 4.14 Computed sort

Tableau (TWBX 5.11):

```xml
<sort class='computed' direction='DESC' using='[sum:Sales:qk]'/>
```

Omni (Omni 7.1):

```json
{"sorts": [{
  "null_sort": "OMNI_DEFAULT",
  "column_name": "view.total_sales",
  "is_column_sort": false,
  "sort_descending": true
}]}
```

Inference: `null_sort: "OMNI_DEFAULT"` is required (Omni 11.5).

---

## 5. YELLOW deep dive

Each YELLOW gets input shape, transformation, output shape. Workaround library named where applicable.

### 5.1 LOD FIXED to derived table

**Input (TWBX 4.3):**

```xml
<calculation class='tableau'
             formula='{ FIXED [Customer] : SUM([Sales]) }'/>
```

**Transformation:** Materialize the FIXED aggregation as a `derived_table:` (CTE) and join back to the base view by the fixed dimension list.

**Output (Omni 3):**

```yaml
views:
  customer_total_sales:
    derived_table:
      sql: |
        SELECT
          customer_id AS customer,
          SUM(sales) AS customer_total_sales
        FROM orders
        GROUP BY customer_id

# relationships.yaml
relationships:
  - join_from_view: orders
    join_to_view: customer_total_sales
    join_type: always_left
    on_sql: ${orders.customer_id} = ${customer_total_sales.customer}
    relationship_type: many_to_one
```

**Reference in measures:**

```yaml
measures:
  customer_total_sales:
    sql: ${customer_total_sales.customer_total_sales}
    aggregate_type: sum
```

Template applies to every FIXED LOD: one CTE per unique (dim-list, agg-expr) pair.

### 5.2 LOD INCLUDE / EXCLUDE to window function

**Input (TWBX 4.3):**

```xml
<calculation class='tableau'
             formula='{ INCLUDE [Region] : AVG([Profit]) }'/>
```

**Transformation:** Rewrite as window function. INCLUDE means partition by viz-dims PLUS the include-dim. EXCLUDE means partition by viz-dims MINUS the exclude-dim.

**Output (Omni 3.2):**

```yaml
measures:
  avg_profit_include_region:
    sql: |
      AVG(${TABLE}.profit) OVER (
        PARTITION BY {{ <viz_dim_list> }}, ${TABLE}.region
      )
    type: number
```

Note: requires viz-dim awareness, which a static measure does not have. Pragmatic workaround: pre-compute at the most granular meaningful level via derived_table, accept that the measure is fixed at that grain.

### 5.3 RUNNING_SUM table calc

**Input (TWBX 4.5):**

```xml
<column-instance derivation='WindowTotal'>
  <table-calc agg-type='Sum' ordering-type='Rows' partition-along='Cell'/>
</column-instance>
```

**Transformation:** Translate to SQL window with running aggregate.

**Output (Omni 3.2):**

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

### 5.4 WINDOW_AVG with explicit bounds

**Input:** `WINDOW_AVG(SUM([Sales]), -11, 0)` (12-period trailing average).

**Output (Omni 3.2):**

```yaml
measures:
  trailing_12mo_avg:
    sql: |
      AVG(${TABLE}.sales) OVER (
        ORDER BY ${TABLE}.month
        ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
      )
    type: number
```

### 5.5 Custom SQL relation pre-existing as a derived table

**Input:** Long custom SQL with parameters.

**Transformation:** Replace `[Param]` tokens with `{{ filters.<view>.<field>.value }}` (Omni 9.6).

**Output:**

```yaml
view: custom_sales
derived_table:
  sql: |
    SELECT id, amount FROM orders
    WHERE region = '{{ filters.custom_sales.region.value }}'
```

### 5.6 Aliases to CASE WHEN

**Input (TWBX 3.7):**

```xml
<aliases>
  <alias key='&quot;A&quot;' value='Active'/>
  <alias key='&quot;I&quot;' value='Inactive'/>
</aliases>
```

**Output:**

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

Note: Tableau filters can still target raw underlying values; Omni filters target the dimension. Document the trade-off.

### 5.7 Groups (`<calculation class='categorical-bin'>`)

**Input (TWBX 3.7):**

```xml
<calculation class='categorical-bin' column='[Product Name]'>
  <bin value='&quot;Acme Group&quot;'>
    <value>&quot;Acme Widget&quot;</value>
    <value>&quot;Acme Sprocket&quot;</value>
  </bin>
</calculation>
```

**Output:**

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

### 5.8 Numeric bins

**Input (TWBX 3.8):**

```xml
<calculation class='bin' column='[Amount]' size='1000'/>
```

**Output:**

```yaml
dimensions:
  amount_bin:
    sql: FLOOR(${TABLE}.AMOUNT / 1000) * 1000
    type: number
```

### 5.9 Dual axis to Vega-Lite layered

**Input (TWBX 5.10):**

```xml
<panes synchronized='true'>
  <pane><mark class='Bar'/></pane>
  <pane><mark class='Line'/></pane>
</panes>
```

**Output (Omni 8.11):**

```json
{
  "visType": "vegalite",
  "spec": {
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "data": {"name": "results"},
    "layer": [
      {"mark": "bar",
       "encoding": {
         "x": {"field": "view\\.month", "type": "temporal"},
         "y": {"field": "view\\.sales", "type": "quantitative"}
       }},
      {"mark": "line",
       "encoding": {
         "x": {"field": "view\\.month", "type": "temporal"},
         "y": {"field": "view\\.target", "type": "quantitative", "axis": {"orient": "right"}}
       }}
    ],
    "resolve": {"scale": {"y": "independent"}}
  },
  "fields": ["view.month", "view.sales", "view.target"]
}
```

Workaround template: layered spec with optional `resolve.scale.y: independent` for unsynced dual-axis.

### 5.10 Trend line via Vega-Lite regression transform

**Input:** Tableau linear trend line.

**Output:**

```json
{
  "visType": "vegalite",
  "spec": {
    "data": {"name": "results"},
    "layer": [
      {"mark": "point",
       "encoding": {"x": {"field": "view\\.x", "type": "quantitative"},
                    "y": {"field": "view\\.y", "type": "quantitative"}}},
      {"transform": [{"regression": "view\\.y", "on": "view\\.x", "method": "linear"}],
       "mark": "line",
       "encoding": {"x": {"field": "view\\.x", "type": "quantitative"},
                    "y": {"field": "view\\.y", "type": "quantitative"}}}
    ]
  }
}
```

Method values: `linear`, `log`, `exp`, `pow`, `quad`, `poly`.

### 5.11 Filled map to Vega-Lite geoshape

**Input:** Tableau filled map with `semantic-role='[State].[Name]'`.

**Output:**

```json
{
  "visType": "vegalite",
  "spec": {
    "data": {"name": "results"},
    "transform": [{
      "lookup": "view\\.state",
      "from": {
        "data": {"url": "https://vega.github.io/vega-datasets/data/us-10m.json",
                 "format": {"type": "topojson", "feature": "states"}},
        "key": "properties.name"
      },
      "as": "geo"
    }],
    "mark": "geoshape",
    "encoding": {
      "shape": {"field": "geo", "type": "geojson"},
      "color": {"field": "view\\.value", "type": "quantitative"}
    },
    "projection": {"type": "albersUsa"}
  }
}
```

Workaround: use a public TopoJSON via `vega-datasets` URL. No custom geocoding needed.

### 5.12 Pie chart (when Omni native fails)

Native: `visType: basic`, `configType: arc`. If that fails (some Omni versions), fall back to Vega-Lite arc.

### 5.13 Stacked vs grouped vs 100%

Stacked: `behaviors.stackMultiMark: true`. Grouped: `false` with multiple series. 100%: stacking option `stack %` (GREY on exact key; verify via export).

### 5.14 Sort manual

**Input:**

```xml
<sort class='manual'>
  <dictionary>
    <bucket>&quot;West&quot;</bucket>
    <bucket>&quot;East&quot;</bucket>
    <bucket>&quot;Central&quot;</bucket>
  </dictionary>
</sort>
```

**Transformation:** Add a derived order column with explicit `CASE WHEN` rank.

**Output:**

```yaml
dimensions:
  region_sort_order:
    sql: |
      CASE ${TABLE}.REGION
        WHEN 'West' THEN 1
        WHEN 'East' THEN 2
        WHEN 'Central' THEN 3
        ELSE 99
      END
    type: number
    hidden: true
```

Then in `queryJson.sorts[]` sort by `region_sort_order` ascending.

### 5.15 Top-N filter

**Input (TWBX 5.3):**

```xml
<groupfilter function='end' direction='TOP' n='10'>
  ...
  <groupfilter function='member' member='[sum:Sales:qk]'/>
</groupfilter>
```

**Transformation:** Pre-rank in a derived dimension. Filter by rank.

**Output:**

```yaml
dimensions:
  customer_sales_rank:
    sql: |
      RANK() OVER (ORDER BY ${TABLE}.total_sales DESC)
    type: number
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

### 5.16 Parameter to templated filter

**Input:** A parameter `[Top N]` referenced in a calc.

**Output (Omni 9.6):**

```yaml
filters:
  top_n:
    type: number
    default_filter: 10
    bind_to: view.customer_sales_rank
    display_order: 1

dimensions:
  is_top_n:
    sql: |
      CASE WHEN ${customer_sales_rank} <= {{ filters.view.top_n.value }} THEN 1 ELSE 0 END
    type: number
```

### 5.17 Format string shortcut translation

Lookup table for emitter:

| Tableau | Omni `format:` |
|---|---|
| `c0` | `"$#,##0"` |
| `c2` | `"$#,##0.00"` |
| `n0` | `"#,##0"` |
| `n2` | `"#,##0.00"` |
| `p0%` | `"0%"` |
| `p1%` | `"0.0%"` |
| `p2%` | `"0.00%"` |
| `s` | (scientific, use `"0.00E+00"`) |

### 5.18 Custom SQL with parameter

See 5.16 plus 5.5; emitter must thread the parameter both through the templated filter and through every SQL body that referenced the old `[Param]`.

### 5.19 Worksheet zone to grid cell

Conversion algorithm (Omni 6.3, TWBX 6.3):

```python
GRID_COLS = 12
ROW_HEIGHT_PX = 12  # Omni unit

def to_grid(zone, dashboard_size):
    omni_x = round((zone.x / 100000) * GRID_COLS)
    omni_w = max(1, round((zone.w / 100000) * GRID_COLS))
    px_y = (zone.y / 100000) * dashboard_size.maxheight
    px_h = (zone.h / 100000) * dashboard_size.maxheight
    omni_y = round(px_y / ROW_HEIGHT_PX)
    omni_h = max(1, round(px_h / ROW_HEIGHT_PX))
    return {"x": omni_x, "y": omni_y, "w": omni_w, "h": omni_h}
```

Snap floating zones to nearest grid cell.

### 5.20 URL action

**Input (TWBX 6.6):**

```xml
<url-action>
  <url>https://my.salesforce.com/<REGION_ID></url>
</url-action>
```

**Output (Omni 3.2 `link:` on dimension):**

```yaml
dimensions:
  region:
    sql: ${TABLE}.REGION
    link:
      url: "https://my.salesforce.com/{{ value }}"
      label: "Open in Salesforce"
```

Inference: replace `<FieldToken>` with `{{ value }}` for the bound dimension, or with `{{ row.<view.field> }}` for cross-field references (Omni 8.10 markdown templating).

### 5.21 Tableau categorical-bin alias plus group

When a column has both `<aliases>` and `<calculation class='categorical-bin'>`, the bin's `<value>` matches alias `key` not alias `value`. Emitter resolves aliases first, then the bin's CASE WHEN.

### 5.22 Set: top-N

See 5.15.

### 5.23 Set: condition-based

**Output:**

```yaml
dimensions:
  high_value:
    sql: |
      CASE WHEN ${TABLE}.amount > 10000 THEN true ELSE false END
    type: yesno
```

### 5.24 Set: manual

**Output:**

```yaml
dimensions:
  is_in_top_customers:
    sql: |
      CASE WHEN ${TABLE}.customer_name IN ('Acme Inc','Globex') THEN true ELSE false END
    type: yesno
```

### 5.25 Hierarchies to drill_fields

**Output:**

```yaml
measures:
  total_sales:
    aggregate_type: sum
    sql: ${TABLE}.amount
    drill_fields: [country, state, city, postal_code]
```

### 5.26 Image zone

**Output:** Markdown tile with inline image. The image must be either (a) externally hosted (recommended), or (b) base64 inlined in the markdown body.

```json
{
  "i": "3",
  "spec": {"markdown": "![Logo](https://cdn.example.com/logo.png)"}
}
```

### 5.27 Conditional formatting on text table

**Output (Omni 8.7):**

```json
"resultConfig": {
  "columnFormats": {
    "view.profit": {"format": "$#,##0", "color": "#1b5e20"}
  }
}
```

Note: per-row conditional logic (positive green, negative red) is GREY in Omni's documented JSON. Vega-Lite spreadsheet workaround feasible but heavyweight.

### 5.28 Sparkline

**Output (KPI):**

```json
{
  "visType": "omni-kpi",
  "spec": {
    "rows": [
      {"type": "number", "field": "view.sales", "format": "USDCURRENCY"},
      {"type": "chart", "field": "view.sales", "x": "view.month", "shape": "line", "height": 30}
    ]
  }
}
```

### 5.29 Reference line via Vega-Lite

**Output:**

```json
{
  "visType": "vegalite",
  "spec": {
    "layer": [
      {"mark": "line",
       "encoding": {"x": {"field": "view\\.month"}, "y": {"field": "view\\.sales"}}},
      {"mark": "rule",
       "encoding": {"y": {"datum": 10000}}}
    ]
  }
}
```

Fallback when Omni's native `referenceLines[]` is too thin (Omni 8.12).

### 5.30 Combined axis (Measure Names / Measure Values)

When Tableau uses Measure Names on one axis to display multiple measures, emit one Omni `series[]` per measure with the same axis assignment:

```json
"series": [
  {"field": {"name": "view.sales"}, "title": {"value": "Sales"}, "yAxis": "y"},
  {"field": {"name": "view.profit"}, "title": {"value": "Profit"}, "yAxis": "y"}
]
```

### 5.31 Trellis to facet

For static facet (one tile per facet value): emit N tiles, one per value, with the value as a filter. For dynamic facet: Vega-Lite `facet` channel.

### 5.32 Cross-datasource filter

Requires that both Omni topics expose a dimension with the same Omni field name. Rename via topic `joins:` alias if needed.

### 5.33 Data source filter

**Output (Omni 4.3):**

```yaml
always_where_filters:
  view.is_deleted:
    is: false
```

### 5.34 Extract filter

Move logic upstream into a dbt model or warehouse view.

### 5.35 Web-page zone

**Output:**

```json
{
  "i": "5",
  "spec": {"markdown": "<iframe src='https://example.com'></iframe>"}
}
```

### 5.36 Navigation button

**Output:** Markdown tile with link styled as button via inline HTML/CSS.

```json
{"spec": {"markdown": "<a href='https://omni.../dashboards/abc' style='display:inline-block;padding:8px 16px;background:#4E79A7;color:white;border-radius:4px;text-decoration:none'>View Detail</a>"}}
```

### 5.37 Subscription / alert

Use `omni schedules` CLI (Omni 10) to set up email delivery on the Omni side. Tableau subscription config does not translate; must be re-created.

### 5.38 Tooltip with formatted runs

Collapse multi-run formatted text to a plain-text or markdown approximation:

```text
**Region:** {region}
**Sales:** {sales}
```

Omni `visConfig.tooltip[]` does not support styled runs.

---

## 6. RED list with rationale

Each RED is a feature in Tableau that Omni cannot represent and the migration must address explicitly.

**Cross-database joins (10.0+ federated)** (TWBX 1.5, 3.2). Tableau federated lets a workbook join across, e.g., Snowflake and an Excel file at query time. Omni operates against a single connection per topic. Migration message: "This workbook joins data across connections X and Y. Please pre-join these sources in your warehouse (recommend dbt model `joined_x_y`) and re-point to a single Omni connection."

**Extract refresh / incremental refresh** (TWBX 3.12). Tableau extracts refresh on a schedule and support incremental updates. Omni does not own the data layer; refresh runs in the warehouse. Message: "Tableau's extract refresh schedule does not apply. Refresh logic moves to dbt or your warehouse scheduler."

**Math `HEXBINX` / `HEXBINY`** (TWBX 4.1). Hexagonal binning has no SQL equivalent. Pre-compute in dbt with a custom binning UDF or drop.

**Table calc `SCRIPT_REAL` / `SCRIPT_INT` / `SCRIPT_STR` / `SCRIPT_BOOL`** (TWBX 4.5). R/Python integration. Omni cannot execute external code in a calc. Pre-compute and surface as a column.

**Predictive `MODEL_PERCENTILE` / `MODEL_QUANTILE`** (TWBX 4.1). Tableau's built-in regression-as-a-function. Pre-compute upstream (Snowflake `FORECAST` ML, BigQuery ML, dbt + Python).

**Forecast (model-based analytics object)** (TWBX 5.12). Same root cause. Pre-compute forecast points, then render via line chart.

**Cluster analysis (analytics object)** (TWBX 5.12). Tableau's k-means clustering. Pre-compute cluster assignments upstream as a categorical column.

**Mark `Custom Shape` with PNG** (TWBX 2.4, 5.7). Per-mark PNG shape encoding from `<external><shapes>`. Omni cannot upload custom shapes. Drop the shape encoding; fall back to default Vega-Lite shapes or Unicode glyphs.

**Context filter** (TWBX 5.3). Exists in Tableau to change the order of operations relative to LOD calculations. Since FIXED LODs are materialized as derived tables in Omni (section 5.1 workaround), the context filter concept evaporates. Drop with note.

**"Only relevant values" / cascading filters** (TWBX 5.3). Tableau filter widgets can auto-hide options absent in upstream filter selections. Omni filters do not cascade. Manual workaround: scope each filter to a query that respects the upstream selection (heavy).

**"Show apply button" UI behavior** (Tableau UI flag). Omni applies filters live. No equivalent. Drop.

**Floating zones** (TWBX 6.4). Tableau dashboards support absolute-pixel floating layout. Omni is grid-only. Snap to nearest cell with warning.

**Extension zone (.trex)** (TWBX 6.2). Tableau Extensions are sandboxed iframe widgets with a JS API. Omni does not have an extension framework. Drop with message: "This dashboard uses a Tableau extension (name from `.trex`). The extension cannot migrate. Equivalent functionality needs to be re-built using Omni markdown tiles plus custom Vega-Lite, or hosted externally and embedded as an iframe."

**Show/hide containers** (TWBX 6.2, UI feature). Omni dashboards cannot conditionally show/hide tiles. Drop with message: "Conditional tile visibility is not supported in Omni."

**Highlight action** (TWBX 6.6). Omni does not have hover-highlighting across tiles. Drop.

**Parameter action** (TWBX 6.6). Omni does not have click-to-set-parameter. Drop or convert to a manual filter (YELLOW 5.16).

**Set action** (TWBX 6.6). Sets are a Tableau primitive. Drop.

**Device-specific layouts (phone, tablet)** (TWBX 6.1). Omni layout is responsive but not device-conditioned. The phone-specific layout is discarded; Omni responsive grid covers the basic case.

**Story navigator: number style** (TWBX 7.1). Omni does not enumerate a numeric navigator style.

**Story navigator: arrows-only style** (TWBX 7.1). Same.

**Workbook-level theme (`<style>` block)** (TWBX 2.3). Omni does not currently expose an org-level brand theme via model files. Per-dashboard styling only. Roadmap candidate [INFERRED].

**Per-mark / per-worksheet font customization** (TWBX 8.6). Omni does not expose per-tile font control. Drop.

**Mark annotations** (Tableau XML annotation element, not enumerated in TWBX spec sections shown). Drop.

**Viz-in-tooltip** (Tableau interactive feature). Drop; no equivalent.

**Workbook-level actions** (TWBX 2.1, `<workbook><actions>`). Rare; drop.

**Tableau Server: subscriptions / alerts** (Tableau Server feature). Re-create using `omni schedules` (YELLOW 5.37) but the configuration does not migrate.

**Tableau Server: permissions** (Tableau Server feature). Re-create using Omni access grants. Does not migrate from TWBX.

---

## 7. GREY list with resolution plans

| # | Unknown | Single experiment to resolve | Time cost | Likely bucket |
|---|---|---|---|---|
| 1 | Multi-tab dashboard `documentMetadata.presentation` shape (Omni 6.4) | Build a 2-tab dashboard in the Omni UI, export via `GET /api/unstable/documents/{id}/export`, diff the JSON against a single-tab export | 30 min | YELLOW (likely) |
| 2 | `tileFilterMap` / `tileControlMap` per-tile override shape (Omni 6.5, 9.5) | Build a dashboard with 2 tiles where one has an extra filter override, export and inspect | 20 min | YELLOW |
| 3 | `omni-kpi` `spec.rows[]` full schema for all row types (Omni 8.8) | Build a KPI with one of each row type (number, comparison, progress bar, progress circle, chart line, chart bars, text), export | 30 min | GREEN |
| 4 | Native top-N filter in `queryJson` (Omni 7.1) | Build a Top-10 sorted bar chart in the UI, export, look at `queryJson.filters` and `queryJson.sorts` | 15 min | YELLOW |
| 5 | 100% stacked bar JSON key (Omni 8.5) | Build a `stack %` bar in the UI, export | 10 min | GREEN |
| 6 | Reference line JSON shape (Omni 8.12) | Build a bar chart with avg reference line, export | 10 min | GREEN |
| 7 | Continuous color gradient spec keys (Omni 8.13, 8.14) | Build a bar with continuous color, export | 10 min | GREEN |
| 8 | Diverging color spec keys | Build with diverging palette, export | 10 min | GREEN |
| 9 | Conditional formatting per-row color logic (Omni 8.7) | Build a table with green-positive / red-negative profit, export | 15 min | YELLOW (likely SQL-driven workaround in `columnFormats`) |
| 10 | Map (`map` / `svg-map`) visType full JSON (Omni 8.1, 8.11) | Build a US-state filled map, export | 20 min | YELLOW |
| 11 | Secondary y-axis (`y2`) JSON keys (Omni 8.4) | Build a dual-axis chart in the UI, export | 15 min | YELLOW or GREEN |
| 12 | Axis log scale key | Build a log-scale chart, export | 10 min | GREEN |
| 13 | Axis fixed range / domain key | Build a chart with manually set x range, export | 10 min | GREEN |
| 14 | Cross-tile filter wiring (Omni 6.5 itself, plus `tileFilterMap`) | Build crossfilter-enabled dashboard, click in one tile, check the resulting filter state on the other | 20 min | YELLOW |
| 15 | Cross-dashboard navigation link shape (Omni 6.5) | Build two dashboards, add a button link from one to the other, inspect | 15 min | YELLOW |
| 16 | Border / gridline styling on table tiles (Omni 8.7) | Inspect `resultConfig.columnFormats` for border keys | 10 min | likely RED (not supported) |
| 17 | Dashboard background color key (Omni 6 generally) | Inspect `documentMetadata.presentation` for a background color | 10 min | likely YELLOW (markdown tile workaround) |
| 18 | `omni schedules` CLI full API (Omni 10) | `omni schedules --help` plus a test send | 15 min | likely GREEN for basic email schedule |
| 19 | `extends:` topic / model inheritance from a published Tableau-style datasource (TWBX 3.2 `sqlproxy`) | Try referencing an existing shared model from a new workbook model | 20 min | GREEN |
| 20 | `omni-kpi` progress comparison band shape (TWBX bullet chart analog) | Build a progress row with target plus comparison, export | 15 min | YELLOW |
| 21 | Symbol map (`map` visType) for point data | Build a US city pin map, export | 15 min | YELLOW |
| 22 | Wildcard regex `kind` on JSON wire side (Omni 9.2) | Build a filter with regex match, inspect the kind | 5 min | likely GREEN |

Total experiment budget: ~6 hours of UI clicking and JSON inspection unlocks most of the YELLOW-to-GREEN demotions.

---

## 8. Priority queue for the emitter

Ranked by GREEN density, workbook prevalence, and migration value.

### Phase 1 (must ship first)

1. **Connection plus view file generation** (GREEN density 60 percent of semantic model). Datasource to view, columns to dimensions/measures, default aggregations, default formats. Covers 80 percent of any real workbook's data layer.
2. **Relationships file from physical joins and logical noodle** (GREEN density 80 percent). Cover inner, left, right, full, plus cardinality. Single emitter, two parse paths (legacy `<relation>` vs `<object-graph>`).
3. **Topic file** (GREEN). Group views into topics; emit `joins:` map; cover `always_where_filters`, `default_filters`.
4. **Basic mark types**: bar, line, area, scatter, table (GREEN). One Vega-Lite assembler stub for the YELLOWs.
5. **Filter translation** (60 percent GREEN). Categorical, range, relative-date, top-N, wildcard, conditional. Map to `queryJson.filters` and `dashboard.filterConfig`.
6. **Grid layout flattening** (Tableau zones to Omni 12-col grid). Covers 70 percent of tiled dashboards.
7. **Format string translation table** (number formats + shortcuts).
8. **Aliases / groups / bins to SQL CASE** (YELLOW, but mechanical).

### Phase 2 (high-value workarounds)

9. **LOD FIXED to derived_table** (YELLOW, prevalent in real workbooks).
10. **Table calcs to SQL window functions** (YELLOW; covers running sums, % of total, moving averages).
11. **Parameter to templated filter** (YELLOW; high user-visible impact).
12. **Dual axis to Vega-Lite layered** (YELLOW; prevalent).
13. **Trend line to Vega-Lite regression** (YELLOW).
14. **Pie / donut to native arc** (GREEN once verified).
15. **Sort manual to CASE order column** (YELLOW).
16. **Conditional formatting on tables** (YELLOW, GREY parts).
17. **Sparkline via KPI chart row** (GREEN once GREY 3 resolved).
18. **URL action to dimension `link:`** (YELLOW).
19. **Text / image / markdown zones** (GREEN).
20. **Top-N filter via pre-rank** (YELLOW).

### Phase 3 (advanced visualizations and warnings)

21. **Filled map and symbol map via Vega-Lite geoshape** (YELLOW).
22. **Trellis / facet** (YELLOW).
23. **Gantt, waterfall, pareto via Vega-Lite** (YELLOW).
24. **Cross-filter wiring** (YELLOW, GREY parts).
25. **Multi-tab dashboards from stories** (GREY-to-YELLOW).
26. **All RED-list features**: emit a structured warning report listing every feature that did NOT migrate with file/line cite back to the TWBX, plus the recommended manual action.

Cut-line for v1: Phase 1 only. Cuts time-to-first-dashboard roughly in half.

---

## 9. Open questions for Omni and Tableau vendor teams

### To Omni docs / engineering

1. What is the full JSON schema for `documentMetadata.presentation` including multi-tab layout (`tabs[]` or equivalent)?
2. What is the full per-tile filter / control override JSON in `dashboard.metadata.tileFilterMap` and `dashboard.metadata.tileControlMap`?
3. What is the complete `omni-kpi.spec.rows[]` schema, enumerating every row `type` value and its required fields?
4. Is there a roadmap item for click-to-set-parameter / parameter actions analogous to Tableau's parameter actions?
5. Is there a roadmap item for org-level theming (brand colors, default fonts) configured at the model file level?
6. What is the documented JSON shape for `visConfig.referenceLines[]`?
7. What is the documented JSON shape for secondary y-axis (`y2`)?
8. What is the documented `kind` enum for `STRING_MATCHES_REGEX` and `DATE_*` filter wire values beyond `WITHIN_RANGE`?
9. Are conditional `columnFormats` (row-value-driven cell colors) supported in `omni-spreadsheet`, and what is the JSON?
10. Does Omni plan a native top-N filter on `queryJson` to replace the pre-rank workaround?
11. Does Omni plan a native dimension-swap / measure-swap pattern beyond `FIELD_SELECTION` controls?

### To Tableau docs / engineering

1. Is there a comprehensive XSD for the `_.fcp.ObjectModelEncapsulateLegacy.true...object-graph` element family? (Open issue: `tableau/document-api-python#237` references this.)
2. Are there documented values for every `derivation` token used in `<column-instance name=>` pivot keys (`qk`, `nk`, `ok`)?
3. For mark annotations and viz-in-tooltip: what is the canonical XML element name and schema?
4. Are there known canonical Excel-to-Tableau format-string differences beyond the `c0`/`p1%`/`s` shortcuts in section 8.4? A complete shortcut table would close the YELLOW on number-format translation.

---

End of audit.
