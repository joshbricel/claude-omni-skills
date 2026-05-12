"""Tests for score_fidelity.py.

Each test builds its decisions.json fixture programmatically (no on-disk
fixtures), invokes the scorer, and asserts on either the in-memory score or the
process exit code. Numeric assertions use a tolerance of three decimals.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

import pytest

# Make the scripts dir importable when running pytest from anywhere.
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.abspath(os.path.join(HERE, ".."))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import score_fidelity  # noqa: E402


def make_decision(
    instance_id: str,
    rule_id: str,
    bucket: str,
    name: Optional[str] = None,
    needs_review: bool = False,
    omitted: bool = False,
    warnings: Optional[List[str]] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """Helper to build one decision dict matching the apply_rules.py contract."""
    return {
        "instance_id": instance_id,
        "tableau_input": {
            "concept_kind": "calculated_field",
            "name": name or instance_id,
        },
        "rule_id": rule_id,
        "rule_name": rule_id,
        "bucket": bucket,
        "strategy_effective": "model_layer_measure",
        "needs_review": needs_review,
        "omitted": omitted,
        "warnings": warnings or [],
        "notes": notes,
    }


def write_decisions(
    tmp_path,
    decisions: List[Dict[str, Any]],
    unmatched: Optional[List[Dict[str, Any]]] = None,
    threshold: float = 0.6,
) -> str:
    """Write a decisions.json fixture and return its path."""
    blob = {
        "version": "1.0",
        "guardrails_effective": {
            "fidelity_threshold_for_rejection": threshold,
        },
        "decisions": decisions,
        "unmatched": unmatched or [],
        "summary": {
            "total_instances": len(decisions),
            "by_bucket": {},
            "by_family": {},
            "needs_review_count": sum(
                1 for d in decisions if d.get("needs_review")
            ),
            "omitted_count": sum(1 for d in decisions if d.get("omitted")),
        },
    }
    path = tmp_path / "decisions.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(blob, fh)
    return str(path)


def run_scorer(
    decisions_path: str,
    report_path: str,
    json_path: Optional[str] = None,
    threshold: Optional[float] = None,
    ignore_threshold: bool = False,
) -> int:
    """Invoke the scorer's main() with CLI args and return its exit code."""
    argv = [
        "--decisions",
        decisions_path,
        "--report",
        report_path,
    ]
    if json_path:
        argv += ["--json-out", json_path]
    if threshold is not None:
        argv += ["--threshold", str(threshold)]
    if ignore_threshold:
        argv += ["--ignore-threshold"]
    return score_fidelity.main(argv)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# -----------------------------------------------------------------------------
# Case 1: All GREEN decisions yield score 1.0 and halt=false.
# -----------------------------------------------------------------------------
def test_all_green(tmp_path):
    decisions = [
        make_decision("c1", "R-CALC-01", "GREEN"),
        make_decision("c2", "R-VIZ-01", "GREEN"),
        make_decision("c3", "R-MODEL-01", "GREEN"),
    ]
    decisions_path = write_decisions(tmp_path, decisions)
    report_path = str(tmp_path / "parity.md")
    json_path = str(tmp_path / "scores.json")

    code = run_scorer(decisions_path, report_path, json_path)
    assert code == 0

    scores = load_json(json_path)
    assert scores["workbook_score"] == pytest.approx(1.0, abs=1e-3)
    assert scores["halt"] is False


# -----------------------------------------------------------------------------
# Case 2: All RED decisions yield score 0.0 and exit code 2.
# -----------------------------------------------------------------------------
def test_all_red(tmp_path):
    decisions = [
        make_decision("c1", "R-CALC-01", "RED", omitted=True),
        make_decision("c2", "R-VIZ-01", "RED", omitted=True),
        make_decision("c3", "R-MODEL-01", "RED", omitted=True),
    ]
    decisions_path = write_decisions(tmp_path, decisions)
    report_path = str(tmp_path / "parity.md")
    json_path = str(tmp_path / "scores.json")

    code = run_scorer(decisions_path, report_path, json_path)
    assert code == 2

    scores = load_json(json_path)
    assert scores["workbook_score"] == pytest.approx(0.0, abs=1e-3)
    assert scores["halt"] is True


# -----------------------------------------------------------------------------
# Case 3: Mixed buckets reproduce an expected weighted average.
# -----------------------------------------------------------------------------
def test_mixed_weighted_average(tmp_path):
    # Hand-computed:
    #   R-CALC GREEN: bucket 1.0, family 1.5 -> num 1.5, den 1.5
    #   R-CALC YELLOW: bucket 0.6, family 1.5 -> num 0.9, den 1.5
    #   R-VIZ GREEN: bucket 1.0, family 1.2 -> num 1.2, den 1.2
    #   R-FILTER RED: bucket 0.0, family 1.0 -> num 0.0, den 1.0
    # Total numerator = 1.5 + 0.9 + 1.2 + 0.0 = 3.6
    # Total denominator = 1.5 + 1.5 + 1.2 + 1.0 = 5.2
    # Score = 3.6 / 5.2 = 0.6923 ish
    decisions = [
        make_decision("c1", "R-CALC-01", "GREEN"),
        make_decision("c2", "R-CALC-02", "YELLOW", needs_review=True),
        make_decision("c3", "R-VIZ-01", "GREEN"),
        make_decision("c4", "R-FILTER-01", "RED", omitted=True),
    ]
    decisions_path = write_decisions(tmp_path, decisions)
    report_path = str(tmp_path / "parity.md")
    json_path = str(tmp_path / "scores.json")

    code = run_scorer(decisions_path, report_path, json_path)
    assert code == 0  # 0.692 > 0.6 default threshold

    scores = load_json(json_path)
    expected = 3.6 / 5.2
    assert scores["workbook_score"] == pytest.approx(expected, abs=1e-3)


# -----------------------------------------------------------------------------
# Case 4: Compound bucket GREEN/YELLOW scores as 0.8.
# -----------------------------------------------------------------------------
def test_compound_bucket(tmp_path):
    # Single decision, R-FILTER (weight 1.0), bucket GREEN/YELLOW => 0.8.
    # Workbook score = 0.8 * 1.0 / 1.0 = 0.8.
    decisions = [
        make_decision("c1", "R-FILTER-01", "GREEN/YELLOW"),
    ]
    decisions_path = write_decisions(tmp_path, decisions)
    report_path = str(tmp_path / "parity.md")
    json_path = str(tmp_path / "scores.json")

    run_scorer(decisions_path, report_path, json_path)
    scores = load_json(json_path)
    assert scores["workbook_score"] == pytest.approx(0.8, abs=1e-3)


# -----------------------------------------------------------------------------
# Case 5: Unmatched entries drag the score down via the divisor.
# -----------------------------------------------------------------------------
def test_unmatched_drags_score(tmp_path):
    # One GREEN R-CALC decision and one unmatched entry.
    # GREEN R-CALC: num 1.5, den 1.5
    # Unmatched: num 0.0, den 1.0
    # Score = 1.5 / 2.5 = 0.6.
    decisions = [make_decision("c1", "R-CALC-01", "GREEN")]
    unmatched = [
        {
            "instance_id": "u1",
            "concept_kind": "unknown",
            "reason": "no matching rule",
        }
    ]
    decisions_path = write_decisions(
        tmp_path, decisions, unmatched=unmatched, threshold=0.5
    )
    report_path = str(tmp_path / "parity.md")
    json_path = str(tmp_path / "scores.json")

    run_scorer(decisions_path, report_path, json_path)
    scores = load_json(json_path)
    # 1.5 / 2.5 = 0.6
    assert scores["workbook_score"] == pytest.approx(0.6, abs=1e-3)

    # The unmatched entry should show up as its own family in the per-family
    # breakdown. We confirm the divisor moved by comparing to a no-unmatched
    # baseline run.
    decisions_path_b = write_decisions(tmp_path, decisions, unmatched=[])
    report_path_b = str(tmp_path / "parity_b.md")
    json_path_b = str(tmp_path / "scores_b.json")
    run_scorer(decisions_path_b, report_path_b, json_path_b)
    scores_b = load_json(json_path_b)
    # Without unmatched, score = 1.5 / 1.5 = 1.0.
    assert scores_b["workbook_score"] == pytest.approx(1.0, abs=1e-3)


# -----------------------------------------------------------------------------
# Case 6: --ignore-threshold proceeds despite a sub-threshold score.
# -----------------------------------------------------------------------------
def test_ignore_threshold(tmp_path):
    decisions = [
        make_decision("c1", "R-CALC-01", "RED", omitted=True),
        make_decision("c2", "R-VIZ-01", "RED", omitted=True),
    ]
    decisions_path = write_decisions(tmp_path, decisions)
    report_path = str(tmp_path / "parity.md")
    json_path = str(tmp_path / "scores.json")

    code = run_scorer(
        decisions_path, report_path, json_path, ignore_threshold=True
    )
    assert code == 0  # Override prevents the exit 2.
    scores = load_json(json_path)
    assert scores["workbook_score"] == pytest.approx(0.0, abs=1e-3)
    # halt remains true even when the override skips the exit.
    assert scores["halt"] is True


# -----------------------------------------------------------------------------
# Case 7: Per-family scoring identifies R-CALC as worst when it is all RED.
# -----------------------------------------------------------------------------
def test_per_family_worst(tmp_path):
    decisions = [
        # R-VIZ family: all GREEN, score should be 1.0.
        make_decision("v1", "R-VIZ-01", "GREEN"),
        make_decision("v2", "R-VIZ-02", "GREEN"),
        # R-CALC family: all RED, score should be 0.0.
        make_decision("c1", "R-CALC-01", "RED", omitted=True),
        make_decision("c2", "R-CALC-02", "RED", omitted=True),
    ]
    decisions_path = write_decisions(tmp_path, decisions, threshold=0.0)
    report_path = str(tmp_path / "parity.md")
    json_path = str(tmp_path / "scores.json")

    run_scorer(decisions_path, report_path, json_path)
    scores = load_json(json_path)

    families = {row["family"]: row["score"] for row in scores["per_family"]}
    assert families["R-CALC"] == pytest.approx(0.0, abs=1e-3)
    assert families["R-VIZ"] == pytest.approx(1.0, abs=1e-3)

    worst = scores["worst_family"]
    assert worst is not None
    assert worst["family"] == "R-CALC"
    assert worst["score"] == pytest.approx(0.0, abs=1e-3)
