"""Contract for the Stage 2 trend-metrics layer.

Compute-free: reason codes, the MetricPoint/TrendMetric abstractions, and the
metrics_trend table schema. The metric computation itself lives in the pure
`metrics/` package.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

METRICS_PIPELINE_VERSION = "metrics-1.0"


class ReasonCode:
    """Closed set of reason codes (Buffett spec section 6.3)."""

    MISSING_INPUT = "missing_input"
    INCOMPLETE_YEAR = "incomplete_year"
    NEGATIVE_BASE = "negative_base"
    ZERO_DENOMINATOR = "zero_denominator"
    NOT_APPLICABLE_SECTOR = "not_applicable_sector"
    INSUFFICIENT_HISTORY = "insufficient_history"
    TSTK_UNAVAILABLE = "tstk_unavailable"
    MIXED_ERA_WINDOW = "mixed_era_window"


REASON_CODES: frozenset[str] = frozenset(
    {
        ReasonCode.MISSING_INPUT,
        ReasonCode.INCOMPLETE_YEAR,
        ReasonCode.NEGATIVE_BASE,
        ReasonCode.ZERO_DENOMINATOR,
        ReasonCode.NOT_APPLICABLE_SECTOR,
        ReasonCode.INSUFFICIENT_HISTORY,
        ReasonCode.TSTK_UNAVAILABLE,
        ReasonCode.MIXED_ERA_WINDOW,
    }
)


@dataclass(frozen=True)
class MetricPoint:
    """One computed metric value (or reasoned null) for a ticker-as_of_year."""

    as_of_year: int
    value: float | None
    reason_code: str | None
    window_years_present: int

    def __post_init__(self) -> None:
        if (self.value is None) == (self.reason_code is None):
            raise ValueError(
                "MetricPoint requires exactly one of value / reason_code."
            )
        if self.reason_code is not None and self.reason_code not in REASON_CODES:
            raise ValueError(f"Unknown reason_code: {self.reason_code!r}")


@dataclass(frozen=True)
class TrendMetric:
    """A declarative trend-metric: identity + a pure compute function.

    `requires_single_era` marks a metric whose inputs are not comparable
    across the provider boundary (see contracts/field_era_semantics.py). Such
    a metric must be composed with `windows.require_single_era`, which nulls
    any window spanning more than one `source_era` with `mixed_era_window`.
    """

    metric_id: str
    version: str
    window_length: int
    formula: str
    compute: Callable[[Any], list[MetricPoint]]
    requires_single_era: bool = False


METRICS_TREND_COLUMNS: tuple[str, ...] = (
    "ticker",
    "as_of_year",
    "metric_id",
    "value",
    "reason_code",
    "window_length",
    "window_years_present",
    "metric_version",
    "computed_at",
    "pipeline_version",
)


def create_metrics_trend_ddl() -> str:
    """DDL for the metrics_trend table."""
    return (
        "CREATE TABLE metrics_trend (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  as_of_year INTEGER NOT NULL,\n"
        "  metric_id VARCHAR NOT NULL,\n"
        "  value DOUBLE,\n"
        "  reason_code VARCHAR,\n"
        "  window_length INTEGER,\n"
        "  window_years_present INTEGER,\n"
        "  metric_version VARCHAR,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, as_of_year, metric_id)\n"
        ")"
    )
