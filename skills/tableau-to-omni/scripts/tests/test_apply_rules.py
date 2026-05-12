"""Tests for the apply_rules rules engine.

The fixtures are generated programmatically in a tmp_path-based fixture so they
live in code, not on disk. The mapping-rules YAML sidecar prefers the real
sibling-agent output if it exists, and falls back to ``fixtures/mapping-rules-fallback.yaml``
otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = SCRIPTS_DIR.parent
FALLBACK_RULES = SCRIPTS_DIR / "tests" / "fixtures" / "mapping-rules-fallback.yaml"
REAL_RULES = SKILL_DIR / "context" / "mapping-rules.yaml"

# Import the module under test directly so we can call functions without a subprocess.
sys.path.insert(0, str(SCRIPTS_DIR))
import apply_rules  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rules_yaml_path() -> Path:
    """Prefer the real sidecar; fall back to the fixture if not yet produced.

    Tests parameterize their assertions against whichever sidecar is in use so
    they pass under both. ``_load_rules`` exposes the active YAML data so a test
    can read the actual strategy for a rule rather than hardcode it.
    """
    if REAL_RULES.exists():
        try:
            data = yaml.safe_load(REAL_RULES.read_bytes()) or {}
            rule_ids = {r.get("id") for r in (data.get("rules") or [])}
            # Sanity check that the real sidecar covers the rules our tests assert on.
            required = {
                "R-CALC-04", "R-CALC-05", "R-CALC-07",
                "R-VIZ-11", "R-DASH-02", "R-ACTION-06",
            }
            if required.issubset(rule_ids):
                return REAL_RULES
        except Exception:
            pass
    return FALLBACK_RULES


def _load_rules(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_bytes()) or {}


def _rule_strategy(rules: Dict[str, Any], rule_id: str) -> str:
    for r in rules.get("rules", []) or []:
        if r.get("id") == rule_id:
            return ((r.get("default_mapping") or {}).get("strategy")) or ""
    return ""


def _rule_bucket(rules: Dict[str, Any], rule_id: str) -> str:
    for r in rules.get("rules", []) or []:
        if r.get("id") == rule_id:
            return r.get("bucket") or ""
    return ""


def _rule_has_alt(rules: Dict[str, Any], rule_id: str, guardrail: str) -> bool:
    for r in rules.get("rules", []) or []:
        if r.get("id") == rule_id:
            alt = ((r.get("default_mapping") or {}).get("alt_strategies")) or {}
            return guardrail in alt
    return False


@pytest.fixture
def ir_dir(tmp_path: Path) -> Path:
    """Synthesize a tiny IR directory with one to two instances per concept family."""
    d = tmp_path / "ir"
    d.mkdir()

    calcs = [
        {  # R-CALC-04 FIXED LOD
            "name": "sales_by_region",
            "caption": "Sales by Region",
            "datasource": "orders_ds",
            "formula": "{FIXED [Region] : SUM([Sales])}",
            "datatype": "real",
            "is_lod": True,
            "lod_kind": "FIXED",
            "is_table_calc": False,
            "depends_on": ["Region", "Sales"],
            "parameter_refs": [],
        },
        {  # R-CALC-05 INCLUDE LOD
            "name": "avg_per_customer",
            "caption": "Avg per Customer",
            "datasource": "orders_ds",
            "formula": "{INCLUDE [Customer] : AVG([Sales])}",
            "datatype": "real",
            "is_lod": True,
            "lod_kind": "INCLUDE",
            "is_table_calc": False,
            "depends_on": ["Customer", "Sales"],
            "parameter_refs": [],
        },
        {  # R-CALC-10 RUNNING_SUM table calc
            "name": "running_sales",
            "caption": "Running Sales",
            "datasource": "orders_ds",
            "formula": "RUNNING_SUM(SUM([Sales]))",
            "datatype": "real",
            "is_lod": False,
            "lod_kind": None,
            "is_table_calc": True,
            "depends_on": ["Sales"],
            "parameter_refs": [],
        },
        {  # Unknown function -> falls to default calc rule
            "name": "weird_calc",
            "caption": "Weird Calc",
            "datasource": "orders_ds",
            "formula": "FOO([Sales])",
            "datatype": "real",
            "is_lod": False,
            "lod_kind": None,
            "is_table_calc": False,
            "depends_on": ["Sales"],
            "parameter_refs": [],
        },
    ]
    (d / "calcs.json").write_text(json.dumps(calcs))

    worksheets = [
        {  # R-VIZ-08 dual-axis
            "name": "Profit vs Sales",
            "datasource_refs": ["orders_ds"],
            "marks": {"type": "line", "encodings": {"rows": ["Profit", "Sales"], "columns": ["OrderDate"]}},
            "filters": [
                {"field": "Region", "kind": "categorical", "values": ["West"]},
            ],
            "axes": [],
            "dual_axis": True,
            "trellis": {"row_pills": [], "col_pills": []},
            "sort": [],
            "reference_lines": [],
            "style_refs": [],
        },
        {  # plain worksheet
            "name": "Sales by Region",
            "datasource_refs": ["orders_ds"],
            "marks": {"type": "bar", "encodings": {"rows": ["Region"], "columns": ["Sales"]}},
            "filters": [],
            "axes": [],
            "dual_axis": False,
            "trellis": {"row_pills": [], "col_pills": []},
            "sort": [],
            "reference_lines": [],
            "style_refs": [],
        },
    ]
    (d / "worksheets.json").write_text(json.dumps(worksheets))

    dashboards = [
        {
            "name": "Main",
            "size": {"kind": "fixed", "w": 1200, "h": 800},
            "zones": [
                {  # R-DASH-02 worksheet zone
                    "kind": "worksheet",
                    "name": "Sales by Region tile",
                    "x": 0, "y": 0, "w": 600, "h": 400,
                    "floating": False,
                    "container_kind": None,
                    "children": [],
                },
                {  # R-DASH-04 floating zone
                    "kind": "worksheet",
                    "name": "Floating callout",
                    "x": 100, "y": 100, "w": 300, "h": 200,
                    "floating": True,
                    "container_kind": None,
                    "children": [],
                },
            ],
            "filters": [],
        },
    ]
    (d / "dashboards.json").write_text(json.dumps(dashboards))

    actions = [
        {"name": "Filter Region", "kind": "filter", "source": "Main", "target": "Detail"},
        {"name": "Highlight Top", "kind": "set", "source": "Main", "target": "Detail"},
    ]
    (d / "actions.json").write_text(json.dumps(actions))

    parameters = [
        {
            "name": "Region Param",
            "domain_kind": "list",
            "datatype": "string",
            "current_value": "West",
            "allowable_values": ["West", "East", "Central"],
        },
    ]
    (d / "parameters.json").write_text(json.dumps(parameters))

    palettes = [
        {"name": "Demo Categorical", "kind": "categorical", "colors": ["#FF5500", "#00AAFF"]},
    ]
    (d / "palettes.json").write_text(json.dumps(palettes))

    styles = [
        {
            "worksheet": "Sales by Region",
            "format_strings": {"Sales": "$#,##0"},
            "fonts": {},
            "conditional_format_rules": [],
        },
    ]
    (d / "styles.json").write_text(json.dumps(styles))

    datasources = [
        {
            "name": "orders_ds",
            "caption": "Orders",
            "connection": {"class": "snowflake", "server": "acct", "db": "DEMO", "schema": "PUBLIC", "table": "ORDERS"},
            "relations": [],
            "columns": [],
        },
    ]
    (d / "datasources.json").write_text(json.dumps(datasources))

    return d


def _run_cli(ir_dir: Path, rules_yaml: Path, tmp_path: Path, extra: List[str] = None) -> Dict[str, Any]:
    """Invoke apply_rules.py as a subprocess and return parsed decisions.json + exit code."""
    out = tmp_path / "decisions.json"
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "apply_rules.py"),
        "--ir-dir", str(ir_dir),
        "--rules-yaml", str(rules_yaml),
        "--out", str(out),
    ]
    if extra:
        cmd.extend(extra)
    res = subprocess.run(cmd, capture_output=True, text=True)
    payload = json.loads(out.read_text()) if out.exists() else {}
    payload["__exit_code__"] = res.returncode
    payload["__stderr__"] = res.stderr
    return payload


def _decision_by_id(decisions: List[Dict[str, Any]], instance_id: str) -> Dict[str, Any]:
    for d in decisions:
        if d["instance_id"] == instance_id:
            return d
    raise AssertionError(f"no decision with instance_id={instance_id}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fixed_lod_matches_r_calc_04(ir_dir: Path, rules_yaml_path: Path, tmp_path: Path):
    rules = _load_rules(rules_yaml_path)
    expected_strategy = _rule_strategy(rules, "R-CALC-04")
    expected_bucket = _rule_bucket(rules, "R-CALC-04")
    res = _run_cli(ir_dir, rules_yaml_path, tmp_path, extra=["--allow-unmatched"])
    d = _decision_by_id(res["decisions"], "calcs[0]")
    assert d["rule_id"] == "R-CALC-04"
    assert d["strategy_default"] == expected_strategy
    assert d["strategy_effective"] == expected_strategy
    assert d["bucket"] == expected_bucket
    assert d["needs_review"] is True


def test_include_lod_maps_to_r_calc_05(ir_dir: Path, rules_yaml_path: Path, tmp_path: Path):
    res = _run_cli(ir_dir, rules_yaml_path, tmp_path, extra=["--allow-unmatched"])
    d = _decision_by_id(res["decisions"], "calcs[1]")
    assert d["rule_id"] == "R-CALC-05"


def test_running_sum_table_calc_maps_to_running_rule(ir_dir: Path, rules_yaml_path: Path, tmp_path: Path):
    # Real sidecar uses R-CALC-07 for RUNNING_*; fallback also uses R-CALC-10
    # historically. The matcher dispatches by predicate so accept either.
    rules = _load_rules(rules_yaml_path)
    res = _run_cli(ir_dir, rules_yaml_path, tmp_path, extra=["--allow-unmatched"])
    d = _decision_by_id(res["decisions"], "calcs[2]")
    assert d["rule_id"] in {"R-CALC-07", "R-CALC-10"}
    assert d["strategy_effective"] == _rule_strategy(rules, d["rule_id"])


def test_dual_axis_worksheet_classified(ir_dir: Path, rules_yaml_path: Path, tmp_path: Path):
    rules = _load_rules(rules_yaml_path)
    res = _run_cli(ir_dir, rules_yaml_path, tmp_path, extra=["--allow-unmatched"])
    d = _decision_by_id(res["decisions"], "worksheets[0]")
    # The matcher dispatches dual-axis to R-VIZ-11 (independent) by default. If
    # the IR carries dual_axis_synchronized=True the matcher would pick R-VIZ-10.
    # The fallback YAML uses R-VIZ-08 for compatibility with older drafts.
    assert d["rule_id"] in {"R-VIZ-08", "R-VIZ-10", "R-VIZ-11"}
    assert d["strategy_effective"] == _rule_strategy(rules, d["rule_id"])


def test_floating_zone_default_snap(ir_dir: Path, rules_yaml_path: Path, tmp_path: Path):
    rules = _load_rules(rules_yaml_path)
    res = _run_cli(ir_dir, rules_yaml_path, tmp_path, extra=["--allow-unmatched"])
    d = _decision_by_id(res["decisions"], "dashboards.Main.zones[1]")
    # Real sidecar uses R-DASH-02 for floating layout; fallback uses R-DASH-04.
    assert d["rule_id"] in {"R-DASH-02", "R-DASH-04"}
    assert d["strategy_effective"] == _rule_strategy(rules, d["rule_id"])
    # Whichever sidecar is active, the default strategy for floating zones
    # is the snap-to-grid emission strategy.
    assert d["strategy_default"] == "dashboard_zone_floating_snap"


def test_floating_zone_with_reject_override(ir_dir: Path, rules_yaml_path: Path, tmp_path: Path):
    rules = _load_rules(rules_yaml_path)
    overrides = tmp_path / "user_guardrails.yaml"
    overrides.write_text(yaml.safe_dump({"guardrails": {"floating_zone_handling": "reject_with_warning"}}))
    res = _run_cli(
        ir_dir, rules_yaml_path, tmp_path,
        extra=["--allow-unmatched", "--guardrails-yaml", str(overrides)],
    )
    d = _decision_by_id(res["decisions"], "dashboards.Main.zones[1]")
    # The override must surface in guardrail_overrides_applied either way.
    overrides_applied = res["guardrail_overrides_applied"]
    assert any(
        o["key"] == "floating_zone_handling" and o["user_value"] == "reject_with_warning"
        for o in overrides_applied
    )
    # If the active rule enumerates an alt_strategy for this guardrail value,
    # the effective strategy must swap. If it does not, the effective strategy
    # stays at the default and a warning must be recorded.
    if _rule_has_alt(rules, d["rule_id"], "floating_zone_handling"):
        assert d["strategy_effective"] == "drop_with_warning"
    else:
        assert d["strategy_effective"] == d["strategy_default"]
        assert any("floating_zone_handling" in w for w in d["warnings"])


def test_set_action_is_red_and_omitted(ir_dir: Path, rules_yaml_path: Path, tmp_path: Path):
    res = _run_cli(ir_dir, rules_yaml_path, tmp_path, extra=["--allow-unmatched"])
    d = _decision_by_id(res["decisions"], "actions[1]")
    assert d["rule_id"] == "R-ACTION-06"
    assert d["bucket"] == "RED"
    assert d["omitted"] is True


def test_unknown_concept_drives_exit_code_1(tmp_path: Path, rules_yaml_path: Path):
    # Construct an IR with an action of an unknown kind so the action matcher fails.
    d = tmp_path / "ir"
    d.mkdir()
    (d / "actions.json").write_text(json.dumps([{"name": "Mystery", "kind": "telepathy", "source": "A", "target": "B"}]))
    out = tmp_path / "decisions.json"
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "apply_rules.py"),
        "--ir-dir", str(d),
        "--rules-yaml", str(rules_yaml_path),
        "--out", str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1, f"expected exit 1, got {res.returncode}, stderr: {res.stderr}"
    payload = json.loads(out.read_text())
    assert any(u["name"] == "Mystery" for u in payload["unmatched"])

    # With --allow-unmatched it should be exit 0 instead.
    cmd.append("--allow-unmatched")
    res2 = subprocess.run(cmd, capture_output=True, text=True)
    assert res2.returncode == 0
