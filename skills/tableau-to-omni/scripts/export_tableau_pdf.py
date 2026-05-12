"""Export the Tableau workbook's dashboard layout to PDF.

This is a visual-tracker tool: it produces a side-by-side comparison
target so a human can verify that the Omni-side dashboard matches the
Tableau original.

Strategy (tries each backend in order, stops at the first that works):

1. **Tableau Desktop CLI** (highest fidelity, requires Tableau Desktop installed).
   On macOS: `/Applications/Tableau Desktop XX.X.app/Contents/MacOS/Tableau`
   does NOT support headless export (Tableau Server's `tabcmd` does, but
   that requires Server). The user's current manual workflow is "Open in
   Tableau Desktop, File > Print, Save as PDF" which is what this backend
   automates via AppleScript if Tableau Desktop is found.

2. **Headless Chrome / Chromium** rendering of `render_layout.py`'s HTML
   output. Works without Tableau Desktop. Lower fidelity (renders the
   zone map, not the actual chart visuals), but deterministic.

3. **Manual fallback** prints clear instructions for the user to do the
   print-to-PDF themselves on the HTML file.

Usage:
    python3 export_tableau_pdf.py --twbx path/to/workbook.twbx --out layout.pdf
    python3 export_tableau_pdf.py --twbx path/to/workbook.twbx --out layout.pdf --backend chrome
    python3 export_tableau_pdf.py --twbx path/to/workbook.twbx --out layout.pdf --backend tableau
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def find_tableau_desktop() -> Path | None:
    """Locate the Tableau Desktop binary on macOS."""
    if sys.platform != "darwin":
        return None
    for parent in Path("/Applications").glob("Tableau Desktop*.app"):
        binary = parent / "Contents" / "MacOS" / "Tableau"
        if binary.exists():
            return binary
    return None


def find_chrome() -> Path | None:
    """Locate a Chromium-family browser for headless PDF rendering."""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chrome"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    return None


def export_via_tableau_desktop(twbx: Path, pdf_out: Path) -> bool:
    """Drive Tableau Desktop's GUI via AppleScript to print to PDF.

    Tableau Desktop has no documented headless export. The available paths:
    1. AppleScript automation of File > Print Dashboard > PDF (slow, GUI-bound)
    2. `tabcmd export ... --pdf` (requires Tableau Server, not Desktop)
    3. Tableau Server REST API `/views/{id}/pdf` (requires Server)

    This function uses path 1 as a last-resort. It only runs if the user
    explicitly requests `--backend tableau`. Returns True on success.
    """
    tab = find_tableau_desktop()
    if tab is None:
        return False
    # AppleScript that opens the workbook and prints to PDF.
    # Note: Tableau's "Print to PDF" is under File menu and brings up a
    # dialog. Real automation would need UI scripting, which is fragile.
    # This is a stub that prints what should be done.
    print(f"Tableau Desktop found at {tab}", file=sys.stderr)
    print("WARN: Tableau Desktop has no headless export. Falling back to manual.", file=sys.stderr)
    print(f"      Open {twbx} in Tableau, choose File > Print to PDF, save to {pdf_out}.", file=sys.stderr)
    return False


def export_via_chrome(twbx: Path, pdf_out: Path) -> bool:
    """Render Tableau zone layout to HTML then headless-print to PDF.

    Uses `render_layout.py` to produce the HTML. Then invokes Chrome
    headless with `--print-to-pdf` to convert. This captures the zone
    geometry but not the actual chart visuals (Tableau Desktop is the
    only thing that renders those without Tableau Server access).
    """
    chrome = find_chrome()
    if chrome is None:
        return False

    # First extract the TWBX to get the .twb XML.
    with tempfile.TemporaryDirectory() as tmp:
        ir_dir = Path(tmp) / "ir"
        ir_dir.mkdir()
        # Run extract.py to populate dashboards.json
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "extract.py"), str(twbx), "--out", str(ir_dir)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"extract.py failed: {result.stderr}", file=sys.stderr)
            return False

        # Render the HTML layout
        html_out = Path(tmp) / "layout.html"
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "render_layout.py"),
             "--ir-dir", str(ir_dir), "--out", str(html_out)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"render_layout.py failed: {result.stderr}", file=sys.stderr)
            return False

        # Chrome headless print-to-pdf
        result = subprocess.run([
            str(chrome),
            "--headless",
            "--disable-gpu",
            "--no-margins",
            f"--print-to-pdf={pdf_out}",
            f"file://{html_out}",
        ], capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"Chrome headless failed: {result.stderr}", file=sys.stderr)
            return False

        if not pdf_out.exists():
            return False
        print(f"wrote {pdf_out} via Chrome headless (zone layout only, not chart visuals)", file=sys.stderr)
        return True


def export_manual(twbx: Path, pdf_out: Path) -> bool:
    """Last resort: emit HTML to a known location, tell user to print it."""
    ir_dir = pdf_out.parent / (pdf_out.stem + "_ir")
    ir_dir.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "extract.py"), str(twbx), "--out", str(ir_dir)],
        check=True, capture_output=True,
    )
    html_out = pdf_out.with_suffix(".html")
    subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "render_layout.py"),
         "--ir-dir", str(ir_dir), "--out", str(html_out)],
        check=True, capture_output=True,
    )
    print(f"wrote {html_out}", file=sys.stderr)
    print(f"NEXT: open {html_out} in a browser and File > Print > Save as PDF to {pdf_out}", file=sys.stderr)
    print(f"   OR install Chrome / Chromium and re-run for automatic PDF rendering", file=sys.stderr)
    return True


BACKENDS = {
    "tableau": export_via_tableau_desktop,
    "chrome": export_via_chrome,
    "manual": export_manual,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--twbx", required=True, type=Path, help="Path to .twbx file")
    ap.add_argument("--out", required=True, type=Path, help="Output PDF path")
    ap.add_argument("--backend", default="auto",
                    choices=["auto", "tableau", "chrome", "manual"],
                    help="auto tries tableau, then chrome, then manual")
    args = ap.parse_args(argv)

    if not args.twbx.exists():
        sys.exit(f"twbx not found: {args.twbx}")

    if args.backend == "auto":
        for name in ("chrome", "manual"):
            ok = BACKENDS[name](args.twbx, args.out)
            if ok:
                return 0
        print("ERROR: no backend worked", file=sys.stderr)
        return 1

    ok = BACKENDS[args.backend](args.twbx, args.out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
