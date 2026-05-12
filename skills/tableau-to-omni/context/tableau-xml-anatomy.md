# Tableau .twb XML Anatomy

The `.twb` file inside a `.twbx` is the workbook definition. Everything visual, every formula, every interaction is encoded in its XML. This file is the field guide.

The on-disk format uses single-quoted attributes. Tag names are lowercase. There is no namespace. ElementTree handles it without configuration.

## Top-level structure

```
<workbook source-build='9.2.0' version='9.2'>
  <preferences>...</preferences>
  <datasources>
    <datasource name='Parameters' .../>            <!-- the parameters pseudo-source -->
    <datasource name='..' caption='..'>            <!-- real data sources -->
      <connection .../>                            <!-- server, db, schema -->
      <relation .../>                              <!-- tables, joins, custom SQL -->
      <calculations>...</calculations>             <!-- pattern A: inline calc fields -->
      <metadata-records>...</metadata-records>     <!-- raw column inventory -->
      <column>...</column>                         <!-- pattern B: column-attached calcs -->
    </datasource>
  </datasources>
  <worksheets>
    <worksheet name='..'>...</worksheet>
  </worksheets>
  <dashboards>
    <dashboard name='..'>
      <zones>...</zones>                           <!-- layout tree -->
    </dashboard>
  </dashboards>
  <windows>
    <window hidden='true' name='..'/>              <!-- sheet visibility flags -->
  </windows>
  <actions>
    <action type='filter|highlight|param|set|url'/>
  </actions>
  <style>
    <style-rule>...</style-rule>                   <!-- fonts, colors, borders -->
  </style>
</workbook>
```

## `<connection>`: where the data comes from

```xml
<connection
    class='snowflake'                              <!-- driver class -->
    server='myorg.snowflakecomputing.com'
    dbname='ACME_EVENTS_DEMO'
    schema='PUBLIC'
    warehouse='COMPUTE_WH'
    username='ANALYST'
    server-oauth=''
    workgroup-auth-mode='prompt'>
  <relation type='table' table='[VW_EVENTS_WIDE]'/>
</connection>
```

`class` is the driver. Common values:

| `class` | What it is |
|---------|------------|
| `snowflake` | Live Snowflake |
| `redshift` | Live Redshift |
| `sqlserver` | Live SQL Server |
| `postgres` | Live Postgres |
| `bigquery` | Live BigQuery |
| `textscan` | CSV / TSV |
| `excel-direct` | Excel |
| `sqlproxy` | Tableau Server-published data source |
| `federated` | Multi-source federation (the proxy abstracts joins) |
| `hyper` | Tableau Hyper extract (in `.twbx`) |
| `tde` | Pre-2020 Tableau Data Extract |

Migration implication: a `sqlproxy` source means the workbook is bound to a Tableau Server-published data source you don't control directly. The `dbname` reveals the original published-source name; you'll need to find or recreate that source in Omni.

## `<relation>`: tables, joins, custom SQL

Single table:

```xml
<relation type='table' table='[VW_EVENTS_WIDE]'/>
```

Custom SQL:

```xml
<relation type='text' name='Custom SQL Query'>
SELECT *
FROM ACME_EVENTS_DEMO.PUBLIC.VW_EVENTS_WIDE
WHERE startdate &gt;= '2025-01-01'
</relation>
```

Multi-table join:

```xml
<relation type='join' join='left'>
  <relation type='table' table='[FCT_EVENT_REGISTRATIONS]'/>
  <relation type='table' table='[DIM_EVENTS]'/>
  <clause type='join'>
    <expression op='='>
      <expression op='[FCT_EVENT_REGISTRATIONS].[EVENT_ID]'/>
      <expression op='[DIM_EVENTS].[EVENT_ID]'/>
    </expression>
  </clause>
</relation>
```

For the migration, custom SQL becomes Omni view SQL. Joins become Omni topic relationships.

## `<column>`: fields and calc fields

A field bound to a source column:

```xml
<column
    datatype='integer'
    name='[EVENT_ID]'
    role='dimension'
    type='ordinal'
    caption='Event Id'/>
```

A calc field (column-attached pattern, post-9.0 workbooks):

```xml
<column datatype='integer' name='[Age]' role='measure' type='quantitative'>
  <calculation class='tableau' formula='DATEDIFF("year", [DOB], TODAY())'/>
</column>
```

A calc field (inline pattern, pre-9.0 or republished workbooks):

```xml
<calculations>
  <calculation column='[Age]' formula='DATEDIFF(&quot;year&quot;, [DOB], TODAY())'/>
</calculations>
```

Both patterns coexist in real workbooks. `extract.py` handles both and dedupes by column name.

### Detecting LODs

Formula starts with `{ FIXED ... :`, `{ INCLUDE ... :`, or `{ EXCLUDE ... :`. Tableau allows whitespace; the regex is `\{\s*(FIXED|INCLUDE|EXCLUDE)\s+`.

LODs are the migration's hardest case. Most translate to subqueries in Omni topic SQL or to derived tables. Some don't translate at all (FIXED at non-trivial grains where the join shape doesn't allow it).

### Detecting table calcs

Look for these function names: `WINDOW_*`, `RUNNING_*`, `INDEX(`, `FIRST(`, `LAST(`, `RANK(`, `TOTAL(`, `LOOKUP(`, `PREVIOUS_VALUE(`, `SCRIPT_*`. Table calcs operate on the post-aggregation virtual table; Omni doesn't have a direct equivalent. They're usually rebuilt as window functions in topic SQL.

## `<datasource name='Parameters'>`: parameters

A pseudo-datasource that holds workbook parameters. Each parameter is a `<column>` with no real data binding:

```xml
<column
    name='[Date Selector]'
    caption='Date Selector'
    datatype='date'
    role='measure'
    type='quantitative'>
  <calculation class='tableau' formula='#2026-04-15#'/>
  <aliases>
    <alias key='..' value='..'/>
  </aliases>
  <members>
    <member alias='..' value='..'/>
  </members>
</column>
```

`<calculation formula='...'/>` is the default value. `<members>` is the optional value list (for "list" parameters).

In Omni: parameters become topic-level template parameters or dashboard filters.

## `<worksheet>`: a single sheet's definition

```xml
<worksheet name='Events Trend'>
  <table>
    <view>
      <datasources>
        <datasource caption='Acme Events' name='federated.xxx'/>
      </datasources>
      <datasource-dependencies datasource='federated.xxx'>
        <column .../>                              <!-- field references -->
      </datasource-dependencies>
      <filter class='..'>...</filter>              <!-- worksheet filters -->
      <slices>
        <column>[STARTDATE]</column>               <!-- pill on rows/cols -->
      </slices>
      <rows>...</rows>                             <!-- rows shelf -->
      <cols>...</cols>                             <!-- columns shelf -->
      <pages>...</pages>                           <!-- pages shelf -->
      <mark class='Bar'/>                          <!-- mark type -->
      <encodings>
        <color column='[Category]'/>
        <size  column='[Total]'/>
      </encodings>
    </view>
  </table>
</worksheet>
```

For the migration, the marks-card shape (rows / cols / mark-type / color / size / shape / detail) maps to Omni `visConfig.spec`.

## `<dashboard>` and `<zones>`: layout

```xml
<dashboard name='Events overview'>
  <size sizing='auto' maxheight='800' maxwidth='1200'/>
  <zones>
    <zone id='1' type='layout-flow' param='vert' x='0' y='0' w='1200' h='800'>
      <zone id='2' type='layout-flow' param='horz' x='0' y='0' w='1200' h='80'>
        <zone id='3' name='Title' type='text' x='0' y='0' w='1200' h='80'>...</zone>
      </zone>
      <zone id='4' name='Events Trend' type='layout-basic' x='0' y='80' w='800' h='400'>
        <!-- this zone hosts a worksheet with the matching name -->
      </zone>
      <zone id='5' name='Filters' type='layout-flow' param='vert' x='800' y='80' w='400' h='400'>
        <zone id='6' name='Geo Filter' type='filter' .../>
      </zone>
    </zone>
  </zones>
</dashboard>
```

Each `<zone>` has `x`, `y`, `w`, `h` in pixels. `param='vert'` or `param='horz'` indicates a vertical or horizontal layout flow. `floating='true'` means the zone is positioned absolutely on top of the layout grid.

`type` values:

| `type` | Meaning |
|--------|---------|
| `layout-flow` | A container that lays out children in a direction (vert or horz) |
| `layout-basic` | A leaf container, often hosting a worksheet (matched by `name`) |
| `text` | A text box |
| `image` | An embedded image |
| `web` | A web page embed |
| `filter` | A filter card |
| `parameter` | A parameter card |
| `legend` | A legend |

For the migration: walk the tree depth-first, collapse layout-flow chains, and emit Omni `gridConfig` blocks.

## `<actions>`: interactivity

```xml
<actions>
  <action type='filter' name='Filter by Geo'>
    <source-dashboards>
      <source-dashboard>Events overview</source-dashboard>
    </source-dashboards>
    <source-sheets>
      <source-sheet name='Geo Filter 2'/>
    </source-sheets>
    <target-sheets>
      <target-sheet name='Events Trend'/>
      <target-sheet name='Events by Category'/>
    </target-sheets>
    <field-mappings>
      <field-mapping source='[NAME (GEO)]' target='[NAME (GEO)]'/>
    </field-mappings>
  </action>
</actions>
```

Action types and Omni mappability:

| Tableau action type | Omni equivalent |
|---------------------|-----------------|
| `filter` | Dashboard filter (with target tile scoping) |
| `highlight` | None native; document and skip |
| `param` (parameter action) | Hard, no clean equivalent. Document. |
| `set` (set action) | None; rebuild as filter or topic-level membership |
| `url` (URL action) | Tile-level click-through link |

## `<style>`: visual formatting

```xml
<style>
  <style-rule element='worksheet'>
    <format attr='font-family' value='Arial'/>
    <format attr='font-size' value='12'/>
  </style-rule>
  <style-rule element='dashboard'>
    <format attr='background-color' value='#FFFFFF'/>
  </style-rule>
</style>
```

For the migration: styles map roughly to Omni dashboard themes. Not every Tableau format property has an Omni equivalent (e.g., banding patterns, conditional cell coloring). Document and rebuild manually for high-value cases.

## `<encoding>`: hardcoded color palettes

When a user picks specific colors for specific values:

```xml
<encodings>
  <color column='[Category]' palette='custom'>
    <map>
      <bucket value='Running'>#FF6B35</bucket>
      <bucket value='Yoga'>#9D4EDD</bucket>
    </map>
  </color>
</encodings>
```

In Omni: dashboard theme color rules or per-tile color overrides.

## What's not in the .twb

- Server-side data refreshes (those live in Tableau Server, separately).
- Per-user permissions (server-only).
- View counts and usage statistics (server-only).
- Subscriptions and alerts (server-only).
- Comments on views (server-only).

If you need any of this, you need Tableau Server REST API access. Out of scope for this skill, in scope for the planned bulk-migration follow-up.
