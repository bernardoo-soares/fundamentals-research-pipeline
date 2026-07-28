"""Load, validate and hash-pin the scorecard configuration.

The only module that reads the YAML. Validation is strict and total: a
malformed ramp or a weight that does not sum to 1.0 is a defect that would
silently distort every score, so it raises at load time rather than producing a
plausible-looking number.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).with_name("buffett_scorecard.yml")

# Closed set of checklist comparisons. A config naming anything else is
# rejected rather than defaulted, since a silently-skipped rule would read as a
# passing one.
CHECKLIST_OPERATORS: frozenset[str] = frozenset({">", ">=", "<", "<="})

# Weights must sum to 1.0 within this tolerance. Floats do not sum exactly, but
# a genuine authoring error (0.30/0.20/0.25/0.15/0.05) is far outside it.
WEIGHT_SUM_TOLERANCE = 1e-9

POINTS_MIN = 0.0
POINTS_MAX = 100.0


@dataclass(frozen=True)
class ChecklistRule:
    """The book's literal pass/fail rule for one criterion."""

    op: str
    threshold: float


@dataclass(frozen=True)
class CriterionConfig:
    """One declarative criterion: which metric, how to grade it, how to judge it."""

    criterion_id: str
    metric_id: str
    ramp: tuple[tuple[float, float], ...]
    checklist: ChecklistRule
    negative_equity_override: bool = False


@dataclass(frozen=True)
class ComponentConfig:
    """One weighted group of criteria."""

    component_id: str
    weight: float
    criteria: tuple[CriterionConfig, ...]


@dataclass(frozen=True)
class ScoringPolicy:
    """Coverage floors, badge thresholds and special-case handling."""

    min_component_coverage: float
    low_confidence_coverage: float
    max_staleness_quarters: int
    negative_equity_override_points: float
    negative_equity_annotation: str


@dataclass(frozen=True)
class ScorecardConfig:
    """The whole validated configuration plus its reproducibility hash."""

    scorer_name: str
    scorer_version: str
    policy: ScoringPolicy
    components: tuple[ComponentConfig, ...]
    config_hash: str

    def criteria(self) -> tuple[CriterionConfig, ...]:
        """Every criterion across all components, in declared order."""
        return tuple(
            criterion
            for component in self.components
            for criterion in component.criteria
        )


def canonical_hash(payload: object) -> str:
    """sha256 of a canonical JSON rendering of the parsed config.

    Hashes the PARSED structure, not the file bytes: a comment or whitespace
    edit must not change the hash, while any value change must. Sorted keys and
    JSON's fixed float repr make the rendering stable across YAML round-trips.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_ramp(criterion_id: str, ramp: list) -> tuple[tuple[float, float], ...]:
    """Reject a ramp that cannot be evaluated unambiguously."""
    if len(ramp) < 2:
        raise ValueError(f"{criterion_id}: a ramp needs at least two anchors.")
    anchors = tuple((float(x), float(points)) for x, points in ramp)
    xs = [x for x, _ in anchors]
    if any(later <= earlier for earlier, later in zip(xs, xs[1:], strict=False)):
        raise ValueError(
            f"{criterion_id}: ramp x-values must be strictly increasing; a "
            "non-monotonic ramp makes the points for a value ambiguous."
        )
    for _, points in anchors:
        if not POINTS_MIN <= points <= POINTS_MAX:
            raise ValueError(
                f"{criterion_id}: ramp points must lie within "
                f"[{POINTS_MIN}, {POINTS_MAX}]; got {points}."
            )
    return anchors


def _parse_criterion(raw: dict) -> CriterionConfig:
    criterion_id = raw["id"]
    checklist = raw["checklist"]
    op = checklist["op"]
    if op not in CHECKLIST_OPERATORS:
        raise ValueError(
            f"{criterion_id}: unknown checklist operator {op!r}; "
            f"expected one of {sorted(CHECKLIST_OPERATORS)}."
        )
    return CriterionConfig(
        criterion_id=criterion_id,
        metric_id=raw["metric_id"],
        ramp=_validate_ramp(criterion_id, raw["ramp"]),
        checklist=ChecklistRule(op=op, threshold=float(checklist["threshold"])),
        negative_equity_override=bool(raw.get("negative_equity_override", False)),
    )


def _validate_unique(ids: list[str], label: str) -> None:
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        raise ValueError(f"Duplicate {label}: {duplicates}.")


def load_scorecard_config(path: str | Path | None = None) -> ScorecardConfig:
    """Read, validate and hash the scorecard configuration.

    Raises ValueError on any inconsistency: component weights not summing to
    1.0, a non-monotonic ramp, an unknown checklist operator, a duplicate id, or
    a coverage floor outside (0, 1]. Each of those would silently distort every
    score rather than fail visibly.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    policy_raw = raw["policy"]
    floor = float(policy_raw["min_component_coverage"])
    if not 0.0 < floor <= 1.0:
        raise ValueError(
            f"min_component_coverage must lie within (0, 1]; got {floor}."
        )
    policy = ScoringPolicy(
        min_component_coverage=floor,
        low_confidence_coverage=float(policy_raw["low_confidence_coverage"]),
        max_staleness_quarters=int(policy_raw["max_staleness_quarters"]),
        negative_equity_override_points=float(
            policy_raw["negative_equity_override_points"]
        ),
        negative_equity_annotation=str(policy_raw["negative_equity_annotation"]),
    )

    components = tuple(
        ComponentConfig(
            component_id=component["id"],
            weight=float(component["weight"]),
            criteria=tuple(
                _parse_criterion(criterion) for criterion in component["criteria"]
            ),
        )
        for component in raw["components"]
    )
    if not components:
        raise ValueError("Scorecard config declares no components.")

    _validate_unique([c.component_id for c in components], "component id")
    _validate_unique(
        [
            criterion.criterion_id
            for component in components
            for criterion in component.criteria
        ],
        "criterion id",
    )

    weight_sum = sum(component.weight for component in components)
    if abs(weight_sum - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"Component weights must sum to 1.0; got {weight_sum}. "
            "A silent shortfall would rescale every composite."
        )
    for component in components:
        if not component.criteria:
            raise ValueError(f"{component.component_id}: declares no criteria.")

    return ScorecardConfig(
        scorer_name=str(raw["scorer_name"]),
        scorer_version=str(raw["scorer_version"]),
        policy=policy,
        components=components,
        config_hash=canonical_hash(raw),
    )
