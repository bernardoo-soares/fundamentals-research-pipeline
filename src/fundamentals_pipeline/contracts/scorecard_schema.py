"""Contract for the Stage 3 scoring layer (platform spec section 7).

Compute-free: the `Scorer` protocol, the value objects crossing it, and the
`scores` / `score_criteria` table schemas. Scoring itself lives in the pure
`scoring/` package.

A scorer reads **only** the `metrics_*` tables -- never raw fundamentals and
never prices -- and scores never feed back into metrics. That keeps the metrics
layer usable as a future ML feature matrix with no leakage path by construction
(spec section 7.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

SCORES_PIPELINE_VERSION = "scores-1.0"

# The quarter whose point-in-time reading stands for fiscal year end. Declared
# here rather than in the builder because it is the same convention
# `warehouse/annualize.py` already uses for every stock field
# (`MAX(CASE WHEN quarter = 4 ...)`); stating it twice as a literal is how the
# two would silently drift apart (S1.5, S2.6).
FISCAL_YEAR_END_QUARTER = 4

# Staleness arithmetic. A ticker's distance from the warehouse's latest quarter
# is measured in quarters, so converting a year gap needs this scale.
QUARTERS_PER_YEAR = 4

# How the badge tuple serialises into the single `scores.badges` column. An
# empty string means "scored, no warnings" -- knowledge, not absence -- which is
# why badges is never written as NULL.
BADGE_SEPARATOR = ","


class ChecklistVerdict(StrEnum):
    """Closed set of literal book-checklist outcomes.

    Distinct from the graded ramp points: the checklist answers the book's raw
    rule ("gross margin above 40%?") while the ramp answers "how far along the
    quality gradient". Both are stored and both are displayed -- the graded score
    ranks, the checklist grounds (spec section 7.3).
    """

    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "n.a."


class ScoreReasonCode(StrEnum):
    """Why a composite or component score is absent.

    Deliberately separate from the metric-grain `ReasonCode`: those explain a
    missing measurement, these explain a score that could not be assembled from
    otherwise-valid measurements.
    """

    NO_APPLICABLE_COMPONENT = "no_applicable_component"
    COMPONENT_COVERAGE_BELOW_FLOOR = "component_coverage_below_floor"
    NO_APPLICABLE_CRITERION = "no_applicable_criterion"
    # Every criterion in the component is era-guarded, so the component is not
    # measurable in this provider era for ANY company.
    ALL_CRITERIA_ERA_UNAVAILABLE = "all_criteria_era_unavailable"


class ScoreBadge(StrEnum):
    """Prominent warnings carried alongside a present score (spec 7.4.2)."""

    LOW_CONFIDENCE = "low_confidence"
    STALE_DATA = "stale_data"
    # At least one criterion was graded off a value carrying a known caveat --
    # a real number with a measured reliability limit, not a null. Standing
    # directive: anything not fully reliable must be flagged to the UI, and a
    # caveat that lives only in a spec or a docstring does not satisfy that.
    UNRELIABLE_INPUT = "unreliable_input"
    # At least one criterion could not be measured in this provider era at all.
    # The score is over a NARROWER question than the scorecard nominally asks.
    ERA_LIMITED = "era_limited"


@dataclass(frozen=True)
class MetricReading:
    """One metric's value for one ticker-year, or its reason for being absent.

    Mirrors the value-XOR-reason invariant the metric grain already enforces, so
    a scorer can never mistake "measured zero" for "not measured".
    """

    metric_id: str
    value: float | None
    reason_code: str | None
    # Advisory caveat carried alongside a real value (the metrics grain's
    # `quality_flag`). Distinct from reason_code, which explains a null.
    quality_flag: str | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.reason_code is None):
            raise ValueError(
                f"{self.metric_id}: exactly one of value / reason_code must be set."
            )
        if self.quality_flag is not None and self.value is None:
            raise ValueError(
                f"{self.metric_id}: a quality_flag qualifies a value, so it "
                "cannot accompany a null. Use reason_code for an absent value."
            )


@dataclass(frozen=True)
class ScorerInput:
    """Everything a scorer may read for one ticker-year."""

    ticker: str
    as_of_year: int
    readings: dict[str, MetricReading]
    source_family: str | None = None
    staleness_quarters: int | None = None

    def reading(self, metric_id: str) -> MetricReading | None:
        """Return one metric's reading, or None when it was never computed."""
        return self.readings.get(metric_id)


@dataclass(frozen=True)
class CriterionResult:
    """One criterion's full audit trail (spec 7.1: per-criterion transparency)."""

    criterion_id: str
    metric_id: str
    component_id: str
    value: float | None
    points: float | None
    weight: float | None
    checklist_verdict: ChecklistVerdict
    reason_code: str | None
    annotation: str = ""
    # Carried through from the metrics grain so the caveat survives to the UI.
    quality_flag: str | None = None

    @property
    def applicable(self) -> bool:
        """Whether this criterion contributed points and weight."""
        return self.points is not None


@dataclass(frozen=True)
class ComponentResult:
    """One weighted component's score, or its exclusion."""

    component_id: str
    score: float | None
    weight: float | None
    # Applicable over MEASURABLE criteria -- era-guarded ones are excluded from
    # the denominator, because they are absent for every company in the era and
    # counting them would penalise each company for a provider limitation.
    coverage_ratio: float
    applicable_criteria: int
    total_criteria: int
    reason_code: str | None = None
    # Criteria that could not be measured in this era at all. Published so the
    # UI can say "3 of 3 measurable, 1 unavailable this era" rather than the
    # indistinguishable "3 of 4".
    era_unavailable_criteria: int = 0

    @property
    def measurable_criteria(self) -> int:
        """Criteria that could have been measured for this era."""
        return self.total_criteria - self.era_unavailable_criteria


@dataclass(frozen=True)
class ScorerOutput:
    """A complete scorecard for one ticker-year."""

    ticker: str
    as_of_year: int
    composite: float | None
    reason_code: str | None
    coverage_ratio: float
    checklist_passed: int
    checklist_applicable: int
    components: tuple[ComponentResult, ...]
    criteria: tuple[CriterionResult, ...]
    badges: tuple[ScoreBadge, ...] = ()

    def __post_init__(self) -> None:
        if (self.composite is None) == (self.reason_code is None):
            raise ValueError(
                f"{self.ticker} {self.as_of_year}: exactly one of composite / "
                "reason_code must be set. A null composite must never be "
                "published as 0, which would rank an unmeasured company as the "
                "worst one."
            )


class Scorer(Protocol):
    """The scoring seam. A future MLScorer implements this same shape.

    `config_hash` is part of the seam, not of any one implementation: it is the
    third element of the reproducibility key (spec 7.1), so the builder must be
    able to record it without knowing which scorer it is driving. A heuristic
    scorer hashes its scorecard YAML; an MLScorer would hash its weights.
    """

    name: str
    version: str
    config_hash: str

    def score(self, inp: ScorerInput) -> ScorerOutput: ...


SCORES_COLUMNS: tuple[str, ...] = (
    "ticker",
    "as_of_year",
    "scorer_name",
    "scorer_version",
    "config_hash",
    "composite",
    "reason_code",
    "coverage_ratio",
    "checklist_passed",
    "checklist_applicable",
    "badges",
    "staleness_quarters",
    "computed_at",
    "pipeline_version",
)

SCORE_CRITERIA_COLUMNS: tuple[str, ...] = (
    "ticker",
    "as_of_year",
    "scorer_name",
    "scorer_version",
    "config_hash",
    "criterion_id",
    "component_id",
    "metric_id",
    "value",
    "points",
    "weight",
    "checklist_verdict",
    "reason_code",
    "annotation",
    "quality_flag",
    "computed_at",
    "pipeline_version",
)

SCORE_COMPONENTS_COLUMNS: tuple[str, ...] = (
    "ticker",
    "as_of_year",
    "scorer_name",
    "scorer_version",
    "config_hash",
    "component_id",
    "score",
    "weight",
    "coverage_ratio",
    "applicable_criteria",
    "total_criteria",
    "era_unavailable_criteria",
    "reason_code",
    "computed_at",
    "pipeline_version",
)

# The reproducibility key (spec 7.1): identical inputs under the same key must
# produce identical rows, so it is the primary key prefix on every score table.
SCORE_KEY_COLUMNS: tuple[str, ...] = (
    "ticker",
    "as_of_year",
    "scorer_name",
    "scorer_version",
    "config_hash",
)


def create_scores_ddl() -> str:
    """DDL for the composite `scores` table."""
    return (
        "CREATE TABLE scores (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  as_of_year INTEGER NOT NULL,\n"
        "  scorer_name VARCHAR NOT NULL,\n"
        "  scorer_version VARCHAR NOT NULL,\n"
        "  config_hash VARCHAR NOT NULL,\n"
        "  composite DOUBLE,\n"
        "  reason_code VARCHAR,\n"
        "  coverage_ratio DOUBLE,\n"
        "  checklist_passed INTEGER,\n"
        "  checklist_applicable INTEGER,\n"
        "  badges VARCHAR,\n"
        "  staleness_quarters INTEGER,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, as_of_year, scorer_name, scorer_version, config_hash)\n"
        ")"
    )


def create_score_components_ddl() -> str:
    """DDL for the per-component `score_components` table."""
    return (
        "CREATE TABLE score_components (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  as_of_year INTEGER NOT NULL,\n"
        "  scorer_name VARCHAR NOT NULL,\n"
        "  scorer_version VARCHAR NOT NULL,\n"
        "  config_hash VARCHAR NOT NULL,\n"
        "  component_id VARCHAR NOT NULL,\n"
        "  score DOUBLE,\n"
        "  weight DOUBLE,\n"
        "  coverage_ratio DOUBLE,\n"
        "  applicable_criteria INTEGER,\n"
        "  total_criteria INTEGER,\n"
        "  era_unavailable_criteria INTEGER,\n"
        "  reason_code VARCHAR,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, as_of_year, scorer_name, scorer_version, "
        "config_hash, component_id)\n"
        ")"
    )


def create_score_criteria_ddl() -> str:
    """DDL for the per-criterion `score_criteria` audit table."""
    return (
        "CREATE TABLE score_criteria (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  as_of_year INTEGER NOT NULL,\n"
        "  scorer_name VARCHAR NOT NULL,\n"
        "  scorer_version VARCHAR NOT NULL,\n"
        "  config_hash VARCHAR NOT NULL,\n"
        "  criterion_id VARCHAR NOT NULL,\n"
        "  component_id VARCHAR NOT NULL,\n"
        "  metric_id VARCHAR NOT NULL,\n"
        "  value DOUBLE,\n"
        "  points DOUBLE,\n"
        "  weight DOUBLE,\n"
        "  checklist_verdict VARCHAR,\n"
        "  reason_code VARCHAR,\n"
        "  annotation VARCHAR,\n"
        "  quality_flag VARCHAR,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, as_of_year, scorer_name, scorer_version, "
        "config_hash, criterion_id)\n"
        ")"
    )
