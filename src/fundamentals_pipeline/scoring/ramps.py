"""Pure graded-ramp and literal-checklist evaluation.

Frame in -> value out. No I/O, no clock, no randomness. These are the two
independent judgements the platform makes about a metric: the ramp grades it on
a continuous 0-100 gradient, the checklist answers the book's raw yes/no rule.
Both are stored and both are displayed -- the graded score ranks, the checklist
grounds (spec 7.3).
"""

from __future__ import annotations

import operator
from collections.abc import Callable

from ..contracts.scorecard_schema import ChecklistVerdict
from .config import POINTS_MAX, POINTS_MIN, ChecklistRule

# Declared once so an operator string maps to exactly one comparison and a
# typo cannot fall through to a default that silently passes.
_COMPARISONS: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def evaluate_ramp(value: float, anchors: tuple[tuple[float, float], ...]) -> float:
    """Piecewise-linear points for a metric value, clamped outside the anchors.

    Clamping rather than extrapolating is deliberate: a gross margin of 0.95
    should score the same 100 as 0.60, not 180. Extrapolation would also let a
    descending ramp produce negative points.

    `anchors` is validated strictly increasing in x by `config._validate_ramp`,
    so the first bracketing segment found is the only one.
    """
    first_x, first_points = anchors[0]
    if value <= first_x:
        return first_points
    last_x, last_points = anchors[-1]
    if value >= last_x:
        return last_points

    for (left_x, left_points), (right_x, right_points) in zip(
        anchors, anchors[1:], strict=False
    ):
        if left_x <= value <= right_x:
            span = right_x - left_x
            fraction = (value - left_x) / span
            return left_points + fraction * (right_points - left_points)

    # Unreachable given a validated ramp and the clamps above; raising rather
    # than returning a default keeps a future validation bug loud.
    raise ValueError(f"Value {value} fell outside the validated ramp {anchors}.")


def evaluate_checklist(value: float, rule: ChecklistRule) -> ChecklistVerdict:
    """Apply the book's literal rule, yielding PASS or FAIL.

    Never returns NOT_APPLICABLE: applicability is decided by whether the metric
    has a value at all, which is the scorer's job, not the rule's.
    """
    comparison = _COMPARISONS[rule.op]
    return (
        ChecklistVerdict.PASS
        if comparison(value, rule.threshold)
        else ChecklistVerdict.FAIL
    )


def clamp_points(points: float) -> float:
    """Confine points to the declared scale.

    A validated ramp cannot exceed it, but the negative-equity override writes
    points directly from config, so the bound is enforced at one shared place.
    """
    return max(POINTS_MIN, min(POINTS_MAX, points))
