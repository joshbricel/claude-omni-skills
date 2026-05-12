---
name: tableau-to-omni
description: >-
  Migrate a Tableau workbook (.twbx) to Omni: unpack the file, mine the XML for
  every calc / parameter / dashboard zone / action / style, then rebuild as an
  Omni dashboard via the official `omni` CLI.  Outputs a structured extraction
  bundle, an Omni import payload, and a parity report.
  TRIGGER when: "migrate this Tableau dashboard to Omni", "convert this .twbx",
  user provides a .twbx path, /tableau-to-omni invoked.
  SKIP for: building net-new Omni dashboards from scratch (use omni-vega-chart);
  branching the model alone (use omni-branch-creator); Looker / Power BI
  conversions (out of scope).
disable-model-invocation: false
user-invocable: true
argument-hint: "<path-to-twbx-file>"
---

# Tableau to Omni Migration

Migrate a Tableau workbook to Omni by mining the .twbx file for every piece of structure (data model, calc fields, parameters, layout, actions, styles, palettes, hidden sheets) and rebuilding the dashboard via the official `omni` CLI.

## Trigger

- "migrate this Tableau dashboard to Omni"
- "convert this .twbx to Omni"
- "lift and shift my Tableau workbook"
- `/tableau-to-omni path/to/dashboard.twbx`

## Scope

- IN scope: end-to-end migration of a single .twbx including XML mining, business rationalization, Omni branch + topic + dashboard build, parity validation, branch promotion.
- OUT of scope: net-new dashboards (use `omni-vega-chart`); branch creation alone (use `omni-branch-creator`); Looker / Power BI / Sigma migrations (different XML); semantic layer authoring from scratch (use `omni-semantic-layer-setup`); bulk Tableau Server crawls (planned follow-up skill).

## Prerequisites

| Requirement | Check |
|-------------|-------|
| `omni` CLI on PATH | `omni --version` (need 1.0.0+) |
| Authenticated profile | `omni config show` (or `omni config init`) |
| `OMNI_API_TOKEN` env var | `echo $OMNI_API_TOKEN` (alternate to profile) |
| Python 3.10+ | `python3 --version` |
| `requests` (already in stdlib for most) | `pip3 show requests` |
| `tableauhyperapi` (optional, for Hyper extracts) | `pip3 show tableauhyperapi` |
| `.twbx` file path | User provides as argument |
| Target Omni model ID | `python3 scripts/omni_deploy.py list-targets` |
| Target connection ID | Same command |

If the CLI is missing: `brew tap exploreomni/tap && brew install omni`.

## The migration is the rationalization

Most Tableau estates are bloated. Same metric calculated three ways across three dashboards. Owners who left two years ago. Dashboards built for questions nobody asks anymore. **Do not lift and shift garbage.**

Before any technical work, run the rationalization track in `context/migration-rationalization.md`. Outputs: a Keep / Consolidate / Retire / Rebuild scoring sheet, a definition reconciliation worksheet, and a published "won't migrate" list with reasons.

## Workflow

The migration runs in three tracks, interleaved.

### Track A: Discovery and rationalization

#### Step 1: Unpack and inventory

A `.twbx` is just a zip. Rename to `.zip` and extract, or run:

```bash
python3 scripts/extract.py "$ARGUMENTS" --out ./extract
```

This unpacks the workbook AND mines its XML into 12 JSON files (counts, datasources, raw columns, calcs, parameters, parameter dependencies, worksheets, dashboards, actions, styles, palettes, hidden sheets).

The script's stdout is a counts summary you read first to size the migration:

```json
{ "datasources": 38, "raw_columns": 132, "calc_fields": 24,
  "lod_calcs": 0, "table_calcs": 0, "parameters": 3, "worksheets": 20,
  "dashboards": 4, "actions": 14, "palettes": 0, "hidden_sheets": 20 }
```

Anything > 10 LOD calcs, > 5 hidden sheets, or > 50 actions is a yellow flag. Note them.

#### Step 2: Read the calc field list out loud

```bash
jq -r '.[] | "[\(.is_lod | if . then "LOD " else "    " end)\(.is_table_calc | if . then "TBL" else "   " end)] \(.caption): \(.formula | gsub("\n"; " "))"' extract/calcs.json
```

This dumps every calc field with its formula in a single column, with markers for LODs and table calcs (the two patterns Omni handles least cleanly). Walk the list with the business owner. Most calcs fall into:

- **Same-shape duplicates** (same formula under different names): consolidate.
- **Stale references**: dead calc fields nobody uses any more (cross-reference with worksheet field-refs in `worksheets.json`).
- **Genuinely complex**: LODs, FIXED at non-trivial grains, IIF chains. These need translation, not auto-conversion.

#### Step 3: Action graph

```bash
jq '[.[] | {name, type, source: .source_sheets, target: .target_sheets, fields: .field_mappings}]' extract/actions.json
```

Reveals interactivity flow. Filter actions translate cleanly to Omni dashboard filters. Set actions and parameter actions are Omni's weak spot. Document them as "manual rebuild" in the report.

#### Step 4: Parameter dependency map

```bash
cat extract/parameter_deps.json
```

Every parameter mapped to the calcs and sheets that reference it. If a parameter drives 0 calcs and 0 sheets, retire it. If it drives only one cosmetic toggle, simplify to a hardcoded value during migration.

#### Step 5: Hidden sheets audit

```bash
cat extract/hidden_sheets.json
```

Sheets used as tooltip vizzes or dashboard data sources but not visible on tabs. Often duplicate logic. The report should explicitly account for each one (kept, merged, retired).

#### Step 6: Score and decide scope

Open `context/migration-rationalization.md`. Walk through the scoring rubric. Produce a `cut_list.md` documenting:
- Dashboards to migrate (with new owner, new folder, new name if changed).
- Dashboards to retire (with reason).
- Calc fields to consolidate or rename.
- Parameters to remove.

Do not skip this step. The scope decision is what makes the migration worth doing.

### Track B: Technical build

#### Step 6.5: Pre-flight, audit existing Omni topics on the same fact

Before authoring a new topic, list the topics that already point at the underlying fact table the migration would target. The Omni model browser or `omni models yaml-get` is enough for this check.

Three outcomes drive the next step:

| Audit result | Migration action |
|--------------|------------------|
| 0 topics on the fact | Proceed: continue to Step 7 to create a new view + topic. |
| 1 topic on the fact | **Use it.** Skip topic creation in Step 9. Map Tableau worksheet fields onto the existing topic's field list. Document any Tableau calc that has no equivalent in `cut_list.md`. |
| 2+ topics (cluster found) | **STOP the migration.** Surface the duplication and triage before proceeding. Do not create yet another topic on the same fact. |

The third outcome is the load-bearing rule: **migration must fail loud on cluster detection**. Creating a duplicate is worse than not migrating.

#### Step 7: Discover Omni targets

```bash
python3 scripts/omni_deploy.py list-targets
```

Captures `connection_id` and `base_model_id` for the data source the migrated dashboard will live on. Save these to a local `.env` (do not check in).

If there is no matching Omni view for the Tableau data source, run the `omni-semantic-layer-setup` skill first to lay one down. The migration depends on the semantic layer existing.

#### Step 8: Create the migration branch

```bash
python3 scripts/omni_deploy.py branch \
  --base-model-id "$BASE_MODEL_ID" \
  --name "tableau-mig-$(date +%Y-%m-%d)"
```

This wraps `omni models create-branch`. The branch is the safe sandbox for the migration. Nothing lands on main until parity passes.

#### Step 9: Author the migration spec, build the import payloads

The production builder (`scripts/build_dashboards.py`) takes one YAML migration spec and emits one `documents-import` payload per dashboard. The spec grammar (full reference in `context/tile-spec-grammar.md`) covers all the chart types we encountered: KPI strips, vertical/horizontal bars (stacked or trellised), line, area, scatter (with trellis), dual-bar, gender callouts, markdown tiles.

```bash
python3 scripts/build_dashboards.py \
  --spec /path/to/migration-spec.yaml \
  --connection-id <conn> \
  --shared-model-id <shared> \
  --branch-id <branch> \
  --template /path/to/working_dashboard_export.json \
  --out-dir /tmp/payloads \
  --also-import \
  --seed-yaml-dir /path/to/migration_yaml \
  --ir-dir ./extract \
  --name-prefix ""
```

The `--template` is any working Omni dashboard's `documents-export` output, used as a structural skeleton (saves us hand-rolling the document/dashboard envelope). `templates/acme-events-spec.yaml` is the worked example from the demo migration: 4 dashboards, 17 tiles.

#### Dashboard names default to the Tableau workbook

`build_dashboards.py` and `build_payload.py` both auto-default the Omni document name to the **source Tableau dashboard name** when a spec entry omits `name:`. Precedence:

1. CLI `--dashboard-name` (build_payload only) or per-entry spec `name:` (build_dashboards): explicit override.
2. Per-entry spec `tableau_name:`: cross-reference into the IR by name.
3. `--ir-dir` `dashboards.json`: positional match (entry N in the spec uses dashboard N from the workbook).

Pass `--name-prefix "Migrated: "` if the target Omni workspace already has a same-named dashboard or you want a tag for filtering. Default prefix is empty: the Omni dashboard name is byte-identical to the Tableau dashboard name. The resolver fails loud (no silent fallback to slug) if none of the three sources resolves a name.

#### IR-driven defaults (omit fields to inherit from Tableau)

`build_dashboards.py` reads `--ir-dir` and fills in two things the spec author historically had to hand-author and routinely got wrong:

| Spec section | Omit to inherit from IR | What you get |
|--------------|-------------------------|--------------|
| `tiles[].layout` | leave out the whole `layout:` map | `zones_to_grid` maps the Tableau dashboard zone tree to a 24-col x 60-row Omni grid, preserving the source proportions. Tile is matched to a worksheet by `tableau_name:` (preferred) or `name:`. |
| `tiles[].color` | leave out `color:` entirely | Resolved from the worksheet's `encodings[shelf=color]` in `worksheets.json`. Tableau's "self-color" pattern (color shelf = row dimension) becomes an Omni `color` binding on the same dimension, restoring per-bar hues. To suppress, set `color: null` explicitly. |
| `dashboards[].filters[].type/kind/values/left_side/right_side` | give only `field:` | `dashboard_filters.json` (from `<shared-views>` and `<extract>` filters) is translated to the matching Omni filterConfig. Tableau `relative-date` becomes `TIME_FOR_INTERVAL_DURATION` with `left_side`/`right_side` derived from `first-period`/`last-period`/`period-type-v2`. Tableau `categorical` becomes `EQUALS` with the member list. |

Explicit spec values always win, so the override path is unchanged. If a tile's name doesn't match anything in the IR or a filter has no matching IR record, the auto-fill is a no-op (it doesn't manufacture defaults).

Authoring the spec is the human curation step. For each Tableau worksheet, decide:

| Tableau viz | Omni tile | Notes |
|-------------|-----------|-------|
| Bar chart | `basic` mark `bar` | Date on x, measure on y, `_dependentAxis: "y"` |
| Line chart | `basic` mark `line` | Same axis rule |
| Text table / KPI strip | `omni-spreadsheet` (`prefersChart: false`) | Visual fidelity is rough |
| Map | `basic` mark `geo_shape` | Limited; document gap |
| Dual-axis | Two stacked tiles | Omni doesn't natively do dual-axis |
| Tooltip viz | Drop or rebuild as separate tile | Omni tooltips are simpler |

Worksheet filters become dashboard-level `filterConfig` entries. Calc fields become Omni view fields (added in the branched model via `omni models create-field`).

Custom palettes from `extract/palettes.json` map to Omni dashboard themes if they fit; otherwise document and rebuild manually.

Layout: Tableau pixel-grid -> Omni 12-column grid. Walk the zone tree in `extract/dashboards.json`, group siblings, and emit Omni `gridConfig` blocks.

#### Step 10: Import the dashboard

```bash
python3 scripts/omni_deploy.py import --payload payload.json
```

Wraps `omni unstable documents-import`. Returns a document ID.

#### Step 10.5: Seed the workbook model with the migration YAML (REQUIRED)

The import API silently forces `workbook.baseModelId = SHARED` and ignores any branch reference in the payload. This means the imported dashboard's workbook model **does not see the view + topic that live on the branch**, so every query 500s with "Could not convert to OmniQuery" the moment the dashboard renders.

**Fix**: write the same view + topic YAML to the WORKBOOK model that the import created, in addition to the branch.

```bash
WORKBOOK_ID="$(jq -r .workbook.id import_resp.json)"

python3 scripts/seed_workbook.py \
  --workbook-id "$WORKBOOK_ID" \
  --yaml-dir /path/to/migration_yaml \
  --also-validate
```

The same `migration_yaml/` directory whose contents were pushed to the branch in Step 9 gets pushed to the workbook model here. The workbook becomes self-contained for query resolution.

Why this is required:
- Workbook models can only extend SHARED or SHARED_EXTENSION (the API rejects branches at top-level `baseModelId`).
- Workbook models hold the bound `modelId` referenced by every `queryJson` in the dashboard's tiles.
- Therefore the workbook MUST itself contain the topic, OR the topic must be on the SHARED model the workbook extends.
- Until merge, the workbook's only path to the topic is local (this step).

The `?branch=<name>` URL parameter that Omni's docs describe is for switching the IDE's editing context to a branch. It does NOT rewrite hardcoded query modelIds in saved dashboards. Do not rely on it for query resolution.

#### The two non-obvious traps inside Step 10.5

`seed_workbook.py` handles both of these for you. Documenting them here so the model keeps the knowledge if the script is ever rewritten.

**Trap 1: queryJson must include `join_paths_from_topic_name`.** A query body without it succeeds in `omni query run` (runtime infers the topic from the view), but fails in every document-load path (`documents get`, `documents-export`, UI dashboard render) with:

```
500: Could not convert to OmniQuery
```

Document-load uses a stricter conversion path that requires the topic binding to be explicit on each saved query. `build_payload.py` writes this for you on every tile. If you build a payload by hand, do not omit it.

**Trap 2: views in schema-named subdirectories register with a schema prefix.** Posting a view file to `<SCHEMA>/<view>.view` causes Omni to register the view as `<schema>__<view>` (lowercased). But the saved queries in the imported dashboard reference the un-prefixed `<view>`, and the topic's `base_view: <view>` doesn't resolve. Document-load 500s with the same conversion error.

The fix: post the view's YAML body at the **root** path `<view>.view`. The body's `schema:` field tells Omni where to file it internally (yaml-get still returns it at `<SCHEMA>/<view>.view`), but the registered view NAME is the un-prefixed form, which matches what the queries reference. If a prefixed copy was already created in a prior attempt, delete it first via `omni models yaml-delete --filename <SCHEMA>/<view>.view`.

After both traps are handled, the bare dashboard URL renders correctly. The `?branch=` URL is unnecessary.

#### Step 11: Validate

```bash
python3 scripts/omni_deploy.py validate --branch-id "$BRANCH_ID"
```

Wraps `omni models validate`. Catches missing fields, broken joins, malformed YAML. Iterate the payload until validate passes clean. Validate runs on the BRANCH (the source of truth that will eventually merge); the workbook is a copy seeded for runtime resolution.

### Track C: Verify and promote

#### Step 12: Parity checks

For each migrated worksheet, run the equivalent Omni query and diff against the Tableau extract.

```bash
omni query run --body '{"modelId":"<branch-model-id>","query":{...}}' --format json > omni_query.json
```

Compare row counts, totals, group-by spot checks, and calc field values. Per analysis standards: nulls, uniqueness, referential integrity, fan-outs, reconciliation, accepted values, freshness, edge cases, determinism. Use the same checklist as the repo's general analysis standards; the parity report has one row per check with pass/fail and the diff value.

If a metric is off by more than 0.5%, stop and find the root cause. Don't merge bad math.

#### Step 13: Rebrand dashboard metadata

Use the CLI to set the right name, folder, owner, and labels:

```bash
omni documents move <doc-id> --body '{"folderPath":"/Sales/Pipeline"}'
omni documents transfer-ownership <doc-id> --body '{"newOwnerId":"<user-id>"}'
omni documents add-label <doc-id> --body '{"name":"migrated-from-tableau"}'
```

#### Step 14: Promote

```bash
python3 scripts/omni_deploy.py merge --branch-id "$BRANCH_ID"
```

Wraps `omni models merge-branch`. Promotes the branch to main. Roll back via `omni models delete-branch` if anything goes sideways post-merge.

#### Step 15: Deprecation playbook

The Tableau workbook is still alive. Tag it as deprecated, set a sunset date, comms to consumers. The Change-Management section of `context/migration-rationalization.md` has the full T-30 / T-14 / T-7 / T-0 / T+30 / T+60 cadence.

## Output

In the working directory:

- `extract/` directory with all JSON files (inventory, calcs, parameters, layout, actions, etc.) and the unpacked `_unpacked/` tree.
- `cut_list.md`: rationalization decisions.
- `payload.json`: the Omni dashboard import payload.
- `parity_report.md`: per-worksheet parity check results.
- `migration_log.md`: step-by-step record of the CLI commands run.

In Omni:

- A model branch with the migrated topic / view changes.
- A dashboard imported via documents-import.
- Folder placement, ownership, labels, and schedules wired up via CLI.

## Error Handling

| Error | Fix |
|-------|-----|
| `.twbx` is not a valid zip | The file may be `.twb` (raw XML) without packaging. Wrap: `zip workbook.twbx workbook.twb` |
| No `.twb` found inside zip | Check the archive contents: `unzip -l workbook.twbx`. Some workbooks use nested directories. |
| `omni` CLI not found | `brew tap exploreomni/tap && brew install omni` |
| Auth error on CLI | `omni config init` and paste a fresh API token, or set `OMNI_API_TOKEN` env var |
| Model not found | Verify with `omni models list --compact`. Token may not have access. |
| Import API returns 400 | Check `exportVersion: "0.1"` (string, not number). Required fields: `baseModelId`, `dashboard`, `document`, `workbookModel`. |
| Charts render flipped (horizontal) | Date dimension is on `y` instead of `x`. Fix: date -> `x.field`, measure -> `y.field`, `_dependentAxis: "y"`. |
| Validate fails on missing field | The payload references a calc field not yet in the branch. Add it via `omni models create-field` first. |
| LOD calc has no Omni equivalent | Most LODs translate to subqueries in Omni topic SQL. Document the translation in `cut_list.md`. |
| Parameter action has no Omni equivalent | Rebuild as a dashboard filter or topic-level template parameter. Document the gap. |

## Checklist

- [ ] `extract.py` ran clean and inventory counts look reasonable
- [ ] Calc field list reviewed with business owner; LODs and table calcs flagged
- [ ] Action graph documented; non-translatable actions called out
- [ ] Parameter dependency map reviewed; dead parameters retired
- [ ] Hidden sheets audited; each one accounted for in the cut list
- [ ] `cut_list.md` published; "won't migrate" list named with reasons
- [ ] Omni connection_id and base_model_id captured
- [ ] Migration branch created via CLI
- [ ] Import payload built and validates clean
- [ ] Per-worksheet parity check passes within tolerance
- [ ] Dashboard moved to correct folder, owner, labels set
- [ ] Branch merged to main
- [ ] Tableau workbook tagged deprecated with sunset date

## Reference Files

| File | Description |
|------|-------------|
| `context/tableau-xml-anatomy.md` | TWB XML structure: every element, attribute, and what it represents. |
| `context/extraction-techniques.md` | Creative TWBX mining tricks: image extraction, palette ripping, action graphs, hidden sheet hunting, two-version diffing. |
| `context/omni-cli-cheatsheet.md` | The `omni` CLI verbs we use, organized by migration phase. |
| `context/omni-api-patterns.md` | Dashboard import payload schema, visConfig patterns, queryJson format, known limitations. |
| `context/migration-rationalization.md` | Business-track rubric: Keep / Consolidate / Retire / Rebuild scoring, definition reconciliation, governance plan. |

## Related Skills

- `omni-branch-creator`: Create a branch directly (used in Step 8 if you skip the wrapper).
- `omni-semantic-layer-setup`: Build the semantic layer if no matching view exists yet (Step 7).
- `omni-vega-chart`: Author Omni charts from natural language (useful for rebuilding charts the auto-translator skips).
