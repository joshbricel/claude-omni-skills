"""Export Omni dashboards as PDFs and stitch a side-by-side comparison vs the
original Tableau printed PDF.

This is the visual verification layer for the migration: it complements the
SQL parity check (`omni query run`) by capturing the rendered output and
producing an artifact that can be visually compared to the Tableau source.

Usage:
    python3 export_and_compare_pdfs.py \
      --identifiers f3ba534e,3f120747,d3806f84,1aebe2f3 \
      --names "Events overview,New Membership,Membership Breakdown,New Member Categories" \
      --out-dir /path/to/output \
      [--tableau-pdf /path/to/printed.pdf]   # optional, builds side-by-side comparison

Produces:
  out-dir/
    omni_<slug>.pdf                # one per Omni dashboard
    comparison.pdf                 # Tableau page on left, Omni page on right (if --tableau-pdf provided)
    summary.md                     # what was exported, file sizes, page counts

Env: OMNI_API_TOKEN, OMNI_BASE_URL.

Why async download flow:
  Omni's `dashboards download` is a 3-step async process:
  1. POST /api/v1/dashboards/<id>/download with body {"format": "pdf"} -> jobId
  2. Poll GET /api/v1/dashboards/<id>/download-status/<jobId> until status=complete
  3. GET /api/v1/dashboards/<id>/download-file/<jobId> -> binary PDF bytes
  We use the omni CLI wrappers for all three.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def cli(*args: str, body: str | None = None, capture_stdout_to: Path | None = None) -> dict | None:
    cmd = ["omni"]
    if "OMNI_BASE_URL" in os.environ:
        cmd += ["--base-url", os.environ["OMNI_BASE_URL"]]
    if "OMNI_API_TOKEN" in os.environ:
        cmd += ["--token", os.environ["OMNI_API_TOKEN"]]
    cmd += list(args) + ["--format", "json"]
    if body is not None:
        cmd += ["--body", body]

    if capture_stdout_to is not None:
        with capture_stdout_to.open("wb") as f:
            r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
        if r.returncode != 0:
            sys.exit(f"omni CLI failed: {' '.join(cmd[:6])}...\n  stderr: {r.stderr.decode()}")
        return None

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"omni CLI failed: {' '.join(cmd[:6])}...\n  stderr: {r.stderr}\n  stdout head: {r.stdout[:600]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def export_one(identifier: str, out_path: Path, *, poll_interval_s: float = 2.0,
               max_wait_s: float = 120.0) -> dict:
    print(f"  [{identifier}] initiating PDF download...", file=sys.stderr)
    init = cli("dashboards", "download", identifier, body=json.dumps({"format": "pdf"}))
    if "existing_job_id" in init:
        job_id = init["existing_job_id"]
        print(f"  [{identifier}] reusing existing job {job_id}", file=sys.stderr)
    elif "job_id" in init:
        job_id = init["job_id"]
    else:
        sys.exit(f"  [{identifier}] unexpected init response: {init}")

    deadline = time.time() + max_wait_s
    last_status = None
    while time.time() < deadline:
        s = cli("dashboards", "download-status", identifier, job_id)
        status = s.get("status", "")
        if status != last_status:
            print(f"  [{identifier}] status={status}", file=sys.stderr)
            last_status = status
        if status == "complete":
            break
        if status in ("failed", "error"):
            return {"identifier": identifier, "error": s.get("error") or status, "job_id": job_id}
        time.sleep(poll_interval_s)
    else:
        return {"identifier": identifier, "error": "timeout", "job_id": job_id}

    cli("dashboards", "download-file", identifier, job_id, capture_stdout_to=out_path)

    size = out_path.stat().st_size
    if size < 4 or out_path.read_bytes()[:4] != b"%PDF":
        return {"identifier": identifier, "error": f"non-PDF response, size={size}", "job_id": job_id}
    print(f"  [{identifier}] wrote {out_path} ({size} bytes)", file=sys.stderr)
    return {"identifier": identifier, "path": str(out_path), "size_bytes": size, "job_id": job_id}


def build_side_by_side(tableau_pdf: Path, omni_pdfs: list[Path], out_path: Path) -> None:
    """Build a side-by-side comparison PDF: Tableau page n on the left, Omni
    dashboard n on the right. Uses pypdf + reportlab if available; otherwise
    just concatenates them.
    """
    try:
        from pypdf import PdfReader, PdfWriter, Transformation, PageObject
    except ImportError:
        sys.exit("pypdf required for side-by-side. Install: pip3 install pypdf")

    tableau_reader = PdfReader(str(tableau_pdf))
    omni_readers = [PdfReader(str(p)) for p in omni_pdfs]

    writer = PdfWriter()
    n_pages = max(len(tableau_reader.pages), len(omni_readers))
    for i in range(n_pages):
        tab_page = tableau_reader.pages[i] if i < len(tableau_reader.pages) else None
        omni_page = omni_readers[i].pages[0] if i < len(omni_readers) else None

        # Compose into an A4-landscape page: tableau-shrink left, omni-shrink right.
        # PDF coordinate units are points (1/72 inch).
        page_w = 1684  # ~ 23.4 inches (A3 landscape style for high res)
        page_h = 1190  # ~ 16.5 inches
        new_page = PageObject.create_blank_page(width=page_w, height=page_h)

        for src_page, x_offset in ((tab_page, 20), (omni_page, page_w / 2 + 20)):
            if src_page is None:
                continue
            src_w = float(src_page.mediabox.width)
            src_h = float(src_page.mediabox.height)
            target_w = page_w / 2 - 40
            target_h = page_h - 40
            scale = min(target_w / src_w, target_h / src_h)
            tx = Transformation().scale(scale).translate(x_offset, (page_h - src_h * scale) / 2)
            new_page.merge_transformed_page(src_page, tx)

        writer.add_page(new_page)

    with out_path.open("wb") as f:
        writer.write(f)
    print(f"  wrote comparison: {out_path} ({out_path.stat().st_size} bytes, {n_pages} pages)", file=sys.stderr)


def main() -> int:
    if shutil.which("omni") is None:
        sys.exit("omni CLI not on PATH.  brew tap exploreomni/tap && brew install omni")

    ap = argparse.ArgumentParser()
    ap.add_argument("--identifiers", required=True,
                    help="Comma-separated dashboard identifiers (e.g. 'cc9592da,0ef2f748,...')")
    ap.add_argument("--names", default=None,
                    help="Comma-separated display names (matched 1:1 with identifiers)")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--tableau-pdf", type=Path, default=None,
                    help="Optional: original Tableau printed PDF.  If provided, build a side-by-side comparison.pdf")
    ap.add_argument("--max-wait", type=float, default=120.0)
    args = ap.parse_args()

    identifiers = [s.strip() for s in args.identifiers.split(",") if s.strip()]
    if args.names:
        names = [s.strip() for s in args.names.split(",")]
        if len(names) != len(identifiers):
            sys.exit("--names count must match --identifiers count")
    else:
        names = identifiers[:]

    args.out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    omni_pdfs = []
    for ident, name in zip(identifiers, names):
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        out_path = args.out_dir / f"omni_{slug}.pdf"
        info = export_one(ident, out_path, max_wait_s=args.max_wait)
        info["name"] = name
        info["slug"] = slug
        results.append(info)
        if "error" in info:
            print(f"  [{ident}] EXPORT FAILED: {info['error']}", file=sys.stderr)
        else:
            omni_pdfs.append(out_path)

    if args.tableau_pdf:
        comparison_path = args.out_dir / "comparison.pdf"
        build_side_by_side(args.tableau_pdf, omni_pdfs, comparison_path)
        results.append({"comparison_pdf": str(comparison_path)})

    # Write summary
    summary_path = args.out_dir / "summary.md"
    with summary_path.open("w") as f:
        f.write("# Omni dashboard PDF export\n\n")
        f.write(f"Exported {len(identifiers)} dashboards from {os.environ.get('OMNI_BASE_URL','')}.\n\n")
        f.write("| Identifier | Name | File | Size |\n|---|---|---|---|\n")
        for r in results:
            if "identifier" in r:
                f.write(f"| `{r['identifier']}` | {r['name']} | `{Path(r['path']).name}` | {r['size_bytes']} bytes |\n")
        if args.tableau_pdf:
            f.write(f"\nSide-by-side comparison: `comparison.pdf`. Source Tableau printed PDF: `{args.tableau_pdf}`.\n")
    print(f"  wrote {summary_path}", file=sys.stderr)

    print(json.dumps({"exported": [r for r in results if "identifier" in r],
                      "comparison_pdf": str(args.out_dir / "comparison.pdf") if args.tableau_pdf else None},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
