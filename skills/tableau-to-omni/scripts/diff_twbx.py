"""Diff two .twbx files at the XML level to reveal what someone changed.

Useful for:
- Reverse-engineering "what did they tweak" between versions.
- Spotting added / removed calc fields, sheets, dashboards, actions.
- Auditing migration drift.

Usage:
    python3 diff_twbx.py before.twbx after.twbx [--mode summary|raw]

Modes:
    summary  Compare extracted JSON shapes (calcs, worksheets, dashboards, actions).
             Reports added / removed / modified items.
    raw      Diff the raw .twb XML line-by-line.  Verbose; pipe through `less`.
"""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent


def extract(twbx: Path, out_dir: Path) -> Path:
    """Run extract.py to dump JSON for the workbook."""
    cmd = ["python3", str(THIS_DIR / "extract.py"), str(twbx), "--out", str(out_dir)]
    subprocess.run(cmd, check=True)
    return out_dir


def by_key(items: list[dict], key: str) -> dict[str, dict]:
    return {(it.get(key) or it.get("name") or json.dumps(it, sort_keys=True)): it for it in items}


def diff_collection(label: str, before: list[dict], after: list[dict], key: str) -> None:
    b = by_key(before, key)
    a = by_key(after, key)
    added = sorted(set(a) - set(b))
    removed = sorted(set(b) - set(a))
    common = set(b) & set(a)
    modified = sorted(k for k in common if json.dumps(b[k], sort_keys=True) != json.dumps(a[k], sort_keys=True))
    if not (added or removed or modified):
        print(f"## {label}: no changes")
        return
    print(f"## {label}")
    if added:
        print(f"  + added ({len(added)}):")
        for k in added:
            print(f"      {k}")
    if removed:
        print(f"  - removed ({len(removed)}):")
        for k in removed:
            print(f"      {k}")
    if modified:
        print(f"  ~ modified ({len(modified)}):")
        for k in modified[:20]:
            print(f"      {k}")
        if len(modified) > 20:
            print(f"      ... and {len(modified) - 20} more")


def cmd_summary(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as tmp_root:
        tmp = Path(tmp_root)
        before_dir = extract(args.before, tmp / "before")
        after_dir = extract(args.after, tmp / "after")

        for label, fname, key in [
            ("Calc fields", "calcs.json", "name"),
            ("Parameters", "parameters.json", "name"),
            ("Worksheets", "worksheets.json", "name"),
            ("Dashboards", "dashboards.json", "name"),
            ("Actions", "actions.json", "name"),
            ("Hidden sheets", "hidden_sheets.json", "name"),
        ]:
            b = json.loads((before_dir / fname).read_text())
            a = json.loads((after_dir / fname).read_text())
            if not isinstance(b, list):
                b = [{"name": x} for x in b] if isinstance(b, list) else []
                a = [{"name": x} for x in a] if isinstance(a, list) else []
            diff_collection(label, b, a, key)
            print()
    return 0


def cmd_raw(args: argparse.Namespace) -> int:
    import zipfile
    def read_twb(path: Path) -> list[str]:
        with zipfile.ZipFile(path) as z:
            twb = next(n for n in z.namelist() if n.endswith(".twb"))
            return z.read(twb).decode().splitlines()
    before = read_twb(args.before)
    after = read_twb(args.after)
    for line in difflib.unified_diff(before, after, fromfile=str(args.before), tofile=str(args.after), n=2):
        print(line)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("before", type=Path)
    ap.add_argument("after", type=Path)
    ap.add_argument("--mode", choices=["summary", "raw"], default="summary")
    args = ap.parse_args()
    return cmd_summary(args) if args.mode == "summary" else cmd_raw(args)


if __name__ == "__main__":
    sys.exit(main())
