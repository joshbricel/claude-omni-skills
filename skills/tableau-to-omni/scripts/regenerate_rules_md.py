#!/usr/bin/env python3
# regenerate_rules_md.py
#
# Render the human-readable mapping rules markdown from the machine YAML.
#
# Workflow:
#   1. Edit context/mapping-rules.yaml. The YAML is the source of truth.
#   2. Run this script to regenerate context/tableau-omni-mapping-rules.md.
#   3. Commit both files in the same change.
#
# The YAML is the machine truth (consumed by the format-emitter rules engine).
# The markdown is the human render (used in PR review and skill context). One way
# only: never edit the markdown by hand, it will be overwritten on the next run.
#
# Dependencies: stdlib + pyyaml. Python 3.9+.

import argparse
import sys
from pathlib import Path

import yaml


# Family order matches the source markdown's section ordering.
FAMILY_ORDER = [
    "R-CONN",
    "R-MODEL",
    "R-FIELD",
    "R-CALC",
    "R-DERIVED",
    "R-PARAM",
    "R-VIZ",
    "R-FILTER",
    "R-COLOR",
    "R-DASH",
    "R-ACTION",
    "R-STORY",
    "R-FORMAT",
    "R-OTHER",
]

FAMILY_HEADINGS = {
    "R-CONN": "R-CONN: Connections and datasources",
    "R-MODEL": "R-MODEL: Semantic model",
    "R-FIELD": "R-FIELD: Columns, dimensions, measures",
    "R-CALC": "R-CALC: Calculated fields, LOD, table calcs",
    "R-DERIVED": "R-DERIVED: Groups, sets, bins, hierarchies",
    "R-PARAM": "R-PARAM: Parameters",
    "R-VIZ": "R-VIZ: Visualizations, marks, encodings, axes",
    "R-FILTER": "R-FILTER: Filters",
    "R-COLOR": "R-COLOR: Palettes and color encoding",
    "R-DASH": "R-DASH: Dashboards (layout, zones, sizing, multi-tab)",
    "R-ACTION": "R-ACTION: Dashboard actions",
    "R-STORY": "R-STORY: Stories",
    "R-FORMAT": "R-FORMAT: Numbers, dates, fonts, banding",
    "R-OTHER": "R-OTHER: Misc",
}


def render_guardrails_block(guardrails: dict) -> str:
    """Render the user-editable YAML guardrails block."""
    lines = [
        "```yaml",
        "# USER GUARDRAILS - EDIT THIS BLOCK",
        "# These keys override rule defaults. Comments name the rule IDs each key influences.",
        "",
    ]
    for key, body in guardrails.items():
        affects = body.get("affects_rules", [])
        affects_str = ", ".join(affects) if isinstance(affects, list) else str(affects)
        lines.append(f"# Affects rules {affects_str}")
        default = body.get("default")
        # Floats and strings serialize differently. Mirror what users see in the source markdown.
        if isinstance(default, str):
            lines.append(f"{key}: {default}")
        else:
            lines.append(f"{key}: {default}")
        options = body.get("options")
        if isinstance(options, list):
            lines.append(f"# valid: {' | '.join(str(o) for o in options)}")
        elif isinstance(options, str):
            lines.append(f"# valid: {options}")
        description = body.get("description")
        if description:
            lines.append(f"# {description}")
        lines.append("")
    lines.append("```")
    return "\n".join(lines)


def render_rule(rule: dict) -> str:
    """Render one rule block in the same shape as the source markdown."""
    lines = []
    lines.append(f"#### {rule['id']}: {rule['name']}")

    bucket = rule.get("bucket", "GREY")
    src = rule.get("tableau_source", {})
    tgt = rule.get("omni_target", {})

    src_section = src.get("spec_section", "")
    tgt_section = tgt.get("spec_section", "")

    # Audit bucket line. Source markdown cites the audit section that classified the bucket.
    # We do not have that audit ref in the YAML, so we cite the tableau spec section instead.
    lines.append(f"- **Bucket** ({src_section or 'audit'}): {bucket}")

    src_xml = src.get("xml_element", "")
    src_pred = src.get("xml_predicate", "")
    src_desc = f"`{src_xml}` ({src_pred})" if src_xml and src_pred else (src_xml or src_pred or "")
    lines.append(f"- **Tableau source** ({src_section}): {src_desc}")

    tgt_path = tgt.get("yaml_path", "")
    tgt_file = tgt.get("file_pattern", "")
    tgt_desc_parts = [p for p in [tgt_path, f"in {tgt_file}" if tgt_file and tgt_file != "n/a" else ""] if p]
    tgt_desc = "; ".join(tgt_desc_parts) if tgt_desc_parts else "none"
    lines.append(f"- **Omni target** ({tgt_section}): {tgt_desc}")

    mapping = rule.get("default_mapping", {})
    lines.append(f"- **Default mapping**: {mapping.get('summary', '')}")
    example = mapping.get("example")
    if example:
        # Pick a code fence flavor based on what the example looks like.
        # Default to yaml since most examples are YAML.
        fence = "yaml"
        head = example.strip().splitlines()[0] if example.strip() else ""
        if head.startswith("{") or head.startswith('"'):
            fence = "json"
        elif head.startswith("#"):
            fence = "yaml"
        lines.append(f"```{fence}")
        # Preserve the example body verbatim (trim trailing newline so the fence sits clean).
        lines.append(example.rstrip("\n"))
        lines.append("```")

    consumed = rule.get("guardrails_consumed", [])
    consumed_str = ", ".join(f"`{c}`" for c in consumed) if consumed else "none"
    lines.append(f"- **Guardrails that override this**: {consumed_str}")
    lines.append(f"- **Failure mode**: {rule.get('failure_mode', 'best_effort')}")
    lines.append(f"- **Verification**: {rule.get('verification', '')}")
    notes = rule.get("notes")
    if notes:
        lines.append(f"- **Notes**: {notes}")
    return "\n".join(lines)


def render_markdown(data: dict) -> str:
    """Render the full markdown document."""
    out = []

    out.append("---")
    out.append("title: Tableau to Omni Mapping Rules")
    out.append("version: 1.0")
    out.append(f"generated_from: {data.get('generated_from', 'mapping-rules.yaml')}")
    src = data.get("source_spec_files", {})
    out.append("source_specs:")
    for label, path in src.items():
        out.append(f"  - path: {path}")
        out.append(f"    label: {label}")
    out.append("---")
    out.append("")

    out.append("# Tableau to Omni Mapping Rules")
    out.append("")
    out.append(
        "Auto-generated from `mapping-rules.yaml`. Do not edit by hand. "
        "Edit the YAML, run `scripts/regenerate_rules_md.py`, commit both."
    )
    out.append("")
    out.append(
        "Single authoritative mapping document. Two layers: a machine-driven defaults "
        "layer (rules R-* below, addressed by stable ID) and a user-editable guardrails "
        "layer (YAML at the top). Guardrails win over defaults."
    )
    out.append("")
    out.append("---")
    out.append("")

    out.append("## USER GUARDRAILS")
    out.append("")
    out.append(render_guardrails_block(data.get("guardrails", {})))
    out.append("")
    out.append("---")
    out.append("")

    out.append("## Mapping Rules")
    out.append("")

    rules_by_family: dict = {}
    for rule in data.get("rules", []):
        rules_by_family.setdefault(rule["family"], []).append(rule)

    for family in FAMILY_ORDER:
        rules = rules_by_family.get(family, [])
        if not rules:
            continue
        out.append(f"### {FAMILY_HEADINGS.get(family, family)}")
        out.append("")
        for rule in rules:
            out.append(render_rule(rule))
            out.append("")

    out.append("---")
    out.append("")
    out.append("## Decisions ledger")
    out.append("")
    out.append("| date | rule_id(s) | decision | rationale | who |")
    out.append("|---|---|---|---|---|")
    out.append("|  |  |  |  |  |")
    out.append("")
    out.append("---")
    out.append("")

    out.append("## Emitter contract")
    out.append("")
    out.append(
        "The format-emitter tool consumes `mapping-rules.yaml` as runtime config. Contract:"
    )
    out.append("")
    out.append(
        "1. Parse the `guardrails` block into a typed dict. Reject unknown keys. Validate "
        "enum values against `options`."
    )
    out.append(
        "2. For each rule referenced by emitter code, look up the rule by stable ID "
        "(`R-FAMILY-NN`). Rule IDs survive forever. Deprecated rules are marked DEPRECATED, "
        "never renumbered."
    )
    out.append(
        "3. Apply guardrails before defaults. A guardrail naming a rule overrides the "
        "rule's default `strategy`."
    )
    out.append(
        "4. Bucket=RED with no override: write a structured warning to "
        "`migration-warnings.md` naming the rule ID, the TWBX section, the affected "
        "workbook entity, and the recommended manual action. Continue."
    )
    out.append(
        "5. Bucket=GREY: emit the default mapping plus a `# TODO: verify against Omni "
        "instance export` comment. Continue."
    )
    out.append(
        "6. Fidelity threshold: each emitted tile carries a fidelity score (1.0 minus 0.1 "
        "per YELLOW rule applied, minus 0.3 per RED rule dropped). If "
        "`fidelity_threshold_for_rejection` is exceeded, the emitter raises rather than emits."
    )
    out.append(
        "7. Every guardrail change must be appended as a row in the Decisions ledger "
        "before the change ships."
    )
    out.append("")

    return "\n".join(out)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the human-readable mapping rules markdown from mapping-rules.yaml."
    )
    parser.add_argument(
        "--yaml",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "context" / "mapping-rules.yaml",
        help="Path to mapping-rules.yaml (default: ../context/mapping-rules.yaml).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output markdown path. If omitted, prints to stdout.",
    )
    args = parser.parse_args(argv)

    if not args.yaml.exists():
        print(f"error: YAML not found: {args.yaml}", file=sys.stderr)
        return 2

    with args.yaml.open() as f:
        data = yaml.safe_load(f)

    markdown = render_markdown(data)

    if args.out:
        args.out.write_text(markdown)
        print(f"wrote {args.out} ({len(markdown.splitlines())} lines)", file=sys.stderr)
    else:
        sys.stdout.write(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
