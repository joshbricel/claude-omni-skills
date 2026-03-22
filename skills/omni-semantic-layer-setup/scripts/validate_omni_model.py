"""
Omni Model Validator — Pre-merge validation for semantic layer YAML.

Catches real Omni model errors that structural checks miss:
1. Omni API validation (remote)
2. Format string validation
3. Aggregate type validation
4. Topic join graph validation
5. View reachability check
6. Relationship field reference validation
7. Auto-fix suggestions
"""

import os
import re
import sys
import requests

# ── Config ──────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("OMNI_BASE_URL", "")
API_KEY = os.environ.get("OMNI_API_KEY", "")
MODEL_ID = os.environ.get("OMNI_MODEL_ID", "")
BRANCH_ID = os.environ.get("OMNI_BRANCH_ID", "")

if not all([BASE_URL, API_KEY, MODEL_ID, BRANCH_ID]):
    print("ERROR: Missing required environment variables.")
    print("Set: OMNI_BASE_URL, OMNI_API_KEY, OMNI_MODEL_ID, OMNI_BRANCH_ID")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ── Valid Omni Formats ──────────────────────────────────────────────────────

VALID_FORMAT_BASES = {
    # Numeric
    "number", "percent", "id", "billions", "millions", "thousands", "big",
    # Currency - accounting
    "accounting", "usdaccounting", "euraccounting", "gbpaccounting", "audaccounting",
    # Currency - currency
    "currency", "usdcurrency", "eurcurrency", "gbpcurrency", "audcurrency",
    # Currency - big currency
    "bigcurrency", "bigusdcurrency", "bigeurcurrency", "biggbpcurrency", "bigaudcurrency",
    # Currency - financial
    "financial", "audfinancial",
}

# Common mistakes → suggested fix
FORMAT_SUGGESTIONS = {
    "usd": "usdcurrency",
    "dollar": "usdcurrency",
    "dollars": "usdcurrency",
    "eur": "eurcurrency",
    "euro": "eurcurrency",
    "gbp": "gbpcurrency",
    "aud": "audcurrency",
    "pct": "percent",
    "percentage": "percent",
    "int": "number",
    "integer": "number",
    "float": "number",
    "decimal": "number",
}

# ── Valid Aggregate Types ───────────────────────────────────────────────────

VALID_AGGREGATE_TYPES = {
    "sum", "count", "count_distinct", "average", "min", "max", "median",
    "list", "percentile",
    "sum_distinct_on", "average_distinct_on", "median_distinct_on",
    "percentile_distinct_on",
}

# ── Results Tracker ─────────────────────────────────────────────────────────

class Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.fixes = []

    def ok(self, msg):
        self.passed += 1
        print(f"   PASS: {msg}")

    def fail(self, msg, fix=None):
        self.failed += 1
        print(f"   FAIL: {msg}")
        if fix:
            self.fixes.append(fix)

    def warn(self, msg):
        self.warnings += 1
        print(f"   WARN: {msg}")


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_branch_yaml():
    url = f"{BASE_URL}/api/v1/models/{MODEL_ID}/yaml?branchId={BRANCH_ID}"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def is_valid_format(fmt):
    """Check if a format string is valid (base or base_N precision)."""
    fmt_lower = fmt.lower()
    if fmt_lower in VALID_FORMAT_BASES:
        return True
    # Check for precision suffix like usdcurrency_0, percent_2
    match = re.match(r'^(.+)_(\d+)$', fmt_lower)
    if match and match.group(1) in VALID_FORMAT_BASES:
        return True
    return False


def parse_view_yaml(content):
    """Extract dimensions and measures with their properties from view YAML."""
    fields = {}
    current_section = None
    current_field = None
    current_props = {}

    for line in content.split('\n'):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        if stripped in ('dimensions:', 'measures:'):
            if current_field and current_section:
                fields[f"{current_section}.{current_field}"] = current_props
            current_section = stripped.rstrip(':')
            current_field = None
            current_props = {}
            continue

        if current_section and stripped and not stripped.startswith('-') and ':' in stripped:
            if indent == 2:
                if current_field:
                    fields[f"{current_section}.{current_field}"] = current_props
                current_field = stripped.split(':')[0].strip()
                current_props = {}
            elif indent == 4 and current_field:
                key = stripped.split(':')[0].strip()
                value = ':'.join(stripped.split(':')[1:]).strip()
                if value.startswith("'") or value.startswith('"'):
                    value = value.strip("'\"")
                current_props[key] = value

    if current_field and current_section:
        fields[f"{current_section}.{current_field}"] = current_props

    return fields


def parse_relationships(content):
    """Parse the relationships YAML into a list of relationship dicts."""
    rels = []
    current = {}
    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('- join_from_view:'):
            if current:
                rels.append(current)
            current = {"from": stripped.split(':')[1].strip()}
        elif stripped.startswith('join_to_view:'):
            current["to"] = stripped.split(':')[1].strip()
        elif stripped.startswith('on_sql:'):
            current["on_sql"] = ':'.join(stripped.split(':')[1:]).strip()
        elif stripped.startswith('relationship_type:'):
            current["type"] = stripped.split(':')[1].strip()
    if current:
        rels.append(current)
    return rels


def parse_topic_joins(content):
    """Parse topic YAML to extract the nested join structure.
    Returns a list of (parent_view, child_view) tuples representing implied joins."""
    joins_section = False
    join_pairs = []
    indent_stack = []  # (indent_level, view_name)

    for line in content.split('\n'):
        stripped = line.strip()
        if stripped == 'joins:':
            joins_section = True
            indent_stack = []
            continue

        if joins_section:
            # End of joins section
            if stripped and not stripped.startswith(' ') and ':' in stripped and not line.startswith('  '):
                if not line.startswith(' '):
                    joins_section = False
                    continue

            if not stripped or stripped.startswith('#'):
                continue

            indent = len(line) - len(line.lstrip())

            # Extract view name (key before the colon)
            if ':' in stripped:
                view_name = stripped.split(':')[0].strip()

                # Pop stack entries at same or deeper indent
                while indent_stack and indent_stack[-1][0] >= indent:
                    indent_stack.pop()

                if indent_stack:
                    parent = indent_stack[-1][1]
                    join_pairs.append((parent, view_name))
                else:
                    # Top-level join from base_view
                    join_pairs.append(("__base__", view_name))

                indent_stack.append((indent, view_name))

    return join_pairs


def get_base_view(topic_content):
    """Extract base_view from topic YAML."""
    for line in topic_content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('base_view:'):
            return stripped.split(':')[1].strip()
    return None


# ── Check 1: Omni API Validation ───────────────────────────────────────────

def check_api_validation(results):
    print("\n1. OMNI API VALIDATION")
    print("   " + "-" * 50)

    url = f"{BASE_URL}/api/v1/models/{MODEL_ID}/validate?branchId={BRANCH_ID}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            results.warn(f"API returned {resp.status_code}: {resp.text[:200]}")
            return

        data = resp.json()

        # API returns a list of {message, is_warning, yaml_path, auto_fix}
        if isinstance(data, list):
            errors = [d for d in data if not d.get("is_warning", False)]
            warnings = [d for d in data if d.get("is_warning", False)]
        else:
            errors = data.get("errors", [])
            warnings = data.get("warnings", [])

        if errors:
            for e in errors:
                msg = e.get("message", str(e)) if isinstance(e, dict) else str(e)
                results.fail(msg)
        else:
            results.ok(f"0 errors from Omni validator")

        if warnings:
            for w in warnings:
                msg = w.get("message", str(w)) if isinstance(w, dict) else str(w)
                results.warn(msg)
        else:
            results.ok(f"0 warnings from Omni validator")

    except requests.RequestException as e:
        results.warn(f"Could not reach Omni API: {e}")


# ── Check 2: Format Strings ────────────────────────────────────────────────

def check_format_strings(yaml_data, results):
    print("\n2. FORMAT STRINGS")
    print("   " + "-" * 50)

    found_any = False
    all_valid = True

    for fname, content in yaml_data.get("files", {}).items():
        if not fname.endswith(".view"):
            continue

        view_name = fname.replace("PUBLIC/", "").replace(".view", "")
        fields = parse_view_yaml(content)

        for field_key, props in fields.items():
            fmt = props.get("format")
            if not fmt:
                continue

            found_any = True

            if is_valid_format(fmt):
                pass  # valid, don't clutter output
            else:
                all_valid = False
                suggestion = FORMAT_SUGGESTIONS.get(fmt.lower(), "usdcurrency")
                results.fail(
                    f'{view_name} > {field_key.split(".")[-1]}: "{fmt}" is not valid. Use "{suggestion}"',
                    fix=f'In build_semantic_layer.py, change format: {fmt} → format: {suggestion} (in {view_name})'
                )

    if not found_any:
        results.warn("No format strings found in any view")
    elif all_valid:
        # Count total
        total = sum(
            1 for f, c in yaml_data.get("files", {}).items()
            if f.endswith(".view")
            for _, p in parse_view_yaml(c).items()
            if p.get("format")
        )
        results.ok(f"All {total} format strings are valid")


# ── Check 3: Aggregate Types ───────────────────────────────────────────────

def check_aggregate_types(yaml_data, results):
    print("\n3. AGGREGATE TYPES")
    print("   " + "-" * 50)

    total = 0
    all_valid = True

    for fname, content in yaml_data.get("files", {}).items():
        if not fname.endswith(".view"):
            continue

        view_name = fname.replace("PUBLIC/", "").replace(".view", "")
        fields = parse_view_yaml(content)

        for field_key, props in fields.items():
            agg = props.get("aggregate_type")
            if not agg:
                continue

            total += 1

            if agg.lower() not in VALID_AGGREGATE_TYPES:
                all_valid = False
                results.fail(
                    f'{view_name} > {field_key.split(".")[-1]}: aggregate_type "{agg}" is not valid. '
                    f'Valid types: {", ".join(sorted(VALID_AGGREGATE_TYPES))}',
                    fix=f'In build_semantic_layer.py, fix aggregate_type: {agg} in {view_name}'
                )

    if all_valid and total > 0:
        results.ok(f"All {total} aggregate_type values are valid")
    elif total == 0:
        results.warn("No aggregate_type values found")


# ── Check 4: Topic Join Graph ──────────────────────────────────────────────

def check_topic_join_graph(yaml_data, results):
    print("\n4. TOPIC JOIN GRAPH")
    print("   " + "-" * 50)

    # Get topic content
    topic_content = None
    for fname, content in yaml_data.get("files", {}).items():
        if fname.endswith(".topic"):
            topic_content = content
            break

    if not topic_content:
        results.fail("No topic file found")
        return

    base_view = get_base_view(topic_content)
    if not base_view:
        results.fail("No base_view found in topic")
        return

    # Parse topic joins
    topic_joins = parse_topic_joins(topic_content)

    # Parse relationships to build the actual graph
    rel_content = yaml_data.get("files", {}).get("relationships", "")
    relationships = parse_relationships(rel_content)

    # Build undirected relationship graph (a relationship works both directions for join purposes)
    rel_edges = set()
    for r in relationships:
        rel_edges.add((r["from"], r["to"]))
        rel_edges.add((r["to"], r["from"]))

    # For each topic join, check that a relationship supports it
    all_valid = True
    for parent, child in topic_joins:
        actual_parent = base_view if parent == "__base__" else parent

        if (actual_parent, child) in rel_edges:
            pass  # valid
        else:
            all_valid = False
            # Find what the child IS connected to
            connected_to = [r["from"] for r in relationships if r["to"] == child]
            connected_to += [r["to"] for r in relationships if r["from"] == child]
            connected_to = [c for c in connected_to if c != actual_parent]

            fix_suggestion = ""
            if connected_to:
                fix_suggestion = f"Move {child} under {connected_to[0]} in the topic joins"

            results.fail(
                f'Topic declares {child} joined via {actual_parent}, but no relationship exists between them',
                fix=f'FIX: {fix_suggestion}' if fix_suggestion else None
            )

    if all_valid:
        results.ok(f"All {len(topic_joins)} topic join paths have matching relationships")


# ── Check 5: View Reachability ──────────────────────────────────────────────

def check_view_reachability(yaml_data, results):
    print("\n5. VIEW REACHABILITY")
    print("   " + "-" * 50)

    # Get topic
    topic_content = None
    for fname, content in yaml_data.get("files", {}).items():
        if fname.endswith(".topic"):
            topic_content = content
            break

    if not topic_content:
        results.fail("No topic file found")
        return

    base_view = get_base_view(topic_content)
    uses_all_views = "all_views.*" in topic_content

    # Build relationship adjacency from actual relationships
    rel_content = yaml_data.get("files", {}).get("relationships", "")
    relationships = parse_relationships(rel_content)

    adjacency = {}
    for r in relationships:
        adjacency.setdefault(r["from"], set()).add(r["to"])
        adjacency.setdefault(r["to"], set()).add(r["from"])

    # BFS from base_view through topic join structure
    # But we also need to respect the topic's join tree — only traverse joins declared in topic
    topic_joins = parse_topic_joins(topic_content)

    # Build the topic's declared join graph
    topic_adj = {}
    for parent, child in topic_joins:
        actual_parent = base_view if parent == "__base__" else parent
        topic_adj.setdefault(actual_parent, set()).add(child)
        topic_adj.setdefault(child, set()).add(actual_parent)

    # Walk from base_view using ONLY topic-declared joins that also have valid relationships
    reachable = set()
    queue = [base_view]
    reachable.add(base_view)

    while queue:
        current = queue.pop(0)
        for neighbor in topic_adj.get(current, set()):
            if neighbor not in reachable:
                # Check if a relationship exists for this edge
                if (current, neighbor) in {(r["from"], r["to"]) for r in relationships} | \
                   {(r["to"], r["from"]) for r in relationships}:
                    reachable.add(neighbor)
                    queue.append(neighbor)

    # Get all views in the model
    all_views = set()
    for fname in yaml_data.get("files", {}).keys():
        if fname.endswith(".view"):
            view_name = fname.replace("PUBLIC/", "").replace(".view", "")
            all_views.add(view_name)

    unreachable = all_views - reachable
    if unreachable and uses_all_views:
        for v in sorted(unreachable):
            results.fail(
                f'{v} is not reachable from base_view {base_view}',
                fix=f'Fix the topic join structure so {v} is reachable, or remove it from fields'
            )
    elif unreachable:
        for v in sorted(unreachable):
            results.warn(f'{v} is not reachable from base_view {base_view} (may be intentional)')
    else:
        results.ok(f"All {len(all_views)} views are reachable from {base_view}")


# ── Check 6: Relationship Field References ─────────────────────────────────

def check_relationship_fields(yaml_data, results):
    print("\n6. RELATIONSHIP FIELD REFERENCES")
    print("   " + "-" * 50)

    rel_content = yaml_data.get("files", {}).get("relationships", "")
    relationships = parse_relationships(rel_content)

    # Build a map of view → set of dimension field names
    view_fields = {}
    for fname, content in yaml_data.get("files", {}).items():
        if not fname.endswith(".view"):
            continue
        view_name = fname.replace("PUBLIC/", "").replace(".view", "")
        fields = parse_view_yaml(content)
        dim_names = set()
        for field_key in fields:
            section, name = field_key.split('.', 1)
            if section == 'dimensions':
                dim_names.add(name)
        view_fields[view_name] = dim_names

    total_refs = 0
    all_valid = True

    for r in relationships:
        on_sql = r.get("on_sql", "")
        # Extract ${view.field} references
        refs = re.findall(r'\$\{(\w+)\.(\w+)\}', on_sql)

        for view, field in refs:
            total_refs += 1
            known_fields = view_fields.get(view, set())

            if not known_fields:
                all_valid = False
                results.fail(f'Relationship {r["from"]} → {r["to"]}: references unknown view "{view}"')
            elif field not in known_fields:
                all_valid = False
                results.fail(
                    f'Relationship {r["from"]} → {r["to"]}: ${{{view}.{field}}} — '
                    f'field "{field}" not found in {view} dimensions',
                    fix=f'Add "{field}" as a dimension in {view}.view, or fix the on_sql reference'
                )

    if all_valid and total_refs > 0:
        results.ok(f"All {total_refs} join condition field references are valid")
    elif total_refs == 0:
        results.warn("No field references found in relationships")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate an Omni model branch before merging.")
    parser.add_argument("--merge", action="store_true",
                        help="If validation passes, merge the branch to production")
    parser.add_argument("--local", action="store_true",
                        help="Validate local YAML from build_semantic_layer.py (skip API fetch)")
    args = parser.parse_args()

    print("=" * 60)
    print("OMNI MODEL VALIDATION")
    print(f"Branch ID: {BRANCH_ID}")
    print("=" * 60)

    results = Results()

    # Fetch branch YAML
    print("\nFetching branch YAML...")
    if args.local:
        print("  --local flag: loading from build_semantic_layer.py...")
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import build_semantic_layer as bsl
        yaml_data = {"files": {
            "PUBLIC/sf_users.view": bsl.SF_USERS_VIEW,
            "PUBLIC/sf_accounts.view": bsl.SF_ACCOUNTS_VIEW,
            "PUBLIC/sf_contacts.view": bsl.SF_CONTACTS_VIEW,
            "PUBLIC/sf_opportunities.view": bsl.SF_OPPORTUNITIES_VIEW,
            "PUBLIC/sf_activities.view": bsl.SF_ACTIVITIES_VIEW,
            "PUBLIC/sf_campaign_members.view": bsl.SF_CAMPAIGN_MEMBERS_VIEW,
            "relationships": bsl.RELATIONSHIPS,
            "salesforce_crm.topic": bsl.SALESFORCE_TOPIC,
            "model": bsl.MODEL_CONFIG,
        }}
        file_count = len(yaml_data["files"])
        print(f"  Loaded {file_count} files from build_semantic_layer.py")
    else:
        try:
            yaml_data = get_branch_yaml()
            file_count = len(yaml_data.get("files", {}))
            print(f"  Found {file_count} files on branch")
        except Exception as e:
            print(f"  ERROR: Could not fetch branch YAML: {e}")
            print("  Re-run with --local to validate local YAML instead.")
            return 1

    # Run all checks
    check_api_validation(results)
    check_format_strings(yaml_data, results)
    check_aggregate_types(yaml_data, results)
    check_topic_join_graph(yaml_data, results)
    check_view_reachability(yaml_data, results)
    check_relationship_fields(yaml_data, results)

    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {results.passed} passed, {results.failed} failed, {results.warnings} warnings")

    if results.fixes:
        print(f"\nSUGGESTED FIXES:")
        for i, fix in enumerate(results.fixes, 1):
            print(f"  {i}. {fix}")

    if results.failed > 0:
        print("\nVALIDATION FAILED — do not merge to production.")
        print("Fix the issues above and re-deploy to the branch first.")
        return 1

    # Merge gate
    if not args.merge:
        print("\nVALIDATION PASSED.")
        print("Review the branch in Omni, then merge with:")
        print(f"  python3 validate_omni_model.py --merge")
        return 0

    # Merge to production
    print("\nMerging branch to production...")
    merge_url = f"{BASE_URL}/api/v1/models/{MODEL_ID}/merge?branchId={BRANCH_ID}"
    resp = requests.post(merge_url, headers=HEADERS)
    if resp.status_code == 200:
        print("  Merged successfully!")
        return 0
    else:
        print(f"  Merge failed: {resp.status_code}: {resp.text}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
