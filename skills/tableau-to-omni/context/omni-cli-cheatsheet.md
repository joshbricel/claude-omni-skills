# Omni CLI Cheatsheet (for the Tableau-to-Omni migration flow)

The official `omni` CLI ships at `1.0.x` from `github.com/exploreomni/cli`. Install:

```bash
brew tap exploreomni/tap
brew install omni
omni config init
```

This file lists the verbs we use during migration, in workflow order. For the full surface, run `omni --help` or `omni agent-help`.

## Authentication and profiles

```bash
omni config init                       # prompts for org URL + API token
omni config show                       # show active profile
omni config use <profile>              # switch profile (multi-tenant work)
```

Token can also come from the `OMNI_API_TOKEN` env var. Per-command override: `--token <token>`.

## Discovery (Step 7 of the migration)

```bash
omni connections list --compact --format json
omni models list --compact --format json
omni content list --compact --format json | jq '.[] | select(.hasDashboard)'
omni folders list --compact --format json
```

Capture `connection_id` and the target `base_model_id`. Save to a local `.env`.

## Branching (Step 8)

```bash
omni models create-branch <base-model-id> --body '{"name":"tableau-mig-2026-05-08"}'
```

Returns the branch model ID. Treat it as the sandbox for the migration.

To start a branch from an existing branch or version (rare, useful for redoing a botched merge):

```bash
omni models create-branch <base-model-id> --body '{"name":"...","startingPoint":"branch:<id>"}'
omni models create-branch <base-model-id> --body '{"name":"...","startingPoint":"version:<id>"}'
```

## Modeling (Step 9, between import and validate)

If the migration adds calc fields or views to the model:

```bash
omni models create-field <branch-model-id> --body '{"viewName":"...","field":{...}}'
omni models update-view  <branch-model-id> --body '{"viewName":"...","fields":[...]}'
omni models list-topics  <branch-model-id> --compact
omni models get-topic    <branch-model-id> <topic-name>
omni models update-topic <branch-model-id> <topic-name> --body '{...}'
```

Or work entirely in YAML (recommended for complex changes, easier to diff):

```bash
omni models yaml-get    <branch-model-id> > model.yaml
# edit model.yaml
omni models yaml-create <branch-model-id> --body "$(cat model.yaml)"
```

## Importing the dashboard (Step 10)

```bash
omni unstable documents-import --body "$(cat payload.json)"
```

Returns the new document ID. Save it for later moves and labels.

If the payload references a model the import API can't find, the response is a 4xx with a clear field-name reason. Most common: missing or wrong `baseModelId`.

## Validation (Step 11)

```bash
omni models validate <branch-model-id>
```

Reports unresolved field references, broken joins, malformed YAML. Iterate until clean.

## Querying for parity (Step 12)

```bash
omni query run --body '{"modelId":"<branch-model-id>","query":{"fields":["topic/field"],"limit":10}}' --format json
omni query wait <job-id>
```

Or use the AI helper to translate a natural-language question into a query (useful for scripting parity checks against business-language rules):

```bash
omni ai generate-query --body '{"modelId":"<branch-model-id>","prompt":"total registrations by month","executeQuery":true}'
```

Async pattern (for long-running queries):

```bash
omni ai job-submit  --body '{"modelId":"<id>","prompt":"..."}'
omni ai job-status  <job-id>
omni ai job-result  <job-id>
omni ai job-visualization <job-id>
```

## Dashboard organization (Step 13)

```bash
omni documents move <doc-id> --body '{"folderPath":"/Sales/Pipeline"}'
omni documents transfer-ownership <doc-id> --body '{"newOwnerId":"<user-id>"}'
omni documents add-label <doc-id> --body '{"name":"migrated-from-tableau"}'
omni documents update-permission-settings <doc-id> --body '{...}'
```

Folder structure should mirror your team layout. Labels are how downstream consumers filter for the new dashboards.

## Round-trip an existing Omni dashboard (for reference)

When you want to see what shape the import API expects, download a working dashboard:

```bash
omni dashboards download <dashboard-id>
```

Returns the JSON definition. Use it as a template for the migrated payload.

## Schedules (Step 14, post-merge)

```bash
omni schedules list --compact
omni schedules create  --body '{...}'
omni schedules pause   <schedule-id>
omni schedules resume  <schedule-id>
omni schedules trigger <schedule-id>
```

If the Tableau workbook had subscriptions or alert rules, recreate them as Omni schedules.

## Promotion (Step 14)

```bash
omni models merge-branch <branch-model-id>
```

Promotes the branch to main. The branch model still exists post-merge; you can delete it once you're confident:

```bash
omni models delete-branch <branch-model-id>
```

## Rollback

If something is wrong post-merge, branch from a prior version of the model:

```bash
omni models list <model-id>            # lists versions
omni models create-branch <model-id> --body '{"name":"rollback","startingPoint":"version:<prior-version-id>"}'
omni models merge-branch <new-branch-id>
```

This is why we never edit main directly.

## Useful patterns we lean on

- **Pipe to jq.** `--format json` plus `jq` is faster than scrolling human output. Default behavior is JSON when piped, human when on a TTY.
- **`--compact` for shell loops.** No indentation, cheaper to grep.
- **`--body -` for stdin.** Lets you build payloads in Python and pipe them in: `cat payload.json | omni unstable documents-import --body -`.
- **`omni ai search-omni-docs --body '{"query":"how do I..."}'`** is the fastest way to find the right verb when you forget.

## Unsupported (as of CLI 1.0.4)

- No first-party "list dashboard tiles" verb. Use the `documents-export` -> read JSON -> filter pattern.
- No bulk dashboard delete; loop with `omni documents delete <id>` per dashboard.
- No native Tableau-to-Omni conversion (this skill IS that).

## Critical undocumented behaviors (we hit these the hard way)

### Workbook models always extend SHARED, never BRANCH

`unstable documents-import` creates a WORKBOOK model with `baseModelId` = SHARED. Setting `workbookModel.base_model_id` = BRANCH in the payload is silently overridden. The API rejects BRANCH at the top-level `baseModelId`.

**Implication**: an imported dashboard cannot inherently see view/topic additions that exist only on a branch. The dashboard's queries fail with "Could not convert to OmniQuery" (HTTP 500 in the UI).

**The fix that actually works**: write the same view + topic YAML to the WORKBOOK model after import, in addition to the branch:

```bash
WORKBOOK_ID="$(jq -r .workbook.id import_resp.json)"
omni models yaml-create $WORKBOOK_ID --body '{"fileName":"PUBLIC/foo.view","yaml":"..."}'
omni models yaml-create $WORKBOOK_ID --body '{"fileName":"foo.topic","yaml":"..."}'
omni models validate $WORKBOOK_ID
```

This makes the workbook self-contained: it carries its own copy of the view + topic, so queries resolve without depending on the branch. The branch still holds the canonical version that merges into SHARED later.

The `scripts/seed_workbook.py` helper in this skill automates the post-import seeding.

### What `?branch=<name>` does NOT do

The Omni docs describe a `?branch=<name>` URL parameter for "switching branches via URL." Important to know what this actually does:

- It **does** switch the IDE's editing context to a branch. Useful when humans are editing.
- It **does not** rewrite the hardcoded query `modelId` baked into a saved dashboard's tiles.

So for a dashboard imported via `unstable documents-import`, opening it with `?branch=<name>` does NOT make queries resolve through the branch. The query's modelId still points to the workbook model, which extends SHARED, which doesn't have the topic. Same 500.

The URL parameter is useful for editing-time experimentation in the IDE, NOT for production query resolution after import.

**The right test-before-merge loop is**:

1. Create branch + add YAML to branch (Step 8-9).
2. Import dashboard against SHARED (Step 10).
3. **Seed the same YAML to the workbook model the import creates** (Step 10.5).
4. Open the bare dashboard URL. Render verified.
5. Iterate the YAML by editing on both branch and workbook simultaneously.
6. Once verified, merge the branch into SHARED. Workbook can then be cleaned up (it has duplicate YAML); easiest path is to leave it; merge promotes the canonical via the branch.

### `documents-import` payload schema gotchas

- Top-level `baseModelId` is required and not present in `documents-export` output (added at import time).
- `document.ephemeral` is a comma-separated string mapping layout tile IDs to qpcM miniUuids: `"1:abc12345,2:def67890,..."`. Required for the import to succeed, even though it's an internal cross-reference.
- `metadataVersion: 2` and `exportVersion: "0.1"` (string, not number).
- `workbookModel.base_model_id` is silently overridden by the top-level `baseModelId` at import time.

### `documents get` returns a different shape than `documents-export`

- `get` returns a PUT-compatible shape (`modelId`, `queryPresentations`, `filterConfig`, etc.).
- `documents-export` returns the import-compatible shape (`document`, `dashboard`, `workbookModel`, etc.).
- These two shapes are not interchangeable.

### `content list` only returns SHARED-scoped content

Branch-scoped documents don't appear in `omni content list`. Use `omni documents list` instead, which returns all documents regardless of model scope.

### `connections list` doesn't accept `--pagesize` or `--modelkind`-style filters

Each list-style verb has different supported flags. Always check `omni <verb> --help` before scripting.

### `queryJson` must include `join_paths_from_topic_name` for the dashboard load path

Saved dashboard queries omit this field at your peril. The runtime `omni query run` API succeeds without it (Omni infers the topic from the view name). But:

```
omni documents get <id>            -> 500 "Could not convert to OmniQuery"
omni unstable documents-export <id> -> 500 same
UI dashboard render                 -> 500 same
```

The error response body returns the failing queryJson, which makes this trap easy to spot: look for the queryJson missing `join_paths_from_topic_name` in the `detail` string.

The build_payload script in this skill writes `join_paths_from_topic_name: <topic-name>` and `topicName: <topic-name>` (at the queryPresentation level) on every tile. If you author a payload by hand, do not omit either.

Match the queryJson key set of a known-working Omni dashboard. The verified-working set:

```
limit, sorts, table, fields, pivots, dbtMode, filters, modelId, version,
metadata, rewriteSql, row_totals, fill_fields, calculations, column_limit,
join_via_map, column_totals, userEditedSQL, dimensionIndex,
default_group_by, custom_summary_types, join_paths_from_topic_name
```

Fields some Omni surfaces produce (`controls`, `manualSort`, `context_metadata`, `query_references`) are NOT part of the dashboard-load schema and including them on saved queries breaks the import-then-render path.

### Views in schema-named subdirectories register with a schema prefix

Posting `omni models yaml-create <workbook> --body '{"fileName":"<SCHEMA>/<view>.view", ...}'` registers the view as `<schema>__<view>` (lowercased). Example: `ACME_EVENTS/vw_events_wide.view` shows up in `omni models get-views` as `acme_events__vw_events_wide`.

This silently breaks dashboards whose saved queries reference the un-prefixed `<view>`. The topic's `base_view: <view>` resolves to nothing.

The workaround: post the YAML body at the root path `<view>.view`. The body's own `schema:` field (e.g. `schema: ACME_EVENTS`) tells Omni where to file it internally, but the registered view NAME stays un-prefixed.

If the prefixed copy already exists from an earlier seed attempt, delete it first:

```bash
omni models yaml-delete <workbook-id> --filename ACME_EVENTS/vw_events_wide.view
omni models yaml-create <workbook-id> --body '{"fileName":"vw_events_wide.view","yaml":"..."}'
```

Verify with:

```bash
omni models get-views <workbook-id> --format json | jq '.views[].name'
```

You want to see `vw_events_wide`, not `acme_events__vw_events_wide`.

`scripts/seed_workbook.py` automates this dance.
