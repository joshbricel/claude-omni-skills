"""Smoke tests for the merged Tableau-to-Omni pipeline.

These tests validate that every script in the pipeline:
1. Exposes a working --help (CLI is callable).
2. Fails clean on missing required args (no Python tracebacks).
3. Where it makes sense, runs against a tiny fixture without external dependencies.

These are NOT integration tests. They do not call the Omni API, do not
read live Tableau files, do not require Snowflake credentials. They exist
to localize failures: if a stage is broken, you find out by running this
file, not by running the full pipeline against a real TWBX.

Each test maps to one pipeline stage. If a stage's smoke test fails, that
stage is the one to investigate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parent.parent


SCRIPTS = [
    # parser stage
    "extract.py",
    "read_hyper.py",
    "diff_twbx.py",
    # mapping stage (the four new components)
    "apply_rules.py",
    "generate_tile_spec.py",
    "score_fidelity.py",
    "regenerate_rules_md.py",
    # builder + deployment stage
    "build_payload.py",
    "build_dashboards.py",
    "seed_workbook.py",
    "omni_deploy.py",
    "create_dashboard.py",
    # validation stage
    "export_and_compare_pdfs.py",
]


def _run(script: str, args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    """Run a script with given args. Captures stdout+stderr, never raises."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_help_works(script: str) -> None:
    """Every script must respond to --help with exit code 0 and a usage line."""
    result = _run(script, ["--help"])
    assert result.returncode == 0, f"{script} --help exited {result.returncode}: {result.stderr}"
    assert "usage:" in result.stdout.lower() or "usage:" in result.stderr.lower(), (
        f"{script} --help did not print a usage line"
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_no_args_fails_cleanly(script: str) -> None:
    """Running a script with no args should fail with argparse error, not a Python traceback.

    Scripts with no required args (omni_deploy.py has subcommands) are allowed to exit 0
    or with a subcommand-level error, but must not throw an uncaught exception.
    """
    result = _run(script, [])
    combined = result.stdout + result.stderr
    # Argparse errors print "the following arguments are required" or "error:".
    # An uncaught traceback contains "Traceback (most recent call last):".
    assert "Traceback (most recent call last):" not in combined, (
        f"{script} threw an uncaught traceback when run with no args:\n{combined}"
    )


def test_regenerate_rules_md_renders_yaml_to_markdown(tmp_path: Path) -> None:
    """The YAML sidecar must round-trip to readable markdown.

    This guards the contract between mapping-rules.yaml and the human-readable doc.
    If this breaks, the YAML schema drifted from what the renderer expects.
    """
    yaml_path = SCRIPTS_DIR.parent / "context" / "mapping-rules.yaml"
    if not yaml_path.exists():
        pytest.skip("mapping-rules.yaml not present in context/")
    out_path = tmp_path / "rendered.md"
    result = _run("regenerate_rules_md.py", ["--yaml", str(yaml_path), "--out", str(out_path)])
    assert result.returncode == 0, f"render failed: {result.stderr}"
    assert out_path.exists(), "renderer claimed success but produced no file"
    body = out_path.read_text()
    assert "# " in body, "rendered markdown has no headings"
    assert "R-CALC" in body, "rendered markdown is missing rule families"


def test_apply_rules_runs_against_fixture_ir(tmp_path: Path) -> None:
    """End-to-end smoke: apply_rules.py against a hand-built minimal IR.

    This proves the rules engine can be exercised without extract.py output.
    If this fails, the rules engine cannot read the YAML sidecar, full stop.
    """
    import json

    yaml_path = SCRIPTS_DIR.parent / "context" / "mapping-rules.yaml"
    if not yaml_path.exists():
        pytest.skip("mapping-rules.yaml not present in context/")

    ir_dir = tmp_path / "ir"
    ir_dir.mkdir()
    # Minimum IR: one trivial calc, no LOD, no table calc.
    (ir_dir / "calcs.json").write_text(json.dumps([{
        "name": "total_sales",
        "caption": "Total Sales",
        "datasource": "orders",
        "formula": "SUM([Sales])",
        "datatype": "real",
        "is_lod": False,
        "lod_kind": None,
        "is_table_calc": False,
        "depends_on": [],
        "parameter_refs": [],
    }]))
    # Empty stubs for the other expected IR files (rules engine should not crash).
    for name in ("worksheets", "dashboards", "actions", "parameters",
                 "palettes", "styles", "datasources"):
        (ir_dir / f"{name}.json").write_text("[]")

    out = tmp_path / "decisions.json"
    result = _run("apply_rules.py", [
        "--ir-dir", str(ir_dir),
        "--rules-yaml", str(yaml_path),
        "--out", str(out),
        "--allow-unmatched",
    ])
    assert result.returncode == 0, f"apply_rules failed: {result.stderr}"
    assert out.exists()
    payload = json.loads(out.read_text())
    assert payload["version"] == "1.0"
    assert "decisions" in payload
    assert "summary" in payload


def test_score_fidelity_runs_against_synthetic_decisions(tmp_path: Path) -> None:
    """End-to-end smoke: score_fidelity.py with a hand-built decisions.json.

    No dependency on apply_rules.py running first. Proves the scorer's
    contract on decisions.json is met.
    """
    import json

    decisions = {
        "version": "1.0",
        "generated_at": "2026-05-11T00:00:00Z",
        "source_ir_dir": "n/a",
        "rules_yaml_sha": "deadbeef",
        "guardrails_effective": {"fidelity_threshold_for_rejection": 0.6},
        "guardrail_overrides_applied": [],
        "decisions": [
            {
                "instance_id": "calcs[0]",
                "tableau_input": {"concept_kind": "calculated_field", "name": "x"},
                "rule_id": "R-CALC-01",
                "rule_name": "Basic arithmetic",
                "bucket": "GREEN",
                "strategy_effective": "model_layer_measure",
                "needs_review": False,
                "omitted": False,
                "warnings": [],
                "notes": "",
            }
        ],
        "summary": {"total_instances": 1, "by_bucket": {"GREEN": 1},
                    "by_family": {"R-CALC": 1}, "needs_review_count": 0,
                    "omitted_count": 0, "no_rule_matched_count": 0},
        "unmatched": [],
    }
    dec_path = tmp_path / "decisions.json"
    dec_path.write_text(json.dumps(decisions))
    report = tmp_path / "report.md"
    result = _run("score_fidelity.py", [
        "--decisions", str(dec_path),
        "--report", str(report),
    ])
    assert result.returncode == 0, f"score_fidelity failed: {result.stderr}"
    assert report.exists()
    body = report.read_text()
    assert "score:" in body or "Score" in body
