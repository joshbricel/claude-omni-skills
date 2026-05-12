# Omni Analytics File Format & API Spec (Reference)

Reference material for programmatic dashboard / chart authoring against an Omni instance. Pulled from `docs.omni.co` (May 2026), the official Omni CLI install pages, the `@omni-co/model-local-editor` npm tool, the `documents-import` API, and verified payload patterns captured by the in-repo `omni-vega-chart` and `tableau-to-omni` skills (real-world hits where the public docs are thin).

Two surfaces matter for code emission:

1. **Model files** (`*.view`, `*.topic`, `model`, `relationships`): YAML, defining the semantic layer.
2. **Document JSON** (dashboards / workbooks): JSON only, written through the `/documents/import` API or the `/documents/{id}` PUT/PATCH endpoints. Workbooks/dashboards are not authored as YAML files in the repo; they are authored as documents.

When the docs only show fragments and the wire format is known from working code, both are quoted with the source called out. Sections explicitly flagged as "thin" are where the docs gave incomplete schemas at the time of writing.

---

## 1. File / Repo Structure

### 1.1 Top-level layout

The Omni model is *not* a free-form filesystem. It is an opinionated set of files exposed both through the in-app Model IDE and through the `GET /api/v1/models/{modelId}/yaml` endpoint, which returns a `files` map with paths like `model.yaml`, `views/customers.yaml`, `views/orders.yaml`.

```
{model_id}/
  model.yaml                    # one per model. ai_settings, ai_context, ai_chat_topics,
                                #   default_filters, cache_policies, constants, custom_formats,
                                #   sample_queries, sets, topic_group_descriptions, ...
  relationships.yaml            # all topic-level joins (centralized list)
  views/
    {view_name}.yaml            # one per view (table / SQL view / workbook query)
    ...
  topics/
    {topic_name}.yaml           # one per topic
    ...
```

Source for paths: example response on `GET model YAML` shows `"model.yaml"` and `"views/customers.yaml"` (https://docs.omni.co/api/models/get-model-yaml).

### 1.2 File extensions and `fileName` semantics

The `Create or update YAML files` API (`POST /api/v1/models/{modelId}/yaml`) accepts a single string `fileName` field whose allowed values are:

> `model`, `relationships`, `<topic_name>.topic`, or `<view_name>.view`

So views and topics are referred to by *suffix*, not subdir, in the API contract: `customers.view`, `orders.view`, `order_items.topic`. The IDE displays them under `views/` and `topics/` folders, but the API `fileName` is the bare logical name plus extension. (https://docs.omni.co/api/models/create-or-update-yaml-files)

| File | Extension in API `fileName` | Path in `GET yaml` `files` map | Contents |
|---|---|---|---|
| Model | `model` | `model.yaml` | model-wide settings (one per model) |
| Relationships | `relationships` | `relationships.yaml` | centralized join list |
| View | `<name>.view` | `views/<name>.yaml` | one per view |
| Topic | `<name>.topic` | `topics/<name>.yaml` | one per topic |

### 1.3 Modes (write semantics)

`POST yaml` requires a `mode`:

> `combined`, `extension`, `staged`, `merged`, `history` (default: `combined`)

- `combined`: write to live model
- `extension`: write to the workbook-level extension overlay (empty `yaml` removes the file)
- `staged`: write to a staged draft
- `merged` / `history`: read views

### 1.4 Required headers

```
Authorization: Bearer <Org API Key | PAT>
Content-Type: application/json
```

Note: the **`/api/unstable/documents/import`** endpoint specifically requires an Organization API Key. PATs are rejected. The `/api/v1/models/.../yaml` endpoints accept either. (https://docs.omni.co/api/content-migration/import-dashboard, https://docs.omni.co/api/models/get-model-yaml)

### 1.5 Workbooks / dashboards do NOT live in YAML

This is the single most important and most easily-missed fact: **dashboards and workbooks are documents, not model files.** They are not edited with `POST yaml`. They are edited via:

- `GET /api/unstable/documents/{dashboardId}/export`: fetch full JSON
- `POST /api/unstable/documents/import`: create from JSON
- `GET /api/v1/documents/{documentId}`: round-trip-able subset
- `PUT /api/v1/documents/{documentId}`: replace round-trip-able subset
- `PATCH /api/v1/dashboards/{dashboardId}/filters`: partial update of filters/controls only

Sources:
- https://docs.omni.co/api/content-migration/import-dashboard
- https://docs.omni.co/api/content-migration/export-dashboard
- https://docs.omni.co/api/documents/get-dashboard-document
- https://docs.omni.co/api/documents/update-dashboard-document
- https://docs.omni.co/api/dashboard-filters/update-dashboard-filterscontrols
- https://docs.omni.co/api/models/get-model-yaml

---

## 2. Model file (`model`) parameters

The model file is the root configuration of the analytical environment. Documented parameters (https://docs.omni.co/docs/modeling/model-files):

| Parameter | Purpose |
|---|---|
| `access_grants` | Limits user access to a particular field (dimension or measure) through user attributes |
| `ai_chat_topics` | Controls which topics the Omni Agent and Dashboard Agent can access |
| `ai_context` | Sets context for the Omni Agent that is applicable for the entire model |
| `ai_settings` | Configure AI behavior for the model, including query scope, analysis validation, conversation context management |
| `auto_run` | Forces all queries using the connection to require a run click |
| `cache_policies` | Establishes caching rules |
| `constants` | Define reusable string values that can be referenced throughout the model |
| `custom_formats` | Defines reusable format objects referenced in dimension/measure `format` parameters |
| `default_cache_policy` | Default cache policy reference |
| `default_numeric_locale` | Global number formatting |
| `default_row_limit` | Query result row constraint |
| `default_timeframes` | Available date/time field options |
| `default_topic_access_filters` | Access restrictions by topic |
| `default_topic_required_access_grants` | Universal access grant requirements |
| `dynamic_schemas` | Virtual schema creation |
| `extends` | Model inheritance |
| `facet_workbook_filters` | Filter suggestion scoping |
| `fiscal_month_offset` | Fiscal calendar offset |
| `ignored_schemas`, `included_schemas`, `ignored_views`, `included_views` | DB content filtering |
| `sample_queries` | Sample queries shown to users / AI |
| `sets` | Reusable field sets |
| `skills` (formerly `workflows`) | AI agent skills / workflows |
| `slot_reservation` | Compute slot reservation |
| `sql_preamble` | SQL run before each query |
| `template` | Template marker |
| `topic_group_descriptions` | Description per topic group |
| `topics` | Topic listing / metadata at model level |
| `warehouse_override` | Warehouse to run queries against |
| `week_start_day` | Week start (e.g., monday) |

### 2.1 `ai_settings` (full example)

From https://docs.omni.co/modeling/models/ai-settings:

```yaml
ai_settings:
  query_all_views_and_fields: enabled       # disabled = topic-scoped only (recommended)
  validate_analysis: enabled
  conversation_prune_length: medium         # short | medium | long | max
  analyze_configuration:                    # complex analytical work
    model: smartest                         # smartest | standard | fastest
                                            # OR opus | sonnet | haiku
    thinking: medium                        # none | low | medium | high
  build_configuration:                      # model + topic generation
    model: standard
    thinking: high
  simple_summarize_configuration:           # summaries, search, field metadata
    model: fastest
    thinking: low
```

The doc explicitly recommends `query_all_views_and_fields: disabled` for production analytics ("better structure, improved performance, and a more guided experience").

Sources:
- https://docs.omni.co/docs/modeling/model-files
- https://docs.omni.co/modeling/models/ai-settings

---

## 3. View file (`<view>.view`) parameters

Documented top-level view parameters (https://docs.omni.co/modeling/views/parameters):

| Parameter | Description |
|---|---|
| `name` | Reference name; implicit from filename |
| `label` | UI override for view name |
| `description` | Free text |
| `sql` | Defines view from a SQL query |
| `query` | Defines view from a workbook query |
| `table_name` | Underlying DB table |
| `schema` | DB schema |
| `folder` | Nest in IDE folder |
| `display_order` | Sort order in field browser |
| `hidden` | Hide from workbook UI (still referenceable) |
| `ignored` | Soft-delete |
| `tags` | Curate view/field groups |
| `extends` | Inherit attributes from another view |
| `required_access_grants` | Limit query ability by user attributes |
| `ai_context` | Free text for the Omni Agent |

Field-level: `dimensions:`, `measures:`, `filters:` (filter-only fields), `sets:`. Note that the public docs don't enumerate every dimension parameter exhaustively, but the Field Syntax page (https://docs.omni.co/modeling/dimensions) confirms the rules:

- Field names: lowercase a-z, 0-9, underscores; must start with a letter.
- Within a view, fields follow a fixed display order (schema dimensions, shared model dimensions, measures, filters). Interleaving is unsupported.

### 3.1 Practical view YAML (verified against a working Omni instance)

This pattern is from the in-repo `omni-semantic-layer-setup` skill (verified working against a real branch). The Omni-side IDE accepts both this minimal form and the more LookML-like nested-field form.

```yaml
view: sf_opportunities
  sql_table_name: DEMO_DB.PUBLIC.SF_OPPORTUNITIES
  label: "Opportunities"
  description: "Salesforce opportunity table at the deal level."

  dimensions:
    id:
      sql: ${TABLE}.Id
      primary_key: true
      hidden: true

    competitor_c:
      sql: ${TABLE}.Competitor__c
      label: "Win Channel / Competitor"
      description: |
        MISLEADING NAME. For WON deals, stores win attribution channel.
        For LOST deals, stores the competitor who won. NULL for open deals.
      synonyms: ["win channel", "competitor"]

    is_closed:
      sql: ${TABLE}.IsClosed
      type: yesno

    is_won:
      sql: ${TABLE}.IsWon
      type: yesno

    fiscal_year:
      sql: ${TABLE}.FiscalYear
      type: number
      label: "Fiscal Year"
      description: "July-start fiscal year. FY25 = Jul 2024 through Jun 2025."

    closedate:
      sql: ${TABLE}.CloseDate
      type: date
      timeframes: [date, week, month, quarter, year]

  measures:
    count:
      type: count

    total_amount:
      sql: ${TABLE}.Amount
      aggregate_type: sum
      label: "Total Deal Value"
      format: "$#,##0"

    win_rate:
      sql: |
        CAST(SUM(CASE WHEN ${is_won} THEN 1 ELSE 0 END) AS FLOAT)
        / NULLIF(SUM(CASE WHEN ${is_closed} THEN 1 ELSE 0 END), 0)
      type: number
      format: "0.0%"
      description: |
        Closed deals that were won. Only counts IsClosed=TRUE deals in denominator.
```

Sources:
- https://docs.omni.co/modeling/views
- https://docs.omni.co/modeling/views/parameters
- https://docs.omni.co/modeling/dimensions
- https://docs.omni.co/modeling/measures

### 3.2 Measure parameters

(https://docs.omni.co/modeling/measures)

| Parameter | Notes |
|---|---|
| `aggregate_type` | `sum`, `count`, `count_distinct`, `average`, `median`, `percentile`, `min`, `max`, `list`. Recommended over raw SQL aggregates so Omni can apply symmetric aggregation. |
| `sql` | Reference dimension via `${field_name}` or `${TABLE}.Col`; can wrap aggregate. |
| `format` | e.g. `usdcurrency`, custom format strings like `"$#,##0"`, `"0.0%"`. |
| `label`, `description`, `hidden`, `group_label` | UI / docs |
| `type` | Data type (number, etc.), used for non-aggregate calculated measures. |
| `value_format` | Additional value formatting. |
| `filters` | Conditional aggregation. |
| `drill_fields` | Fields shown on click-through |
| `html` | Custom HTML rendering |
| `link` | Hyperlink |

```yaml
count_california_seniors:
  aggregate_type: count
  filters:
    age:
      greater_than_or_equal_to: 65
    state:
      is: California
```

### 3.3 Dimension types

(https://docs.omni.co/modeling/dimensions)

Dimensions can be date/time, string, boolean, or numeric. The page does not enumerate the literal `type` enum verbatim, but observed values: `string`, `number`, `date`, `timestamp`, `yesno`, `boolean`, `tier`, `duration`, plus numeric subtypes via `format`. Date dimensions accept a `timeframes:` list. Note: this is one of the **thin** parts of the public docs. Production code emitting dimension YAML should set the obvious type and let Omni reject via `validate-model` if invalid.

### 3.4 Custom format strings

`format:` accepts named values OR a format string. Named values seen in docs / payload examples: `usdcurrency`, `currency`, `percent`, `decimal`, `id`, `string`. Named formats can be promoted to `USDCURRENCY` (uppercase) inside the visConfig payload. See section 8. Custom format strings follow Excel-style: `"$#,##0"`, `"0.0%"`, `"#,##0.00"`.

---

## 4. Topic file (`<topic>.topic`) parameters

Documented top-level topic parameters (https://docs.omni.co/modeling/topics/parameters):

| Parameter | Required | Description |
|---|---|---|
| `base_view` | Yes | Defines the base view for the topic |
| `label` | | Display name |
| `group_label` | | Group the topic belongs to |
| `description` | | Free text |
| `sample_queries` | | List of sample queries the topic supports |
| `joins` | | Other views included in the topic |
| `fields` | | Curates which fields are accessible |
| `access_filters` | | Per-user-attribute row-level access |
| `required_access_grants` | | List of access grants required to view |
| `hidden` | | Removes the topic from the workbook |
| `default_filters` | | Filters applied to all rows; visible/removable by users |
| `cache_policy` | | Cache policy for the topic |
| `relationships` | | Topic-level joins |
| `extends` | | Inherit and override another topic |
| `ai_fields` | | Curates fields provided to the Omni Agent |
| `ai_context` | | Free text for the Omni Agent (this topic) |
| `always_where_sql` | | SQL always applied as a WHERE |
| `always_where_filters` | | Filter form of always-where |

Note: the page also references `always_join` and `conditionally_join`, but the official guide does not show full YAML. Conditional joins are typically implemented via templated filters (see section 9.6).

### 4.1 Verbatim example from `topics/setup`

(https://docs.omni.co/modeling/topics/setup)

```yaml
base_view: ecomm__order_items
label: Order Transactions
group_label: Orders & Fulfillment
ai_context: |
  You are an expert data analyst, who has a vast amount of experience analyzing ecommerce data to find useful insights and trends.
  Our data has information about orders at the line item level in the order items table, users in our user table, inventory in our inventory items table, and products in the products table.
joins:
  ecomm__users: {}
  ecomm__inventory_items:
    ecomm__products:
      ecomm__distribution_centers: {}
fields: [
  all_views.*,
  -ecomm__users.email,
  -ecomm__users.first_name,
  -ecomm__users.last_name
]
```

Reading: `joins:` is a *map*, not a list. Nesting expresses the join tree (`order_items` to `inventory_items` to `products` to `distribution_centers`). Empty object `{}` means "join with default settings."

`fields:` is a flow-sequence (list) where:
- `all_views.*` includes everything from every joined view by default
- Items prefixed `-` exclude specific fields

### 4.2 `sample_queries` (from in-repo verified usage)

Public docs are **thin** here. The form that has been observed to work:

```yaml
sample_queries:
  - question: "How many deals did we win from referral partners in FY25?"
    fields: [sf_opportunities.count, sf_opportunities.total_amount]
    filters:
      sf_opportunities.competitor_c: "CH - Partner Referral"
      sf_opportunities.stage_name: "Closed Won"
      sf_opportunities.fiscal_year: "2025"
```

Each sample query has a natural-language `question`, the `fields` it should resolve to, and a flat map of `filters`. These flow into the AI Agent as few-shot examples.

### 4.3 `default_filters` and `always_where_filters`

Doc reference is sparse. Best-practice reference (https://docs.omni.co/getting-started/best-practices) recommends both for "applying correct defaults and avoiding querying excessive data volumes." Form is the same as standard filter syntax (section 9):

```yaml
default_filters:
  sf_opportunities.fiscal_year:
    is: 2025
always_where_filters:
  sf_opportunities.is_deleted:
    is: false
```

Sources:
- https://docs.omni.co/modeling/topics
- https://docs.omni.co/modeling/topics/setup
- https://docs.omni.co/modeling/topics/parameters

---

## 5. Relationships file (`relationships`)

Centralized join definitions. (https://docs.omni.co/modeling/relationships)

```yaml
relationships:
  - join_from_view: users
    join_from_view_as: buyers
    join_from_view_as_label: Buyers
    join_to_view: user_facts
    join_type: always_left
    on_sql: ${users.id} = ${user_facts.id}
    relationship_type: one_to_one
    reversible: true
```

Documented parameters:

| Param | Notes |
|---|---|
| `join_from_view` | Source view |
| `join_to_view` | Target view |
| `join_from_view_as` | Alias for source |
| `join_from_view_as_label` | Display label for alias |
| `join_to_view_as`, `join_to_view_as_label` | Symmetric for target |
| `join_type` | `always_left`, `always_inner`, `always_full`, `always_right` (and conditional variants) |
| `relationship_type` | `one_to_one`, `one_to_many`, `many_to_one`, `many_to_many`, `assumed_many_to_one` |
| `on_sql` | The SQL ON clause, with `${view.field}` references |
| `reversible` | Boolean, can be traversed both directions |

The shorthand form (just under a topic) uses an even more compact spelling. See section 4.1.

Sources:
- https://docs.omni.co/modeling/relationships

---

## 6. Workbook / Dashboard JSON

There is **no dashboard YAML schema** in the model repo. Dashboards are documents transferred as JSON via the import / export / get / put endpoints. There are *two* schemas in play:

- The **`/api/unstable/documents/import` and `.../export`** schema: full fidelity, used for migration and round-trip. This is the schema you should target when emitting dashboards programmatically.
- The **`/api/v1/documents/{id}`** GET/PUT schema: a stable but reduced subset designed for round-trip editing of name / filters / queryPresentations / visConfig.

Below is the full unstable schema, then the stable schema.

### 6.1 Full import payload (unstable, used for migration)

Endpoint: `POST {BASE_URL}/api/unstable/documents/import`. Authorization: `Bearer <Org API Key>` (PAT not accepted). Status: beta. (https://docs.omni.co/api/content-migration/import-dashboard)

Top-level fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `baseModelId` | UUID | yes | Target model. **Critical.** |
| `dashboard` | object | yes | Full dashboard object (see 6.2) |
| `document` | object | yes | Document metadata |
| `workbookModel` | object | yes | Workbook-level model overlay |
| `exportVersion` | string | yes | **Must be `"0.1"` (string)** |
| `identifier` | string | no | Custom identifier |
| `folderPath` | string | no | Destination folder |
| `fileUploads` | array OR object | no | **Must be `{}` not `[]` when empty** (verified gotcha) |

A complete, working single-tile minimal payload (used in production by the in-repo `omni-vega-chart` skill; templates/dashboard-payload.json):

```json
{
  "baseModelId": "REPLACE_WITH_MODEL_ID",
  "exportVersion": "0.1",
  "fileUploads": {},
  "queryModels": {},
  "dashboard": {
    "crossfilterEnabled": false,
    "facetFilters": false,
    "name": "REPLACE_WITH_DASHBOARD_NAME",
    "metadata": {
      "layouts": {
        "lg": [
          {"i": "1", "x": 0, "y": 0, "w": 12, "h": 42}
        ]
      },
      "textTiles": [],
      "hiddenTiles": [],
      "tileSettings": {},
      "tileFilterMap": {},
      "tileControlMap": {}
    },
    "metadataVersion": 2,
    "queryPresentationCollection": {
      "filterConfig": {},
      "filterConfigVersion": 0,
      "filterOrder": [],
      "queryPresentationCollectionMemberships": [
        {
          "queryPresentation": {
            "type": "query",
            "name": "REPLACE_WITH_TILE_NAME",
            "subTitle": "",
            "description": "",
            "prefersChart": true,
            "automaticVis": true,
            "topicName": "REPLACE_WITH_TOPIC",
            "isSql": false,
            "filterOrder": [],
            "resultConfig": {
              "tableType": "spreadsheet",
              "rowBanding": {"enabled": false, "bandSize": 1},
              "expandedRows": {},
              "columnFormats": {},
              "hideIndexColumn": false,
              "truncateHeaders": true,
              "showDescriptions": true,
              "visColumnDisplay": "hide-view-name"
            },
            "aiConfig": {},
            "query": {
              "queryJson": {
                "limit": 500,
                "sorts": [],
                "table": "REPLACE_WITH_VIEW",
                "fields": [],
                "pivots": [],
                "dbtMode": false,
                "filters": {},
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
                "join_paths_from_topic_name": "REPLACE_WITH_TOPIC"
              }
            },
            "visConfig": {
              "visType": "basic",
              "spec": {},
              "fields": [],
              "version": 0
            }
          }
        }
      ]
    }
  },
  "document": {
    "connectionId": "REPLACE_WITH_CONNECTION_ID",
    "name": "REPLACE_WITH_DASHBOARD_NAME",
    "description": "",
    "scope": "organization",
    "type": "document"
  },
  "workbookModel": {
    "connection_id": "REPLACE_WITH_CONNECTION_ID",
    "views": [],
    "relationships": [],
    "model_kind": "WORKBOOK",
    "base_model_id": "REPLACE_WITH_MODEL_ID",
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

### 6.2 Dashboard object

| Field | Type | Notes |
|---|---|---|
| `name` | string | Title |
| `crossfilterEnabled` | bool | Enables tile-to-tile cross-filter |
| `facetFilters` | bool | Faceted filters enabled |
| `metadataVersion` | int | **Must be `2`** |
| `metadata.layouts.lg` | array | 12-col grid; objects with `i`, `x`, `y`, `w`, `h` |
| `metadata.textTiles` | array | Markdown / text tile definitions |
| `metadata.hiddenTiles` | array | Tile IDs hidden from the canvas |
| `metadata.tileSettings` | object | Per-tile UI settings keyed by `i` |
| `metadata.tileFilterMap` | object | Per-tile filter overrides |
| `metadata.tileControlMap` | object | Per-tile control overrides |
| `queryPresentationCollection.filterConfig` | object | Dashboard filters (see section 9) |
| `queryPresentationCollection.filterConfigVersion` | int | Default `0` |
| `queryPresentationCollection.filterOrder` | array | Field-name display order |
| `queryPresentationCollection.queryPresentationCollectionMemberships` | array | Tiles |

### 6.3 Layout grid

12-column responsive grid. Layout objects in `dashboard.metadata.layouts.lg`:

```json
[
  {"i": "1", "x": 0,  "y": 0,  "w": 12, "h": 15},
  {"i": "2", "x": 0,  "y": 15, "w": 6,  "h": 42},
  {"i": "3", "x": 6,  "y": 15, "w": 6,  "h": 42}
]
```

| Property | Description |
|---|---|
| `i` | Tile index, **string**, 1-based, matches the order in `queryPresentationCollectionMemberships` |
| `x` | Column 0-11 |
| `y` | Row, stacks top-to-bottom |
| `w` | Width 1-12 |
| `h` | Height (~12px per unit) |

### 6.4 Multi-tab dashboards

Multi-tab is exposed in the `documentMetadata.presentation` block of the stable PUT schema (https://docs.omni.co/api/documents/update-dashboard-document) and via additional layout breakpoints (`md`, `sm`) in the unstable schema. The public docs don't show a literal `tabs:` array; tabs are stored within `documentMetadata.presentation` and the metadata layouts. **Thin docs.** When in doubt, export an existing multi-tab dashboard via `GET .../export` and copy the structure.

### 6.5 Cross-filtering and drill linkage

`dashboard.crossfilterEnabled: true` enables click-to-filter across tiles. Per-tile drill behavior is in:
- `metadata.tileFilterMap[i]`: extra filters for that tile when dashboard filters change
- `visConfig.spec` per chart: drill_fields on the underlying measure (model side)

The `cross-filtering` doc page returns 404, so this is **thin**. Best practice is to leave `crossfilterEnabled: true` and let Omni wire it on shared dimensions.

### 6.6 Markdown / image / text tiles

Live in `dashboard.metadata.textTiles` (array). The `i` of a text tile cross-references with `metadata.layouts.lg`. The exact JSON shape is undocumented in public pages. Markdown content goes inline; supports HTML, CSS (sanitized), Mustache template variables `{{view.field}}`, and built-in components `ChangeArrow` and `Sparkline` (https://docs.omni.co/visualize-present/visualizations/types/markdown). Iframes are allowed (Google Docs, Maps, YouTube). JavaScript is stripped.

For divider / header tiles use a markdown tile with `# Heading` or an `<hr>`.

Sources:
- https://docs.omni.co/api/content-migration/import-dashboard
- https://docs.omni.co/api/content-migration/export-dashboard
- https://docs.omni.co/visualize-present/dashboards
- https://docs.omni.co/visualize-present/visualizations/types/markdown

### 6.7 Round-trip-able stable schema (`PUT /v1/documents/{id}`)

Used for less-than-full-fidelity edits but stable. (https://docs.omni.co/api/documents/update-dashboard-document, https://docs.omni.co/api/documents/get-dashboard-document)

```json
{
  "modelId": "abc123",
  "name": "Monthly Sales Dashboard",
  "description": "Total monthly sales.",
  "facetFilters": true,
  "refreshInterval": null,
  "filterConfig": {
    "order_items.category": {
      "type": "string",
      "kind": "EQUALS",
      "values": ["Electronics"],
      "is_negative": false
    }
  },
  "filterOrder": ["order_items.category"],
  "queryPresentations": [
    {
      "name": "Sales Trend",
      "description": "Monthly sales over time",
      "prefersChart": true,
      "topicName": "order_items",
      "query": {
        "fields": ["order_items.created_at[month]", "order_items.sale_price_sum"],
        "table": "order_items"
      },
      "visConfig": {
        "visType": "basic",
        "spec": {"mark": {"type": "line"}}
      }
    }
  ],
  "documentMetadata": {
    "presentation": {
      "filters": {
        "collapsible": true,
        "defaultExpanded": false
      }
    }
  },
  "clearExistingDraft": true
}
```

Required fields: `modelId`, `name` (1-254 chars), `facetFilters`, `refreshInterval` (>=60s or null), `filterConfig`, `filterOrder`, `queryPresentations` (>=1).

---

## 7. Tile / queryPresentation

Each tile in `queryPresentationCollectionMemberships[]` is a `queryPresentation` object:

| Field | Type | Notes |
|---|---|---|
| `type` | string | `"query"` for data tiles |
| `name` | string | Tile title |
| `subTitle` | string | Subtitle |
| `description` | string | Description text |
| `prefersChart` | bool | `true` for chart, `false` for table/spreadsheet |
| `automaticVis` | bool | **Must be `true`** when using `visType: basic`. `false` causes "No chart available" |
| `topicName` | string | Semantic topic this tile queries |
| `isSql` | bool | `false` for model-based, `true` for raw SQL tiles |
| `filterOrder` | array | Tile-local filter order |
| `resultConfig` | object | Table rendering (banding, banding size, column formats, hideIndexColumn, truncateHeaders, showDescriptions, visColumnDisplay) |
| `aiConfig` | object | AI-generated insights config |
| `query` | object | `{queryJson: {...}}` (see section 7.1) |
| `visConfig` | object | Chart spec (see section 8) |

### 7.1 queryJson

```json
{
  "limit": 500,
  "sorts": [
    {
      "null_sort": "OMNI_DEFAULT",
      "column_name": "view.field_name",
      "is_column_sort": false,
      "sort_descending": true
    }
  ],
  "table": "view_name",
  "fields": ["view.field1", "view.field2[month]"],
  "pivots": [],
  "dbtMode": false,
  "filters": { "view.field": { } },
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

Key invariants (verified gotchas, not in public docs):

- `version: 8`: current queryJson schema version.
- Every sort entry **must include `null_sort: "OMNI_DEFAULT"`**.
- `table` is the **base view** name, not the topic.
- `join_paths_from_topic_name` should be set so the query resolves joins through the right topic.
- `rewriteSql: true` lets Omni do its standard transforms.

### 7.2 Field reference syntax

All field references use dot notation: `view_name.field_name`.

| Granularity | Syntax | Example |
|---|---|---|
| Day | `[day]` | `sf_opportunities.closedate[day]` |
| Week | `[week]` | `sf_opportunities.closedate[week]` |
| Month | `[month]` | `sf_opportunities.closedate[month]` |
| Quarter | `[quarter]` | `sf_opportunities.closedate[quarter]` |
| Year | `[year]` | `sf_opportunities.closedate[year]` |

In Vega-Lite custom specs only, escape the dot: `users\\.id`, `users\\.created_at\\[date\\]`.

Sources:
- https://docs.omni.co/api/content-migration/import-dashboard
- https://docs.omni.co/visualize-present/visualizations/types/custom

---

## 8. visConfig: chart / visualization config

`visConfig` is JSON, not YAML. Shape:

```json
{
  "visType": "basic | omni-spreadsheet | omni-kpi | omni-table | omni-markdown | omni-ai-summary-markdown | summary-value | spreadsheet-tab | map | svg-map | funnel | sankey | single-record | vegalite",
  "spec": { },
  "fields": ["view.field1", "view.field2"],
  "version": 0
}
```

### 8.1 Supported visualization types (from /visualize-present/visualizations/types)

| Doc page | `visType` | Notes |
|---|---|---|
| Bar | `basic` (mark `bar`) | Stacked / grouped via `behaviors.stackMultiMark` |
| Line | `basic` (mark `line`) | Time on x, measure on y |
| Area | `basic` (mark `area`) | |
| Scatterplot | `basic` (mark `circle`) | |
| Boxplot | `basic` (mark `boxplot`) | |
| Pie & Donut | `basic` (configType `arc`) | Donut via inner radius |
| Heatmap | `basic` | |
| Funnel | `funnel` | dedicated visType |
| Sankey | `sankey` | dedicated |
| Map | `map` or `svg-map` | |
| Single record | `single-record` | |
| KPI | `omni-kpi` | |
| Table | `omni-table` or `omni-spreadsheet` | spreadsheet is the "results" style |
| Markdown | `omni-markdown` | |
| AI summary | `omni-ai-summary-markdown` | |
| Custom Vega-Lite | `vegalite` | |

(https://docs.omni.co/visualize-present/visualizations/types)

### 8.2 Critical rendering invariants (verified, public docs are thin on these)

1. `automaticVis` MUST be `true` when `visType: basic`. False breaks rendering with "No chart available."
2. `exportVersion` MUST be `"0.1"` as a *string* (not number, not float).
3. `metadataVersion` MUST be the integer `2`.
4. `fileUploads` MUST be `{}` (object), not `[]` (array). Empty array is rejected.
5. String filters MUST include a `kind` field, otherwise the dashboard page **crashes**.
6. `omni-kpi` with empty `spec: {}` does not render. Use `omni-spreadsheet` as a fallback.

### 8.3 Axis convention by chart type (verified)

Axis assignment differs between line and bar charts:

| Chart Type | x | y | `_dependentAxis` | series |
|---|---|---|---|---|
| Line / Multi-line | dimension (time) `field.name` | measure (title only) | `"y"` | `"yAxis": "y"` |
| Bar (horizontal) | measure (title only) | dimension `field.name` | `"x"` | `"xAxis": "x"` |
| Stacked / Grouped bar | measure (title only) | dimension `field.name` | `"x"` | `"xAxis": "x"` |
| Scatter | dimension `field.name` | measure (title only) | `"x"` | `"xAxis": "x"` |

### 8.4 Line chart (basic visType)

```json
{
  "visType": "basic",
  "spec": {
    "version": 0,
    "configType": "cartesian",
    "mark": {"type": "line"},
    "x": {
      "field": {"name": "sf_opportunities.closedate[month]"},
      "axis": {
        "title": {"value": ""},
        "sort": {"field": "sf_opportunities.closedate[month]", "order": "ascending"}
      }
    },
    "y": {
      "axis": {"title": {"value": "Revenue, FY25"}}
    },
    "series": [{
      "mark": {"type": "line", "_mark_color": "#4E79A7"},
      "field": {"name": "sf_opportunities.total_amount"},
      "title": {"value": "Revenue", "format": "USDCURRENCY"},
      "yAxis": "y"
    }],
    "tooltip": [
      {"field": {"name": "sf_opportunities.closedate[month]"}},
      {"field": {"name": "sf_opportunities.total_amount"}}
    ],
    "behaviors": {"stackMultiMark": false},
    "_dependentAxis": "y"
  },
  "fields": ["sf_opportunities.closedate[month]", "sf_opportunities.total_amount"],
  "version": 0
}
```

Line-mark properties (https://docs.omni.co/visualize-present/visualizations/types/line):

| Property | Values |
|---|---|
| `mark.type` | `line` |
| Show points alongside line | toggle in mark config |
| Line style | solid or dashed |
| Line thickness | numeric (default 1) |
| Opacity | 0..1 |
| Interpolation | `linear`, `monotone`, `step`, `step before`, `step after` |
| Stacking | `automatic`, `stack`, `group`, `overlay`, `stack %` (under series/color) |

Secondary y-axis: assign `"yAxis": "y2"` on additional `series[]` and add a second axis under `spec`. Public docs are **thin** on the exact y2 spec keys.

### 8.5 Bar chart (horizontal)

Omni renders bars horizontally. Category goes on `y`, measure goes on the series.

```json
{
  "visType": "basic",
  "spec": {
    "version": 0,
    "configType": "cartesian",
    "mark": {"type": "bar"},
    "x": {"axis": {"title": {"value": "Revenue"}}},
    "y": {
      "field": {"name": "sf_opportunities.region"},
      "axis": {
        "title": {"value": ""},
        "sort": {"field": "sf_opportunities.total_amount", "order": "descending"}
      }
    },
    "series": [{
      "mark": {"type": "bar", "_mark_color": "#4E79A7"},
      "field": {"name": "sf_opportunities.total_amount"},
      "title": {"value": "Revenue"},
      "xAxis": "x"
    }],
    "tooltip": [
      {"field": {"name": "sf_opportunities.region"}},
      {"field": {"name": "sf_opportunities.total_amount"}}
    ],
    "behaviors": {"stackMultiMark": false},
    "_dependentAxis": "x"
  },
  "fields": ["sf_opportunities.region", "sf_opportunities.total_amount"],
  "version": 0
}
```

- **Stacked bar:** set `behaviors.stackMultiMark: true`. Max recommended segments: 4.
- **Grouped bar:** `behaviors.stackMultiMark: false` with multiple `series[]`.
- **100% stacked:** stacking option `stack %` (encoded somewhere in series/color block; **thin docs**, verify via UI export).
- **Bar config (https://docs.omni.co/visualize-present/visualizations/types/bar):** stacking values "Automatic, Stack, Group, Overlay, Stack %", plus totals labels.

### 8.6 Scatter

```json
{
  "visType": "basic",
  "spec": {
    "version": 0,
    "configType": "cartesian",
    "mark": {"type": "circle"},
    "x": {"axis": {"title": {"value": "Deal Size"}}},
    "y": {
      "field": {"name": "sf_opportunities.region"},
      "axis": {"title": {"value": "Region"}}
    },
    "series": [{
      "mark": {"type": "circle", "_mark_color": "#4E79A7"},
      "field": {"name": "sf_opportunities.total_amount"},
      "title": {"value": "Revenue"},
      "xAxis": "x"
    }],
    "behaviors": {"stackMultiMark": false},
    "_dependentAxis": "x"
  },
  "fields": ["sf_opportunities.region", "sf_opportunities.total_amount"],
  "version": 0
}
```

### 8.7 Table / spreadsheet

```json
{
  "visType": "omni-spreadsheet",
  "spec": {},
  "fields": ["view.field1", "view.field2"],
  "version": 0
}
```

Set `prefersChart: false` on the queryPresentation. `resultConfig` controls table-specific rendering:

```json
{
  "tableType": "spreadsheet",
  "rowBanding": {"enabled": true, "bandSize": 1},
  "expandedRows": {},
  "columnFormats": {
    "sf_opportunities.total_amount": {
      "format": "USDCURRENCY",
      "decimals": 0,
      "color": "#4E79A7"
    }
  },
  "hideIndexColumn": false,
  "truncateHeaders": true,
  "showDescriptions": true,
  "visColumnDisplay": "hide-view-name"
}
```

(https://docs.omni.co/visualize-present/visualizations/types/table)

Conditional formatting and color scales are configured under `resultConfig.columnFormats` per column. Public docs are **thin** on the exact JSON keys for color scales. Easiest path is to set them in the UI then export.

### 8.8 KPI

```json
{
  "visType": "omni-kpi",
  "spec": {
    "rows": [
      {
        "type": "number",
        "field": "sf_opportunities.total_amount",
        "format": "USDCURRENCY"
      },
      {
        "type": "comparison",
        "field": "sf_opportunities.total_amount_yoy",
        "format": "percent"
      },
      {
        "type": "progress",
        "field": "sf_opportunities.attainment_pct",
        "target": 1.0,
        "shape": "bar"
      },
      {
        "type": "chart",
        "field": "sf_opportunities.total_amount",
        "x": "sf_opportunities.closedate[month]",
        "shape": "line",
        "height": 30
      },
      {
        "type": "text",
        "markdown": "**Quarterly target tracker**"
      }
    ]
  },
  "fields": ["sf_opportunities.total_amount"],
  "version": 0
}
```

KPI is row-based. Components: `number`, `comparison`, `progress` (bar/circle), `chart` (sparkline; bars or lines), `text` (markdown). (https://docs.omni.co/docs/visualization-and-dashboards/visualization-types/kpi). Public docs do not enumerate every JSON key. Derived from UI / observed payloads. **Thin.**

### 8.9 Funnel

```json
{
  "visType": "funnel",
  "spec": {
    "orientation": "vertical",
    "alignment": "center",
    "gap": 4,
    "color": "#4E79A7",
    "dataLabels": {
      "enabled": true,
      "position": "middle",
      "fontSize": 12,
      "format": "decimal",
      "percentChange": "percentOfPrevious",
      "percentChangeFormat": "0.0%"
    },
    "tooltips": {"enabled": true}
  },
  "fields": ["sf_opportunities.stage_name", "sf_opportunities.count"],
  "version": 0
}
```

`orientation`: `vertical` | `horizontal`. `alignment`: `left` | `center` | `right`. `dataLabels.percentChange`: `none` | `percentOfFirst` | `percentOfPrevious`.

(https://docs.omni.co/visualize-present/visualizations/types/funnel)

### 8.10 Markdown tile

```json
{
  "visType": "omni-markdown",
  "spec": {
    "markdown": "# {{sf_opportunities.region}}\n**Revenue:** {{sf_opportunities.total_amount}}\n<ChangeArrow value={{sf_opportunities.total_amount_yoy}} />\n<Sparkline field='sf_opportunities.total_amount' />"
  },
  "fields": ["sf_opportunities.region", "sf_opportunities.total_amount", "sf_opportunities.total_amount_yoy"],
  "version": 0
}
```

Mustache template binding: `{{view.field}}`, `{{#result}} ... {{/result}}` for loops. Built-in tags `<ChangeArrow>`, `<Sparkline>`. Iframes allowed; JS stripped. CSS `@media` may not work in PDF export. (https://docs.omni.co/visualize-present/visualizations/types/markdown)

### 8.11 Custom Vega-Lite

```json
{
  "visType": "vegalite",
  "spec": {
    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
    "data": {"name": "results"},
    "mark": "bar",
    "encoding": {
      "x": {"field": "sf_opportunities\\.region", "type": "nominal"},
      "y": {"field": "sf_opportunities\\.total_amount", "type": "quantitative"}
    }
  },
  "fields": ["sf_opportunities.region", "sf_opportunities.total_amount"],
  "version": 0
}
```

Reference fields in Vega-Lite by `view\\.field_name` (escaped dot). Date granularity: `users\\.created_at\\[date\\]`. Drill is unavailable on custom Vega specs. (https://docs.omni.co/visualize-present/visualizations/types/custom)

### 8.12 Reference lines, trend lines, forecasting

The line-chart doc references these as features but does not enumerate JSON keys. The current way to add a reference line via API is to embed the spec in `vegalite` visType or add a series with a constant calculation. **Thin docs.**

### 8.13 Number / value formatting

Allowed `format` values (seen in payloads + measure docs):

- Named: `USDCURRENCY`, `currency`, `percent`, `decimal`, `id`, `string`
- Excel-style format strings: `"$#,##0"`, `"0.0%"`, `"#,##0.00"`
- Custom-format references (defined under `model.custom_formats`)

In `series[].title.format` the named values are uppercase: `"format": "USDCURRENCY"`.

### 8.14 Color palette (Tableau 10 muted, used by default in spec_builder)

| Index | Hex | Use |
|---|---|---|
| 0 | `#4E79A7` | first / single series |
| 1 | `#F28E2B` | second |
| 2 | `#E15759` | third |
| 3 | `#76B7B2` | fourth |
| 4 | `#59A14F` | fifth |
| 5 | `#EDC948` | sixth |
| 6 | `#B07AA1` | seventh (max) |

Per-series color: `series[].mark._mark_color: "#HEX"`. Per-value (data-driven) color: pass a categorical field in `fields[]` and let `automaticVis: true` map it to color. Org-level theme override: model file does not currently expose a brand-color override; theming is dashboard-level via spec.

Sources:
- https://docs.omni.co/visualize-present/visualizations/types
- https://docs.omni.co/visualize-present/visualizations/types/bar
- https://docs.omni.co/visualize-present/visualizations/types/line
- https://docs.omni.co/visualize-present/visualizations/types/funnel
- https://docs.omni.co/visualize-present/visualizations/types/kpi
- https://docs.omni.co/visualize-present/visualizations/types/table
- https://docs.omni.co/visualize-present/visualizations/types/markdown
- https://docs.omni.co/visualize-present/visualizations/types/custom
- https://docs.omni.co/docs/visualization-and-dashboards/visualization-types/kpi

---

## 9. Filters

Filters appear in three places:
- **Inside `queryJson.filters`**: applies to a single tile's query.
- **Inside `dashboard.queryPresentationCollection.filterConfig`**: dashboard-level.
- **In topic / view / measure YAML**: model-level (`always_where_filters`, `default_filters`, measure `filters`).

### 9.1 Filter operators (YAML / model side)

(https://docs.omni.co/modeling/filters and /modeling/filters/operators)

| Category | Operators |
|---|---|
| Conditional | `is`, `not`, `and`, `or` |
| Cross-query | `cancel_query_filter`, `field_name_in_query`, `field_name_not_in_query` |
| Date/time | `before`, `between_dates`, `day_of_week`, `month_of_year`, `time_for_duration`, `date_offset_from_query` |
| Numeric | `between`, `greater_than`, `less_than`, plus `_or_equal_to` variants |
| String | `contains`, `starts_with`, `ends_with`, `case_insensitive` |

Negation: prefix `not_` (except `is`, `and`, `or`. For `is` use the `not` operator).

YAML form:

```yaml
sf_opportunities.stage_name:
  is: Closed Won

sf_opportunities.amount:
  between: [10000, 100000]

sf_opportunities.closedate:
  time_for_duration:
    left: 12 months ago
    right: 12 months

users.region:
  not_is: [Hawaii, Alaska]
```

Boolean three-state: `true`, `false`, `null`, plus the special `falsey` (false-or-null).

### 9.2 Filter `kind` values (JSON / wire side)

These appear in `queryJson.filters` and `dashboard.filterConfig`. The filter wire schema:

```json
{
  "<view.field>": {
    "type": "string|number|date|boolean|null|by_query|user_attribute|composite",
    "kind": "<KIND>",
    "values": [],
    "left_side": "...",
    "right_side": "...",
    "is_negative": false,
    "treat_nulls_as_false": false
  }
}
```

Documented `type` values (https://docs.omni.co/api/dashboard-filters/update-dashboard-filterscontrols):

`string`, `number`, `date`, `boolean`, `null`, `by_query`, `user_attribute`, `composite`.

Documented `kind` values are sparse in the public docs. Only `EQUALS` (string) and `WITHIN_RANGE` (date) are explicitly enumerated. **Thin.** Based on observed working payloads:

| Type | Common `kind` values |
|---|---|
| string | `STRING_IS`, `EQUALS`, `STRING_CONTAINS`, `STRING_STARTS_WITH`, `STRING_ENDS_WITH`, `STRING_IS_NULL`, `STRING_IS_NOT_NULL` |
| number | `EQUALS`, `GREATER_THAN`, `LESS_THAN`, `BETWEEN`, `WITHIN_RANGE`, `NUMBER_IS_NULL` |
| date | `IS_ON_DAY_OF_WEEK`, `IS_ON_DAY_OF_QUARTER`, `IS_IN_MONTH_OF_YEAR`, `IS_ON_DAY_OF_YEAR`, `IS_AT_HOUR_OF_DAY`, `IS_IN_QUARTER_OF_YEAR`, `IS_IN_WEEK_OF_YEAR`, `IS_ON_DAY_OF_MONTH`, `BETWEEN`, `ON_OR_AFTER`, `BEFORE`, `TIME_FOR_INTERVAL_DURATION`, `TIME_FOR_UNIT_DURATION`, `QUERY_OFFSET` (full enum surfaced via the dashboards-update-filters 400 error message) |
| boolean | (`type: boolean` only; no `kind`) |

**Relative-date filters all use `TIME_FOR_INTERVAL_DURATION` on the wire**, which is the JSON form of YAML `time_for_duration`. The query planner rejects `TIME_FOR_UNIT_DURATION` even though the dashboard PATCH API accepts it ("Invalid literal value '12 months' in filter").

The UI picker that Omni renders depends on the relationship between `left_side` and `right_side`, not on the kind name. Two patterns matter for migrations:

- **"In the past N units"** picker, which is the symmetric form per the docs (`time_for_duration: [N units ago, N units]`):
  ```json
  {"kind": "TIME_FOR_INTERVAL_DURATION", "type": "date",
   "left_side": "12 months ago", "right_side": "12 months", "is_negative": false}
  ```
- **Offset-plus-duration** picker (e.g. "starting 6 months ago, for 4 months"):
  ```json
  {"kind": "TIME_FOR_INTERVAL_DURATION", "type": "date",
   "left_side": "6 months ago", "right_side": "4 months", "is_negative": false}
  ```

Key Omni date-literal semantics (confirmed against generated SQL):

- `"N units ago"` resolves to the START of the period that is (N-1) calendar units back from now (truncated, inclusive of current). So `"12 months ago"` becomes `INTERVAL '-11 month'`, not `'-12 month'`. This is why the symmetric `[N units ago, N units]` form covers a window of exactly N calendar units ending at the current period.
- `"N complete units ago"` is the strict form, resolving to `INTERVAL '-N unit'` (excludes the current period).
- The `"is_negative"` flag flips the filter to exclude rather than include the window.

Working examples from the in-repo `omni-vega-chart` skill:

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

```json
{
  "sf_opportunities.iswon": {
    "type": "boolean",
    "is_negative": false,
    "treat_nulls_as_false": false
  }
}
```

**Reminder gotcha (verified):** string filters that omit `kind` crash the dashboard page client-side.

### 9.3 Dashboard-level filter shape

```json
{
  "filterConfig": {
    "sf_opportunities.closedate": {
      "type": "date",
      "label": "Date Range",
      "kind": "TIME_FOR_INTERVAL_DURATION",
      "hidden": false,
      "fieldName": "sf_opportunities.closedate",
      "left_side": "27 months ago",
      "right_side": "27 months",
      "required": false,
      "description": "Roll-up window."
    },
    "sf_opportunities.region": {
      "type": "string",
      "kind": "STRING_IS",
      "values": ["Northeast", "West"],
      "label": "Region",
      "required": false,
      "hidden": false,
      "fieldName": "sf_opportunities.region"
    }
  },
  "filterOrder": ["sf_opportunities.closedate", "sf_opportunities.region"]
}
```

### 9.4 Controls (UI widgets layered on filters)

`PATCH /v1/dashboards/{id}/filters` distinguishes `filters` from `controls`. Control `type` values:

| `type` | Effect |
|---|---|
| `FIELD_SELECTION` | Single-select dropdown for swapping the field bound to a tile |
| `MULTI_FIELD_SELECTION` | Parent control grouping child controls |
| `FIELD_PICKER` | Multi-select field picker |
| `PERIOD_OVER_PERIOD` | Time comparison control |

Control fields: `id`, `type`, `kind`, `label`, `description`, `field`, `options[]` (`{label, value}`), `hidden`. Update fields: `label`, `description`, `hidden`.

```json
{
  "id": "metric_picker",
  "type": "FIELD_SELECTION",
  "kind": "FIELD",
  "label": "Metric",
  "field": "sf_opportunities.total_amount",
  "options": [
    {"label": "Revenue", "value": "sf_opportunities.total_amount"},
    {"label": "Deal Count", "value": "sf_opportunities.count"}
  ]
}
```

(https://docs.omni.co/api/dashboard-filters/get-dashboard-filters-and-controls, https://docs.omni.co/api/dashboard-filters/update-dashboard-filterscontrols)

### 9.5 Filter linking across tiles

Per-tile overrides go in `dashboard.metadata.tileFilterMap` and `dashboard.metadata.tileControlMap`, keyed by tile `i` (the same string as in `layouts.lg`). Public docs are **thin** on the exact override shape. The safest path is to roundtrip-export an existing dashboard with linked filters and copy the structure.

### 9.6 Templated filters (model side)

(https://docs.omni.co/modeling/templated-filters)

```yaml
filters:
  status:
    type: string
    suggest_from_field: order_items.status
    default_filter: active
    filter_single_select_only: true
    suggestion_list: [active, pending, cancelled]
    bind_to: order_items.status
    display_order: 1

dimensions:
  filtered_revenue:
    sql: |
      SUM(CASE WHEN ${TABLE}.status = '{{filters.order_items.status.value}}'
                THEN ${TABLE}.amount ELSE 0 END)
    type: number
```

`filters` block fields:
- `type`: `boolean | column | number | string | timestamp`
- `default_filter`, `filter_single_select_only`, `suggestion_list`, `suggest_from_field`, `bind_to`, `display_order`

Reference the value: `{{filters.<view>.<field>.value}}`, `{{filters.<view>.<field>.range_start}}`, `range_end`.

Self-referential conditional logic:
- `{{ <view>.<field>.in_query }}`: present in SELECT or WHERE
- `{{ <view>.<field>.is_selected }}`: present in SELECT
- `{{ <view>.<field>.is_filtered }}`: present in WHERE

Mustache:
- `{{# view.field.filter }}expr{{/ view.field.filter }}`: render when filter present
- `{{^ view.field.filter }}default{{/ view.field.filter }}`: render when absent

Sources:
- https://docs.omni.co/modeling/filters
- https://docs.omni.co/modeling/filters/operators
- https://docs.omni.co/modeling/templated-filters
- https://docs.omni.co/api/dashboard-filters/get-dashboard-filters-and-controls
- https://docs.omni.co/api/dashboard-filters/update-dashboard-filterscontrols

---

## 10. CLI / API surface

### 10.1 Two CLIs to disambiguate

There are **two** distinct CLI surfaces:

#### A. The official Omni CLI (`omni`)

(https://docs.omni.co/developers/cli, https://docs.omni.co/developers/cli/install, https://docs.omni.co/developers/cli/commands)

Install:

```bash
brew tap exploreomni/tap && brew install omni
# OR
curl -fsSL https://raw.githubusercontent.com/exploreomni/cli/main/install.sh | sh
```

Platforms: macOS amd64/arm64, Linux amd64/arm64, Windows amd64.

Output: every command returns JSON to stdout. Errors go to stderr as JSON. Use `--compact` for pipe-to-`jq`. Global flags: `--help`, `--token`, `--base-url`, `--profile`, `--compact`.

Command groups:

| Group | Purpose |
|---|---|
| `omni config` | Manage CLI profiles interactively |
| `omni agent-help` | Usage guide for AI agents |
| `omni query run` | Execute semantic queries |
| `omni models` | Models, views, fields, topics, branches |
| `omni connections` | DB connections, dbt configs |
| `omni documents` | Documents incl. dashboards |
| `omni dashboards` | Download dashboards, manage filters |
| `omni folders` | Folder management |
| `omni labels` | Content labels |
| `omni users` | Roles, email-only users |
| `omni scim` | SCIM provisioning |
| `omni embed` | SSO embed sessions |
| `omni ai` | Generate queries / search docs |
| `omni schedules` | Delivery schedules |
| `omni uploads` | CSV / Excel upload |
| `omni unstable` | Preview / experimental endpoints |

The CLI auto-generates from the OpenAPI spec, so anything you can hit on the API you can hit on the CLI.

#### B. The model-local-editor (`omni-sync`)

(https://docs.omni.co/guides/modeling/local-development, https://www.npmjs.com/package/@omni-co/model-local-editor)

```bash
npm install -g @omni-co/model-local-editor

# init: pull model YAML to local fs, optionally creating a branch
omni-sync init <model_id> --branch <branch-name> --create-branch

# start: watch local files, push saves to the branch with validation
omni-sync start <model_id>

# merge: promote branch to shared model
omni-sync merge-branch <model_id> <branch-name> --delete-branch
```

Env vars: `OMNI_API_KEY`, `OMNI_BASE_URL`. Status: **beta, under active development**. Node 16+. Recommends git integration with "Pull request required" + "Always create branches."

This is the closest thing Omni has to a LookML-style local edit loop. It works on **model files only** (views, topics, model, relationships), not on dashboards/workbooks.

### 10.2 Dashboard / workbook authoring APIs

| Endpoint | Method | Stable? | Purpose |
|---|---|---|---|
| `/api/unstable/documents/import` | POST | beta | **Create a dashboard from full JSON** |
| `/api/unstable/documents/{id}/export` | GET | beta | **Export full dashboard JSON** (round-trip-able) |
| `/api/v1/documents` | POST | stable | Create document (less fidelity than import) |
| `/api/v1/documents` | GET | stable | List documents |
| `/api/v1/documents/{id}` | GET | stable | Get round-trip-able dashboard JSON |
| `/api/v1/documents/{id}` | PUT | stable | Update document (round-trip subset) |
| `/api/v1/documents/{id}` | DELETE | stable | Delete |
| `/api/v1/documents/{id}/queries` | GET | stable | Get queries within a document |
| `/api/v1/dashboards/{id}/filters` | GET | stable | Get filters/controls |
| `/api/v1/dashboards/{id}/filters` | PATCH | stable | Update filters/controls |
| `/api/v1/models/{id}/yaml` | GET | stable | Get model YAML files |
| `/api/v1/models/{id}/yaml` | POST | stable | Create/update YAML files |
| `/api/v1/models/{id}/yaml/{file}` | DELETE | stable | Delete YAML file |
| `/api/v1/models` | POST | stable | Create model (e.g., new branch) |
| `/api/v1/models` | GET | stable | List models |
| `/api/v1/models/{id}/validate` | POST | stable | Validate model |
| `/api/v1/content/validate` | POST | stable | Validate content |
| `/api/v1/content/find-and-replace` | POST | stable | Find/replace across content |

Auth headers (all): `Authorization: Bearer <token>`. **Note:** `/api/unstable/documents/import` requires Organization API Key, NOT PAT.

---

## 11. Known gotchas / undocumented behavior (verified)

### 11.1 Workbooks always extend SHARED (verified true, May 2026)

The user's stored memory (`feedback_omni_workbook_extends_shared.md`) flags that the imported workbook always extends the SHARED model regardless of the `?branch=` URL parameter. This remains true. The `documents-import` doc only requires `baseModelId`; the `?branch=` URL is misleading because workbooks always extend SHARED. Mitigation in this repo is `seed_workbook.py`.

### 11.2 `documents-import` API is unstable (verified, still beta)

The endpoint is at `/api/unstable/documents/import`. The doc explicitly says "This API is in beta and may have future breaking changes." When emitting against this endpoint:
- Pin `exportVersion: "0.1"` (string).
- Pin `metadataVersion: 2` (integer).
- Validate against a fresh export from the target instance before treating shape as fixed.

### 11.3 `fileUploads: {}` not `[]`

Empty file uploads must be the empty object. Empty array fails validation.

### 11.4 String filters require `kind`

Omitting `kind` on a `type: string` filter crashes the dashboard page in the browser. Always emit one of the `STRING_*` kinds.

### 11.5 Sort entries require `null_sort: "OMNI_DEFAULT"`

Every `sorts[]` entry needs this key. Missing it produces an opaque API error.

### 11.6 `automaticVis` semantics

`visType: basic` requires `automaticVis: true`. With `false`, complex specs fail to render. For non-`basic` visTypes (`omni-spreadsheet`, etc.), `automaticVis` is generally ignored.

### 11.7 Bar charts render horizontally by default

The Vega-Lite-style assumption "x = horizontal axis = category" does NOT hold. In Omni `basic` bar charts, the category goes on `y` and `_dependentAxis` is `"x"`. Putting the category on `x` produces a chart that looks rotated 90 degrees from the spec.

### 11.8 Branch URLs in the IDE vs the API

The `?branch=` URL parameter is purely cosmetic when using `documents-import`. See 11.1.

### 11.9 Order of operations for new dashboards

1. Branch must already exist (use `omni-branch-creator` skill or `POST /api/v1/models` with `modelKind: BRANCH`).
2. Topics referenced in `topicName` and field names must exist on the target `baseModelId`.
3. `seed_workbook.py` (or equivalent) primes the workbook to extend the right SHARED model.
4. Then `POST documents/import`.

### 11.10 The `omni-kpi` "blank" trap

`omni-kpi` with `spec: {}` renders empty. Either populate `spec.rows[]` or fall back to `omni-spreadsheet`.

---

## 12. AI / Omni Agent context

### 12.1 Where AI context lives

| Place | Param | Purpose |
|---|---|---|
| Model | `ai_context` (string) | Context that applies to every topic |
| Model | `ai_settings` (object) | Behavior config (see section 2.1) |
| Model | `ai_chat_topics` (list) | Whitelist of topics agents can use |
| Model | `sample_queries` (list) | Few-shot examples for AI |
| Topic | `ai_context` (string) | Topic-specific context |
| Topic | `ai_fields` (list) | Fields exposed to the agent |
| Topic | `sample_queries` (list) | Topic-level few-shot |
| View | `ai_context` (string) | View-specific |
| Dimension/Measure | `description` (string) | **Feeds field-level AI guidance** |
| Dimension/Measure | `synonyms` (list) | Alternative terms for AI matching |

### 12.2 AI context pattern (verified working in production)

```yaml
ai_context: |
  This is a SaaS company's Salesforce CRM data.

  CRITICAL FIELD NOTES:
  - Competitor__c is MISLEADINGLY named. For WON deals it stores the win
    attribution channel (values starting with 'CH -'). For LOST deals it
    stores the competitor who won. For open deals it is NULL.
  - "Channel Wins" means: Competitor__c LIKE 'CH%' AND StageName = 'Closed Won'
  - IsClosed is TRUE for BOTH won AND lost deals. Always pair with IsWon.
  - FiscalYear uses July start. FY25 = Jul 2024 through Jun 2025.
  - WhatId in Activities is a polymorphic lookup usually pointing to an Opportunity.
  - Win Rate = COUNT(IsWon=TRUE) / COUNT(IsClosed=TRUE), not divided by all deals.

  COMMON QUERIES:
  - Pipeline: WHERE IsClosed = FALSE
  - FY25 Wins: WHERE FiscalYear = 2025 AND IsWon = TRUE
  - Activity by rep: GROUP BY OwnerName, Type
```

### 12.3 Sample queries

```yaml
sample_queries:
  - question: "How many deals did we win from referral partners in FY25?"
    fields: [sf_opportunities.count, sf_opportunities.total_amount]
    filters:
      sf_opportunities.competitor_c: "CH - Partner Referral"
      sf_opportunities.stage_name: "Closed Won"
      sf_opportunities.fiscal_year: "2025"

  - question: "What is our win rate by region?"
    fields: [sf_opportunities.region_c, sf_opportunities.win_rate]
    filters:
      sf_opportunities.is_closed: "true"
```

### 12.4 Field descriptions feed AI

`description` fields on dimensions and measures are the strongest signal Omni has when the agent picks fields. The agent matches user questions against:
1. Field labels.
2. Field descriptions.
3. Synonyms list (if present).
4. Sample queries (as few-shot).
5. ai_context blocks (model > topic > view).

`synonyms:` is a list field on dimensions and measures used to expand the agent's match set ("revenue", "rev", "sales", "top line"). Public docs are **thin** on enumerating this. The in-repo `omni-semantic-layer-setup` skill confirms it works.

Sources:
- https://docs.omni.co/modeling/models/ai-settings
- https://docs.omni.co/modeling/topics/setup
- (in-repo) `skills/omni-semantic-layer-setup/context/view-yaml-patterns.md`

---

## 13. Quick reference: emitting a one-tile dashboard

End-to-end emission target:

1. Resolve `baseModelId` (use `omni models list` or persist).
2. Resolve `connectionId` from the model (used in `document.connectionId` and `workbookModel.connection_id`).
3. Build `queryJson` (table=base_view, fields, filters, sorts).
4. Build `visConfig` per chart type (section 8).
5. Wrap in dashboard envelope (section 6.1).
6. POST `/api/unstable/documents/import` with Organization API Key.
7. Returns `{dashboard.dashboardId, miniUuidMap, workbook}`. Build URL: `{BASE_URL}/dashboards/{dashboardId}`.

For multi-tile: append more `queryPresentationCollectionMemberships[]`, give each a unique tile index `i` ("1", "2", "3"), and add matching layout objects in `metadata.layouts.lg`.

---

## Sources (consolidated)

- https://docs.omni.co/api
- https://docs.omni.co/api/content-migration/import-dashboard
- https://docs.omni.co/api/content-migration/export-dashboard
- https://docs.omni.co/api/documents/get-dashboard-document
- https://docs.omni.co/api/documents/update-dashboard-document
- https://docs.omni.co/api/documents/create-document
- https://docs.omni.co/api/documents/list-documents
- https://docs.omni.co/api/documents/delete-document
- https://docs.omni.co/api/documents/get-document-queries
- https://docs.omni.co/api/dashboard-filters/get-dashboard-filters-and-controls
- https://docs.omni.co/api/dashboard-filters/update-dashboard-filterscontrols
- https://docs.omni.co/api/models/create-or-update-yaml-files
- https://docs.omni.co/api/models/get-model-yaml
- https://docs.omni.co/api/models/delete-a-yaml-file
- https://docs.omni.co/api/models/create-model
- https://docs.omni.co/api/models/list-models
- https://docs.omni.co/api/models/validate-model
- https://docs.omni.co/api/topics/retrieve-a-topic
- https://docs.omni.co/api/content/retrieve-content
- https://docs.omni.co/api/content-validator/validate-content
- https://docs.omni.co/api/content-validator/find-and-replace-content
- https://docs.omni.co/developers/cli
- https://docs.omni.co/developers/cli/install
- https://docs.omni.co/developers/cli/commands
- https://docs.omni.co/guides/modeling/local-development
- https://docs.omni.co/modeling/develop/guides/model-ide
- https://docs.omni.co/modeling/views
- https://docs.omni.co/modeling/views/parameters
- https://docs.omni.co/modeling/dimensions
- https://docs.omni.co/modeling/measures
- https://docs.omni.co/modeling/topics
- https://docs.omni.co/modeling/topics/setup
- https://docs.omni.co/modeling/topics/parameters
- https://docs.omni.co/modeling/relationships
- https://docs.omni.co/modeling/filters
- https://docs.omni.co/modeling/filters/operators
- https://docs.omni.co/modeling/templated-filters
- https://docs.omni.co/modeling/models/ai-settings
- https://docs.omni.co/docs/modeling/model-files
- https://docs.omni.co/visualize-present/dashboards
- https://docs.omni.co/visualize-present/dashboards/migrate
- https://docs.omni.co/visualize-present/visualizations/types
- https://docs.omni.co/visualize-present/visualizations/types/bar
- https://docs.omni.co/visualize-present/visualizations/types/line
- https://docs.omni.co/visualize-present/visualizations/types/funnel
- https://docs.omni.co/visualize-present/visualizations/types/kpi
- https://docs.omni.co/visualize-present/visualizations/types/table
- https://docs.omni.co/visualize-present/visualizations/types/markdown
- https://docs.omni.co/visualize-present/visualizations/types/custom
- https://docs.omni.co/docs/visualization-and-dashboards/visualization-types/kpi
- https://docs.omni.co/getting-started/best-practices
- https://docs.omni.co/llms.txt
- https://www.npmjs.com/package/@omni-co/model-local-editor
- (in-repo) `skills/omni-vega-chart/context/visconfig-patterns.md`
- (in-repo) `skills/omni-vega-chart/context/omni-field-syntax.md`
- (in-repo) `skills/omni-vega-chart/templates/dashboard-payload.json`
- (in-repo) `skills/tableau-to-omni/context/omni-api-patterns.md`
- (in-repo) `skills/omni-semantic-layer-setup/context/view-yaml-patterns.md`
