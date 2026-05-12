"""Unit tests for the dashboard-name-from-Tableau auto-default behaviour added
in v1.5.

Two surfaces resolve dashboard names today:
  - build_payload.py: single-dashboard path, single tile-spec.yaml.
  - build_dashboards.py: multi-dashboard migration-spec path.

Each script has its own resolver, intentionally narrow to its inputs.  The
tests below exercise the four precedence rules of each resolver in turn so a
later refactor doesn't silently re-prioritise the inputs.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

# Make the scripts/ dir importable as flat modules.
THIS = Path(__file__).resolve()
SCRIPTS_DIR = THIS.parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_payload as bp
import build_dashboards as bd


# ----- build_payload.resolve_dashboard_name -----

def test_build_payload_explicit_arg_wins(tmp_path: Path) -> None:
    ir_dir = tmp_path
    (ir_dir / "dashboards.json").write_text(json.dumps([{"name": "From IR"}]))
    tile_yaml = {"dashboards": [{"name": "From spec list"}], "dashboard_name": "From spec key"}

    out = bp.resolve_dashboard_name("Explicit override", "", tile_yaml, ir_dir)

    assert out == "Explicit override"


def test_build_payload_spec_top_level_dashboard_name(tmp_path: Path) -> None:
    ir_dir = tmp_path
    (ir_dir / "dashboards.json").write_text(json.dumps([{"name": "From IR"}]))
    tile_yaml = {"dashboards": [{"name": "From spec list"}], "dashboard_name": "From spec key"}

    out = bp.resolve_dashboard_name(None, "", tile_yaml, ir_dir)

    assert out == "From spec key"


def test_build_payload_spec_dashboards_list_first_entry() -> None:
    tile_yaml = {"dashboards": [{"name": "First listed"}, {"name": "Second listed"}]}

    out = bp.resolve_dashboard_name(None, "", tile_yaml, None)

    assert out == "First listed"


def test_build_payload_ir_dashboards_json_fallback(tmp_path: Path) -> None:
    (tmp_path / "dashboards.json").write_text(json.dumps([{"name": "Event Dashboard Basic"}]))
    tile_yaml: dict = {}

    out = bp.resolve_dashboard_name(None, "", tile_yaml, tmp_path)

    assert out == "Event Dashboard Basic"


def test_build_payload_name_prefix_is_applied(tmp_path: Path) -> None:
    (tmp_path / "dashboards.json").write_text(json.dumps([{"name": "Foo"}]))

    out = bp.resolve_dashboard_name(None, "Migrated: ", {}, tmp_path)

    assert out == "Migrated: Foo"


def test_build_payload_fails_loud_with_no_inputs() -> None:
    with pytest.raises(SystemExit):
        bp.resolve_dashboard_name(None, "", {}, None)


# ----- build_dashboards.resolve_dashboard_name -----

def test_build_dashboards_explicit_name_wins() -> None:
    out = bd.resolve_dashboard_name(
        {"slug": "x", "name": "Explicit"},
        name_prefix="",
        ir_names=["IR positional"],
        spec_index=0,
    )

    assert out == "Explicit"


def test_build_dashboards_tableau_name_cross_reference() -> None:
    out = bd.resolve_dashboard_name(
        {"slug": "x", "tableau_name": "From tableau_name field"},
        name_prefix="",
        ir_names=["Wrong positional"],
        spec_index=0,
    )

    assert out == "From tableau_name field"


def test_build_dashboards_ir_positional_fallback() -> None:
    out = bd.resolve_dashboard_name(
        {"slug": "events"},
        name_prefix="",
        ir_names=["Events overview", "Membership Breakdown"],
        spec_index=1,
    )

    assert out == "Membership Breakdown"


def test_build_dashboards_name_prefix_is_applied() -> None:
    out = bd.resolve_dashboard_name(
        {"slug": "x", "name": "Plain"},
        name_prefix="Migrated: ",
        ir_names=[],
        spec_index=0,
    )

    assert out == "Migrated: Plain"


def test_build_dashboards_fails_loud_when_no_source() -> None:
    with pytest.raises(SystemExit):
        bd.resolve_dashboard_name(
            {"slug": "x"},
            name_prefix="",
            ir_names=[],
            spec_index=0,
        )


def test_build_dashboards_load_ir_names_handles_missing_dir(tmp_path: Path) -> None:
    assert bd.load_ir_dashboard_names(None) == []
    assert bd.load_ir_dashboard_names(tmp_path) == []  # file missing


def test_build_dashboards_load_ir_names_reads_extract_output(tmp_path: Path) -> None:
    (tmp_path / "dashboards.json").write_text(json.dumps([
        {"name": "A", "zones": []},
        {"name": "B", "zones": []},
        {"zones": []},  # missing name, skipped
    ]))

    assert bd.load_ir_dashboard_names(tmp_path) == ["A", "B"]
