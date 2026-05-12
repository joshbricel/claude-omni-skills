# Tableau TWBX / .twb XML Format Spec (Reference)

Deep technical reference for parsing the Tableau Workbook (TWB) XML format from inside a Tableau Packaged Workbook (TWBX) archive, oriented toward emitting an Omni Analytics workbook (YAML model + JSON dashboard import payload).

This file is the Level 2/3 companion to the Level 1 `tableau-parsing-guide.md` in the same directory. Read that first; it covers the basic shape. This file fills in: full element/attribute coverage, the post-2020.2 logical layer, calculation language internals, table-calc XML, every filter variant, dashboard zone tree, action XML, color and format strings, the .hyper extract, and an exhaustive map-to-Omni table at the end.

The companion file `omni-cli-format-spec.md` covers Omni's side. Section names in the Map-to-Omni section reference that file by section number.

---

## 0. Scope, conventions, source materials

### 0.1 What is in scope

- `.twbx` archive layout and the sibling `.tdsx` / `.tds` formats
- The full `.twb` XML tree from `<workbook>` root down through worksheets, dashboards, stories, actions, parameters, custom palettes
- Calculated fields (formula language) and table calculation XML
- Filter XML for every UI variant (categorical, range, top-N, conditional, relative-date, context, wildcard)
- Dashboard zone tree and the percentage-based coordinate system
- `.hyper` extract: structure and how to read it via the Hyper API
- A consolidated Tableau-to-Omni concept map with file/section pointers

### 0.2 What is out of scope

- Omni semantics, YAML, and JSON shape (see `omni-cli-format-spec.md`)
- Tableau Server REST API, permissions, schedules
- TableCalc internals beyond what surfaces in XML
- Tableau Prep `.tfl` / `.tflx` flow files

### 0.3 Conventions

- Element names appear as `<element>`, attributes as `attr=`.
- All XML examples are extracted from public reference workbooks, the official `tableau-document-schemas` XSD, the `document-api-python` library source, or community reverse-engineering posts. Citations end every section.
- XML entity escaping in formula text: `>` becomes `&gt;`, `<` becomes `&lt;`, `&` becomes `&amp;`, `"` becomes `&quot;`. A parser must un-escape before evaluating Tableau syntax.
- Tableau-internal field names use the bracket pattern `[FieldName]` in the XML. Generated calculation names follow `[Calculation_<19-digit-id>]`.
- Datasource-qualified references use `[datasource_name].[FieldName]` with optional aggregation prefix and type suffix, e.g. `[orders].[sum:AMOUNT:qk]`. See section 5.4.

### 0.4 Sources

- Tableau Document Schemas (official XSD, Feb 2026): `https://github.com/tableau/tableau-document-schemas`
- `document-api-python`: `https://github.com/tableau/document-api-python`
- Hyper API: `https://tableau.github.io/hyper-db/docs/`
- `tableauandbehold.com` series on TDS / TWB internals
- `bitips.blog`, Yaron Lirase Medium, Shivaug Medium, ranvithm/tableau.xml, drintoul/tableau-xml-parse
- `cmtoomey` annotated workbook gist (`https://gist.github.com/cmtoomey/96342ba07dd5cba6ecc6`)
- Tableau Help (color palettes, format strings, LOD semantics, dashboard layout)

Per-section citations appear at the end of each numbered section.

---

## 1. TWBX archive layout

### 1.1 File extensions and what each contains

| Ext | Container | Holds |
|-----|-----------|-------|
| `.twb` | Plain XML | Workbook only. Live-connection only. No data. |
| `.twbx` | Zip | `.twb` + extracts (`.hyper` / `.tde`) + images / shapes / mapsource files. |
| `.tds` | Plain XML | Single datasource only (root is `<datasource>`, not `<workbook>`). No data. |
| `.tdsx` | Zip | `.tds` + extracts and local file data referenced by the connection. |
| `.hyper` | Tableau Hyper file (Postgres-derived columnar) | Extract data. SQL-queryable via Hyper API. |
| `.tde` | Tableau Data Extract (legacy, pre-Hyper) | Extract data. Deprecated since 2018. Tableau auto-upgrades to `.hyper`. |
| `.tfl` / `.tflx` | Prep flow | Out of scope for this spec. |

### 1.2 TWBX zip directory layout

```text
my_workbook.twbx (zip)
├── my_workbook.twb              # the XML root, name matches archive
├── Data/
│   └── Datasources/
│       └── federated_xxxx.hyper  # one .hyper per embedded extract
├── Image/                        # PNG / JPG images embedded in dashboards
│   └── img_<hash>.png
├── Shapes/                       # custom shape PNGs (also base64 embedded in .twb under <external><shapes>)
│   └── my_shape.png
├── Mapsource/                    # custom map TMS / WMS configs
└── Extras/                       # rare; cached metadata, custom geocoding
```

The `.twb` is always at the archive root. There is exactly one. Its filename is informational; the `<workbook>` element is the canonical source of name and version metadata.

```python
import zipfile

with zipfile.ZipFile("my_workbook.twbx") as z:
    twb = next(n for n in z.namelist() if n.endswith(".twb"))
    hypers = [n for n in z.namelist() if n.endswith(".hyper")]
    images = [n for n in z.namelist() if n.startswith("Image/")]
    shapes = [n for n in z.namelist() if n.startswith("Shapes/")]
```

### 1.3 Embedded vs live extracts

- **Live connection.** The `<datasource>` has a `<connection>` whose `class` attribute names the source (e.g. `snowflake`, `postgres`, `redshift`, `excel-direct`). No `Data/` directory. The `<datasource>` may still contain a `<extract>` child if the user enabled extracting.
- **Embedded extract.** A `<connection class="hyper">` (or `class="dataengine"` for legacy `.tde`) points at `Data/Datasources/<name>.hyper` inside the archive. The original live-connection `<connection>` is preserved alongside as a sibling so Tableau can refresh.
- **Multi-connection (federated).** The `<datasource>` has `<connection class="federated">` wrapping `<named-connections>` with one `<named-connection>` per underlying source. See section 3.2.

### 1.4 Server-published workbooks

A workbook published to Tableau Server / Cloud and then downloaded locally has a `<repository-location>` element on `<workbook>`:

```xml
<repository-location derived-from="https://10ax.online.tableau.com/.../workbooks/Foo"
                     id="Foo" path="/t/site/workbooks" revision="3.0"
                     site="site"/>
```

Published datasources gain `<connection class="sqlproxy">` pointing at the server, plus a `<repository-location>` inside the `<datasource>`.

### 1.5 Tableau version and breaking changes

`<workbook version="...">` is the workbook format version. Major schema breaks:

| Tableau version | What changed |
|-----------------|--------------|
| 9.0 | Story XML added (`<story>`, `<story-points>`). |
| 10.0 | Cross-database joins, multi-connection `<connection class="federated">` introduced. |
| 10.5 | `.hyper` replaces `.tde` for new extracts. |
| 18.1 / 2018.1 | `<datasource>` adds `<aliases>` element with explicit value mappings (replacing inline `value-mapping` runs). |
| 2020.2 | Logical layer added. Old `<relation>` tree is wrapped in `<_.fcp.ObjectModelEncapsulateLegacy.true...relation>`. New `<_.fcp.ObjectModelEncapsulateLegacy.true...object-graph>` element holds the noodle relationships. See section 3.4. |
| 2020.4 | Set actions enabled at workbook level (`<set-action>` in `<actions>`). |
| 2021.4 | Parameter actions added. |
| 2026.1 | First officially-published XSD (`twb_2026.1.0.xsd`). |

Older workbooks load in newer Tableau but the on-disk version stays at the original. Newer workbooks fail to open in older Tableau when the version delta is large.

### 1.6 Citations

- `https://github.com/tableau/tableau-document-schemas`
- `https://github.com/tableau/document-api-python`
- `https://www.thedataschool.co.uk/a/marc-reid/tableaus-many-file-types/`
- `https://help.tableau.com/current/pro/desktop/en-us/environ_filesandfolders.htm`
- `https://help.tableau.com/current/pro/desktop/en-us/export_connection.htm`

---

## 2. .twb XML root and global elements

### 2.1 `<workbook>` root

```xml
<?xml version='1.0' encoding='utf-8'?>
<workbook locale='en_US'
          original-version='18.1'
          source-build='2024.3.0 (20243.24.1023.1234)'
          source-platform='mac'
          version='18.1'
          xml:base='https://10ax.online.tableau.com/...'
          xmlns:user='http://www.tableausoftware.com/xml/user'>
  <document-format-change-manifest>
    <ManifestByVersion/>
  </document-format-change-manifest>
  <preferences> ... </preferences>
  <style/>
  <repository-location .../>
  <datasources> ... </datasources>
  <worksheets> ... </worksheets>
  <dashboards> ... </dashboards>
  <stories> ... </stories>             <!-- optional -->
  <windows> ... </windows>             <!-- per-tab UI state, ignorable -->
  <thumbnails> ... </thumbnails>       <!-- base64 PNGs for tab previews -->
  <external>
    <shapes> ... </shapes>             <!-- custom shape library -->
  </external>
  <actions> ... </actions>             <!-- workbook-level (rare; usually per-dashboard) -->
</workbook>
```

Attribute notes:

- `version` is the on-disk format version. `original-version` is the version that first authored the document.
- `source-platform` is `win` or `mac`. Affects path separators in file connections.
- `xmlns:user` is always present; user-defined attributes (e.g. `user:ui-enumeration` on filters, `user:auto-column-width`) live in this namespace.

### 2.2 `<preferences>` (UI prefs and color palettes)

```xml
<preferences>
  <preference name='ui.encoding.shelf.height' value='250'/>
  <preference name='ui.shelf.height' value='26'/>

  <color-palette name='My Brand Categorical' type='regular'>
    <color>#eb912b</color>
    <color>#7099a5</color>
    <color>#c71f34</color>
    <color>#1d437d</color>
  </color-palette>

  <color-palette name='Brand Sequential' type='ordered-sequential'>
    <color>#eb912b</color>
    <color>#eb9c42</color>
    <color>#ebad67</color>
    <color>#eacba8</color>
  </color-palette>

  <color-palette name='Brand Diverging' type='ordered-diverging'>
    <color>#eb912b</color>
    <color>#59879b</color>
  </color-palette>
</preferences>
```

`type` values:

| `type` | Meaning |
|--------|---------|
| `regular` | Categorical (discrete values, distinct hues). |
| `ordered-sequential` | Continuous, single hue varying in intensity. |
| `ordered-diverging` | Continuous, two hues with neutral midpoint. |

**Custom palettes can also be defined in the user-level `Preferences.tps` file.** When a workbook references a palette by name on a color encoding, the parser resolves first against the workbook's `<preferences>` and falls back to the system file. The TWBX is self-contained for palettes used in encodings, since Tableau copies the palette definition into the workbook XML on save.

### 2.3 `<style>` (workbook-global default formatting)

```xml
<style>
  <style-rule element='worksheet'>
    <format attr='font-family' value='Tableau Book'/>
    <format attr='font-size' value='10'/>
  </style-rule>
  <style-rule element='dashboard'>
    <format attr='background-color' value='#f5f5f5'/>
  </style-rule>
</style>
```

Per-worksheet and per-dashboard `<style>` overrides this. The cascade: workbook style > dashboard style > worksheet style > zone-style > pane-style > mark-level format.

### 2.4 `<thumbnails>` and `<external>`

`<thumbnails>` holds base64 PNG previews used by Tableau Desktop for tab thumbnails. Safe to ignore for migration.

`<external><shapes>` holds the custom shape library, base64-encoded:

```xml
<external>
  <shapes>
    <shape name='star_filled.png'>iVBORw0KGgoAAAANSUhEUgAAAAg...</shape>
  </shapes>
</external>
```

Decoder: `base64.b64decode(shape.text)` gives the PNG bytes. Match `name=` against shape encodings on marks.

### 2.5 `<repository-location>`

When the workbook came from Tableau Server, this names the site, project path, content name, and revision. Useful for traceability; not required to render the workbook.

### 2.6 Citations

- `https://github.com/tableau/tableau-document-schemas`
- `https://help.tableau.com/current/pro/desktop/en-us/formatting_create_custom_colors.htm`
- `https://gist.github.com/cmtoomey/96342ba07dd5cba6ecc6`
- `https://www.clearlyandsimply.com/clearly_and_simply/2014/05/extract-custom-shapes-from-a-tableau-workbook.html`

---

## 3. Datasources (the semantic model)

The `<datasources>` element contains one or more `<datasource>` children plus the special `Parameters` datasource (always present). Each `<datasource>` is the rough equivalent of an Omni view file (or, for federated multi-table, an Omni topic). See section 11 for mapping detail.

### 3.1 `<datasource>` element

```xml
<datasource caption='Sales Data'
            inline='true'
            name='federated.0xxxx99sample0a1b2c3'
            version='18.1'
            hasconnection='true'>
  <connection .../>
  <aliases enabled='yes'/>
  <column .../>
  <column .../>
  <calculation .../>
  <drill-paths> ... </drill-paths>
  <semantic-values> ... </semantic-values>
  <extract> ... </extract>             <!-- present iff datasource has an extract -->
  <layout dim-percentage='0.5' .../>   <!-- IDE state, ignorable -->
  <datasource-dependencies datasource='[Parameters]'> ... </datasource-dependencies>
</datasource>
```

Attribute notes:

- `name`: machine identifier. Pattern `federated.<base36-hash>` for federated, or literal `Parameters`, or user-set name.
- `caption`: display name shown in Tableau UI. Often matches the table or the user's pretty name.
- `inline='true'`: datasource is embedded in this workbook. `false` indicates a published-on-server reference.
- `version`: per-datasource format version. Can lag the workbook version.
- `hasconnection='false'`: used for the `Parameters` datasource and for "no data" scratch datasources.

### 3.2 `<connection>` element by class

The `class` attribute drives every other attribute. Common classes:

| `class` | Source | Notable extra attrs |
|---------|--------|----------------------|
| `snowflake` | Snowflake | `dbname`, `schema`, `server`, `warehouse`, `username`, `service` |
| `postgres` | Postgres | `dbname`, `port`, `server`, `username`, `sslmode` |
| `redshift` | Redshift | `dbname`, `port`, `server`, `username` |
| `bigquery` | BigQuery | `project`, `connection-dialect`, `service-account` |
| `sqlserver` | SQL Server | `dbname`, `server`, `authentication`, `instancename` |
| `oracle` | Oracle | `service`, `server`, `port` |
| `mysql` | MySQL | `dbname`, `server`, `port` |
| `databricks` | Databricks | `server`, `dbname`, `httppath`, `authentication` |
| `excel-direct` | Local .xlsx | `filename` (absolute path on author's machine) |
| `textscan` | Local CSV | `filename`, `directory` |
| `hyper` | Embedded `.hyper` | `dbname` (path inside zip), `tablename`, `schema='Extract'` |
| `dataengine` | Legacy `.tde` | `dbname`, `tablename` |
| `federated` | Multi-source wrapper | wraps `<named-connections>` |
| `sqlproxy` | Tableau Server published datasource | `server` (Tableau Server URL), `dbname` (datasource luid) |
| `tableau` | Tableau Server data-source connection (alt) | similar to sqlproxy |
| `googlesheets` | Google Sheets | `tableId`, `username` |
| `salesforce` | Salesforce | `username`, `server` |

Universal connection attributes (read by `document-api-python`'s `Connection` class):

- `class`, `dbname`, `server`, `username`, `authentication`, `schema`, `service`, `port`, `query-band-spec`, `one-time-sql`

```xml
<connection class='snowflake'
            dbname='ANALYTICS'
            schema='PUBLIC'
            server='abc12345.us-east-1.snowflakecomputing.com'
            warehouse='WH_ANALYTICS'
            username='SVC_TABLEAU'
            service=''
            authentication='userpass'
            one-time-sql='ALTER SESSION SET QUERY_TAG=&apos;tableau&apos;'>
  <relation .../>
  <metadata-records> ... </metadata-records>
</connection>
```

Federated multi-connection example:

```xml
<connection class='federated'>
  <named-connections>
    <named-connection caption='Snowflake Prod' name='snowflake.0xa1b2c3'>
      <connection class='snowflake' dbname='ANALYTICS' .../>
    </named-connection>
    <named-connection caption='Customers CSV' name='textscan.0x9z8y7x'>
      <connection class='textscan' filename='/path/to/customers.csv'/>
    </named-connection>
  </named-connections>
  <relation type='join' join='left'> ... </relation>
</connection>
```

### 3.3 `<relation>` element (physical layer)

`<relation>` describes the physical query. Three primary `type` values:

#### type='table'

Simple table reference:

```xml
<relation connection='snowflake.0xa1b2c3'
          name='ORDERS'
          table='[ANALYTICS].[PUBLIC].[ORDERS]'
          type='table'/>
```

#### type='text' (Custom SQL)

Embedded SQL. Body of the element is the SQL text:

```xml
<relation connection='snowflake.0xa1b2c3'
          name='Custom SQL Query'
          type='text'>
SELECT o.id, o.amount, c.name
FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE o.created_at &gt; &apos;2024-01-01&apos;
  </relation>
```

XML escaping is critical. The parser must un-escape `&gt;`, `&lt;`, `&amp;`, `&apos;`, `&quot;` before round-tripping or translating the SQL.

#### type='join'

Physical-layer join. Wraps two child `<relation>` elements. The `<clause>` describes the join condition; `<expression>` builds the boolean tree.

```xml
<relation join='left' type='join'>
  <clause type='join'>
    <expression op='='>
      <expression op='[orders].[customer_id]'/>
      <expression op='[customers].[id]'/>
    </expression>
  </clause>
  <relation name='orders' table='[ANALYTICS].[PUBLIC].[ORDERS]' type='table'/>
  <relation name='customers' table='[ANALYTICS].[PUBLIC].[CUSTOMERS]' type='table'/>
</relation>
```

`join` values: `inner`, `left`, `right`, `full`. Multi-table joins nest: the second `<relation>` of an outer `<relation type='join'>` can itself be `type='join'`.

#### type='union'

```xml
<relation type='union' all='yes' is-cross-database='no'>
  <relation name='Q1' table='[Q1_SALES]' type='table'/>
  <relation name='Q2' table='[Q2_SALES]' type='table'/>
</relation>
```

#### type='collection'

Wrapper used in the new logical-layer model (see 3.4) when a logical table contains multiple physical relations.

### 3.4 Logical layer (post-2020.2 noodle model)

In Tableau 2020.2+, the data model split into a **logical layer** (relationships, the noodle UI) above the **physical layer** (joins, unions, custom SQL). Both serialize into the same `<datasource>`, wrapped in version-encapsulation elements that gate the parser by feature flag.

The wrapping element name is dynamic. Two variants appear simultaneously for legacy compatibility:

- `<_.fcp.ObjectModelEncapsulateLegacy.true...relation>`: the legacy physical-layer relation tree (consumed by Tableau when the workbook is opened in a pre-2020.2 client or in legacy mode).
- `<_.fcp.ObjectModelEncapsulateLegacy.false...relation>`: the same content shape, parsed by 2020.2+ clients.

The new element on top of these is the **object graph**:

```xml
<_.fcp.ObjectModelEncapsulateLegacy.true...object-graph>
  <objects>
    <object caption='Orders' id='Orders_xyz'>
      <properties context=''>
        <relation connection='snowflake.0xa1b2c3' name='ORDERS' table='[ANALYTICS].[PUBLIC].[ORDERS]' type='table'/>
      </properties>
    </object>
    <object caption='Customers' id='Customers_abc'>
      <properties context=''>
        <relation connection='snowflake.0xa1b2c3' name='CUSTOMERS' table='[ANALYTICS].[PUBLIC].[CUSTOMERS]' type='table'/>
      </properties>
    </object>
  </objects>
  <relationships>
    <relationship>
      <expression op='='>
        <expression op='[Orders_xyz].[customer_id]'/>
        <expression op='[Customers_abc].[id]'/>
      </expression>
      <first-end-point object-id='Orders_xyz' cardinality='many'/>
      <second-end-point object-id='Customers_abc' cardinality='one'/>
    </relationship>
  </relationships>
</_.fcp.ObjectModelEncapsulateLegacy.true...object-graph>
```

Critical observations for a parser:

- The encapsulating tag name has a literal period in it. Standard XML namespace handling does **not** apply; Tableau treats `_.fcp.ObjectModelEncapsulateLegacy.true` as an opaque element name. Use `findall("./{*}*")` style matching or string-match the tag name.
- `<objects>` is the logical-layer table list; each `<object>` is a logical table. Its `<properties>/<relation>` is the physical resolution (a single table, a join tree, or a `type='collection'` containing several physical relations stitched together).
- `<relationships>` is the noodle. Each `<relationship>` has cardinality (`one` / `many`) on each end and a boolean `<expression>` for the join condition.
- A logical table can be referenced from columns and worksheets without ever being physically joined; Tableau resolves the relationship lazily per-query.

For a workbook authored pre-2020.2 and never re-saved, the logical-layer block is absent and only the legacy `<relation>` tree exists. For 2020.2+, both blocks coexist.

### 3.5 `<column>` element (the heart of the semantic model)

Every field in the datasource is a `<column>`. Three flavors:

1. **Physical column**: pulled from the source schema. `name` matches the database column.
2. **Calculated column**: has a `<calculation>` child.
3. **Parameter**: in the `Parameters` datasource. Has `param-domain-type=`. See 3.10.

Full attribute reference:

| Attribute | Values | Notes |
|-----------|--------|-------|
| `name` | `[FieldName]` or `[Calculation_<19-digit-id>]` | Internal identifier. Always bracketed in the XML. |
| `caption` | Display name | Optional. Falls back to the bracket-stripped name. |
| `datatype` | `string`, `integer`, `real`, `date`, `datetime`, `boolean`, `geometry`, `spatial`, `table` | `table` is the post-2020.2 logical-table marker. |
| `role` | `dimension`, `measure` | Tableau's role classification. |
| `type` | `nominal`, `ordinal`, `quantitative` | Measurement type. Affects default UI behavior (continuous vs discrete pills). |
| `aggregation` | `Sum`, `Avg`, `Count`, `CountD`, `Min`, `Max`, `AttributeOf`, `Median`, `StDev`, `Var`, `None` | Default aggregation for measures. |
| `default-format` | Excel-style format string | See section 8.4. |
| `semantic-role` | `[State].[Name]`, `[Country].[Name]`, `[ZipCode].[Name]`, `[City].[Name]`, `[Latitude]`, `[Longitude]`, `[County].[Name]`, `[Area Code].[Name]` | Geographic role. Drives map rendering. |
| `param-domain-type` | `list`, `range`, `any` | Only on parameter columns. |
| `value` | literal | Default value for parameters. |
| `hidden` | `true` / `false` | Field visible in field picker. |
| `auto-column` | `true` / `false` | Auto-generated bin/group/etc. |
| `alias` | display alias for the field name | Less common than `caption`. |

Physical column example:

```xml
<column datatype='real' name='[AMOUNT]' role='measure'
        type='quantitative' default-format='$#,##0.00;-$#,##0.00'
        aggregation='Sum'/>
```

Calculated column example:

```xml
<column caption='Profit Ratio' datatype='real' default-format='p1%'
        name='[Calculation_5571209093911105]' role='measure' type='quantitative'>
  <calculation class='tableau' formula='SUM([Profit])/SUM([Sales])' scope-isolation='false'/>
</column>
```

Calculated column with description:

```xml
<column caption='Days to Close' datatype='integer' name='[Calculation_99]'
        role='measure' type='quantitative'>
  <calculation class='tableau' formula='DATEDIFF(&quot;day&quot;, [Created Date], [Closed Date])'/>
  <desc>
    <formatted-text>
      <run>Number of days between Created Date and Closed Date.</run>
    </formatted-text>
  </desc>
</column>
```

Geographic semantic-role:

```xml
<column datatype='string' name='[STATE]' role='dimension' type='nominal'
        semantic-role='[State].[Name]'/>
```

### 3.6 `<calculation>` element

Class values:

| `class` | Meaning |
|---------|---------|
| `tableau` | User-written formula in Tableau formula language. The `formula` attr holds the source. |
| `categorical-bin` | Group definition (see 3.7). |
| `bin` | Numeric bin (see 3.8). |
| `set` | Set definition (see 3.9). |

Tableau-class calculation:

```xml
<calculation class='tableau'
             formula='IF [Stage] = &quot;Closed Won&quot; THEN [Amount] END'
             scope-isolation='false'/>
```

`scope-isolation`:
- `false` (default): the calc is evaluated in the surrounding view's context.
- `true`: calc is evaluated independently. Used for some LOD / quick-table-calc behaviors.

The `formula` attribute body uses Tableau syntax; see section 4.

### 3.7 `<group>` and `<aliases>`

Two distinct concepts the XML often conflates:

**Aliases** remap one display value per data value, in place:

```xml
<column datatype='string' name='[STATUS]' role='dimension' type='nominal'>
  <aliases>
    <alias key='&quot;A&quot;' value='Active'/>
    <alias key='&quot;I&quot;' value='Inactive'/>
    <alias key='&quot;P&quot;' value='Pending'/>
  </aliases>
</column>
```

`key` is the underlying data value, double-quoted for strings (literal quotes inside the `key=` attribute, escaped). `value` is the display label.

**Groups** combine multiple values into named buckets. Stored as a calculated field with `class='categorical-bin'`:

```xml
<column caption='Manufacturer' name='[Product Name (group)]'
        role='dimension' type='nominal'>
  <calculation class='categorical-bin' column='[Product Name]'>
    <bin value='&quot;Acme Group&quot;'>
      <value>&quot;Acme Widget&quot;</value>
      <value>&quot;Acme Sprocket&quot;</value>
    </bin>
    <bin value='&quot;Globex Group&quot;'>
      <value>&quot;Globex Foo&quot;</value>
      <value>&quot;Globex Bar&quot;</value>
    </bin>
  </calculation>
</column>
```

### 3.8 `<bin>` (numeric binning)

Numeric bins use a different calculation class. Two storage shapes appear:

```xml
<column caption='Amount (bin)' datatype='real' name='[Amount (bin)]'
        role='dimension' type='ordinal'>
  <calculation class='bin' column='[Amount]' decimals='2' new-bin='auto' size='1000'/>
</column>
```

`size` is the bin width. `decimals` is the precision.

### 3.9 `<set>` (computed sets)

Three kinds: condition-based, top-N, manual list.

Manual:

```xml
<column caption='Top 10 Customers' datatype='string' name='[Top 10 Customers Set]'
        role='dimension' type='nominal'>
  <calculation class='set'>
    <constant>
      <value>&quot;Acme Inc&quot;</value>
      <value>&quot;Globex&quot;</value>
    </constant>
  </calculation>
</column>
```

Condition-based:

```xml
<column caption='High Value Orders' datatype='string' name='[High Value Set]'
        role='dimension' type='nominal'>
  <calculation class='set'>
    <condition>
      <expression op='&gt;'>
        <expression op='SUM'>
          <expression op='[Amount]'/>
        </expression>
        <expression op='10000'/>
      </expression>
    </condition>
  </calculation>
</column>
```

Top-N:

```xml
<calculation class='set'>
  <top-n direction='top' n='10' field='SUM([Sales])'/>
</calculation>
```

### 3.10 Parameters

Parameters live in a special datasource:

```xml
<datasource hasconnection='false' inline='true' name='Parameters'>
  <column caption='Top N' datatype='integer' name='[Parameter 1]'
          param-domain-type='range' role='measure' type='quantitative' value='5'>
    <calculation class='tableau' formula='5'/>
    <range granularity='5' max='20' min='5'/>
  </column>

  <column caption='Selected Region' datatype='string' name='[Parameter 2]'
          param-domain-type='list' role='dimension' type='nominal' value='&quot;West&quot;'>
    <calculation class='tableau' formula='&quot;West&quot;'/>
    <aliases>
      <alias key='&quot;West&quot;' value='West Region'/>
      <alias key='&quot;East&quot;' value='East Region'/>
    </aliases>
    <members>
      <member alias='West Region' value='&quot;West&quot;'/>
      <member alias='East Region' value='&quot;East&quot;'/>
    </members>
  </column>

  <column caption='Free Text' datatype='string' name='[Parameter 3]'
          param-domain-type='any' role='measure' type='nominal' value='&quot;default&quot;'>
    <calculation class='tableau' formula='&quot;default&quot;'/>
  </column>

  <column caption='Date Picker' datatype='date' name='[Parameter 4]'
          param-domain-type='range' role='measure' type='quantitative' value='#2024-01-01#'>
    <calculation class='tableau' formula='#2024-01-01#'/>
    <range granularity='1' max='#2024-12-31#' min='#2024-01-01#' period-type='day'/>
  </column>
</datasource>
```

`param-domain-type` values:

| Value | Meaning |
|-------|---------|
| `list` | Discrete `<members>` list with optional aliases. |
| `range` | `<range>` child with `min`, `max`, `granularity` (and `period-type` for dates). |
| `any` | No domain restriction; accepts any value of the datatype. |

Date / datetime literals use the `#YYYY-MM-DD#` syntax inside `value`, `formula`, and `<range>` attributes.

`<members>` is the list-domain enumeration. Each `<member>` has `value` (literal) and optional `alias` (display).

### 3.11 `<hierarchy>` / `<drill-paths>`

Drill hierarchies live at the datasource level:

```xml
<drill-paths>
  <drill-path name='Geography'>
    <field>[Country]</field>
    <field>[State]</field>
    <field>[City]</field>
    <field>[Postal Code]</field>
  </drill-path>
  <drill-path name='Product'>
    <field>[Category]</field>
    <field>[Sub-Category]</field>
    <field>[Product Name]</field>
  </drill-path>
</drill-paths>
```

`<field>` content is the bracketed column name. The order is the drill order. No depth limit.

### 3.12 `<extract>` element

```xml
<extract count='-1' enabled='true' units='records'>
  <connection access_mode='readonly' author-locale='en_US'
              class='hyper'
              dbname='Data/Datasources/federated_xxxx.hyper'
              schema='Extract'
              tablename='Extract'
              update-time='2024-09-01 14:33:21.000'>
    <relation name='Extract' table='[Extract].[Extract]' type='table'/>
    <refresh increment-key='' incremental-updates='false'/>
  </connection>
</extract>
```

Notes:

- `count='-1'` means all rows. Positive value caps row count.
- `units` is `records` or `percent`.
- `dbname` is the path **inside the TWBX zip**, not on the filesystem.
- `schema='Extract'` and `tablename='Extract'` are conventions; the actual `.hyper` SQL schema may have different names. Inspect via Hyper API (section 10).
- `refresh` describes incremental refresh config.

### 3.13 `<metadata-records>`

A flat per-column metadata block, separate from the `<column>` definitions, that Tableau caches at extract time:

```xml
<metadata-records>
  <metadata-record class='column'>
    <remote-name>AMOUNT</remote-name>
    <remote-type>5</remote-type>
    <local-name>[AMOUNT]</local-name>
    <parent-name>[ORDERS]</parent-name>
    <remote-alias>AMOUNT</remote-alias>
    <ordinal>3</ordinal>
    <local-type>real</local-type>
    <aggregation>Sum</aggregation>
    <approx-count>10000</approx-count>
    <contains-null>true</contains-null>
    <attributes>
      <attribute datatype='string' name='DebugRemoteType'>&quot;Numeric&quot;</attribute>
    </attributes>
  </metadata-record>
</metadata-records>
```

For migration, prefer the `<column>` definitions over `<metadata-record>`. The metadata records are a snapshot and may be stale.

### 3.14 `<datasource-dependencies>`

Cross-datasource references appear at the worksheet level (see section 5.2) and inside the `Parameters` datasource (used to declare which other datasource a parameter is bound to for dynamic parameters).

```xml
<datasource-dependencies datasource='federated.0xa1b2c3'>
  <column datatype='string' name='[STATE]' role='dimension' type='nominal'/>
  <column-instance column='[sum:AMOUNT:qk]' derivation='Sum' name='[sum:AMOUNT:qk]' pivot='key' type='quantitative'/>
</datasource-dependencies>
```

This block declares which fields the worksheet uses from a given datasource. Critical for the parser: it identifies the actual fields in scope for the chart's encodings.

### 3.15 Citations

- `https://tableauandbehold.com/2016/06/29/how-tds-twb-files-work-xml/`
- `https://tableauandbehold.com/2016/10/04/changing-parameters-in-workbook-xml/`
- `https://github.com/tableau/document-api-python/issues/237`
- `https://github.com/tableau/document-api-python/blob/master/tableaudocumentapi/connection.py`
- `https://gist.github.com/cmtoomey/96342ba07dd5cba6ecc6`
- `https://help.tableau.com/current/pro/desktop/en-us/parameters_create.htm`

---

## 4. Calculated fields and LOD calculations

The Tableau formula language is Excel-like with extensions. The XML stores formulas as opaque strings on `<calculation formula="...">`. To map to Omni, the parser must lex and re-emit.

### 4.1 Function categories (full inventory)

| Category | Functions |
|----------|-----------|
| Arithmetic | `+`, `-`, `*`, `/`, `%`, `^`, `ABS`, `CEILING`, `FLOOR`, `ROUND`, `EXP`, `LN`, `LOG`, `POWER`, `SQRT`, `SQUARE`, `SIGN`, `MIN`, `MAX`, `PI`, `DEGREES`, `RADIANS`, `SIN`, `COS`, `TAN`, `ASIN`, `ACOS`, `ATAN`, `ATAN2`, `HEXBINX`, `HEXBINY`, `DIV`, `ZN` |
| Logical | `IF...THEN...ELSEIF...ELSE...END`, `IIF(test, then, else, [unknown])`, `CASE [field] WHEN value THEN ... END`, `AND`, `OR`, `NOT`, `IFNULL`, `ISNULL`, `ISDATE`, `MAX`, `MIN` |
| String | `LEN`, `LEFT`, `RIGHT`, `MID`, `UPPER`, `LOWER`, `TRIM`, `LTRIM`, `RTRIM`, `REPLACE`, `CONTAINS`, `STARTSWITH`, `ENDSWITH`, `FIND`, `FINDNTH`, `SPLIT`, `REGEXP_MATCH`, `REGEXP_EXTRACT`, `REGEXP_EXTRACT_NTH`, `REGEXP_REPLACE`, `ASCII`, `CHAR`, `SPACE` |
| Date | `DATEPART`, `DATETRUNC`, `DATEADD`, `DATEDIFF`, `DATENAME`, `DATEPARSE`, `MAKEDATE`, `MAKETIME`, `MAKEDATETIME`, `NOW`, `TODAY`, `YEAR`, `MONTH`, `DAY`, `WEEK`, `WEEKDAY`, `QUARTER`, `HOUR`, `MINUTE`, `SECOND`, `ISOWEEK`, `ISOQUARTER`, `ISOYEAR`, `ISOWEEKDAY` |
| Type conversion | `INT`, `FLOAT`, `STR`, `DATE`, `DATETIME`, `BOOL` |
| Aggregation (used inside calcs) | `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `COUNTD`, `MEDIAN`, `STDEV`, `STDEVP`, `VAR`, `VARP`, `ATTR`, `PERCENTILE`, `CORR`, `COVAR`, `COVARP` |
| Table calculations | `RUNNING_SUM`, `RUNNING_AVG`, `RUNNING_MIN`, `RUNNING_MAX`, `RUNNING_COUNT`, `WINDOW_SUM`, `WINDOW_AVG`, `WINDOW_MIN`, `WINDOW_MAX`, `WINDOW_COUNT`, `WINDOW_VAR`, `WINDOW_STDEV`, `WINDOW_MEDIAN`, `WINDOW_PERCENTILE`, `WINDOW_CORR`, `WINDOW_COVAR`, `INDEX`, `RANK`, `RANK_DENSE`, `RANK_MODIFIED`, `RANK_PERCENTILE`, `RANK_UNIQUE`, `FIRST`, `LAST`, `LOOKUP`, `PREVIOUS_VALUE`, `SCRIPT_REAL`, `SCRIPT_INT`, `SCRIPT_STR`, `SCRIPT_BOOL`, `TOTAL`, `SIZE` |
| Spatial | `MAKEPOINT`, `MAKELINE`, `DISTANCE`, `BUFFER`, `AREA` |
| Predictive | `MODEL_PERCENTILE`, `MODEL_QUANTILE` |

### 4.2 Logical syntax shapes

```text
IF [Stage] = "Closed Won" THEN [Amount]
ELSEIF [Stage] = "Closed Lost" THEN 0
ELSE NULL
END

IIF([Amount] > 1000, "Big", "Small", "Unknown")

CASE [Region]
  WHEN "West" THEN 1
  WHEN "East" THEN 2
  ELSE 0
END
```

### 4.3 LOD (Level of Detail) expressions

Three keywords inside curly braces. Syntax:

```text
{ [FIXED | INCLUDE | EXCLUDE] <dimension_list> : <aggregate_expression> }
```

Examples:

```text
{ FIXED [Customer] : SUM([Sales]) }
{ INCLUDE [Region] : AVG([Profit]) }
{ EXCLUDE [Order Date] : MAX([Sales]) }
{ FIXED : SUM([Sales]) }                              -- table-scoped
{ FIXED [Customer], [Region] : SUM([Sales]) }         -- multi-dim
```

Filter execution semantics:

| LOD type | Position in order of operations |
|----------|-----------------------------------|
| `FIXED` | Computed before dimension filters. Honors only data-source filters, extract filters, and **context** filters. |
| `INCLUDE` / `EXCLUDE` | Computed after dimension filters. |

The XML stores the LOD verbatim in `formula`:

```xml
<calculation class='tableau'
             formula='{ FIXED [Customer] : SUM([Sales]) }'/>
```

The parser must distinguish LODs from regular aggregations because they translate differently to Omni (see section 11).

### 4.4 Dependencies between calculated fields

Calculated fields can reference other calculated fields by their `[Calculation_<id>]` name **or** by their `[caption]` (Tableau resolves both at parse time). Example:

```xml
<column caption='Profit' name='[Calculation_001]'>
  <calculation class='tableau' formula='[Sales] - [Cost]'/>
</column>

<column caption='Profit Ratio' name='[Calculation_002]'>
  <calculation class='tableau' formula='[Profit] / [Sales]'/>
</column>
```

The second references the first by caption (`[Profit]`). The parser must build a dependency DAG, topologically sort, and emit Omni measures in dependency order. Forward references are legal in Tableau.

### 4.5 Table calculations in XML

Table calcs surface in two places:

1. **Inline in formula text** when the user wrote `WINDOW_AVG(SUM([Sales]), -11, 0)` directly.
2. **As a wrapper on a column-instance** at the worksheet level (the "Quick Table Calculation" UI pathway):

```xml
<column-instance column='[sum:Sales:qk]'
                 derivation='WindowTotal'
                 name='[__:Calculation_99:WindowTotal_1]'
                 pivot='key'
                 type='quantitative'>
  <table-calc agg-type='Sum'
              ordering-type='Rows'
              from='-11'
              to='0'
              partition-along='Cell'
              direction='Row'/>
</column-instance>
```

Attribute reference:

| Attribute | Values |
|-----------|--------|
| `derivation` | `WindowTotal`, `WindowAvg`, `WindowSum`, `RunningTotal`, `RunningAvg`, `Rank`, `RankDense`, `RankUnique`, `Index`, `PercentOfTotal`, `Difference`, `PercentDifference`, `MovingAverage`, `MovingTotal`, `Lookup`, `First`, `Last`, `Total`, `Size`, `Custom` |
| `agg-type` | `Sum`, `Avg`, `Min`, `Max`, `Count` (the inner aggregation for the window) |
| `ordering-type` | `Rows`, `Columns`, `Cell`, `Pane` (addressing) |
| `from`, `to` | Window bounds. Negative = lookback; `-1` = previous; `0` = current; positive = look-ahead. |
| `partition-along` | The dimension partitioning the window. |
| `direction` | `Row`, `Column`, or a specific field reference |

Custom table calcs use `derivation='Custom'` and a child `<formula>` element. Most quick table calcs are storable purely via attributes.

### 4.6 Citations

- `https://help.tableau.com/current/pro/desktop/en-us/calculations_calculatedfields_lod_overview.htm`
- `https://help.tableau.com/current/pro/desktop/en-us/functions_functions_tablecalculation.htm`
- `https://help.tableau.com/current/pro/desktop/en-us/order_of_operations.htm`
- `https://www.flerlagetwins.com/2024/08/includeexclude.html`

---

## 5. Worksheets (the actual charts)

A worksheet is a chart definition. It pulls fields from one or more datasources (via `<datasource-dependencies>`), arranges them on shelves (`<rows>`, `<cols>`, `<encodings>`), applies filters, and renders a mark type.

### 5.1 `<worksheet>` element

```xml
<worksheet name='Sales by Region'>
  <table>
    <view>
      <datasources>
        <datasource caption='Sales Data' name='federated.0xa1b2c3'/>
      </datasources>
      <datasource-dependencies datasource='federated.0xa1b2c3'>
        <column datatype='string' name='[REGION]' role='dimension' type='nominal'/>
        <column datatype='real' name='[AMOUNT]' role='measure' type='quantitative'/>
        <column-instance column='[AMOUNT]' derivation='Sum' name='[sum:AMOUNT:qk]'
                         pivot='key' type='quantitative'/>
        <column-instance column='[REGION]' derivation='None' name='[none:REGION:nk]'
                         pivot='key' type='nominal'/>
      </datasource-dependencies>
      <filter class='categorical' column='[federated.0xa1b2c3].[STAGENAME]'> ... </filter>
      <slices> ... </slices>
      <aggregation value='true'/>
    </view>
    <style> ... </style>
    <panes>
      <pane>
        <view> ... </view>
        <mark class='Bar'/>
        <encodings>
          <color column='[federated.0xa1b2c3].[none:REGION:nk]'/>
          <text column='[federated.0xa1b2c3].[sum:AMOUNT:qk]'/>
        </encodings>
      </pane>
    </panes>
    <rows>[federated.0xa1b2c3].[none:REGION:nk]</rows>
    <cols>[federated.0xa1b2c3].[sum:AMOUNT:qk]</cols>
  </table>
</worksheet>
```

### 5.2 `<datasource-dependencies>` (which fields are in scope)

Two child element types:

- `<column>`: a raw field reference (mirrors the `<column>` in the datasource).
- `<column-instance>`: a derived "instance" of a column, typically with an aggregation prefix or a quick table calc. This is what shelves and encodings actually reference.

`<column-instance>` attributes:

| Attribute | Description |
|-----------|-------------|
| `column` | Bracketed name of the underlying column. |
| `name` | The instance's own bracketed name. Pattern: `[<derivation>:<column>:<pivot-key>]`. |
| `derivation` | Aggregation or table-calc derivation (`Sum`, `Avg`, `None`, `Year`, `Month`, `WindowTotal`, ...). |
| `pivot` | `key` or `value`, used in field reference syntax. |
| `type` | `nominal`, `ordinal`, `quantitative`. |

### 5.3 `<filter>` element

Universal attributes: `class`, `column`. Optional: `filter-group` (for filter ordering), `context` (true/false for context filters).

#### Categorical filter

Include specific values:

```xml
<filter class='categorical' column='[ds].[STAGENAME]' filter-group='2'>
  <groupfilter function='member'
               level='[STAGENAME]'
               member='&quot;Closed Won&quot;'
               user:ui-enumeration='inclusive'
               user:ui-marker='enumerate'/>
</filter>
```

Multiple values:

```xml
<filter class='categorical' column='[ds].[STAGENAME]'>
  <groupfilter function='union' user:ui-enumeration='inclusive'>
    <groupfilter function='member' level='[STAGENAME]' member='&quot;Closed Won&quot;'/>
    <groupfilter function='member' level='[STAGENAME]' member='&quot;Negotiation&quot;'/>
  </groupfilter>
</filter>
```

Exclude (NOT IN):

```xml
<filter class='categorical' column='[ds].[STAGENAME]'>
  <groupfilter function='except' user:ui-enumeration='exclusive'>
    <groupfilter function='member' level='[STAGENAME]' member='&quot;Closed Lost&quot;'/>
  </groupfilter>
</filter>
```

Wildcard (contains / starts-with / ends-with / matches-regex):

```xml
<filter class='categorical' column='[ds].[NAME]'>
  <groupfilter function='filter' level='[NAME]'
               user:ui-enumeration='inclusive'
               user:ui-marker='wildcard'
               user:ui-wildcard='Contains'
               user:ui-wildcard-value='Acme'/>
</filter>
```

`user:ui-wildcard` values: `Contains`, `StartsWith`, `EndsWith`, `MatchesRegex`, `Exactly`.

#### Range / quantitative filter

```xml
<filter class='quantitative' column='[ds].[AMOUNT]' include-values='in-range'>
  <min>1000</min>
  <max>50000</max>
</filter>
```

`include-values`: `in-range`, `non-null`, `null`, `all`.

#### Top-N filter

```xml
<filter class='categorical' column='[ds].[CUSTOMER]' filter-group='1'>
  <groupfilter function='end' direction='TOP' n='10' user:ui-marker='top'>
    <groupfilter function='level-members' level='[CUSTOMER]'/>
    <groupfilter function='member' level='[Measure]' member='[sum:Sales:qk]'/>
  </groupfilter>
</filter>
```

`direction`: `TOP` or `BOTTOM`. `n` is integer or a parameter reference.

#### Conditional filter

```xml
<filter class='categorical' column='[ds].[CUSTOMER]'>
  <groupfilter function='filter' user:ui-marker='condition'>
    <groupfilter function='level-members' level='[CUSTOMER]'/>
    <expression op='&gt;'>
      <expression op='SUM'><expression op='[Sales]'/></expression>
      <expression op='10000'/>
    </expression>
  </groupfilter>
</filter>
```

#### Relative-date filter

```xml
<filter class='relative-date' column='[ds].[ORDER_DATE]'
        first-period='-3' last-period='0'
        period-type='month'
        include-future='false'
        include-null='false'
        anchor='#2024-09-01#'>
</filter>
```

`period-type`: `year`, `quarter`, `month`, `week`, `day`, `hour`, `minute`, `second`. `first-period` is start offset (negative = past). `anchor` is the reference date (defaults to TODAY()).

#### Context filter

A regular filter with `context='true'`:

```xml
<filter class='categorical' column='[ds].[REGION]' context='true'>
  <groupfilter function='member' level='[REGION]' member='&quot;West&quot;'/>
</filter>
```

Context filters change the order-of-operations: they are evaluated before FIXED LODs and before non-context dimension filters.

### 5.4 Field reference syntax in shelves and encodings

`<rows>`, `<cols>`, and encoding `column=` attributes use this canonical pattern:

```text
[<datasource_name>].[<derivation>:<column>:<pivot_key>]
```

| Token | Values |
|-------|--------|
| `<datasource_name>` | Matches a `<datasource name=...>`. Often `federated.0xa1b2c3`. |
| `<derivation>` | `none` (no aggregation), `sum`, `avg`, `min`, `max`, `cnt`, `cntd`, `med`, `attr`, `usr` (user-defined), `yr`, `mn`, `dy`, `qr`, `wk`, `hr`, `mt`, `sc`, plus table-calc tokens. For datetimes, `yr-truncate`, `qr-truncate`, etc. |
| `<column>` | Underlying column name without brackets. Calculation IDs appear as `Calculation_<digits>`. |
| `<pivot_key>` | `qk` (quantitative key), `nk` (nominal key), `ok` (ordinal key). Drives mark type defaults. |

Examples:

| Reference | Meaning |
|-----------|---------|
| `[ds].[sum:AMOUNT:qk]` | SUM(AMOUNT), quantitative |
| `[ds].[none:REGION:nk]` | REGION as a discrete dimension |
| `[ds].[yr:ORDER_DATE:ok]` | YEAR(ORDER_DATE), ordinal |
| `[ds].[cntd:CUSTOMER_ID:qk]` | COUNTD(CUSTOMER_ID) |
| `[ds].[Multiple Values]` | Tableau's "Measure Names" pseudo-dimension |
| `[ds].[:Measure Names]` | The literal Measure Names placeholder |

`<rows>` and `<cols>` are space-separated lists of these references:

```xml
<rows>[ds].[none:REGION:nk] [ds].[none:CATEGORY:nk]</rows>
<cols>[ds].[yr:ORDER_DATE:ok] [ds].[sum:AMOUNT:qk]</cols>
```

### 5.5 `<panes>` and `<pane>`

A worksheet is rendered as one or more panes. Single-axis charts have one pane. Dual-axis charts have two panes (one per axis). Trellis (small-multiples) has many.

```xml
<panes>
  <pane id='1' selection-relaxation-option='selection-relaxation-allow'>
    <view>
      <breakdown value='auto'/>
    </view>
    <mark class='Bar'/>
    <encodings>
      <color column='[ds].[none:CATEGORY:nk]'/>
      <size column='[ds].[sum:QTY:qk]'/>
    </encodings>
    <style>
      <style-rule element='mark'>
        <format attr='mark-color' value='#1f77b4'/>
      </style-rule>
    </style>
  </pane>
</panes>
```

### 5.6 `<mark>` element (mark types)

`mark.class` values:

| Class | Chart family |
|-------|--------------|
| `Automatic` | Tableau auto-picks based on shelves |
| `Bar` | Vertical or horizontal bar |
| `Line` | Line chart |
| `Area` | Area chart |
| `Square` | Square mark |
| `Circle` | Scatter / circle mark |
| `Shape` | Custom shape mark (uses `<external><shapes>`) |
| `Text` | Text table / cross-tab |
| `Map` | Filled map (chloropleth) |
| `Polygon` | Polygon (custom shapes from spatial data) |
| `Gantt Bar` | Gantt chart |
| `Pie` | Pie chart (adds `<angle>` encoding) |
| `Density` | Heatmap / density |

### 5.7 `<encodings>` element

Each child element corresponds to an encoding shelf on the Marks card:

```xml
<encodings>
  <color column='[ds].[none:CATEGORY:nk]'/>
  <size column='[ds].[sum:QTY:qk]'/>
  <shape column='[ds].[none:STATUS:nk]'/>
  <text column='[ds].[sum:AMOUNT:qk]'/>
  <label column='[ds].[sum:AMOUNT:qk]'/>
  <detail column='[ds].[none:CUSTOMER:nk]'/>
  <tooltip column='[ds].[none:NOTES:nk]'/>
  <path column='[ds].[ORDER:nk]'/>
  <angle column='[ds].[sum:PCT:qk]'/>
  <lod column='[ds].[none:CUSTOMER:nk]'/>
</encodings>
```

Encoding semantics:

| Element | Effect |
|---------|--------|
| `<color>` | Color encoding. Discrete maps to categorical palette. Continuous maps to sequential/diverging palette. |
| `<size>` | Mark size mapped to a measure. |
| `<shape>` | Discrete shape mapping. References shape names from `<external><shapes>` or built-in palettes. |
| `<text>` | Text content of the mark (for text tables, labels). |
| `<label>` | Mark label, separate from text. |
| `<detail>` | Splits marks without changing other encodings. |
| `<tooltip>` | Adds a field to the tooltip without affecting marks. |
| `<path>` | Draws lines connecting marks in a specific order (custom path lines). |
| `<angle>` | Pie chart slice angle. |
| `<lod>` | Per-mark level-of-detail dimension override. |

Multiple fields per shelf appear as multiple child elements with the same name.

### 5.8 `<formatted-text>` and `<run>`

Used in tooltips, descriptions, captions, titles. A `<run>` is a styled text span; multiple `<run>` elements compose a styled string.

```xml
<tooltip>
  <formatted-text>
    <run fontfamily='Tableau Book' fontsize='10' bold='true'>Region: </run>
    <run fontfamily='Tableau Book' fontsize='10'>&lt;Region&gt;</run>
    <run> | Sales: &lt;SUM(Amount)&gt;</run>
  </formatted-text>
</tooltip>
```

Field tokens use `<FieldName>` literal-angle-bracket syntax inside the run text. The tokens are resolved against the worksheet's field references at render time.

### 5.9 Continuous vs discrete pills

Driven by the column's `type`:

- `nominal` is discrete (blue pill in UI)
- `ordinal` is discrete-ordered (blue pill)
- `quantitative` is continuous (green pill)

Plus the derivation prefix in the column-instance reference. `none:` is discrete; `sum:`, `avg:`, etc., are continuous when the underlying column is `quantitative`.

### 5.10 Axes (`<axis>`)

```xml
<axis class='quantitative'
      axis-end='100000'
      axis-start='0'
      include-zero='true'
      logarithmic='false'
      reversed='false'
      synchronized='false'
      tick-units='auto'
      title='Sales'/>
```

Dual-axis sync is per-pair. When two panes are paired:

```xml
<panes synchronized='true'>
  <pane> ... </pane>
  <pane> ... </pane>
</panes>
```

### 5.11 Sort

Sort settings on a shelf use `<sort>` inside `<column-instance>` or `<encoding>`:

```xml
<sort class='manual'>
  <dictionary>
    <bucket>&quot;West&quot;</bucket>
    <bucket>&quot;East&quot;</bucket>
    <bucket>&quot;Central&quot;</bucket>
  </dictionary>
</sort>

<sort class='computed' direction='DESC' using='[sum:Sales:qk]' nested='false'/>

<sort class='alphabetic' direction='ASC'/>
```

`class`: `manual`, `computed`, `alphabetic`. `direction`: `ASC`, `DESC`. `nested='true'` means the sort applies within the parent dimension's groups.

### 5.12 Reference lines, bands, distributions, forecasts

Analytics objects live in `<formula-elements>` or `<reference-line>` siblings under the pane. Example:

```xml
<reference-line line-type='avg' label='Average' show-label='true'>
  <formatting>
    <format attr='stroke-color' value='#999999'/>
    <format attr='stroke-style' value='dashed'/>
  </formatting>
  <line-target field='[sum:Sales:qk]' scope='entire-table'/>
</reference-line>

<reference-band band-type='custom' from='avg' to='max'>
  <formatting>
    <format attr='fill-color' value='#cccccc'/>
    <format attr='fill-opacity' value='0.3'/>
  </formatting>
</reference-band>

<reference-distribution dist-type='percentile' percentiles='25,50,75'/>

<forecast model='AAA' periods='6' period-type='month' include-prediction-intervals='true'/>
```

### 5.13 Color encoding details

Color encoding adds child elements to `<color>`:

```xml
<color column='[ds].[sum:Profit:qk]'>
  <map-color-continuous palette='Orange-Blue Diverging'
                        start='-5000' end='5000' center='0'
                        reversed='false' stepped='true' steps='5'/>
</color>

<color column='[ds].[none:Region:nk]'>
  <map-color-discrete palette='My Brand Categorical'>
    <map key='&quot;West&quot;' value='#eb912b'/>
    <map key='&quot;East&quot;' value='#7099a5'/>
  </map-color-discrete>
</color>
```

`palette` references either a built-in palette name (`Tableau 10`, `Tableau 20`, `Color Blind`, `Seattle Grays`, etc.) or a custom palette defined in `<preferences>`.

Per-mark overrides:

```xml
<color column='[ds].[none:Region:nk]'>
  <map key='&quot;West&quot;' value='#eb912b'/>
</color>
```

### 5.14 Citations

- `https://gist.github.com/cmtoomey/96342ba07dd5cba6ecc6`
- `https://github.com/ranvithm/tableau.xml`
- `https://help.tableau.com/current/pro/desktop/en-us/viewparts_marks_markproperties.htm`
- `https://help.tableau.com/current/pro/desktop/en-us/qs_relative_dates.htm`
- `https://help.tableau.com/current/pro/desktop/en-us/filtering_context.htm`
- `https://www.flerlagetwins.com/2022/07/top-n.html`

---

## 6. Dashboards

### 6.1 `<dashboard>` element

```xml
<dashboard name='Sales Overview' inherit-style='no'>
  <style> ... </style>
  <size maxheight='800' maxwidth='1200'
        minheight='800' minwidth='1200'/>
  <zones> ... </zones>
  <devicelayouts>
    <devicelayout name='Phone' auto-generated='true'>
      <size sizing-mode='at-least' minheight='600' minwidth='320'/>
      <zones> ... </zones>
    </devicelayout>
  </devicelayouts>
  <filters-with-target> ... </filters-with-target>
  <actions> ... </actions>
</dashboard>
```

Size modes:

- `<size minheight=... minwidth=... maxheight=... maxwidth=...>` with min equal to max yields fixed size.
- `<size sizing-mode='automatic'/>` yields auto.
- `<size sizing-mode='range' min=... max=...>` yields responsive within range.

### 6.2 `<zones>` tree

The `<zones>` element is the root of a recursive tree. The outermost `<zone>` covers the whole dashboard. Layout containers nest inside.

```xml
<zones>
  <zone id='1' h='100000' w='100000' x='0' y='0' type-v2='layout-basic'>
    <zone id='2' h='10000' w='100000' x='0' y='0' type-v2='title' name='Dashboard Title'>
      <zone-style>
        <format attr='background-color' value='#ffffff'/>
      </zone-style>
    </zone>
    <zone id='3' h='90000' w='100000' x='0' y='10000' type-v2='layout-flow' param='horz'>
      <zone id='4' h='90000' w='50000' x='0' y='10000' name='Sales Worksheet' worksheet='Sales by Region'/>
      <zone id='5' h='90000' w='50000' x='50000' y='10000' name='Profit Worksheet' worksheet='Profit by Region'/>
    </zone>
  </zone>
</zones>
```

Zone attributes:

| Attribute | Description |
|-----------|-------------|
| `id` | Unique integer in the dashboard. |
| `x`, `y` | Position in 100,000-unit relative coordinates (percent times 1,000). |
| `w`, `h` | Width/height in same units. |
| `minw`, `minh`, `maxw`, `maxh` | Optional min/max in pixels. |
| `type-v2` | Zone kind (see table). |
| `name` | Display name. For worksheet zones, often the worksheet name. |
| `worksheet` | Reference to a `<worksheet name=...>`. Only present on worksheet zones. |
| `param` | For flow containers: `horz` (horizontal) or `vert` (vertical). |
| `is-floating` | `true` if floating, otherwise tiled. |
| `floating-order` | Z-index when floating. |

`type-v2` values:

| Value | Zone kind |
|-------|-----------|
| `layout-basic` | Generic tiled container (root, manual layouts). |
| `layout-flow` | Horizontal/vertical flow container (the "stripes" UI). |
| `title` | Dashboard title text zone. |
| `text` | Text block. |
| `image` | Image zone. References a file in `Image/` or `<external><images>`. |
| `web-page` | URL-embedded web page. Has `<url>` child or `url=` attribute. |
| `blank` | Blank spacer. |
| `button` | Navigation button. Triggers go-to-sheet or URL. |
| `extension` | Tableau Extension. References a `.trex` manifest. |
| `bookmark` | (legacy) bookmarked view reference. |
| `paramctrl` | Parameter control widget. Bound to a `<column>` from `Parameters`. |
| `filter` | Filter widget. Bound to a worksheet's filter. |
| `legend` | Color/shape/size legend widget. |
| `highlighter` | Highlighter widget. |

### 6.3 The 100,000-unit coordinate system

`x`, `y`, `w`, `h` are stored as percent times 1,000 of the parent zone (not pixels). The outermost zone's parent is the dashboard `<size>` block, so `w=100000, h=100000` means full-dashboard. A child with `w=50000` is half its parent's width.

Conversion to pixels for a fixed-size dashboard:

```text
pixel_w = (zone.w / 100000) * dashboard.size.maxwidth
pixel_h = (zone.h / 100000) * dashboard.size.maxheight
```

Floating zones with `is-floating='true'` use absolute pixel coordinates instead.

### 6.4 Floating vs tiled

Default is tiled. Floating zones layer on top, with explicit pixel x/y/w/h:

```xml
<zone id='99' is-floating='true' floating-order='1'
      x='100' y='50' w='200' h='100' name='Floating Logo' type-v2='image'>
  <image-zone>
    <image-properties>
      <url>my_logo.png</url>
    </image-properties>
  </image-zone>
</zone>
```

### 6.5 Dashboard filters and `<filters-with-target>`

Filters that span multiple worksheets:

```xml
<filters-with-target>
  <filter-with-target column='[ds].[REGION]'>
    <target worksheet='Sales by Region'/>
    <target worksheet='Profit by Region'/>
    <target worksheet='Orders by Region'/>
  </filter-with-target>
</filters-with-target>
```

This declares "the Region filter applies to all three worksheets". Without `<filters-with-target>`, a per-worksheet filter only applies to its host worksheet.

### 6.6 Dashboard actions (`<actions>` inside `<dashboard>`)

Six action types correspond to UI choices. Each is a sibling element under `<actions>`:

#### Filter action

```xml
<filter-action name='Click Region to Filter' run-on='select' clearing='leave'>
  <source><sheet name='Sales by Region'/></source>
  <target><sheet name='Profit by Region'/></target>
  <fields>
    <field source-field='[REGION]' target-field='[REGION]'/>
  </fields>
</filter-action>
```

`run-on`: `select`, `hover`, `menu`. `clearing`: `leave`, `clear`, `show-all`.

#### Highlight action

```xml
<highlight-action name='Highlight Region' run-on='select'>
  <source><sheet name='Sales by Region'/></source>
  <target><sheet name='Profit by Region'/></target>
  <fields all='true'/>
</highlight-action>
```

#### URL action

```xml
<url-action name='Open Salesforce Record' run-on='menu'>
  <source><sheet name='Sales by Region'/></source>
  <url>https://my.salesforce.com/<REGION_ID></url>
  <browser-target>new-window</browser-target>
</url-action>
```

URL field tokens use `<FieldName>` syntax (literal angle brackets in the URL string).

#### Go-to-Sheet (navigation) action

```xml
<navigation-action name='Drill to Detail' run-on='select'>
  <source><sheet name='Sales by Region'/></source>
  <target><sheet name='Region Detail'/></target>
</navigation-action>
```

#### Parameter action

```xml
<parameter-action name='Set Selected Region' run-on='select'>
  <source><sheet name='Sales by Region'/></source>
  <target-parameter parameter='[Parameter 2]'/>
  <source-field>[REGION]</source-field>
  <aggregation>None</aggregation>
</parameter-action>
```

#### Set action

```xml
<set-action name='Pin Region' run-on='select' clearing='leave'>
  <source><sheet name='Sales by Region'/></source>
  <target-set set='[Top Regions Set]'/>
  <fields>
    <field source-field='[REGION]'/>
  </fields>
</set-action>
```

### 6.7 Citations

- `https://medium.com/@lorench/breaking-tableau-inxml-resizing-dashboards-17b704cd7322`
- `https://help.tableau.com/current/pro/desktop/en-us/dashboards_organize_floatingandtiled.htm`
- `https://help.tableau.com/current/pro/desktop/en-us/actions_dashboards.htm`
- `https://github.com/tableau/document-api-python/blob/master/tableaudocumentapi/workbook.py`

---

## 7. Stories

Stories are sequences of dashboard / worksheet snapshots with text annotations, like a slideshow.

### 7.1 `<story>` element

```xml
<stories>
  <story name='Q1 Review'>
    <story-points>
      <story-point captioned-as='QC1: Pipeline Health'
                   caption='Pipeline Health'
                   id='1'>
        <story-snapshot type='dashboard' name='Sales Overview'>
          <filter> ... </filter>   <!-- frozen filter state -->
          <parameter> ... </parameter>
        </story-snapshot>
      </story-point>
      <story-point captioned-as='QC2: Win Rate Trends'
                   caption='Win Rate Trends'
                   id='2'>
        <story-snapshot type='worksheet' name='Win Rate by Quarter'>
          ...
        </story-snapshot>
      </story-point>
    </story-points>
    <size maxheight='800' maxwidth='1200' minheight='800' minwidth='1200'/>
    <navigator type='caption'/>
  </story>
</stories>
```

`<navigator>` types: `dot`, `caption`, `number`, `arrows-only`.

A story-point's `<story-snapshot>` records the UI state at capture time: filter values, parameter values, mark selection, sort. The snapshot pins the experience even if the underlying data changes.

For migration: stories typically translate to either multi-tab Omni dashboards (one tab per story-point) or to several separate Omni dashboards linked by navigation. See section 11.

---

## 8. Formatting and color

### 8.1 Custom palettes (recap from 2.2)

Workbook-scoped palettes live in `<preferences><color-palette>`. Three types:

- `regular`: categorical
- `ordered-sequential`: single-hue continuous
- `ordered-diverging`: two-hue continuous

### 8.2 Per-encoding palette references

Color encodings reference palettes by name (`palette='My Brand Categorical'`). The name resolves first against workbook `<preferences>`, then against the user's `Preferences.tps`.

### 8.3 Conditional formatting

Conditional formatting on text tables uses `<style-rule>` with a calculated condition:

```xml
<style-rule element='cell'>
  <condition>
    <expression op='&gt;'>
      <expression op='SUM'>
        <expression op='[Profit]'/>
      </expression>
      <expression op='0'/>
    </expression>
  </condition>
  <format attr='background-color' value='#c8e6c9'/>
  <format attr='font-color' value='#1b5e20'/>
</style-rule>
```

### 8.4 Format strings

Tableau's number/date format strings are Excel-derived but with extensions. They appear on `default-format=` (column) or as `<format>` rules.

Number format syntax: `Positive;Negative;Zero;Null` (semicolon-separated sections, last three optional).

| Token | Meaning |
|-------|---------|
| `0` | Required digit (zero-padded). |
| `#` | Optional digit. |
| `.` | Decimal point. |
| `,` | Thousands separator (or scaling: trailing comma divides by 1000). |
| `%` | Multiplies value by 100, appends "%". |
| `*` | Repeats the next character to fill width (`*0` pads with zeros). |
| `$` | Literal `$` (or locale currency symbol). |
| `\` | Escape next character literally. |
| `"text"` | Literal text. |
| `[Red]`, `[Blue]`, `[Color N]` | Color the section. |
| `[<condition>]` | Apply section only when value matches. |

Date format tokens:

| Token | Meaning |
|-------|---------|
| `yyyy` | 4-digit year |
| `yy` | 2-digit year |
| `MMMM`, `MMM`, `MM`, `M` | Month: full name, short name, 2-digit, 1-2-digit |
| `dd`, `d` | Day |
| `HH`, `H`, `hh`, `h` | Hour (24/12) |
| `mm`, `m` | Minute |
| `ss`, `s` | Second |
| `tt`, `t` | AM/PM |
| `dddd`, `ddd` | Day name |

Tableau-only short codes (built-in shortcuts):

| Code | Equivalent |
|------|------------|
| `c0` | `$#,##0` (currency, 0 decimals) |
| `c2` | `$#,##0.00` |
| `n0` | `#,##0` |
| `n2` | `#,##0.00` |
| `p0%` | `0%` (percent, no decimals) |
| `p1%` | `0.0%` |
| `p2%` | `0.00%` |
| `s` | scientific |
| `*00000` | 5-digit zero-padded (zip codes) |

### 8.5 Background colors and banding

Worksheet-level format rules:

```xml
<format attr='pane-fill' value='#fafafa'/>
<format attr='row-banding' value='#eeeeee'/>
<format attr='row-banding-band' value='2'/>
<format attr='column-banding' value='#ffffff'/>
```

### 8.6 Fonts and font scaling

```xml
<format attr='font-family' value='Tableau Book'/>
<format attr='font-size' value='10'/>
<format attr='font-color' value='#333333'/>
<format attr='font-weight' value='bold'/>
<format attr='font-style' value='italic'/>
<format attr='font-underline' value='true'/>
```

Tableau ships a font family (`Tableau`, `Tableau Book`, `Tableau Light`, `Tableau Bold`, `Tableau Medium`, `Tableau Semibold`). Substitution falls back to system fonts.

### 8.7 Citations

- `https://help.tableau.com/current/pro/desktop/en-us/formatting_create_custom_colors.htm`
- `https://help.tableau.com/current/pro/desktop/en-us/formatting_specific_numbers.htm`
- `https://help.tableau.com/current/pro/desktop/en-us/dates_custom_date_formats.htm`
- `https://interworks.com/blog/2021/05/13/tricks-of-the-trade-custom-number-formatting-in-tableau/`

---

## 9. Filters and parameters consolidated

(Section 5.3 covered filter XML in worksheet context; section 3.10 covered parameters. This section is the single-place reference indexed by filter/parameter kind.)

### 9.1 Filter taxonomy (every variant)

| Kind | XML signature | Notes |
|------|---------------|-------|
| Categorical inclusive | `<filter class='categorical'>` plus `<groupfilter function='member' member='...'>` | Most common. |
| Categorical exclusive | `<groupfilter function='except'>` wrapping `member` | NOT IN. |
| Categorical multi-value | `<groupfilter function='union'>` wrapping multiple `member` | IN list. |
| Wildcard | `<groupfilter function='filter' user:ui-marker='wildcard'>` with `user:ui-wildcard=`, `user:ui-wildcard-value=` | Contains/starts/ends/regex. |
| Top-N / Bottom-N | `<groupfilter function='end' direction='TOP\|BOTTOM' n=...>` | Limits to N. |
| Conditional | `<groupfilter function='filter' user:ui-marker='condition'>` with `<expression>` | Boolean expression. |
| Quantitative range | `<filter class='quantitative' include-values='in-range'>` with `<min>`, `<max>` | Numeric. |
| Date range | `<filter class='quantitative'>` with date `<min>`, `<max>` | Same shape. |
| Relative date | `<filter class='relative-date' first-period=... last-period=... period-type=...>` | Rolling window. |
| Date period | `<filter class='quantitative'>` plus a `column-instance` with date derivation | Year/quarter/month filters. |
| Context | Any filter with `context='true'` | Re-orders execution. |
| Data source filter | Same shapes as above, but at `<datasource>` level | Pre-aggregates. |
| Extract filter | `<extract>/<connection>/<filter>` | Filters at extract time. |

### 9.2 Parameter domain types (recap)

| `param-domain-type` | Domain element | Notes |
|---------------------|----------------|-------|
| `list` | `<members>` plus optional `<aliases>` | Discrete values. |
| `range` | `<range min= max= granularity= [period-type=]>` | Numeric or date range. |
| `any` | (none) | Free-form input. |

### 9.3 Parameter actions (5.3 cross-reference to 6.6)

Already covered in section 6.6. A `<parameter-action>` writes a value into a Parameters-datasource column on user click. The downstream effect is whatever calculations / filters reference that parameter.

---

## 10. Hyper extract structure

### 10.1 What `.hyper` is

`.hyper` is Tableau's extract format since 10.5, replacing the legacy `.tde`. It is a Postgres-derived columnar SQL database in a single file. The Tableau Hyper API (`tableauhyperapi` Python package) is the only supported way to read or write it.

### 10.2 Connecting and listing schema

```python
from tableauhyperapi import HyperProcess, Connection, Telemetry, CreateMode

with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
    with Connection(endpoint=hyper.endpoint, database='Data/Datasources/extract.hyper') as conn:
        # List schemas (almost always just 'Extract')
        schema_names = conn.catalog.get_schema_names()

        # List tables in a schema
        for table in conn.catalog.get_table_names('Extract'):
            print(table)
            # Get column definitions
            table_def = conn.catalog.get_table_definition(table)
            for col in table_def.columns:
                print(f"  {col.name}: {col.type}")

        # Read rows
        with conn.execute_query('SELECT * FROM "Extract"."Extract" LIMIT 100') as result:
            for row in result:
                print(row)
```

### 10.3 SQL dialect

Hyper SQL is closest to Postgres with extensions:

- Double-quoted identifiers, single-quoted strings.
- Postgres-style types: `INTEGER`, `BIGINT`, `DOUBLE PRECISION`, `TEXT`, `DATE`, `TIMESTAMP`, `TIMESTAMP_TZ`, `INTERVAL`, `BOOLEAN`, `BYTEA`, `GEOGRAPHY`.
- Window functions, CTEs, JSON support, spatial functions.

### 10.4 Pulling sample data without a connection

For TWBX files that have an embedded `.hyper`, this is the **only** way to extract sample rows without re-establishing the live connection:

1. Unzip the TWBX. Locate `.hyper` files in `Data/Datasources/`.
2. Open each via the Hyper API.
3. List tables, sample N rows per table.
4. Match table names back to `<datasource>` `<extract><connection tablename=...>` references in the `.twb`.

For TWBX files that are live-connection only (no embedded extract), no sample data is recoverable from the file alone.

### 10.5 Citations

- `https://tableau.github.io/hyper-db/docs/`
- `https://tableau.github.io/hyper-db/lang_docs/py/tableauhyperapi.html`
- `https://pypi.org/project/tableauhyperapi/`

---

## 11. Map-to-Omni reference table

This is the consolidated mapping from every Tableau concept to its Omni equivalent (or to "no direct equivalent / requires workaround"). Section pointers reference `omni-cli-format-spec.md`.

### 11.1 Datasources, fields, calculations

| Tableau concept | XML element/attr | Omni concept | Omni file/section | Notes |
|-----------------|-------------------|--------------|-------------------|-------|
| `<datasource>` (single-table) | `<datasource><connection><relation type='table'>` | `<view>.view` YAML | `omni-cli-format-spec.md` section 3 (View file) | One Tableau datasource maps to one Omni view file. `caption` becomes view `label:`. |
| `<datasource>` (multi-table federated) | `<connection class='federated'>` | `<topic>.topic` YAML plus relationships | section 4 (Topic), section 5 (Relationships) | Topic groups views; relationships file declares joins. |
| `<datasource>` (logical layer object-graph) | `<_.fcp.ObjectModelEncapsulateLegacy.true...object-graph><objects><relationships>` | Topic plus relationships | section 4, section 5 | Each `<object>` becomes a view; each `<relationship>` becomes a relationships entry. Cardinality maps to `relationship_type:`. |
| Live SQL connection | `<connection class='snowflake|postgres|...'>` | Connection settings on Omni model | section 2 (Model file) | Map `class` to Omni connection type. `dbname`/`schema` map to `schema:` and `sql_table_name:` on the view. |
| Custom SQL relation | `<relation type='text'>SQL</relation>` | `derived_table:` on the view | section 3 (View file) | Wrap the SQL in `derived_table.sql:`. Alternatively materialize as a Snowflake/dbt view first. |
| Join relation (physical layer) | `<relation type='join' join='left'>` | Pre-aggregated SQL view OR explicit `joins:` in topic | section 4, section 5 | Tableau physical joins translate to either the topic's relationships file or to a derived_table SQL view. |
| Union relation | `<relation type='union'>` | Snowflake `UNION ALL` view | section 3 (`derived_table:`) | No native union in Omni topics. Materialize upstream. |
| `<column>` physical | `<column datatype= role= type= name=>` | Omni `dimension:` or `measure:` | section 3.2, section 3.3 | `role='dimension'` becomes `dimension:`; `role='measure'` becomes `measure:` with `type:` from `aggregation`. |
| `<column>` calculated (simple SQL-translatable) | `<calculation class='tableau' formula='[A]+[B]'>` | Omni `dimension:` with `sql:` | section 3.2 | Translate `[Field]` to `${field_name}` in Omni `sql:`. |
| `<column>` calculated (date) | `formula='DATETRUNC("month",[d])'` | Omni `dimension_group:` | section 3.3 | Map `DATETRUNC` to Omni date timeframes (`year`, `quarter`, `month`, `week`, `day`). |
| `<column>` calculated (LOD `FIXED`) | `formula='{ FIXED [c] : SUM([s]) }'` | Pre-aggregated SQL view OR `measure:` with custom SQL window | section 3.2 | Omni does not have LODs natively. Easiest: materialize the FIXED LOD as a derived_table or upstream view, then reference it. |
| `<column>` calculated (LOD `INCLUDE` / `EXCLUDE`) | `formula='{ INCLUDE ... }'` | Window function in `measure: { sql: }` OR derived view | section 3.2 | Translate to a SQL window function partitioned by the include/exclude dim list. |
| `<column>` calculated (table calc, e.g. `RUNNING_SUM`) | `formula='RUNNING_SUM(SUM([x]))'` | Omni `measure:` with `sql:` window function | section 3.2 | Translate to `SUM(...) OVER (ORDER BY ...)` in the underlying SQL. Order/partition matches Tableau's addressing/partitioning. |
| `<column>` calculated (`WINDOW_AVG`/`WINDOW_SUM` etc.) | `formula='WINDOW_AVG(SUM([x]),-11,0)'` | Omni `measure:` with `sql:` window function | section 3.2 | `OVER (ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)`. |
| `<column>` calculated (`INDEX`, `RANK`) | `formula='RANK(SUM([s]))'` | Omni `measure:` with `sql:` `RANK() OVER (...)` | section 3.2 | Direct mapping to SQL window functions. |
| `<aliases>` (value remapping) | `<alias key= value=>` | Omni `dimension: { value_format: case_sql_when }` OR a SQL CASE | section 3.2 | Translate to a `CASE WHEN underlying = 'A' THEN 'Active' ...` in the dimension's `sql:`. |
| `<group>` (categorical-bin) | `<calculation class='categorical-bin'>` | Omni `dimension:` with `sql:` CASE | section 3.2 | One CASE WHEN per `<bin>`. |
| `<bin>` (numeric bin) | `<calculation class='bin' size=...>` | Omni `dimension:` with `sql:` `FLOOR(x/size)*size` | section 3.2 | Express as a CASE WHEN range or arithmetic floor. |
| `<set>` (manual / condition / top-N) | `<calculation class='set'>` | Omni filter set OR boolean `dimension:` | section 9 (Filters) | Manual set becomes a boolean dim CASE. Condition set becomes a boolean dim with the condition. Top-N set has no direct equivalent; pre-rank in SQL. |
| `<drill-paths>` (hierarchy) | `<drill-paths><drill-path>` | Omni AI context (`drill_fields:`) on view | section 3 (View) | Omni does not have a strict drill hierarchy; record as ordered `drill_fields` for AI. |
| Parameter (`list` domain) | `<column param-domain-type='list'>` plus `<members>` | Omni `filter:` with control list | section 9.4 (Controls), section 9.6 (Templated filters) | `<member>` values map to control allowed values. |
| Parameter (`range` domain) | `<column param-domain-type='range'>` plus `<range>` | Omni `filter:` with range control | section 9.4 | Map `min`/`max`/`granularity` to control bounds. |
| Parameter (`any` domain) | `<column param-domain-type='any'>` | Omni `filter:` with text control | section 9.4 | Free-form text. |
| Parameter referenced inside calculation | `[Parameter 1]` token in `formula=` | Omni templated filter `{% condition ... %}` OR liquid var | section 9.6 | Replace with Omni filter reference syntax. |

### 11.2 Worksheets, marks, encodings

| Tableau concept | XML element/attr | Omni concept | Omni section | Notes |
|-----------------|-------------------|--------------|--------------|-------|
| `<worksheet>` | `<worksheet name=...>` | Dashboard tile | section 6.6 (Markdown/image/text tiles), section 7 (queryPresentation) | One worksheet maps to one tile in `dashboard.tiles[]`. |
| `<rows>` / `<cols>` | space-separated field references | Tile `queryJson.fields` plus `queryJson.pivots` | section 7.1 (queryJson) | Rows plus Cols become fields. Date fields auto-pivot. |
| Mark: `Bar` | `<mark class='Bar'/>` | `bar` visType | section 8.5 (Bar chart) | Tableau bars default vertical with measure on Rows; Omni bars default horizontal. Set `visConfig.barOrientation`. |
| Mark: `Line` | `<mark class='Line'/>` | `line` visType | section 8.4 (Line chart) | Direct mapping. |
| Mark: `Area` | `<mark class='Area'/>` | `line` visType with `fillBelow=true` | section 8.4 | Omni handles areas as a line variant. |
| Mark: `Circle` (scatter) | `<mark class='Circle'/>` | `scatter` visType | section 8.6 (Scatter) | Direct mapping. |
| Mark: `Square`, `Shape` | `<mark class='Square|Shape'/>` | `scatter` with custom mark style | section 8.6 | Shape encoding maps to Vega-Lite `shape` channel. |
| Mark: `Text` (text table) | `<mark class='Text'/>` | `table` visType | section 8.7 (Table / spreadsheet) | Direct mapping. |
| Mark: `Map` (filled) | `<mark class='Map'/>` plus geographic semantic-role | Custom Vega-Lite | section 8.11 (Custom Vega-Lite) | No native filled-map in Omni. Use Vega-Lite `geoshape`. |
| Mark: `Pie` | `<mark class='Pie'/>` plus `<angle>` encoding | Custom Vega-Lite OR donut | section 8.11 | No native pie in Omni; emit Vega-Lite. |
| Mark: `Gantt Bar` | `<mark class='Gantt Bar'/>` | Custom Vega-Lite | section 8.11 | No native Gantt. |
| Encoding: `<color>` (discrete) | `<color column=>` with `<map-color-discrete>` | `visConfig.colors` plus per-series mapping | section 8.14 (Color palette) | Map palette name to Omni's color array. |
| Encoding: `<color>` (continuous) | `<color column=>` with `<map-color-continuous>` | `visConfig.colorScale` (gradient) | sections 8.13 to 8.14 | Continuous color becomes Omni gradient. |
| Encoding: `<size>` | `<size column=>` | `visConfig.size` (Vega-Lite) | section 8.6, section 8.11 | Size mapping. |
| Encoding: `<shape>` | `<shape column=>` | `visConfig.shape` (Vega-Lite) | section 8.11 | Maps to shape channel. |
| Encoding: `<text>` / `<label>` | `<text column=>` | `visConfig.labels: {field, format}` | section 8.13 | Tableau formatted-text tooltips become Omni tile-level tooltip. |
| Encoding: `<detail>` | `<detail column=>` | Add to `queryJson.fields` (without pivoting) | section 7.1 | Detail splits marks; in Omni this is just an extra field. |
| Encoding: `<tooltip>` | `<tooltip column=>` | `queryJson.tooltipFields` | section 7.1 | Tooltip-only fields. |
| Encoding: `<path>` | `<path column=>` | Vega-Lite `order` channel | section 8.11 | Custom path lines. |
| Encoding: `<lod>` | `<lod column=>` | Equivalent to `<detail>` for Omni purposes | section 7.1 | Per-mark LOD. |
| Dual axis | paired `<panes synchronized='true'>` | `visConfig.layers` (Vega-Lite) | section 8.11 | No native dual-axis; emit layered Vega-Lite. |
| Reference line | `<reference-line>` | `visConfig.referenceLines[]` | section 8.12 (Reference lines, trend lines, forecasting) | Direct mapping. |
| Reference band | `<reference-band>` | Custom Vega-Lite layer | sections 8.11 to 8.12 | Limited native support. |
| Trend line | `<trendline>` (analytics object) | Vega-Lite `regression` transform | section 8.11 | Emit as Vega-Lite. |
| Forecast | `<forecast>` | No equivalent | (none) | Tableau forecasts are model-based; Omni has no forecasting primitive. Best path: pre-compute forecast in dbt/Snowflake and surface as a measure. |
| Sort manual | `<sort class='manual'><dictionary>` | `queryJson.sorts[]` with explicit ordering OR a custom case-when ranker | section 7.1 | Manual sort needs a derived order column in SQL. |
| Sort computed | `<sort class='computed' direction='DESC' using=...>` | `queryJson.sorts[].direction` | section 7.1 | Direct mapping. |
| Axis (`<axis>`) | `<axis axis-start= axis-end= logarithmic=>` | `visConfig.x.axis` / `y.axis` | sections 8.4 to 8.6 | Map start/end/log. |

### 11.3 Filters

| Tableau filter | XML | Omni equivalent | Omni section |
|----------------|-----|-----------------|--------------|
| Categorical inclusive | `<groupfilter function='member'>` | `is` operator filter | section 9.1 (`equal_to`) |
| Categorical exclusive | `<groupfilter function='except'>` | `is not` operator | section 9.1 (`not_equal_to`) |
| Multi-value IN | `<groupfilter function='union'>` of members | `is` with array value, `kind: EQUALS` | section 9.1, section 9.2 (Filter `kind`) |
| Wildcard contains | `user:ui-wildcard='Contains'` | `contains` operator | section 9.1 |
| Wildcard starts/ends | `StartsWith`/`EndsWith` | `starts_with`/`ends_with` | section 9.1 |
| Wildcard regex | `MatchesRegex` | `matches_regex` | section 9.1 |
| Top-N | `<groupfilter function='end' direction='TOP' n=>` | Tile-level top-N (in queryJson) | section 7.1 |
| Quantitative range | `<filter class='quantitative'>` | `between` operator | section 9.1 |
| Date range | quantitative-class on date | `between` on a `dimension_group` | section 9.1, section 3.3 |
| Relative date | `<filter class='relative-date' first-period= last-period=>` | Omni date filter with `relative_to_now` | section 9.1 (`relative_date_*`), section 9.3 |
| Context filter | `context='true'` | No direct equivalent; effect is already what Omni does by default for most filters | section 9 | Tableau's order-of-operations gymnastics often disappear in Omni. |
| Conditional filter | `<groupfilter function='filter' user:ui-marker='condition'>` | Templated filter or HAVING clause | section 9.6 |
| Data source filter | `<filter>` at datasource level | Omni `always_where_filters:` on topic | section 4.3 (`default_filters`, `always_where_filters`) |

### 11.4 Dashboards

| Tableau concept | XML element/attr | Omni concept | Omni section |
|-----------------|-------------------|--------------|--------------|
| `<dashboard>` | `<dashboard name=>` | Omni dashboard tab | section 6 (Dashboard JSON), section 6.4 (Multi-tab) |
| `<size minwidth= maxwidth=>` | dashboard size | Omni dashboard layout grid (12-col) | section 6.3 (Layout grid) |
| `<zone type-v2='layout-basic|layout-flow'>` | container | Implicit grid in Omni | section 6.3 | Omni uses 12-col grid; flatten Tableau's container tree to grid x/y/w/h. |
| `<zone>` worksheet zone | `<zone worksheet=>` | Omni tile | section 6.2 (Dashboard object), section 7 | One zone maps to one tile. |
| Conversion: Tableau (x,y,w,h)/100000 to Omni grid | math | 12-col cell coordinates | section 6.3 | `omni_x = round((zone.x / 100000) * 12)`; same for w. |
| `<zone type-v2='text'>` | text block | Omni markdown tile | section 6.6 |
| `<zone type-v2='image'>` | image block | Omni image tile | section 6.6 |
| `<zone type-v2='web-page'>` | web page | Omni iframe (limited) OR markdown link | section 6.6 |
| `<zone type-v2='blank'>` | spacer | Omni empty grid cell (just leave gap) | section 6.3 |
| `<zone type-v2='button'>` | navigation button | Omni dashboard cross-link | section 6.5 (Cross-filtering and drill linkage) |
| `<zone type-v2='paramctrl'>` | parameter widget | Omni filter control | section 9.4 (Controls) |
| `<zone type-v2='filter'>` | filter widget | Omni filter control | section 9.4 |
| `<zone type-v2='legend'>` | legend | Auto-rendered from tile's color encoding | section 8.14 |
| `<filters-with-target>` | dashboard filter scope | Dashboard-level `filters[]` linked across tiles | section 9.5 (Filter linking across tiles) |
| Floating zone | `is-floating='true'` | No equivalent; flatten to nearest grid cell | section 6.3 | Omni layout is grid-only. |
| Phone layout | `<devicelayout name='Phone' auto-generated='true'>` | (none, ignored) | n/a | Omni handles responsive layout automatically. |

### 11.5 Dashboard actions

| Tableau action | XML | Omni equivalent | Omni section |
|----------------|-----|-----------------|--------------|
| Filter action | `<filter-action>` | Cross-tile filter linkage | section 6.5, section 9.5 |
| Highlight action | `<highlight-action>` | No direct equivalent | n/a | Omni does not have hover-highlighting across tiles; closest is shared filters. |
| URL action | `<url-action>` | Omni drill link OR markdown URL | section 6.5 |
| Navigation action | `<navigation-action>` | Cross-dashboard link | section 6.5 |
| Parameter action | `<parameter-action>` | Filter linking with click-to-set | section 9.5 (limited) |
| Set action | `<set-action>` | No direct equivalent | n/a | Sets are Tableau-specific; usually drop on migration. |

### 11.6 Stories

| Tableau | XML | Omni |
|---------|-----|------|
| `<story>` | container | One Omni dashboard with multiple tabs OR multiple linked dashboards |
| `<story-point>` | snapshot | One tab in a multi-tab dashboard (section 6.4) |
| `<story-snapshot>` filter state | frozen filter values | Per-tab default filter values |
| `<navigator type='caption'>` | navigator UI | Omni's tab strip |

### 11.7 Color and format

| Tableau | XML | Omni |
|---------|-----|------|
| `<color-palette type='regular'>` | categorical | `colors:` array on the dashboard or model AI settings (section 2.1) |
| `<color-palette type='ordered-sequential'>` | continuous single-hue | `visConfig.colorScale` gradient (section 8.13) |
| `<color-palette type='ordered-diverging'>` | continuous two-hue | `visConfig.colorScale` diverging |
| Per-encoding `<map-color-discrete>` | manual color map | `visConfig.seriesColors` (section 8.14) |
| `default-format='c0'` etc. | shortcut format | Omni `value_format:` (section 3.4 Custom format strings) |
| `default-format='#,##0;-#,##0;"-"'` | full format | Direct paste into Omni `value_format:` (Excel format compatible) |
| Conditional formatting | `<style-rule><condition>` | Omni conditional formatting on table tiles (section 8.7) |

### 11.8 Things with no clean Omni equivalent (workarounds)

| Tableau feature | Why it's hard in Omni | Recommended workaround |
|-----------------|-----------------------|------------------------|
| LOD calculations (especially `INCLUDE`/`EXCLUDE`) | Omni has no per-query LOD primitive | Materialize as a derived view or window function |
| Quick table calcs (Running, Difference, % Difference) | Same | SQL window functions in `measure: { sql: }` |
| Forecasting | No native model | Pre-compute upstream |
| Story points | No native slideshow | Multi-tab dashboard or sequence of dashboards |
| Set actions | No equivalent | Drop or convert to filter plus parameter |
| Highlight actions | No native cross-tile highlight | Drop or convert to shared filter |
| Floating zones | Grid-only | Snap to nearest grid cell |
| Custom shapes (per-mark PNG) | Limited Vega-Lite shape support | Drop or use Vega-Lite custom shape encoding |
| Dual-axis sync with two different mark types | Vega-Lite layered chart needed | Emit `visConfig` with custom Vega-Lite |
| Filled maps with custom geocoding | Omni has limited geo | Use Vega-Lite `geoshape` with public TopoJSON |

---

## 12. Parsing checklist (extended)

The Level 1 guide's checklist plus the deeper items this spec covers:

- [ ] Unzip the TWBX. Inventory `.twb`, `.hyper`, `Image/`, `Shapes/`, `Mapsource/`.
- [ ] Parse the `.twb` with an XML parser that does **not** strip namespace declarations or treat `_.fcp.ObjectModelEncapsulateLegacy.true...` as a namespaced element. Use raw tag matching.
- [ ] Detect Tableau version (`<workbook version=>`). Branch the parser on pre-2020.2 vs post-2020.2 logical layer.
- [ ] Extract `<workbook>` metadata: name, version, source-platform, repository-location.
- [ ] Extract `<preferences><color-palette>` definitions. Build a palette-name to color-list map.
- [ ] For each `<datasource>`:
  - [ ] Extract `<connection>`. Detect `class`. Capture all attrs (`dbname`, `schema`, `server`, `warehouse`, `port`, `username`, `service`, `one-time-sql`, `query-band-spec`).
  - [ ] If `class='federated'`: recurse into `<named-connections>`.
  - [ ] Extract `<relation>` tree (legacy physical layer). Identify joins, custom SQL, unions.
  - [ ] If post-2020.2: extract `<_.fcp.ObjectModelEncapsulateLegacy.true...object-graph>`. Build logical-table list and relationship list.
  - [ ] Extract every `<column>` (physical, calculated, parameter). Capture all attrs.
  - [ ] Capture `<calculation>` formulas. Build dependency DAG.
  - [ ] Capture `<aliases>`, `<group>`, `<bin>`, `<set>`.
  - [ ] Capture `<drill-paths>`.
  - [ ] If `<extract>` present: capture path to `.hyper` inside the zip.
- [ ] Open `.hyper` via Hyper API. Capture schema/table/column structure. Optionally sample rows.
- [ ] For each `<worksheet>`:
  - [ ] Capture name.
  - [ ] Capture `<datasource-dependencies>` to know which fields are in scope.
  - [ ] Capture `<rows>`, `<cols>` shelf field references.
  - [ ] Capture every `<filter>` and classify by kind (categorical/quant/relative-date/top-N/conditional/wildcard/context).
  - [ ] For each `<pane>`: capture `<mark class=>` and every `<encodings>` child.
  - [ ] Capture `<axis>` settings.
  - [ ] Capture `<sort>` settings.
  - [ ] Capture reference lines, bands, trend lines, forecasts.
  - [ ] Capture conditional formatting `<style-rule>` rules.
- [ ] For each `<dashboard>`:
  - [ ] Capture name and size.
  - [ ] Walk `<zones>` recursively. Build flat list of leaf zones with absolute (x,y,w,h) in 100,000-units.
  - [ ] Convert 100,000-units to Omni 12-col grid.
  - [ ] Capture `<filters-with-target>` and `<actions>`.
- [ ] For each `<story>`: enumerate `<story-points>`, capture frozen filter/parameter snapshots.
- [ ] Build Tableau-to-Omni mapping per section 11. Emit Omni model YAML, view YAML, topic YAML, and dashboard JSON.
- [ ] Validate: every Tableau worksheet referenced by a dashboard zone exists. Every calculated field referenced by a worksheet exists. Every parameter referenced by a calculation or filter exists.

---

## 13. Citations (consolidated)

**Official Tableau:**
- Tableau Document Schemas (XSDs, Feb 2026): `https://github.com/tableau/tableau-document-schemas`
- Document API Python: `https://github.com/tableau/document-api-python`
- Hyper API: `https://tableau.github.io/hyper-db/docs/`
- Tableau file types help: `https://help.tableau.com/current/pro/desktop/en-us/environ_filesandfolders.htm`
- Custom color palettes: `https://help.tableau.com/current/pro/desktop/en-us/formatting_create_custom_colors.htm`
- LOD overview: `https://help.tableau.com/current/pro/desktop/en-us/calculations_calculatedfields_lod_overview.htm`
- Table calc functions: `https://help.tableau.com/current/pro/desktop/en-us/functions_functions_tablecalculation.htm`
- Order of operations: `https://help.tableau.com/current/pro/desktop/en-us/order_of_operations.htm`
- Number formatting: `https://help.tableau.com/current/pro/desktop/en-us/formatting_specific_numbers.htm`
- Custom date formats: `https://help.tableau.com/current/pro/desktop/en-us/dates_custom_date_formats.htm`
- Mark properties: `https://help.tableau.com/current/pro/desktop/en-us/viewparts_marks_markproperties.htm`
- Relative date filters: `https://help.tableau.com/current/pro/desktop/en-us/qs_relative_dates.htm`
- Context filters: `https://help.tableau.com/current/pro/desktop/en-us/filtering_context.htm`
- Dashboard floating/tiled: `https://help.tableau.com/current/pro/desktop/en-us/dashboards_organize_floatingandtiled.htm`
- Dashboard actions: `https://help.tableau.com/current/pro/desktop/en-us/actions_dashboards.htm`
- Parameters: `https://help.tableau.com/current/pro/desktop/en-us/parameters_create.htm`
- Hyper API Python ref: `https://tableau.github.io/hyper-db/lang_docs/py/tableauhyperapi.html`

**Document API source:**
- `https://github.com/tableau/document-api-python/blob/master/tableaudocumentapi/connection.py`
- `https://github.com/tableau/document-api-python/blob/master/tableaudocumentapi/workbook.py`
- `https://github.com/tableau/document-api-python/issues/237` (object-model encapsulation schema change)

**Community reverse-engineering:**
- cmtoomey annotated workbook gist: `https://gist.github.com/cmtoomey/96342ba07dd5cba6ecc6`
- ranvithm/tableau.xml: `https://github.com/ranvithm/tableau.xml`
- drintoul/tableau-xml-parse: `https://github.com/drintoul/tableau-xml-parse`
- bitips.blog: `https://bitips.blog/2023/09/01/unravel-tableau-workbook-structure-twb-twbx/`
- Yaron Lirase: `https://medium.com/@yaron.lirase/unraveling-tableau-workbook-structure-twbx-twb-bdc3b2a93492`
- Tableau and Behold (TDS/TWB): `https://tableauandbehold.com/2016/06/29/how-tds-twb-files-work-xml/`
- Tableau and Behold (Parameters): `https://tableauandbehold.com/2016/10/04/changing-parameters-in-workbook-xml/`
- CoEnterprise XML metadata blog: `https://www.coenterprise.com/blog/uncovering-the-value-of-tableaus-workbook-xml-metadata/`
- Loren Crook (dashboard XML resizing): `https://medium.com/@lorench/breaking-tableau-inxml-resizing-dashboards-17b704cd7322`
- Flerlage Twins (LOD INCLUDE/EXCLUDE): `https://www.flerlagetwins.com/2024/08/includeexclude.html`
- Flerlage Twins (Top N): `https://www.flerlagetwins.com/2022/07/top-n.html`
- InterWorks (number formatting): `https://interworks.com/blog/2021/05/13/tricks-of-the-trade-custom-number-formatting-in-tableau/`
- Custom shapes extraction: `https://www.clearlyandsimply.com/clearly_and_simply/2014/05/extract-custom-shapes-from-a-tableau-workbook.html`

---

End of Tableau TWBX format spec. Cross-reference `omni-cli-format-spec.md` for the corresponding Omni file shapes, and `tableau-parsing-guide.md` for the lighter Level 1 introduction.
