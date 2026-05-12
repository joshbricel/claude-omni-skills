#!/usr/bin/env python3
"""Fidelity scorer for the Tableau-to-Omni migration emitter.

Consumes a `decisions.json` produced by `apply_rules.py` (the rules engine) and
produces:

1. A numeric workbook fidelity score in [0.0, 1.0].
2. Per-dashboard fidelity scores when an IR directory with `dashboards.json`
   is supplied.
3. A markdown parity report at the path passed to `--report`.
4. Optional machine-readable scores JSON at `--json-out`.
5. A halt/proceed decision driven by the workbook score versus the
   `fidelity_threshold_for_rejection` guardrail (default 0.6).

No emojis. No em dashes. JSON in, markdown out. The script does not import or
call any sibling emitter script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Bucket weights: each maps a bucket label to a fidelity multiplier in [0, 1].
# Compound buckets like "GREEN/YELLOW" are evaluated as the mean of the two
# halves (so "GREEN/YELLOW" -> (1.0 + 0.6) / 2 = 0.8).
BUCKET_WEIGHTS: Dict[str, float] = {
    "GREEN": 1.0,
    "YELLOW": 0.6,
    "RED": 0.0,
    "GREY": 0.3,
}

# Per-family critical-path multipliers. A family is the prefix of a rule_id up
# to (and including) the second hyphen, e.g. R-CALC-04 -> family "R-CALC".
# Unknown families fall back to 1.0.
FAMILY_WEIGHTS: Dict[str, float] = {
    "R-MODEL": 1.5,
    "R-FIELD": 1.5,
    "R-CALC": 1.5,
    "R-VIZ": 1.2,
    "R-FILTER": 1.0,
    "R-DASH": 1.2,
    "R-ACTION": 0.6,
    "R-STORY": 0.5,
    "R-FORMAT": 0.7,
    "R-COLOR": 0.7,
    "R-CONN": 1.0,
    "R-DERIVED": 1.0,
    "R-PARAM": 1.0,
    "R-OTHER": 1.0,
}

# Sentinel family used when a decision has no rule_id (e.g. unmatched entries
# carried through from decisions.unmatched[]). Treated as worst-priority so it
# is not weighted out of existence.
UNMATCHED_FAMILY = "R-UNMATCHED"
UNMATCHED_FAMILY_WEIGHT = 1.0


@dataclass
class ScoredDecision:
    """A single decision after bucket and family weighting.

    Attributes:
        instance_id: identifier from decisions.json.
        rule_id: rule that fired, or empty for unmatched.
        family: derived from rule_id (e.g. R-CALC). UNMATCHED_FAMILY when blank.
        name: tableau_input.name when present, else the instance_id.
        bucket: raw bucket label (may be compound, e.g. GREEN/YELLOW).
        bucket_weight: numeric resolution of the bucket label.
        family_weight: numeric resolution of the family.
        warnings: warnings copied from the input decision.
        needs_review: bool flag from input.
        omitted: bool flag from input.
        notes: free-text notes from input.
    """

    instance_id: str
    rule_id: str
    family: str
    name: str
    bucket: str
    bucket_weight: float
    family_weight: float
    warnings: List[str] = field(default_factory=list)
    needs_review: bool = False
    omitted: bool = False
    notes: str = ""

    @property
    def numerator_contribution(self) -> float:
        """Weighted score this decision contributes to the workbook numerator."""
        return self.bucket_weight * self.family_weight

    @property
    def denominator_contribution(self) -> float:
        """Weighted score this decision contributes to the workbook denominator."""
        # Max possible bucket weight is 1.0, so the per-decision denominator is
        # just the family weight. This keeps the score in [0, 1].
        return self.family_weight * 1.0


def family_from_rule_id(rule_id: Optional[str]) -> str:
    """Extract the family prefix from a rule id like 'R-CALC-04' -> 'R-CALC'.

    Falls back to UNMATCHED_FAMILY when rule_id is missing or malformed.
    """
    if not rule_id:
        return UNMATCHED_FAMILY
    parts = rule_id.split("-")
    if len(parts) < 2:
        return UNMATCHED_FAMILY
    # Most families are "R-CALC", "R-VIZ", etc. Use the first two segments.
    return "-".join(parts[:2])


def resolve_bucket_weight(bucket: str) -> float:
    """Translate a bucket label to a numeric weight in [0, 1].

    Compound labels (e.g. "GREEN/YELLOW") average their halves so the formula
    stays transparent and order-independent. Unknown labels score 0.0.
    """
    if not bucket:
        return 0.0
    label = bucket.strip().upper()
    if "/" in label:
        halves = [h.strip() for h in label.split("/") if h.strip()]
        if not halves:
            return 0.0
        return sum(BUCKET_WEIGHTS.get(h, 0.0) for h in halves) / len(halves)
    return BUCKET_WEIGHTS.get(label, 0.0)


def resolve_family_weight(family: str) -> float:
    """Translate a family label to a numeric weight."""
    if family == UNMATCHED_FAMILY:
        return UNMATCHED_FAMILY_WEIGHT
    return FAMILY_WEIGHTS.get(family, 1.0)


def load_decisions(path: str) -> Dict[str, Any]:
    """Load the decisions.json file produced by apply_rules.py."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "decisions" not in data:
        raise ValueError(f"{path} has no 'decisions' array")
    return data


def load_ir_scope_map(ir_dir: Optional[str]) -> Dict[str, List[str]]:
    """Build {dashboard_name: [instance_ids in scope]} from IR dashboards.json.

    The IR's dashboards.json is expected to be a list of dashboards, each with a
    name and `member_worksheets` (the Tableau worksheet names it contains). When
    the IR cannot be located we return an empty map; callers fall back to
    "all decisions" scope.
    """
    if not ir_dir:
        return {}
    dashboards_path = os.path.join(ir_dir, "dashboards.json")
    if not os.path.exists(dashboards_path):
        return {}
    with open(dashboards_path, "r", encoding="utf-8") as fh:
        dashboards = json.load(fh)
    if not isinstance(dashboards, list):
        return {}
    scope: Dict[str, List[str]] = {}
    for dash in dashboards:
        name = dash.get("name") or dash.get("dashboard_name")
        if not name:
            continue
        members = dash.get("member_worksheets") or dash.get("worksheets") or []
        if not isinstance(members, list):
            continue
        # Member worksheets are referenced by name. Decisions carry
        # tableau_input.name; we collect those names so the caller can match.
        scope[name] = [str(m) for m in members]
    return scope


def score_decision(raw: Dict[str, Any]) -> ScoredDecision:
    """Turn a single raw decision dict into a ScoredDecision."""
    rule_id = raw.get("rule_id") or ""
    tableau_input = raw.get("tableau_input") or {}
    name = tableau_input.get("name") or raw.get("instance_id") or ""
    bucket = raw.get("bucket") or ""
    family = family_from_rule_id(rule_id)
    return ScoredDecision(
        instance_id=str(raw.get("instance_id") or ""),
        rule_id=rule_id,
        family=family,
        name=str(name),
        bucket=str(bucket),
        bucket_weight=resolve_bucket_weight(bucket),
        family_weight=resolve_family_weight(family),
        warnings=list(raw.get("warnings") or []),
        needs_review=bool(raw.get("needs_review")),
        omitted=bool(raw.get("omitted")),
        notes=str(raw.get("notes") or ""),
    )


def score_unmatched(raw: Dict[str, Any]) -> ScoredDecision:
    """Score an entry from decisions.unmatched[].

    Unmatched entries did not even get classified, so they score worse than RED.
    They are assigned the UNMATCHED family at default weight 1.0.
    """
    return ScoredDecision(
        instance_id=str(raw.get("instance_id") or ""),
        rule_id="",
        family=UNMATCHED_FAMILY,
        name=str(raw.get("instance_id") or raw.get("concept_kind") or ""),
        bucket="UNMATCHED",
        bucket_weight=0.0,
        family_weight=UNMATCHED_FAMILY_WEIGHT,
        warnings=[],
        needs_review=False,
        omitted=True,
        notes=str(raw.get("reason") or ""),
    )


def aggregate(scored: Iterable[ScoredDecision]) -> float:
    """Aggregate weighted decisions into a workbook (or scope) score in [0, 1]."""
    numerator = 0.0
    denominator = 0.0
    for s in scored:
        numerator += s.numerator_contribution
        denominator += s.denominator_contribution
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def score_per_family(scored: List[ScoredDecision]) -> List[Tuple[str, float, int, float]]:
    """Compute per-family scores.

    Returns a list of (family, score, count, family_weight) sorted ascending by
    score (worst first), then by family name for determinism.
    """
    by_family: Dict[str, List[ScoredDecision]] = {}
    for s in scored:
        by_family.setdefault(s.family, []).append(s)
    rows: List[Tuple[str, float, int, float]] = []
    for family, items in by_family.items():
        score = aggregate(items)
        rows.append((family, score, len(items), resolve_family_weight(family)))
    rows.sort(key=lambda row: (row[1], row[0]))
    return rows


def score_per_dashboard(
    scored: List[ScoredDecision],
    raw_decisions: List[Dict[str, Any]],
    scope_map: Dict[str, List[str]],
) -> List[Tuple[str, float, int]]:
    """Compute per-dashboard scores using the IR's `member_worksheets` field.

    Falls back to a single "(all decisions)" row when no scope info is
    available. Matching is done by checking whether a decision's
    `tableau_input.name` or `tableau_input.worksheet` appears in the dashboard's
    member_worksheets list.
    """
    if not scope_map:
        return [("(all decisions)", aggregate(scored), len(scored))]

    # Build a quick lookup from instance_id to ScoredDecision so we can
    # restrict to scope without re-running score_decision.
    by_id: Dict[str, ScoredDecision] = {s.instance_id: s for s in scored}

    rows: List[Tuple[str, float, int]] = []
    for dashboard_name, member_worksheets in scope_map.items():
        member_set = {m for m in member_worksheets}
        in_scope: List[ScoredDecision] = []
        for raw in raw_decisions:
            tableau_input = raw.get("tableau_input") or {}
            ws = tableau_input.get("worksheet") or tableau_input.get("name")
            if not ws:
                continue
            if ws in member_set:
                instance_id = str(raw.get("instance_id") or "")
                if instance_id in by_id:
                    in_scope.append(by_id[instance_id])
        if not in_scope:
            rows.append((dashboard_name, 0.0, 0))
            continue
        rows.append((dashboard_name, aggregate(in_scope), len(in_scope)))
    # Sort dashboards alphabetically for determinism.
    rows.sort(key=lambda row: row[0])
    return rows


def bucket_breakdown(scored: List[ScoredDecision]) -> List[Tuple[str, int, float]]:
    """Count decisions by raw bucket label.

    Returns (bucket, count, percentage) sorted by bucket name for determinism.
    """
    total = len(scored)
    counts: Dict[str, int] = {}
    for s in scored:
        counts[s.bucket or "(blank)"] = counts.get(s.bucket or "(blank)", 0) + 1
    rows = []
    for bucket in sorted(counts.keys()):
        count = counts[bucket]
        pct = (count / total * 100.0) if total else 0.0
        rows.append((bucket, count, pct))
    return rows


def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    """Render a small markdown table. Empty rows yield an italic placeholder."""
    if not rows:
        return "_None._\n"
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out) + "\n"


def _format_warnings(warnings: List[str]) -> str:
    if not warnings:
        return ""
    return "; ".join(warnings)


def _example_math(scored: List[ScoredDecision]) -> str:
    """Build the 'How this score was computed' demonstration block.

    Picks the first decision (deterministically sorted earlier) and walks the
    arithmetic so the reader sees one bucket+family pair end-to-end.
    """
    if not scored:
        return "_No decisions to demonstrate._\n"
    sample = scored[0]
    lines = [
        f"Example decision: `{sample.instance_id}` (rule `{sample.rule_id or 'unmatched'}`).",
        "",
        f"- Bucket: `{sample.bucket}` resolves to bucket_weight = {sample.bucket_weight:.3f}",
        f"- Family: `{sample.family}` resolves to family_weight = {sample.family_weight:.3f}",
        f"- Numerator contribution: bucket_weight * family_weight = "
        f"{sample.bucket_weight:.3f} * {sample.family_weight:.3f} = "
        f"{sample.numerator_contribution:.3f}",
        f"- Denominator contribution: family_weight = {sample.family_weight:.3f}",
        "",
        "Workbook score = sum(numerator contributions) / sum(denominator contributions).",
    ]
    return "\n".join(lines) + "\n"


def build_markdown_report(
    decisions_blob: Dict[str, Any],
    scored: List[ScoredDecision],
    workbook_score: float,
    threshold: float,
    halt: bool,
    per_family: List[Tuple[str, float, int, float]],
    per_dashboard: List[Tuple[str, float, int]],
    bucket_rows: List[Tuple[str, int, float]],
    unmatched_raw: List[Dict[str, Any]],
) -> str:
    """Render the parity-report.md document."""
    worst_family_label = "(none)"
    if per_family:
        worst_family, worst_score, _, _ = per_family[0]
        worst_family_label = f"{worst_family} ({worst_score:.2f})"

    out: List[str] = []
    out.append("# Tableau-to-Omni parity report")
    out.append("")

    # 1. TL;DR
    out.append("## TL;DR")
    out.append("")
    out.append(
        f"Workbook fidelity score: **{workbook_score:.3f}** "
        f"(threshold {threshold:.2f}, halt = {str(halt).lower()}). "
        f"Worst-scoring family: {worst_family_label}."
    )
    out.append("")
    out.append("```summary")
    out.append(f"score: {workbook_score:.3f}")
    out.append(f"halt: {str(halt).lower()}")
    out.append(f"threshold: {threshold:.2f}")
    out.append(f"worst_family: {worst_family_label}")
    out.append("```")
    out.append("")

    # 2. Scorecard
    out.append("## Scorecard")
    out.append("")
    scorecard_rows: List[List[str]] = [
        ["Workbook", f"{workbook_score:.3f}", str(len(scored))]
    ]
    for dash, score, n in per_dashboard:
        scorecard_rows.append([f"Dashboard: {dash}", f"{score:.3f}", str(n)])
    out.append(_md_table(["Scope", "Score", "Decisions"], scorecard_rows))
    out.append("")

    # 3. Bucket breakdown
    out.append("## Bucket breakdown")
    out.append("")
    bucket_table = [
        [bucket, str(count), f"{pct:.1f}%"]
        for bucket, count, pct in bucket_rows
    ]
    out.append(_md_table(["Bucket", "Count", "Percent"], bucket_table))
    out.append("")

    # 4. Per-family scores
    out.append("## Per-family scores")
    out.append("")
    family_table = [
        [family, f"{score:.3f}", str(count), f"{weight:.2f}"]
        for family, score, count, weight in per_family
    ]
    out.append(
        _md_table(["Family", "Score", "Decisions", "Family weight"], family_table)
    )
    out.append("")

    # 5. Review queue (YELLOW with needs_review)
    out.append("## Review queue")
    out.append("")
    review_rows: List[List[str]] = []
    for s in scored:
        bucket_upper = s.bucket.upper()
        is_yellow = bucket_upper == "YELLOW" or "YELLOW" in bucket_upper.split("/")
        if is_yellow and s.needs_review:
            review_rows.append(
                [
                    s.rule_id or "(unmatched)",
                    s.name,
                    s.bucket,
                    _format_warnings(s.warnings),
                ]
            )
    out.append(_md_table(["Rule ID", "Name", "Bucket", "Warnings"], review_rows))
    out.append("")

    # 6. Omitted (RED)
    out.append("## Omitted (RED)")
    out.append("")
    red_rows: List[List[str]] = []
    for s in scored:
        if s.bucket.upper() == "RED" or s.omitted:
            reason = s.notes or _format_warnings(s.warnings) or "omitted"
            red_rows.append([s.rule_id or "(unmatched)", s.name, reason])
    out.append(_md_table(["Rule ID", "Name", "Reason"], red_rows))
    out.append("")

    # 7. Unresolved (GREY)
    out.append("## Unresolved (GREY)")
    out.append("")
    grey_rows: List[List[str]] = []
    for s in scored:
        if s.bucket.upper() == "GREY":
            plan = s.notes or _format_warnings(s.warnings) or "needs investigation"
            grey_rows.append([s.rule_id or "(unmatched)", s.name, plan])
    out.append(_md_table(["Rule ID", "Name", "Resolution plan"], grey_rows))
    out.append("")

    # 8. Unmatched
    out.append("## Unmatched")
    out.append("")
    unmatched_rows: List[List[str]] = []
    for u in unmatched_raw:
        unmatched_rows.append(
            [
                str(u.get("instance_id") or ""),
                str(u.get("concept_kind") or ""),
                str(u.get("reason") or ""),
            ]
        )
    out.append(_md_table(["Instance ID", "Concept kind", "Reason"], unmatched_rows))
    out.append("")

    # 9. Verification checklist
    out.append("## Verification checklist")
    out.append("")
    # This script is JSON-in, markdown-out. Without the hyper-extract data it
    # cannot run the data checks, so most rows are skipped.
    checklist_rows = [
        ["Nulls", "skipped", "no source data access in this script"],
        ["Uniqueness / grain", "skipped", "no source data access in this script"],
        ["Fan-outs", "skipped", "no joins evaluated here"],
        ["Referential integrity", "skipped", "no source data access in this script"],
        ["Row counts", "skipped", "no source data access in this script"],
        ["Reconciliation", "skipped", "no source data access in this script"],
        ["Accepted values", "skipped", "no source data access in this script"],
        ["Range / boundary", "skipped", "no source data access in this script"],
        ["Freshness", "skipped", "no source data access in this script"],
        ["Edge cases", "skipped", "no source data access in this script"],
        [
            "Determinism",
            "pass",
            "decisions sorted before scoring, output is deterministic",
        ],
    ]
    out.append(_md_table(["Check", "Status", "Note"], checklist_rows))
    out.append("")

    # 10. Recommendation
    out.append("## Recommendation")
    out.append("")
    out.append(_recommendation(workbook_score, threshold, halt, per_family))
    out.append("")

    # Bonus: how the score was computed
    out.append("## How this score was computed")
    out.append("")
    out.append(
        "Per-decision contribution = bucket_weight * family_weight. "
        "Workbook score = sum of per-decision contributions divided by "
        "sum of per-decision family weights. Compound buckets like "
        "`GREEN/YELLOW` average their halves. Unmatched entries score 0.0 at "
        "family weight 1.0 (worse than RED because they were never "
        "classified)."
    )
    out.append("")
    out.append(_example_math(scored))
    out.append("")

    return "\n".join(out)


def _recommendation(
    score: float,
    threshold: float,
    halt: bool,
    per_family: List[Tuple[str, float, int, float]],
) -> str:
    """One-paragraph recommendation derived from the scoreboard state."""
    if halt:
        worst = per_family[0][0] if per_family else "unknown family"
        return (
            f"Pause and fix. Workbook score {score:.3f} is below threshold "
            f"{threshold:.2f}. Start with `{worst}`, which is the worst-scoring "
            "family. Re-run the rules engine after fixes and re-score."
        )
    if score >= 0.9:
        return (
            f"Ship as-is. Workbook score {score:.3f} clears threshold "
            f"{threshold:.2f} with margin to spare."
        )
    if score >= 0.75:
        return (
            f"Ship after YELLOW review. Workbook score {score:.3f} clears "
            f"threshold {threshold:.2f}, but the review queue should be walked "
            "before promoting the branch."
        )
    return (
        f"Borderline. Workbook score {score:.3f} clears threshold "
        f"{threshold:.2f} but only just. Recommend fixing the top family or "
        "two before promoting."
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Build the argparse namespace for the script."""
    parser = argparse.ArgumentParser(
        description=(
            "Score the fidelity of a Tableau-to-Omni migration by consuming "
            "the rules engine's decisions.json and emitting a parity report."
        )
    )
    parser.add_argument(
        "--decisions",
        required=True,
        help="Path to decisions.json from apply_rules.py.",
    )
    parser.add_argument(
        "--ir-dir",
        default=None,
        help=(
            "Optional path to the IR directory produced by extract.py. "
            "Required for per-dashboard scoping via dashboards.json."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=(
            "Override the workbook fidelity threshold. Defaults to the value "
            "in decisions.json guardrails_effective, or 0.6 if missing."
        ),
    )
    parser.add_argument(
        "--ignore-threshold",
        action="store_true",
        help="Exit 0 even when the workbook score is below threshold.",
    )
    parser.add_argument(
        "--report",
        required=True,
        help="Output path for the parity-report.md markdown file.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path for machine-readable scores JSON.",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    """Execute the scorer. Returns the process exit code."""
    blob = load_decisions(args.decisions)
    raw_decisions: List[Dict[str, Any]] = list(blob.get("decisions") or [])
    raw_unmatched: List[Dict[str, Any]] = list(blob.get("unmatched") or [])

    # Sort decisions by instance_id for deterministic scoring order. Unmatched
    # is sorted the same way and appended afterwards.
    raw_decisions.sort(key=lambda d: str(d.get("instance_id") or ""))
    raw_unmatched.sort(key=lambda d: str(d.get("instance_id") or ""))

    scored: List[ScoredDecision] = [score_decision(d) for d in raw_decisions]
    scored.extend(score_unmatched(u) for u in raw_unmatched)

    workbook_score = aggregate(scored)

    guardrails = blob.get("guardrails_effective") or {}
    threshold = (
        args.threshold
        if args.threshold is not None
        else float(guardrails.get("fidelity_threshold_for_rejection", 0.6))
    )

    halt = workbook_score < threshold
    per_family = score_per_family(scored)
    scope_map = load_ir_scope_map(args.ir_dir)
    per_dashboard = score_per_dashboard(scored, raw_decisions, scope_map)
    bucket_rows = bucket_breakdown(scored)

    report_md = build_markdown_report(
        decisions_blob=blob,
        scored=scored,
        workbook_score=workbook_score,
        threshold=threshold,
        halt=halt,
        per_family=per_family,
        per_dashboard=per_dashboard,
        bucket_rows=bucket_rows,
        unmatched_raw=raw_unmatched,
    )

    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(report_md)

    if args.json_out:
        json_payload = {
            "workbook_score": workbook_score,
            "threshold": threshold,
            "halt": halt,
            "worst_family": (
                {
                    "family": per_family[0][0],
                    "score": per_family[0][1],
                }
                if per_family
                else None
            ),
            "per_family": [
                {
                    "family": family,
                    "score": score,
                    "decisions": count,
                    "family_weight": weight,
                }
                for family, score, count, weight in per_family
            ],
            "per_dashboard": [
                {"dashboard": name, "score": score, "decisions": n}
                for name, score, n in per_dashboard
            ],
            "buckets": [
                {"bucket": bucket, "count": count, "percent": pct}
                for bucket, count, pct in bucket_rows
            ],
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(json_payload, fh, indent=2, sort_keys=True)

    summary = (
        f"score={workbook_score:.3f} threshold={threshold:.2f} "
        f"halt={str(halt).lower()}"
    )
    print(summary, file=sys.stderr)

    if halt and not args.ignore_threshold:
        worst = per_family[0][0] if per_family else "unknown"
        print(
            f"FAIL: workbook fidelity {workbook_score:.3f} < threshold "
            f"{threshold:.2f}. Worst family: {worst}.",
            file=sys.stderr,
        )
        return 2
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point compatible with `python3 -m` or direct invocation."""
    args = parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
