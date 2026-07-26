"""Tests for graded-ramp and literal-checklist evaluation."""

from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.scorecard_schema import ChecklistVerdict
from fundamentals_pipeline.scoring.config import ChecklistRule
from fundamentals_pipeline.scoring.ramps import (
    clamp_points,
    evaluate_checklist,
    evaluate_ramp,
)

# The spec's own worked example (section 7.3): gross_margin
# <= 0.20 -> 0 pts; 0.40 -> 80; >= 0.60 -> 100; linear between.
_GROSS_MARGIN = ((0.20, 0.0), (0.40, 80.0), (0.60, 100.0))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.20, 0.0),  # lower anchor
        (0.40, 80.0),  # the book threshold
        (0.60, 100.0),  # upper anchor
        (0.30, 40.0),  # midpoint of the first segment
        (0.50, 90.0),  # midpoint of the second
    ],
)
def test_ramp_reproduces_the_spec_worked_example(value, expected):
    assert evaluate_ramp(value, _GROSS_MARGIN) == pytest.approx(expected)


@pytest.mark.parametrize(("value", "expected"), [(0.05, 0.0), (0.95, 100.0)])
def test_ramp_clamps_rather_than_extrapolating(value, expected):
    """A 95% gross margin scores the same 100 as 60%, not 180.

    Extrapolating would also let a descending ramp produce negative points.
    """
    assert evaluate_ramp(value, _GROSS_MARGIN) == pytest.approx(expected)


def test_ramp_handles_descending_points_for_lower_is_better_metrics():
    """One evaluator serves both directions, so no metric needs an invert flag."""
    sga = ((0.30, 100.0), (0.80, 20.0), (1.20, 0.0))
    assert evaluate_ramp(0.30, sga) == pytest.approx(100.0)
    assert evaluate_ramp(0.55, sga) == pytest.approx(60.0)  # midpoint
    assert evaluate_ramp(0.80, sga) == pytest.approx(20.0)
    assert evaluate_ramp(2.00, sga) == pytest.approx(0.0)  # clamped, not negative


def test_ramp_never_leaves_the_declared_scale():
    """Property: points stay within [0, 100] across the whole domain."""
    for step in range(-50, 250):
        value = step / 100.0
        assert 0.0 <= evaluate_ramp(value, _GROSS_MARGIN) <= 100.0


@pytest.mark.parametrize(
    ("op", "threshold", "value", "expected"),
    [
        (">", 0.40, 0.41, ChecklistVerdict.PASS),
        (">", 0.40, 0.40, ChecklistVerdict.FAIL),  # strict
        (">=", 0.80, 0.80, ChecklistVerdict.PASS),  # inclusive
        ("<", 0.15, 0.14, ChecklistVerdict.PASS),
        ("<", 0.15, 0.15, ChecklistVerdict.FAIL),
        ("<=", 4.0, 4.0, ChecklistVerdict.PASS),
    ],
)
def test_checklist_applies_the_literal_rule(op, threshold, value, expected):
    assert evaluate_checklist(value, ChecklistRule(op, threshold)) == expected


def test_checklist_never_returns_not_applicable():
    """Applicability is the scorer's decision, not the rule's.

    A rule given a value always answers pass or fail; a metric with no value
    never reaches the rule.
    """
    for op, threshold in ((">", 0.0), ("<", 0.0)):
        verdict = evaluate_checklist(0.0, ChecklistRule(op, threshold))
        assert verdict in {ChecklistVerdict.PASS, ChecklistVerdict.FAIL}


def test_clamp_points_bounds_the_override():
    """The negative-equity override writes points straight from config."""
    assert clamp_points(150.0) == 100.0
    assert clamp_points(-10.0) == 0.0
    assert clamp_points(70.0) == 70.0
