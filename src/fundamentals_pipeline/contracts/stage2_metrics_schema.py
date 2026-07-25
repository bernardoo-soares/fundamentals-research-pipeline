"""Contract for the Stage 2 trend-metrics layer.

Compute-free: reason codes, the MetricPoint/TrendMetric abstractions, and the
metrics_trend table schema. The metric computation itself lives in the pure
`metrics/` package.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .metric_reason_codes import (  # re-exported for existing importers
    REASON_CODES,
    ReasonCode,
    validate_value_xor_reason,
)

__all__ = [
    "METRICS_PIPELINE_VERSION",
    "METRICS_TREND_COLUMNS",
    "MetricPoint",
    "REASON_CODES",
    "ReasonCode",
    "TrendMetric",
    "create_metrics_trend_ddl",
]

METRICS_PIPELINE_VERSION = "metrics-1.0"


@dataclass(frozen=True)
class MetricPoint:
    """One computed metric value (or reasoned null) for a ticker-as_of_year."""

    as_of_year: int
    value: float | None
    reason_code: str | None
    window_years_present: int

    def __post_init__(self) -> None:
        validate_value_xor_reason(self.value, self.reason_code)


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
