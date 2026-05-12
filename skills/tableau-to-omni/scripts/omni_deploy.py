"""Wrapper around the Omni CLI for the build phase of a Tableau-to-Omni migration.

Uses the official `omni` CLI rather than raw HTTP so the migration log shows
real CLI commands.

Subcommands:
    branch         Create a model branch from base model
    list-targets   List connections + models the user can build into
    import         POST a dashboard payload via `omni unstable documents-import`
    validate       Run `omni models validate` on the branch
    merge          Merge the branch via `omni models merge-branch`
    delete-branch  Delete the branch via `omni models delete-branch`

Each command prints the resolved `omni` invocation before running it, so the
migration log doubles as a CLI tutorial.

Examples:
    python3 omni_deploy.py list-targets
    python3 omni_deploy.py branch --base-model-id $MID --name tableau-mig-2026-01-01
    python3 omni_deploy.py import --payload payload.json
    python3 omni_deploy.py validate --branch-id <branch-id>
    python3 omni_deploy.py merge --branch-id <branch-id>
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def assert_cli() -> None:
    if shutil.which("omni") is None:
        sys.exit("error: `omni` CLI not on PATH.  Install with: brew tap exploreomni/tap && brew install omni")


def run(cmd: list[str], capture: bool = True) -> dict | str:
    """Run an omni CLI command, echo it, return parsed JSON or raw stdout."""
    print(f"  $ {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        sys.exit(f"omni CLI failed (exit {result.returncode}):\n{result.stderr}")
    if not capture:
        return ""
    out = result.stdout.strip()
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out


def cmd_list_targets(args: argparse.Namespace) -> int:
    print("Connections:", file=sys.stderr)
    conns = run(["omni", "connections", "list", "--compact", "--format", "json"])
    print(json.dumps(conns, indent=2))
    print("\nModels:", file=sys.stderr)
    models = run(["omni", "models", "list", "--compact", "--format", "json"])
    print(json.dumps(models, indent=2))
    return 0


def cmd_branch(args: argparse.Namespace) -> int:
    # CLI 1.0.4+ takes --name directly; the --body shape was removed.
    cmd = [
        "omni", "models", "create-branch", args.base_model_id,
        "--name", args.name,
        "--format", "json",
    ]
    if args.starting_point:
        # starting-point is not exposed as a top-level flag in 1.0.4; if needed,
        # use the raw HTTP API. For now we warn and proceed without it.
        print(f"warn: starting_point {args.starting_point!r} ignored; CLI 1.0.4 does not expose it", file=sys.stderr)
    result = run(cmd)
    print(json.dumps(result, indent=2))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    payload_path: Path = args.payload
    if not payload_path.exists():
        sys.exit(f"payload not found: {payload_path}")
    result = run([
        "omni", "unstable", "documents-import",
        "--body", payload_path.read_text(),
        "--format", "json",
    ])
    print(json.dumps(result, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    result = run([
        "omni", "models", "validate", args.branch_id,
        "--format", "json",
    ])
    print(json.dumps(result, indent=2))
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    result = run([
        "omni", "models", "merge-branch", args.branch_id,
        "--format", "json",
    ])
    print(json.dumps(result, indent=2))
    return 0


def cmd_delete_branch(args: argparse.Namespace) -> int:
    result = run([
        "omni", "models", "delete-branch", args.branch_id,
        "--format", "json",
    ])
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    assert_cli()

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-targets", help="List Omni connections + models")

    p_branch = sub.add_parser("branch", help="Create a model branch")
    p_branch.add_argument("--base-model-id", required=True)
    p_branch.add_argument("--name", required=True)
    p_branch.add_argument("--starting-point", default=None,
                          help="Optional starting point: 'shared', 'branch:<id>', or 'version:<id>'")

    p_imp = sub.add_parser("import", help="POST a dashboard payload via documents-import")
    p_imp.add_argument("--payload", type=Path, required=True)

    p_val = sub.add_parser("validate", help="Validate a model branch")
    p_val.add_argument("--branch-id", required=True)

    p_merge = sub.add_parser("merge", help="Merge a model branch into main")
    p_merge.add_argument("--branch-id", required=True)

    p_del = sub.add_parser("delete-branch", help="Delete a model branch")
    p_del.add_argument("--branch-id", required=True)

    args = ap.parse_args()

    return {
        "list-targets": cmd_list_targets,
        "branch": cmd_branch,
        "import": cmd_import,
        "validate": cmd_validate,
        "merge": cmd_merge,
        "delete-branch": cmd_delete_branch,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
