"""Seed a freshly-imported workbook model with the migration's view + topic YAML.

Required because Omni's documents-import API forces workbook.baseModelId = SHARED.
The workbook can't see view/topic additions made on a branch.  Without this step,
the imported dashboard 500s with "Could not convert to OmniQuery".

Run this AFTER `omni unstable documents-import` succeeds, with the workbook ID
returned in the import response (response.workbook.id).

Usage:
    python3 seed_workbook.py \
      --workbook-id <workbook-uuid> \
      --yaml-dir /path/to/yaml \
      [--also-validate]

The --yaml-dir is the same directory whose files were earlier pushed to the
branch.  This script writes the same files to the workbook model, making the
workbook self-contained for query resolution.

VIEW PREFIX TRAP (the second undocumented behavior we hit):

When you POST a `.view` file to `<SCHEMA>/<viewname>.view` on a workbook,
Omni registers the view as `<schema>__<viewname>` (lowercased).  E.g.
`ACME_EVENTS/vw_events_wide.view` shows up in `models get-views` as
`acme_events__vw_events_wide`.  But the saved queries on the dashboard
reference the un-prefixed `vw_events_wide`, so the topic's `base_view:
vw_events_wide` doesn't resolve, and document-load conversion fails.

Workaround: post the view with the un-prefixed file name (root path, no
schema directory).  Omni still stores it under the schema dir internally
(yaml-get returns it at `<SCHEMA>/<view>.view`), but the registered view
NAME is the un-prefixed `<view>`.  This script handles the dance:

  1.  yaml-create with the path the caller specified.
  2.  If the resulting view is auto-prefixed (`<schema>__<view>`), delete
      and re-seed at the un-prefixed root path.
  3.  Topic files (`*.topic`) are passed through unchanged.

Env: OMNI_API_TOKEN, OMNI_BASE_URL.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def cli(*args: str):
    base_url = os.environ.get("OMNI_BASE_URL")
    token = os.environ.get("OMNI_API_TOKEN")
    cmd = ["omni"]
    if base_url:
        cmd += ["--base-url", base_url]
    if token:
        cmd += ["--token", token]
    cmd += [*args, "--format", "json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"omni CLI failed: {' '.join(cmd[:6])} ...\n{r.stderr}")
    out = r.stdout.strip()
    if not out:
        return {}
    parsed = json.loads(out)
    if isinstance(parsed, dict) and parsed.get("status", 0) >= 400 and "detail" in parsed:
        sys.exit(f"omni API error {parsed['status']}: {parsed['detail']}")
    return parsed


def yaml_create(workbook_id: str, file_name: str, yaml_text: str) -> dict:
    body = json.dumps({"fileName": file_name, "yaml": yaml_text})
    cmd = ["omni", "models", "yaml-create", workbook_id, "--body", body, "--format", "json"]
    if "OMNI_BASE_URL" in os.environ:
        cmd += ["--base-url", os.environ["OMNI_BASE_URL"]]
    if "OMNI_API_TOKEN" in os.environ:
        cmd += ["--token", os.environ["OMNI_API_TOKEN"]]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"success": False, "error": r.stderr}
    return json.loads(r.stdout) if r.stdout.strip() else {}


def yaml_delete(workbook_id: str, file_name: str) -> dict:
    cmd = ["omni", "models", "yaml-delete", workbook_id, "--filename", file_name, "--format", "json"]
    if "OMNI_BASE_URL" in os.environ:
        cmd += ["--base-url", os.environ["OMNI_BASE_URL"]]
    if "OMNI_API_TOKEN" in os.environ:
        cmd += ["--token", os.environ["OMNI_API_TOKEN"]]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return {"success": r.returncode == 0, "stderr": r.stderr}


def get_view_names(workbook_id: str) -> list[str]:
    resp = cli("models", "get-views", workbook_id)
    return [v.get("name") for v in resp.get("views", []) if isinstance(v, dict)]


def seed_view_unprefixed(workbook_id: str, schema_path: str, view_basename: str, yaml_text: str) -> None:
    """Seed a view file such that the registered view NAME is un-prefixed.

    The trap: posting `<SCHEMA>/<view>.view` registers the view as
    `<schema>__<view>` (lowercased schema prefix).  Saved query bodies
    reference the un-prefixed name, so they fail to resolve.

    The fix: post the same YAML body at the root path `<view>.view`.
    Omni stores it under `<SCHEMA>/<view>.view` internally (the YAML body's
    `schema:` field controls placement) but registers the un-prefixed view
    NAME.

    If the prefixed copy is already present (e.g. from a previous failed
    seed attempt), delete it first.
    """
    prefixed_path = f"{schema_path}/{view_basename}.view"
    root_path = f"{view_basename}.view"

    existing = get_view_names(workbook_id)
    schema_prefix = schema_path.lower() + "__"
    prefixed_name = schema_prefix + view_basename

    if prefixed_name in existing:
        print(f"     deleting auto-prefixed copy {prefixed_path}", file=sys.stderr)
        d = yaml_delete(workbook_id, prefixed_path)
        if not d["success"]:
            sys.exit(f"failed to delete prefixed copy of {prefixed_path}: {d.get('stderr')}")

    print(f"     seeding {view_basename} at root path (suppresses {schema_prefix} prefix)", file=sys.stderr)
    resp = yaml_create(workbook_id, root_path, yaml_text)
    if resp.get("status", 0) >= 400 or resp.get("success") is False:
        sys.exit(f"root-path seed rejected for {root_path}: {resp.get('saveError') or resp.get('detail') or resp}")


def main() -> int:
    if shutil.which("omni") is None:
        sys.exit("omni CLI not on PATH.  brew tap exploreomni/tap && brew install omni")

    ap = argparse.ArgumentParser()
    ap.add_argument("--workbook-id", required=True,
                    help="Workbook model ID (from the documents-import response.workbook.id)")
    ap.add_argument("--yaml-dir", type=Path, required=True,
                    help="Directory of YAML files to seed (mirrors the branch YAML)")
    ap.add_argument("--also-validate", action="store_true",
                    help="Run `omni models validate` after seeding")
    args = ap.parse_args()

    if not args.yaml_dir.exists():
        sys.exit(f"yaml-dir not found: {args.yaml_dir}")

    files = sorted(p for p in args.yaml_dir.rglob("*") if p.is_file() and p.suffix in (".view", ".topic"))
    if not files:
        sys.exit(f"no .view / .topic files in {args.yaml_dir}")

    # Two passes so views are registered before topics resolve `base_view`.
    views = [f for f in files if f.suffix == ".view"]
    topics = [f for f in files if f.suffix == ".topic"]

    for f in views:
        rel = f.relative_to(args.yaml_dir).as_posix()
        parts = rel.rsplit("/", 1)
        if len(parts) == 2:
            schema_path, fname = parts
            view_basename = fname[: -len(".view")]
            print(f"  -> view {rel}", file=sys.stderr)
            seed_view_unprefixed(args.workbook_id, schema_path, view_basename, f.read_text())
        else:
            # already at root
            print(f"  -> view {rel} (already root)", file=sys.stderr)
            resp = yaml_create(args.workbook_id, rel, f.read_text())
            if resp.get("status", 0) >= 400 or resp.get("success") is False:
                sys.exit(f"seed rejected for {rel}: {resp.get('saveError') or resp.get('detail') or resp}")

    for f in topics:
        rel = f.relative_to(args.yaml_dir).as_posix()
        print(f"  -> topic {rel}", file=sys.stderr)
        resp = yaml_create(args.workbook_id, rel, f.read_text())
        if resp.get("status", 0) >= 400 or resp.get("success") is False:
            sys.exit(f"seed rejected for {rel}: {resp.get('saveError') or resp.get('detail') or resp}")
        print(f"     ok", file=sys.stderr)

    if args.also_validate:
        print("Validating workbook...", file=sys.stderr)
        result = cli("models", "validate", args.workbook_id)
        # Filter to errors that block our migration; warnings about other
        # views (e.g. inherited tenant_flattened_fields) are not blockers.
        blocking = [
            e for e in (result if isinstance(result, list) else [])
            if not e.get("is_warning")
            and "tenant_flattened_fields" not in (e.get("yaml_path") or "")
        ]
        if blocking:
            print("VALIDATION ERRORS:", file=sys.stderr)
            print(json.dumps(blocking, indent=2))
            return 1
        print("  clean (or only inherited-model warnings)", file=sys.stderr)

    print(f"workbook {args.workbook_id}: seeded {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
