"""Unit tests for Tableau relative-date and categorical filter translation
into Omni dashboard filterConfig shapes.

Background, Omni date literal semantics (docs.omni.co/modeling/filters/
operators/time-for-duration plus empirical SQL inspection):

- Natural-language `"N units ago"` resolves to the START of the period that
  is (N-1) calendar units back from now, truncated and inclusive of the
  current period. So `"12 months ago"` becomes `INTERVAL '-11 month'`.
- The "in the past N units" UI picker is the symmetric pattern:
  `time_for_duration: [N units ago, N units]`, i.e. left and right both
  carry `period_count`.
- To get a strict N-units-back start (exclusive of current period), use
  `"N complete units ago"` which becomes `INTERVAL '-N unit'`.

The full date-filter kind enum surfaced via the API's 400 response:
    IS_ON_DAY_OF_WEEK, IS_ON_DAY_OF_QUARTER, IS_IN_MONTH_OF_YEAR,
    IS_ON_DAY_OF_YEAR, IS_AT_HOUR_OF_DAY, IS_IN_QUARTER_OF_YEAR,
    IS_IN_WEEK_OF_YEAR, IS_ON_DAY_OF_MONTH, BETWEEN, ON_OR_AFTER, BEFORE,
    TIME_FOR_INTERVAL_DURATION, TIME_FOR_UNIT_DURATION, QUERY_OFFSET.

TIME_FOR_UNIT_DURATION is accepted by the dashboards-filter PATCH API but
the query planner rejects it ("Invalid literal value"). The mapper sticks
to TIME_FOR_INTERVAL_DURATION for everything.
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS = Path(__file__).resolve()
SCRIPTS_DIR = THIS.parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import build_dashboards as bd


# ----- relative-date: "in the past N" pattern -----

def test_last_12_months_inclusive_maps_to_in_the_past_shape() -> None:
    """Tableau `first-period=-11, last-period=0, period-type=month` is the
    canonical "last 12 months including current". Must map to Omni's
    `time_for_duration: [12 months ago, 12 months]`, which the UI renders
    as "in the past 12 months". Both sides use period_count (12), NOT
    abs(first) (11). Using abs(first) on the left gives the same data
    window but a range-picker UI rather than the "in the past N" picker.
    """
    out = bd._tableau_filter_to_omni_default({
        "class": "relative-date",
        "relative_date": {
            "first_period": "-11", "last_period": "0",
            "period_type": "month", "include_future": True,
        },
    })
    assert out == {
        "type": "date",
        "kind": "TIME_FOR_INTERVAL_DURATION",
        "left_side": "12 months ago",
        "right_side": "12 months",
    }


def test_last_4_weeks_inclusive_maps_to_in_the_past_shape() -> None:
    out = bd._tableau_filter_to_omni_default({
        "class": "relative-date",
        "relative_date": {
            "first_period": "-3", "last_period": "0", "period_type": "week",
        },
    })
    assert out == {
        "type": "date",
        "kind": "TIME_FOR_INTERVAL_DURATION",
        "left_side": "4 weeks ago",
        "right_side": "4 weeks",
    }


def test_single_current_period_maps_to_one_unit_window() -> None:
    """first=0, last=0 = "just this period". Becomes the degenerate
    "in the past 1 unit" filter."""
    out = bd._tableau_filter_to_omni_default({
        "class": "relative-date",
        "relative_date": {
            "first_period": "0", "last_period": "0", "period_type": "day",
        },
    })
    assert out == {
        "type": "date",
        "kind": "TIME_FOR_INTERVAL_DURATION",
        "left_side": "1 days ago",
        "right_side": "1 days",
    }


# ----- relative-date: true offset windows -----

def test_3_to_6_months_ago_maps_to_offset_window() -> None:
    """first=-6, last=-3 = "6 months ago, 4 months long". Window does NOT
    end at the current period (last != 0), so use offset+length form:
    left_side anchors at abs(first), right_side carries period_count.
    """
    out = bd._tableau_filter_to_omni_default({
        "class": "relative-date",
        "relative_date": {
            "first_period": "-6", "last_period": "-3", "period_type": "month",
        },
    })
    assert out == {
        "type": "date",
        "kind": "TIME_FOR_INTERVAL_DURATION",
        "left_side": "6 months ago",
        "right_side": "4 months",
    }


def test_future_window_maps_to_offset_window() -> None:
    """first=1, last=12 = future window. last != 0 so offset path.
    Edge case worth pinning down."""
    out = bd._tableau_filter_to_omni_default({
        "class": "relative-date",
        "relative_date": {
            "first_period": "1", "last_period": "12", "period_type": "month",
        },
    })
    assert out["kind"] == "TIME_FOR_INTERVAL_DURATION"
    assert out["left_side"] == "1 months ago"
    assert out["right_side"] == "12 months"


# ----- categorical filter -----

def test_categorical_with_members_maps_to_equals() -> None:
    out = bd._tableau_filter_to_omni_default({
        "class": "categorical",
        "members": ["Northeast", '"West"', "  South  "],
    })
    assert out == {
        "type": "string",
        "kind": "EQUALS",
        "values": ["Northeast", "West", "South"],
    }


def test_categorical_empty_returns_none() -> None:
    assert bd._tableau_filter_to_omni_default({
        "class": "categorical",
        "members": [],
    }) is None


def test_unknown_class_returns_none() -> None:
    assert bd._tableau_filter_to_omni_default({
        "class": "top-n",
        "values": ["whatever"],
    }) is None


def test_unsupported_period_type_returns_none() -> None:
    """Tableau exposes period-type-v2 tokens we don't know how to map yet
    (e.g. fiscal-year variants). Return None so the caller can fall back
    to the hand-authored filter shape."""
    assert bd._tableau_filter_to_omni_default({
        "class": "relative-date",
        "relative_date": {
            "first_period": "-1", "last_period": "0",
            "period_type": "fiscal-year",
        },
    }) is None
