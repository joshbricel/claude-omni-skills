"""apply_rules.py

Rules engine for the Tableau-to-Omni emitter.

Given the IR dumped by ``extract.py`` and the mapping-rules YAML sidecar, classify
every Tableau concept instance against a rule and resolve the effective emission
strategy after user guardrail overrides are applied. The output is a deterministic
``decisions.json`` document consumed downstream by ``build_payload.py`` (or its
successor) to produce Omni model/view/topic/dashboard files.

The matcher is a small table of predicate functions paired with rule IDs. The
table at the top of the module is intended to read as a spec by itself: each
predicate describes one shape of Tableau IR, and the rule ID describes where it
goes in Omni. New IR shapes get a new predicate; new rules get added to the YAML
sidecar without code change.

CLI:

    python3 apply_rules.py \
        --ir-dir /path/to/extract-output \
        --rules-yaml skills/tableau-to-omni/context/mapping-rules.yaml \
        [--guardrails-yaml path/to/user-overrides.yaml] \
        --out decisions.json
        [--allow-unmatched]

Exit codes:
    0  every instance matched a rule, or --allow-unmatched was passed
    1  one or more instances did not match a rule
    2  hard failure (missing input, malformed YAML)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Matcher table
# ---------------------------------------------------------------------------
#
# Each entry is (predicate, rule_id). Predicates take a single IR instance
# (a dict) and return True if the rule applies. The first predicate that
# matches wins; predicates are evaluated in declaration order, so more specific
# shapes must appear before more general ones.
#
# Concept families are keyed by the IR file the instance came from. The
# dispatcher in ``classify_instance`` selects the right matcher list based on
# the family, so a predicate only sees instances of the right shape.


def _is_calc_lod_fixed(c: Dict[str, Any]) -> bool:
    return bool(c.get("is_lod")) and (c.get("lod_kind") or "").upper() == "FIXED"


def _is_calc_lod_include(c: Dict[str, Any]) -> bool:
    return bool(c.get("is_lod")) and (c.get("lod_kind") or "").upper() == "INCLUDE"


def _is_calc_lod_exclude(c: Dict[str, Any]) -> bool:
    return bool(c.get("is_lod")) and (c.get("lod_kind") or "").upper() == "EXCLUDE"


def _has_token(formula: str, tokens: Iterable[str]) -> bool:
    f = (formula or "").upper()
    return any(t in f for t in tokens)


def _is_calc_running(c: Dict[str, Any]) -> bool:
    if not c.get("is_table_calc"):
        return False
    return _has_token(c.get("formula", ""), ["RUNNING_SUM", "RUNNING_AVG", "RUNNING_MIN", "RUNNING_MAX", "RUNNING_COUNT"])


def _is_calc_window(c: Dict[str, Any]) -> bool:
    if not c.get("is_table_calc"):
        return False
    return _has_token(c.get("formula", ""), ["WINDOW_SUM", "WINDOW_AVG", "WINDOW_MIN", "WINDOW_MAX", "WINDOW_COUNT", "WINDOW_MEDIAN", "WINDOW_STDEV", "WINDOW_VAR"])


def _is_calc_rank(c: Dict[str, Any]) -> bool:
    if not c.get("is_table_calc"):
        return False
    return _has_token(c.get("formula", ""), ["RANK", "RANK_DENSE", "RANK_MODIFIED", "RANK_PERCENTILE", "RANK_UNIQUE"])


def _is_calc_index_first_last_size(c: Dict[str, Any]) -> bool:
    if not c.get("is_table_calc"):
        return False
    return _has_token(c.get("formula", ""), ["INDEX(", "FIRST(", "LAST(", "SIZE("])


def _is_calc_table_calc_other(c: Dict[str, Any]) -> bool:
    return bool(c.get("is_table_calc"))


def _is_calc_aggregate(c: Dict[str, Any]) -> bool:
    return _has_token(c.get("formula", ""), ["SUM(", "AVG(", "MIN(", "MAX(", "COUNT(", "COUNTD(", "MEDIAN("])


def _is_calc_string(c: Dict[str, Any]) -> bool:
    return _has_token(c.get("formula", ""), ["LEFT(", "RIGHT(", "MID(", "CONCAT(", "REPLACE(", "TRIM(", "UPPER(", "LOWER("])


def _is_calc_date(c: Dict[str, Any]) -> bool:
    return _has_token(c.get("formula", ""), ["DATETRUNC", "DATEPART", "DATEADD", "DATEDIFF", "TODAY(", "NOW("])


def _is_calc_logical(c: Dict[str, Any]) -> bool:
    return _has_token(c.get("formula", ""), ["IIF(", "CASE ", "IF ", "IFNULL(", "ZN(", "ISNULL("])


def _is_calc_default(_c: Dict[str, Any]) -> bool:
    return True


def _is_worksheet_dual_axis(w: Dict[str, Any]) -> bool:
    return bool(w.get("dual_axis"))


def _is_worksheet_trellis(w: Dict[str, Any]) -> bool:
    trellis = w.get("trellis") or {}
    rows = trellis.get("row_pills") or []
    cols = trellis.get("col_pills") or []
    return len(rows) >= 1 or len(cols) >= 1


def _is_worksheet_default(_w: Dict[str, Any]) -> bool:
    return True


def _is_zone_floating(z: Dict[str, Any]) -> bool:
    return bool(z.get("floating"))


def _is_zone_container(z: Dict[str, Any]) -> bool:
    return z.get("kind") == "container"


def _is_zone_worksheet(z: Dict[str, Any]) -> bool:
    return z.get("kind") == "worksheet"


def _is_zone_default(_z: Dict[str, Any]) -> bool:
    return True


def _action_kind_eq(kind: str) -> Callable[[Dict[str, Any]], bool]:
    return lambda a: a.get("kind") == kind


def _param_domain_eq(kind: str) -> Callable[[Dict[str, Any]], bool]:
    return lambda p: p.get("domain_kind") == kind


def _palette_kind_eq(kind: str) -> Callable[[Dict[str, Any]], bool]:
    return lambda p: p.get("kind") == kind


def _is_filter_relative_date(f: Dict[str, Any]) -> bool:
    return f.get("kind") == "relative_date"


def _is_filter_top_n(f: Dict[str, Any]) -> bool:
    return f.get("kind") == "top_n"


def _is_filter_default(_f: Dict[str, Any]) -> bool:
    return True


# Family-keyed matcher table. Predicate order matters within each list.
# Rule IDs match the sidecar at context/mapping-rules.yaml (sibling-produced).
MATCHERS: Dict[str, List[Tuple[Callable[[Dict[str, Any]], bool], str]]] = {
    "calc": [
        (_is_calc_lod_fixed, "R-CALC-04"),                # LOD FIXED
        (_is_calc_lod_include, "R-CALC-05"),              # LOD INCLUDE
        (_is_calc_lod_exclude, "R-CALC-06"),              # LOD EXCLUDE
        (_is_calc_running, "R-CALC-07"),                  # RUNNING_*
        (_is_calc_window, "R-CALC-08"),                   # WINDOW_*
        (_is_calc_rank, "R-CALC-09"),                     # RANK family
        (_is_calc_index_first_last_size, "R-CALC-10"),    # INDEX/FIRST/LAST/SIZE
        (_is_calc_table_calc_other, "R-CALC-12"),         # custom table calc
        (_is_calc_logical, "R-CALC-02"),                  # IF / IIF / CASE
        (_is_calc_string, "R-CALC-03"),                   # string / date / type
        (_is_calc_date, "R-CALC-03"),                     # string / date / type
        (_is_calc_aggregate, "R-CALC-01"),                # arithmetic / aggregate
        (_is_calc_default, "R-CALC-01"),                  # default arithmetic
    ],
    "worksheet": [
        # Dual-axis: prefer "independent" R-VIZ-11 since the IR does not carry
        # the synchronized bit reliably; R-VIZ-10 is selected only when the IR
        # explicitly indicates synchronization.
        (lambda w: bool(w.get("dual_axis")) and bool(w.get("dual_axis_synchronized")), "R-VIZ-10"),
        (_is_worksheet_dual_axis, "R-VIZ-11"),
        (_is_worksheet_trellis, "R-VIZ-13"),
        (_is_worksheet_default, "R-VIZ-01"),              # bar mark fallback
    ],
    "zone": [
        (_is_zone_floating, "R-DASH-02"),                 # floating layout
        (_is_zone_container, "R-DASH-03"),                # container
        (_is_zone_worksheet, "R-DASH-05"),                # worksheet zone
        (_is_zone_default, "R-DASH-01"),                  # tiled layout root
    ],
    "action": [
        (_action_kind_eq("filter"), "R-ACTION-01"),
        (_action_kind_eq("highlight"), "R-ACTION-02"),
        (_action_kind_eq("url"), "R-ACTION-03"),
        (_action_kind_eq("navigation"), "R-ACTION-04"),
        (_action_kind_eq("parameter"), "R-ACTION-05"),
        (_action_kind_eq("set"), "R-ACTION-06"),
    ],
    "parameter": [
        (_param_domain_eq("list"), "R-PARAM-01"),
        (_param_domain_eq("range"), "R-PARAM-02"),
        (_param_domain_eq("all"), "R-PARAM-03"),
    ],
    "palette": [
        (_palette_kind_eq("categorical"), "R-COLOR-01"),
        (_palette_kind_eq("sequential"), "R-COLOR-02"),
        (_palette_kind_eq("diverging"), "R-COLOR-02"),
    ],
    "filter": [
        (_is_filter_relative_date, "R-FILTER-05"),
        (_is_filter_top_n, "R-FILTER-06"),
        (_is_filter_default, "R-FILTER-01"),
    ],
    "style": [
        # Style entries are dispatched by sub-kind in walk_ir (not predicate),
        # because there is one rule per kind of style block.
    ],
    "datasource": [],
}


# Style sub-kind -> rule ID. Datasource and style families dispatch by content
# shape rather than a predicate list.
STYLE_RULES: Dict[str, str] = {
    "format_string": "R-FORMAT-01",
}

# Default datasource rule when nothing more specific applies.
DATASOURCE_DEFAULT_RULE = "R-CONN-01"


def _classify_datasource(ds: Dict[str, Any]) -> str:
    """Pick an R-CONN-* rule based on the connection metadata."""
    conn = ds.get("connection") or {}
    klass = (conn.get("class") or "").lower()
    if klass in {"hyper", "tde", "dataengine"}:
        return "R-CONN-02"
    if klass == "sqlproxy":
        return "R-CONN-07"
    if klass == "federated":
        return "R-CONN-04"
    return DATASOURCE_DEFAULT_RULE


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Decision:
    """One classification result for a single Tableau IR instance."""

    instance_id: str
    tableau_input: Dict[str, Any]
    rule_id: Optional[str]
    rule_name: Optional[str]
    bucket: Optional[str]
    strategy_default: Optional[str]
    strategy_effective: Optional[str]
    guardrails_applied: List[str]
    emission_target: Dict[str, Any]
    needs_review: bool
    omitted: bool
    warnings: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "tableau_input": self.tableau_input,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "bucket": self.bucket,
            "strategy_default": self.strategy_default,
            "strategy_effective": self.strategy_effective,
            "guardrails_applied": sorted(self.guardrails_applied),
            "emission_target": self.emission_target,
            "needs_review": self.needs_review,
            "omitted": self.omitted,
            "warnings": sorted(self.warnings),
            "notes": self.notes,
        }


@dataclass
class Unmatched:
    instance_id: str
    concept_kind: str
    name: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "concept_kind": self.concept_kind,
            "name": self.name,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# IR loading
# ---------------------------------------------------------------------------

# Filename -> concept family + concept-kind label for output.
IR_FILES: Dict[str, Tuple[str, str]] = {
    "calcs.json": ("calc", "calculated_field"),
    "worksheets.json": ("worksheet", "worksheet"),
    "dashboards.json": ("dashboard", "dashboard"),
    "actions.json": ("action", "action"),
    "parameters.json": ("parameter", "parameter"),
    "palettes.json": ("palette", "palette"),
    "styles.json": ("style", "style"),
    "datasources.json": ("datasource", "datasource"),
}


def load_ir(ir_dir: Path) -> Dict[str, Any]:
    """Load every IR JSON file present in ``ir_dir``. Missing files are skipped."""
    ir: Dict[str, Any] = {}
    for fname in IR_FILES:
        p = ir_dir / fname
        if not p.exists():
            continue
        try:
            with p.open() as fh:
                ir[fname] = json.load(fh)
        except json.JSONDecodeError as e:
            print(f"warning: could not parse {p}: {e}", file=sys.stderr)
            ir[fname] = []
    return ir


# ---------------------------------------------------------------------------
# Rules and guardrails
# ---------------------------------------------------------------------------


def load_rules_yaml(path: Path) -> Tuple[Dict[str, Any], str]:
    """Load the mapping-rules sidecar and return (parsed, sha256)."""
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    parsed = yaml.safe_load(raw) or {}
    return parsed, sha


def deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Deep-merge ``over`` into ``base``. Returns (merged, overrides_applied).

    Overrides are recorded as flat (key, default, user_value) records so that
    downstream consumers see exactly what changed.
    """
    merged: Dict[str, Any] = json.loads(json.dumps(base))  # cheap deep copy
    overrides: List[Dict[str, Any]] = []
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            sub_merged, sub_overrides = deep_merge(merged[k], v)
            merged[k] = sub_merged
            for o in sub_overrides:
                o["key"] = f"{k}.{o['key']}"
                overrides.append(o)
        else:
            if merged.get(k) != v:
                overrides.append({"key": k, "default": merged.get(k), "user_value": v})
            merged[k] = v
    return merged, overrides


def build_rule_index(rules_yaml: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Index rules by ID for O(1) lookup."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in rules_yaml.get("rules", []) or []:
        rid = r.get("id")
        if rid:
            out[rid] = r
    return out


def effective_guardrails(
    rules_yaml: Dict[str, Any],
    user_overrides: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Resolve the effective guardrails after merging user overrides.

    The sidecar guardrails block looks like:
        guardrails:
            lod_placement:
                default: model_layer
                options: [...]
                affects_rules: [...]
    The user override file looks like:
        guardrails:
            lod_placement: snowflake_view
    So we resolve to a flat key->value map of the effective choice for each
    guardrail before applying.

    Returns (effective, defaults, overrides_applied).
    """
    defaults: Dict[str, Any] = {}
    for k, v in (rules_yaml.get("guardrails") or {}).items():
        if isinstance(v, dict) and "default" in v:
            defaults[k] = v["default"]
        else:
            defaults[k] = v
    user_block = (user_overrides or {}).get("guardrails") or {}
    merged = dict(defaults)
    overrides: List[Dict[str, Any]] = []
    for k, v in user_block.items():
        if defaults.get(k) != v:
            overrides.append({"key": k, "default": defaults.get(k), "user_value": v})
        merged[k] = v
    return merged, defaults, overrides


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_instance(family: str, instance: Dict[str, Any]) -> Optional[str]:
    """Return the rule ID matching ``instance`` in ``family``, or None."""
    for pred, rid in MATCHERS.get(family, []):
        try:
            if pred(instance):
                return rid
        except Exception:
            # A malformed instance should not crash the engine; treat as no match.
            continue
    return None


def resolve_strategy(
    rule: Dict[str, Any],
    guardrails: Dict[str, Any],
    guardrail_defaults: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, List[str], List[str]]:
    """Decide the effective strategy given the rule's default and active guardrails.

    Returns (default_strategy, effective_strategy, guardrails_applied, warnings).

    The rule may name guardrails in ``guardrails_consumed``. For each consumed
    guardrail, if ``default_mapping.alt_strategies[guardrail][value]`` is set,
    we swap to that strategy. If the user has changed the guardrail away from
    its default and the rule does not enumerate an alternate for that value,
    we emit a warning. When ``guardrail_defaults`` is omitted we conservatively
    skip the "changed from default" check, since we cannot tell.
    """
    default_strategy = ((rule.get("default_mapping") or {}).get("strategy")) or "manual_review"
    effective = default_strategy
    consumed: List[str] = list(rule.get("guardrails_consumed") or [])
    warnings: List[str] = []

    # Look for an ``alt_strategies`` map under default_mapping for explicit
    # guardrail-keyed overrides. Shape:
    #   default_mapping:
    #     strategy: model_layer_measure
    #     alt_strategies:
    #       lod_placement:
    #         snowflake_view: snowflake_view
    #         workbook_layer: workbook_tile_calc
    alt = ((rule.get("default_mapping") or {}).get("alt_strategies")) or {}
    for g in consumed:
        gv = guardrails.get(g)
        if gv is None:
            continue
        bucket = alt.get(g) or {}
        if gv in bucket:
            effective = bucket[gv]
        else:
            # Only warn if the user actually changed the guardrail away from the default.
            default_val = (guardrail_defaults or {}).get(g) if guardrail_defaults is not None else None
            if guardrail_defaults is not None and gv != default_val:
                warnings.append(
                    f"guardrail '{g}' set to '{gv}' but rule {rule.get('id')} has no alt_strategies for that value; using default strategy '{default_strategy}'"
                )
    return default_strategy, effective, consumed, warnings


def emission_target_for(rule: Dict[str, Any], instance: Dict[str, Any], family: str) -> Dict[str, Any]:
    """Resolve the rule's emission target, substituting <name> with the instance name."""
    tgt = dict(rule.get("omni_target") or {})
    name = instance.get("name") or instance.get("caption") or ""
    if "yaml_path" in tgt and isinstance(tgt["yaml_path"], str):
        tgt["yaml_path"] = tgt["yaml_path"].replace("<name>", str(name))
    return tgt


def is_omitted(rule: Dict[str, Any]) -> bool:
    """A rule is omitted only when its bucket says no equivalent exists.

    `failure_mode` describes what to do on malformed input, not the default path.
    The YAML sidecar agent populated it with values like `reject` / `warn_and_drop`
    even for GREEN rules. So we key omission strictly off the bucket label, with
    RED meaning "no Omni equivalent, drop with warning."
    """
    return (rule.get("bucket") or "").upper() == "RED"


def needs_review(rule: Dict[str, Any]) -> bool:
    bucket = (rule.get("bucket") or "").upper()
    fm = (rule.get("failure_mode") or "").lower()
    return bucket in {"YELLOW", "RED"} or fm in {"manual_review", "best_effort"}


# ---------------------------------------------------------------------------
# Per-family walkers
# ---------------------------------------------------------------------------


def _summarize_calc(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "concept_kind": "calculated_field",
        "name": c.get("name"),
        "caption": c.get("caption"),
        "datasource": c.get("datasource"),
        "formula": c.get("formula"),
        "datatype": c.get("datatype"),
        "is_lod": bool(c.get("is_lod")),
        "lod_kind": c.get("lod_kind"),
        "is_table_calc": bool(c.get("is_table_calc")),
    }


def _extract_mark_type(marks: Any) -> Optional[str]:
    """Read mark type from either the rich `{type: ...}` shape or extract.py's `[{class: ...}]`."""
    if isinstance(marks, dict):
        return marks.get("type") or marks.get("class")
    if isinstance(marks, list) and marks:
        first = marks[0] if isinstance(marks[0], dict) else {}
        return first.get("type") or first.get("class")
    return None


def _summarize_worksheet(w: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "concept_kind": "worksheet",
        "name": w.get("name"),
        "mark_type": _extract_mark_type(w.get("marks")),
        "dual_axis": bool(w.get("dual_axis")),
        "has_trellis": bool((w.get("trellis") or {}).get("row_pills") or (w.get("trellis") or {}).get("col_pills")),
        # extract.py emits `datasources`; richer IRs may emit `datasource_refs`.
        "datasource_refs": w.get("datasource_refs") or w.get("datasources") or [],
    }


def _zone_kind(z: Dict[str, Any]) -> str:
    """Classify a zone using either rich `kind` or extract.py's `type` + `worksheet_ref`."""
    if z.get("kind"):
        return z["kind"]
    if z.get("worksheet_ref"):
        return "worksheet"
    t = (z.get("type") or "").lower()
    if t.startswith("layout"):
        return "container"
    return t or "unknown"


def _summarize_zone(z: Dict[str, Any], dash_name: str) -> Dict[str, Any]:
    kind = _zone_kind(z)
    # extract.py uses `param: horz|vert` for container direction.
    param = (z.get("param") or "").lower()
    container_kind = z.get("container_kind") or (
        "horizontal" if param.startswith("horz") else "vertical" if param.startswith("vert") else None
    )
    return {
        "concept_kind": "dashboard_zone",
        "dashboard": dash_name,
        "kind": kind,
        "name": z.get("name") or z.get("worksheet_ref") or kind,
        "floating": bool(z.get("floating") or z.get("is_floating")),
        "container_kind": container_kind,
        "position": {"x": z.get("x"), "y": z.get("y"), "w": z.get("w"), "h": z.get("h")},
    }


def _summarize_action(a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "concept_kind": "action",
        "name": a.get("name"),
        "kind": a.get("kind"),
        "source": a.get("source"),
        "target": a.get("target"),
    }


def _summarize_parameter(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "concept_kind": "parameter",
        "name": p.get("name"),
        "domain_kind": p.get("domain_kind"),
        "datatype": p.get("datatype"),
        "current_value": p.get("current_value"),
    }


def _summarize_palette(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "concept_kind": "palette",
        "name": p.get("name"),
        "kind": p.get("kind"),
        "color_count": len(p.get("colors") or []),
    }


def _summarize_style(s: Dict[str, Any], sub_kind: str, field_name: str, value: Any) -> Dict[str, Any]:
    return {
        "concept_kind": f"style_{sub_kind}",
        "worksheet": s.get("worksheet"),
        "field": field_name,
        "value": value,
    }


def _summarize_filter(f: Dict[str, Any], host: str) -> Dict[str, Any]:
    return {
        "concept_kind": "filter",
        "host": host,
        "field": f.get("field"),
        "kind": f.get("kind"),
        "values": f.get("values"),
    }


def _flatten_zones(zones: List[Dict[str, Any]], dash_name: str, path: str = "") -> List[Tuple[str, Dict[str, Any]]]:
    """Walk the zone tree depth-first, yielding (instance_id, zone) tuples."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    for idx, z in enumerate(zones or []):
        node_path = f"{path}[{idx}]" if path else f"[{idx}]"
        out.append((f"dashboards.{dash_name}.zones{node_path}", z))
        children = z.get("children") or []
        if children:
            out.extend(_flatten_zones(children, dash_name, f"{node_path}.children"))
    return out


# ---------------------------------------------------------------------------
# Decision construction
# ---------------------------------------------------------------------------


def build_decision(
    instance_id: str,
    summary: Dict[str, Any],
    family: str,
    instance: Dict[str, Any],
    rule_index: Dict[str, Dict[str, Any]],
    guardrails: Dict[str, Any],
    guardrail_defaults: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Decision], Optional[Unmatched]]:
    """Classify a single instance and return either a Decision or an Unmatched record."""
    rid = classify_instance(family, instance)
    if rid is None:
        return None, Unmatched(
            instance_id=instance_id,
            concept_kind=summary.get("concept_kind", family),
            name=summary.get("name", ""),
            reason=f"no matcher fired for family '{family}'",
        )
    rule = rule_index.get(rid)
    if rule is None:
        return None, Unmatched(
            instance_id=instance_id,
            concept_kind=summary.get("concept_kind", family),
            name=summary.get("name", ""),
            reason=f"matcher returned rule id '{rid}' which is not in the rules YAML",
        )
    default_strategy, effective_strategy, consumed, warnings = resolve_strategy(rule, guardrails, guardrail_defaults)
    return (
        Decision(
            instance_id=instance_id,
            tableau_input=summary,
            rule_id=rid,
            rule_name=rule.get("name"),
            bucket=rule.get("bucket"),
            strategy_default=default_strategy,
            strategy_effective=effective_strategy,
            guardrails_applied=consumed,
            emission_target=emission_target_for(rule, instance, family),
            needs_review=needs_review(rule),
            omitted=is_omitted(rule),
            warnings=warnings,
            notes=rule.get("notes", "") or "",
        ),
        None,
    )


def walk_ir(
    ir: Dict[str, Any],
    rule_index: Dict[str, Dict[str, Any]],
    guardrails: Dict[str, Any],
    guardrail_defaults: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Decision], List[Unmatched]]:
    """Walk every IR file and classify every instance."""
    decisions: List[Decision] = []
    unmatched: List[Unmatched] = []

    # calcs
    for idx, c in enumerate(ir.get("calcs.json") or []):
        d, u = build_decision(f"calcs[{idx}]", _summarize_calc(c), "calc", c, rule_index, guardrails, guardrail_defaults)
        (decisions if d else unmatched).append(d or u)

    # worksheets (and their filters)
    for idx, w in enumerate(ir.get("worksheets.json") or []):
        d, u = build_decision(f"worksheets[{idx}]", _summarize_worksheet(w), "worksheet", w, rule_index, guardrails, guardrail_defaults)
        (decisions if d else unmatched).append(d or u)
        for fidx, f in enumerate(w.get("filters") or []):
            host = w.get("name", f"worksheets[{idx}]")
            d, u = build_decision(
                f"worksheets[{idx}].filters[{fidx}]",
                _summarize_filter(f, host),
                "filter",
                f,
                rule_index,
                guardrails,
                guardrail_defaults,
            )
            (decisions if d else unmatched).append(d or u)

    # dashboards: walk zones, walk dashboard-level filters
    for idx, dash in enumerate(ir.get("dashboards.json") or []):
        dash_name = dash.get("name", f"dashboards[{idx}]")
        for zid, z in _flatten_zones(dash.get("zones") or [], dash_name):
            d, u = build_decision(zid, _summarize_zone(z, dash_name), "zone", z, rule_index, guardrails, guardrail_defaults)
            (decisions if d else unmatched).append(d or u)
        for fidx, f in enumerate(dash.get("filters") or []):
            d, u = build_decision(
                f"dashboards[{idx}].filters[{fidx}]",
                _summarize_filter(f, dash_name),
                "filter",
                f,
                rule_index,
                guardrails,
                guardrail_defaults,
            )
            (decisions if d else unmatched).append(d or u)

    # actions
    for idx, a in enumerate(ir.get("actions.json") or []):
        d, u = build_decision(f"actions[{idx}]", _summarize_action(a), "action", a, rule_index, guardrails, guardrail_defaults)
        (decisions if d else unmatched).append(d or u)

    # parameters
    for idx, p in enumerate(ir.get("parameters.json") or []):
        d, u = build_decision(f"parameters[{idx}]", _summarize_parameter(p), "parameter", p, rule_index, guardrails, guardrail_defaults)
        (decisions if d else unmatched).append(d or u)

    # palettes
    for idx, p in enumerate(ir.get("palettes.json") or []):
        d, u = build_decision(f"palettes[{idx}]", _summarize_palette(p), "palette", p, rule_index, guardrails, guardrail_defaults)
        (decisions if d else unmatched).append(d or u)

    # styles: each style block can carry multiple format strings, fonts, and cond rules.
    # We emit one decision per format string and one per cond rule, classified by
    # the dedicated style rule IDs in the YAML (R-FORMAT-* family).
    #
    # The IR shape here varies: a richer extractor may emit a list of per-worksheet
    # style blocks, while extract.py emits a single dict with global_styles / format_rules /
    # conditional_formatting. Normalize both shapes to a list of dicts before iteration.
    styles_raw = ir.get("styles.json")
    if isinstance(styles_raw, dict):
        styles_list = [styles_raw]
    elif isinstance(styles_raw, list):
        styles_list = [s for s in styles_raw if isinstance(s, dict)]
    else:
        styles_list = []
    for idx, s in enumerate(styles_list):
        fmt_strings = (s.get("format_strings") or {})
        for field_name, value in sorted(fmt_strings.items()):
            # Synthesize an instance shape the style matcher can use.
            instance = {"sub_kind": "format_string", "field": field_name, "value": value}
            # Style rules are indexed directly by ID via STYLE_RULES.
            rid = STYLE_RULES["format_string"]
            rule = rule_index.get(rid)
            if rule is None:
                unmatched.append(
                    Unmatched(
                        instance_id=f"styles[{idx}].format_strings.{field_name}",
                        concept_kind="style_format_string",
                        name=field_name,
                        reason=f"rule {rid} not in YAML",
                    )
                )
                continue
            default_strategy, effective_strategy, consumed, warnings = resolve_strategy(rule, guardrails, guardrail_defaults)
            decisions.append(
                Decision(
                    instance_id=f"styles[{idx}].format_strings.{field_name}",
                    tableau_input=_summarize_style(s, "format_string", field_name, value),
                    rule_id=rid,
                    rule_name=rule.get("name"),
                    bucket=rule.get("bucket"),
                    strategy_default=default_strategy,
                    strategy_effective=effective_strategy,
                    guardrails_applied=consumed,
                    emission_target=emission_target_for(rule, {"name": field_name}, "style"),
                    needs_review=needs_review(rule),
                    omitted=is_omitted(rule),
                    warnings=warnings,
                    notes=rule.get("notes", "") or "",
                )
            )

    # datasources: one decision per datasource describing the upstream connection.
    for idx, ds in enumerate(ir.get("datasources.json") or []):
        rid = _classify_datasource(ds)
        rule = rule_index.get(rid)
        summary = {
            "concept_kind": "datasource",
            "name": ds.get("name"),
            "caption": ds.get("caption"),
            "connection": ds.get("connection"),
        }
        if rule is None:
            unmatched.append(
                Unmatched(
                    instance_id=f"datasources[{idx}]",
                    concept_kind="datasource",
                    name=ds.get("name", ""),
                    reason=f"rule {rid} not in YAML",
                )
            )
            continue
        default_strategy, effective_strategy, consumed, warnings = resolve_strategy(rule, guardrails)
        decisions.append(
            Decision(
                instance_id=f"datasources[{idx}]",
                tableau_input=summary,
                rule_id=rid,
                rule_name=rule.get("name"),
                bucket=rule.get("bucket"),
                strategy_default=default_strategy,
                strategy_effective=effective_strategy,
                guardrails_applied=consumed,
                emission_target=emission_target_for(rule, ds, "datasource"),
                needs_review=needs_review(rule),
                omitted=is_omitted(rule),
                warnings=warnings,
                notes=rule.get("notes", "") or "",
            )
        )

    # Sort everything for determinism.
    decisions.sort(key=lambda d: d.instance_id)
    unmatched.sort(key=lambda u: u.instance_id)
    return decisions, unmatched


# ---------------------------------------------------------------------------
# Summary and output
# ---------------------------------------------------------------------------


def summarize(decisions: List[Decision], unmatched: List[Unmatched]) -> Dict[str, Any]:
    by_bucket = Counter(d.bucket or "UNKNOWN" for d in decisions)
    by_family = Counter((d.rule_id or "").split("-")[0] + "-" + (d.rule_id or "").split("-")[1] for d in decisions if d.rule_id)
    return {
        "total_instances": len(decisions) + len(unmatched),
        "by_bucket": dict(sorted(by_bucket.items())),
        "by_family": dict(sorted(by_family.items())),
        "needs_review_count": sum(1 for d in decisions if d.needs_review),
        "omitted_count": sum(1 for d in decisions if d.omitted),
        "no_rule_matched_count": len(unmatched),
    }


def write_decisions(
    out_path: Path,
    ir_dir: Path,
    rules_sha: str,
    guardrails_effective: Dict[str, Any],
    overrides_applied: List[Dict[str, Any]],
    decisions: List[Decision],
    unmatched: List[Unmatched],
) -> None:
    payload = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_ir_dir": str(ir_dir),
        "rules_yaml_sha": rules_sha,
        "guardrails_effective": guardrails_effective,
        "guardrail_overrides_applied": overrides_applied,
        "decisions": [d.to_dict() for d in decisions],
        "summary": summarize(decisions, unmatched),
        "unmatched": [u.to_dict() for u in unmatched],
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def print_stderr_summary(decisions: List[Decision], unmatched: List[Unmatched]) -> None:
    summary = summarize(decisions, unmatched)
    print("apply_rules summary", file=sys.stderr)
    print(f"  total instances: {summary['total_instances']}", file=sys.stderr)
    print(f"  by bucket:       {summary['by_bucket']}", file=sys.stderr)
    print(f"  needs review:    {summary['needs_review_count']}", file=sys.stderr)
    print(f"  omitted:         {summary['omitted_count']}", file=sys.stderr)
    print(f"  unmatched:       {summary['no_rule_matched_count']}", file=sys.stderr)
    top_rules = Counter(d.rule_id for d in decisions if d.rule_id).most_common(5)
    if top_rules:
        print("  top rules fired:", file=sys.stderr)
        for rid, n in top_rules:
            print(f"    {rid}: {n}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Apply the Tableau-to-Omni mapping rules to an extracted IR.")
    p.add_argument("--ir-dir", required=True, type=Path, help="Directory containing extract.py output JSON files.")
    p.add_argument("--rules-yaml", required=True, type=Path, help="Path to the mapping-rules.yaml sidecar.")
    p.add_argument("--guardrails-yaml", type=Path, default=None, help="Optional user guardrail overrides YAML.")
    p.add_argument("--out", required=True, type=Path, help="Output path for decisions.json.")
    p.add_argument("--allow-unmatched", action="store_true", help="Exit 0 even if some instances did not match a rule.")
    return p.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    if not args.ir_dir.exists():
        print(f"error: --ir-dir {args.ir_dir} does not exist", file=sys.stderr)
        return 2
    if not args.rules_yaml.exists():
        print(f"error: --rules-yaml {args.rules_yaml} does not exist", file=sys.stderr)
        return 2
    rules_yaml, rules_sha = load_rules_yaml(args.rules_yaml)
    user_overrides: Optional[Dict[str, Any]] = None
    if args.guardrails_yaml:
        if not args.guardrails_yaml.exists():
            print(f"error: --guardrails-yaml {args.guardrails_yaml} does not exist", file=sys.stderr)
            return 2
        user_overrides = yaml.safe_load(args.guardrails_yaml.read_bytes()) or {}
    guardrails, guardrail_defaults, overrides_applied = effective_guardrails(rules_yaml, user_overrides)
    for o in overrides_applied:
        print(f"guardrail override: {o['key']}: {o['default']} -> {o['user_value']}", file=sys.stderr)
    rule_index = build_rule_index(rules_yaml)
    ir = load_ir(args.ir_dir)
    decisions, unmatched = walk_ir(ir, rule_index, guardrails, guardrail_defaults)
    write_decisions(args.out, args.ir_dir, rules_sha, guardrails, overrides_applied, decisions, unmatched)
    print_stderr_summary(decisions, unmatched)
    if unmatched and not args.allow_unmatched:
        return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
