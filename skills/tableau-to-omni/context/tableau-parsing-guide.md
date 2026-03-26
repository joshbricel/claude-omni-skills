# Tableau Workbook Parsing Guide

Reference for parsing `.twb` XML files extracted from `.twbx` archives. Covers the XML structure for connections, columns, calculated fields, worksheets, and dashboard layout.

## File Format

A `.twbx` file is a zip archive containing:
- One `.twb` file (the workbook XML)
- An optional `Data/` directory with Hyper extracts
- Optional image or shape files

```python
import zipfile

with zipfile.ZipFile("dashboard.twbx", "r") as z:
    twb_files = [f for f in z.namelist() if f.endswith(".twb")]
    # Usually one .twb file at the root level
```

## XML Root Structure

```xml
<workbook version="2025.2" ...>
  <preferences />
  <datasources>
    <datasource name="..." caption="...">
      <connection ... />
      <column ... />
      <column ... />
    </datasource>
  </datasources>
  <worksheets>
    <worksheet name="...">
      <table>
        <view> ... </view>
        <style> ... </style>
        <panes> ... </panes>
      </table>
    </worksheet>
  </worksheets>
  <dashboards>
    <dashboard name="...">
      <zones> ... </zones>
    </dashboard>
  </dashboards>
</workbook>
```

## 1. Connection Details

Location: `workbook > datasources > datasource > connection`

```xml
<connection class="snowflake" dbname="DEMO_DB" schema="PUBLIC"
            server="account.snowflakecomputing.com"
            username="USER" warehouse="WH_NAME">
  <relation name="TABLE_NAME" table="[DB].[SCHEMA].[TABLE]" type="table" />
</connection>
```

Key attributes:
| Attribute | Description |
|-----------|-------------|
| `class` | Connection type (snowflake, postgres, bigquery, etc.) |
| `dbname` | Database name |
| `schema` | Schema name |
| `server` | Server hostname |
| `relation.table` | Full table reference |

## 2. Columns / Fields

Location: `datasource > column`

```xml
<column datatype="string" name="[STAGENAME]" role="dimension"
        semantic-role="[State].[Name]" type="nominal">
  <desc>
    <formatted-text><run>Stage Name</run></formatted-text>
  </desc>
</column>
```

```xml
<column datatype="real" name="[AMOUNT]" role="measure"
        type="quantitative" default-format="c0"
        aggregation="Sum" />
```

Key attributes:
| Attribute | Values | Description |
|-----------|--------|-------------|
| `datatype` | string, real, integer, date, boolean | Column data type |
| `role` | dimension, measure | Tableau role |
| `type` | nominal, ordinal, quantitative | Measurement type |
| `aggregation` | Sum, Count, Avg, Min, Max | Default aggregation |
| `default-format` | Format string | Number/date format |
| `caption` | Display name | Friendly name (if different from column) |

### Physical vs Calculated Columns

Physical columns have a `name` matching the database column (e.g., `[AMOUNT]`).

Calculated columns have a generated name and a `calculation` child:

```xml
<column caption="Close Date Filter"
        datatype="boolean"
        name="[Calculation_2624543104377954307]"
        role="dimension" type="nominal">
  <calculation class="tableau" formula="[CLOSEDATE] &gt; date('2024-01-01')" />
</column>
```

Note: XML escaping means `>` appears as `&gt;` in formulas.

## 3. Calculated Fields

Location: `datasource > column > calculation`

Common Tableau calculation patterns:

| Pattern | Example | Omni Translation |
|---------|---------|-------------------|
| Date comparison | `[CLOSEDATE] > date('2024-01-01')` | Date filter with relative range |
| WINDOW_AVG | `WINDOW_AVG(SUM([AMOUNT]), -11, 0)` | No direct equivalent (custom SQL) |
| IF/THEN | `IF [STAGE] = 'Won' THEN [AMOUNT] END` | SQL CASE expression |
| DATEDIFF | `DATEDIFF('month', [Created], TODAY())` | Omni date dimension with granularity |
| CONTAINS | `CONTAINS([NAME], 'test')` | SQL LIKE or ILIKE |

### Table Calculations

Table calculations are defined at the column-instance level within worksheets, not at the datasource level:

```xml
<column-instance column="[sum:AMOUNT:qk]" derivation="WindowTotal"
                 type="quantitative">
  <table-calc ordering-type="Rows"
              agg-type="Avg" from="-11" to="0" />
</column-instance>
```

Key attributes:
| Attribute | Description |
|-----------|-------------|
| `derivation` | WindowTotal, Rank, RunningTotal, etc. |
| `ordering-type` | Rows, Columns, or specific field |
| `agg-type` | Avg, Sum, Count for the window |
| `from`, `to` | Window boundaries (negative = lookback) |

## 4. Worksheets

Location: `workbook > worksheets > worksheet`

### Fields on Axes

```xml
<worksheet name="Closed Won Amount">
  <table>
    <view>
      <datasources>
        <datasource name="datasource_name" />
      </datasources>
      <datasource-dependencies datasource="datasource_name">
        <column datatype="..." name="..." />
        <column-instance column="..." derivation="..." type="..." />
      </datasource-dependencies>
    </view>
  </table>
</worksheet>
```

Rows and columns shelves are defined in `<rows>` and `<cols>` elements:

```xml
<rows>[datasource].[field1] [datasource].[field2]</rows>
<cols>[datasource].[date_field]</cols>
```

### Filters

Worksheet filters appear as `<filter>` elements:

```xml
<filter class="categorical" column="[datasource].[Calculation_123]">
  <groupfilter function="member" level="[Calculation_123]"
               member="true" user:ui-enumeration="inclusive"
               user:ui-marker="enumerate" />
</filter>
```

```xml
<filter class="categorical" column="[datasource].[STAGENAME]">
  <groupfilter function="member" level="[STAGENAME]"
               member="&quot;Closed Won&quot;"
               user:ui-enumeration="inclusive" />
</filter>
```

Filter types:
| Type | XML Pattern |
|------|-------------|
| Include specific value | `function="member"` with `member="value"` |
| Exclude values | `function="except"` wrapping `function="member"` |
| Range filter | `function="and"` with `min`/`max` |
| Boolean (true only) | `member="true"` on calculated boolean field |

### Mark Types and Encodings

```xml
<panes>
  <pane>
    <mark class="Automatic" />
    <encodings>
      <color column="[datasource].[:Measure Names]" />
      <text column="[datasource].[sum:AMOUNT:qk]" />
    </encodings>
  </pane>
</panes>
```

Mark classes: `Automatic`, `Bar`, `Line`, `Area`, `Circle`, `Square`, `Text`, `Shape`, `Gantt Bar`

Encoding types: `color`, `size`, `shape`, `text`, `tooltip`, `detail`, `path`

## 5. Dashboard Layout

Location: `workbook > dashboards > dashboard`

### Size

```xml
<dashboard name="Dashboard Name">
  <size maxheight="800" maxwidth="1000"
        minheight="800" minwidth="1000" />
```

### Zones

Each zone represents a worksheet placement or container:

```xml
<zone h="17500" id="4" type-v2="layout-basic" w="98400"
      x="800" y="1000">
  <zone h="17500" id="5" name="Pipeline Stages"
        w="98400" x="800" y="1000">
    <zone-style>
      <format attr="border-style" value="none" />
    </zone-style>
  </zone>
</zone>
```

Zone attributes:
| Attribute | Description |
|-----------|-------------|
| `x`, `y` | Position in Tableau units (not pixels) |
| `w`, `h` | Width and height in Tableau units |
| `name` | Worksheet name (links to worksheet definition) |
| `type-v2` | `layout-basic` (container), `layout-flow` (flow) |

### Converting Tableau Layout to Omni Grid

Tableau uses arbitrary coordinate units. Omni uses a 12-column grid.

Conversion approach:
1. Find the total dashboard width from the `<size>` element
2. Calculate each zone's proportional width: `zone.w / total_width`
3. Map to 12-column grid: `round(proportion * 12)`
4. Stack vertically by sorting zones by `y` coordinate

Example:
```
Tableau: w=98400 out of 100000 total -> 12/12 columns (full width)
Tableau: w=49200 out of 100000 total -> 6/12 columns (half width)
```

### Phone Layout

Phone layouts are auto-generated and appear as separate zone trees with `type-v2="layout-flow"`. These can generally be ignored for migration since Omni handles responsive layout automatically.

## 6. Dashboard Name

The dashboard name is extracted from the `<dashboard>` element's `name` attribute:

```xml
<dashboard name="Salesforce Demo dashboard">
```

Use this value as the Omni document name (`dashboard.name` and `document.name` in the import payload) so the migrated dashboard retains the original Tableau workbook title.

```python
dashboards = root.findall('.//dashboards/dashboard')
for dash in dashboards:
    dashboard_name = dash.get('name', 'Untitled Dashboard')
```

## Parsing Checklist

- [ ] Extract dashboard name from `<dashboard name="...">`
- [ ] Extract connection type, server, database, schema, table
- [ ] List all physical columns with datatype, role, aggregation
- [ ] Extract calculated field formulas (unescape XML entities)
- [ ] Identify table calculations and their window parameters
- [ ] Parse each worksheet: fields on rows/columns, filters, mark types
- [ ] Map dashboard zones to worksheet names with positions
- [ ] Note custom sorts, number formats, color overrides
- [ ] Identify measure aliases (display names)
