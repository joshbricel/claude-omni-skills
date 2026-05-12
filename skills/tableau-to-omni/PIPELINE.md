# Tableau-to-Omni pipeline

Componentized data flow from a `.twbx` file to a live Omni dashboard. Every stage is one script, with documented inputs and outputs. Failures localize: if a stage breaks, only that stage's smoke test fails, and the script can be re-run in isolation against fixtures.

## Stages

```
┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────┐   ┌───────────┐
│  PARSE   │ → │   MAP    │ → │   BUILD      │ → │  DEPLOY  │ → │  VERIFY   │
└──────────┘   └──────────┘   └──────────────┘   └──────────┘   └───────────┘
  extract.py     apply_rules    build_payload     omni_deploy    score_fidelity
  read_hyper     generate_tile  build_dashboards  seed_workbook  diff_twbx
                 score_fidelity                   create_dash    export_and_
                                                                 compare_pdfs
```

The four new components shipped 2026-05-11 (`apply_rules`, `generate_tile_spec`, `score_fidelity`, `regenerate_rules_md`) sit between extraction and payload building, automating the previously-manual tile-spec authoring step.

## Stage 1: PARSE

Turns the binary `.twbx` into a structured IR (intermediate representation) of JSON files.

| Script | Input | Output | Standalone-runnable? |
|---|---|---|---|
| `extract.py` | `path/to/workbook.twbx` | 13 JSON files in `--out` dir: `inventory.json`, `datasources.json`, `calcs.json`, `parameters.json`, `parameter_deps.json`, `worksheets.json`, `dashboards.json`, `actions.json`, `styles.json`, `palettes.json`, `hidden_sheets.json`, `annotations.json`, `raw_columns.json` | Yes. No network. |
| `read_hyper.py` | `path/to/extract.hyper` | CSV rows or schema dump | Yes. Requires `tableauhyperapi`. |
| `diff_twbx.py` | two `.twbx` files | diff report | Yes. No network. |

**Test in isolation:**
```bash
python3 scripts/extract.py path/to/sample.twbx --out /tmp/ir-out
ls /tmp/ir-out/   # should contain 13 .json files
```

**Common failure modes:**
- Malformed `.twbx`: not a valid zip. Smoke test catches via `test_no_args_fails_cleanly`.
- New Tableau XML version with elements `extract.py` does not parse: missing fields appear as empty arrays in the IR. Inspect `inventory.json` first.

## Stage 2: MAP

Applies the 129-rule mapping (with user guardrails) to the IR, emits decisions, generates a downstream-consumable tile-spec, and scores fidelity. The four scripts here form a self-contained subsystem.

| Script | Input | Output | Standalone-runnable? |
|---|---|---|---|
| `apply_rules.py` | `--ir-dir` (PARSE output), `--rules-yaml` (`context/mapping-rules.yaml`), optional `--guardrails-yaml` | `decisions.json` | Yes. Pure JSON-in, JSON-out. |
| `generate_tile_spec.py` | `--decisions decisions.json`, `--ir-dir` | `tile-spec.yaml` + `migration-report.md` | Yes. |
| `score_fidelity.py` | `--decisions decisions.json` | `parity-report.md` + optional `--json-out scores.json` | Yes. |
| `regenerate_rules_md.py` | `--yaml context/mapping-rules.yaml` | Human-readable rules markdown | Yes. One-way render: YAML is the machine truth. |

**Test in isolation** (no PARSE output required):
```bash
# 1. Synthesize a tiny IR by hand:
mkdir /tmp/fixture-ir
echo '[{"name":"x","is_lod":false,"lod_kind":null,"is_table_calc":false,"formula":"SUM([Sales])","datatype":"real","datasource":"o","caption":"","depends_on":[],"parameter_refs":[]}]' > /tmp/fixture-ir/calcs.json
for n in worksheets dashboards actions parameters palettes styles datasources; do echo '[]' > /tmp/fixture-ir/$n.json; done

# 2. Run the rules engine:
python3 scripts/apply_rules.py --ir-dir /tmp/fixture-ir --rules-yaml context/mapping-rules.yaml --out /tmp/decisions.json --allow-unmatched

# 3. Score it:
python3 scripts/score_fidelity.py --decisions /tmp/decisions.json --report /tmp/parity-report.md
```

**Common failure modes:**
- `apply_rules.py` exit 1 with unmatched concepts: a Tableau construct in the IR did not match any rule's predicate. Add `--allow-unmatched` for now; long-term, extend the matcher table in `apply_rules.py` (search `MATCHERS = `).
- `score_fidelity.py` exit 2: workbook score is below the `fidelity_threshold_for_rejection` guardrail. Inspect the per-family table; the worst family is named in stderr.
- Rules YAML schema drift: if a sibling script's output stops matching the YAML schema, the smoke test `test_regenerate_rules_md_renders_yaml_to_markdown` will fail.

## Stage 3: BUILD

Turns the tile-spec into an Omni `documents-import` JSON payload.

| Script | Input | Output | Standalone-runnable? |
|---|---|---|---|
| `build_payload.py` | `--tile-spec`, `--template` (working Omni export), model/connection IDs | Import payload JSON | Yes (no network). Requires a known-good template. |
| `build_dashboards.py` | `--spec` (multi-dashboard YAML, e.g. `templates/acme-events-spec.yaml`), model/connection IDs | Multiple import payloads | Yes with `--dry-run`. |

**Test in isolation:**
```bash
python3 scripts/build_dashboards.py --spec templates/acme-events-spec.yaml --dry-run --connection-id stub --shared-model-id stub --branch-id stub
```

**Common failure modes:**
- Template structural drift: if Omni changes the unstable import API's payload shape, the template stops being a valid skeleton. Re-export a working dashboard and replace the template.
- Tile-spec extension keys leaking into payload: `generate_tile_spec.py` emits superset dicts with `provenance`, `review_queue`, etc. that `build_payload.py` should ignore. If they leak, filter at the BUILD boundary.

## Stage 4: DEPLOY

Pushes the payload to Omni, then seeds the workbook to work around the SHARED-model-extends behavior.

| Script | Input | Output | Standalone-runnable? |
|---|---|---|---|
| `omni_deploy.py` | subcommand (`branch`, `import`, `validate`, `merge`, `delete-branch`, `list-targets`) | Side effects on Omni | No (requires `omni` CLI + API key). |
| `seed_workbook.py` | `--workbook-id`, `--yaml-dir` | Side effects on Omni | No (requires API key). |
| `create_dashboard.py` | `--payload`, IDs | Side effects on Omni (HTTP variant of import) | No (requires API key). |

**Test in isolation:**
Each script has `--help` smoke tests. Real integration requires:
```bash
export OMNI_API_KEY=...
export OMNI_BASE_URL=https://yourcompany.omniapp.co
python3 scripts/omni_deploy.py list-targets    # cheapest smoke test against live Omni
```

**Common failure modes:**
- 500 "Could not convert to OmniQuery" after import: the `seed_workbook.py` step did not run, or the view name was registered with a `<schema>__<view>` prefix. See section 11.1 of `context/omni-cli-format-spec.md`.
- 401: bad API key. `omni config show` to verify.
- 404 on import: model ID is wrong. `omni_deploy.py list-targets` to get the right ID.

## Stage 5: VERIFY

Confirms the migrated dashboard matches the Tableau original.

| Script | Input | Output | Standalone-runnable? |
|---|---|---|---|
| `score_fidelity.py` | decisions.json | parity-report.md | Yes (already used in MAP stage, runs again here for post-deploy validation). |
| `export_and_compare_pdfs.py` | `--identifiers` (Omni doc IDs), Tableau export | PDF-by-PDF visual diff | Yes (requires API key for export step). |

## How a single stage failure surfaces

The smoke test file `scripts/tests/test_pipeline_smoke.py` parametrizes over every script in the pipeline. Each script gets:

1. A `test_help_works[script]` case that verifies the CLI is callable.
2. A `test_no_args_fails_cleanly[script]` case that verifies no uncaught Python tracebacks.

Plus three end-to-end smoke tests that exercise the MAP stage from synthetic inputs:

3. `test_regenerate_rules_md_renders_yaml_to_markdown` (YAML → markdown round-trip)
4. `test_apply_rules_runs_against_fixture_ir` (engine consumes IR + YAML)
5. `test_score_fidelity_runs_against_synthetic_decisions` (scorer consumes decisions)

If a stage breaks, only its row in the parametrized output fails. Run with:

```bash
python3 -m pytest scripts/tests/ -v
```

For a single stage:

```bash
python3 -m pytest scripts/tests/test_pipeline_smoke.py -v -k extract
python3 -m pytest scripts/tests/test_pipeline_smoke.py -v -k apply_rules
```

## Component boundaries (contract reference)

Every component reads structured input and writes structured output. No component imports another component's Python module. The boundaries are JSON / YAML files on disk.

```
.twbx
  │  binary archive
  ▼
[extract.py]
  │  13 JSON files (the IR)
  ▼
[apply_rules.py]  ←──  context/mapping-rules.yaml  ←──  context/tableau-omni-mapping-rules.md
  │  decisions.json                                       (human edits the YAML at top;
  ▼                                                       regenerate_rules_md.py re-renders)
[generate_tile_spec.py]    [score_fidelity.py]
  │  tile-spec.yaml         │  parity-report.md
  ▼                         │
[build_payload.py]          │  (halts pipeline if score < threshold)
  │  import-payload.json
  ▼
[omni_deploy.py import] → Omni API
  │  workbook UUID
  ▼
[seed_workbook.py] → Omni API
  │
  ▼
[export_and_compare_pdfs.py] → parity verification
```

Every arrow is a file. To debug, replace the upstream file with a hand-built fixture and run the downstream script in isolation.

## Test suite summary

- 22 unit tests (one per component's internal logic, lives in `test_apply_rules.py`, `test_generate_tile_spec.py`, `test_score_fidelity.py`)
- 29 smoke tests (cross-component CLI sanity + minimal end-to-end fixture runs, lives in `test_pipeline_smoke.py`)
- 51 total tests, all passing as of 2026-05-11

Run all: `python3 -m pytest scripts/tests/ -q`
