"""Contract for the Stage 2 metrics_quarterly (point-in-time & TTM) layer.

Compute-free: the QuarterPoint/QuarterMetric abstractions, quality-flag
vocabulary, and the metrics_quarterly table schema. Computation lives in the
pure `metrics/quarterly.py` module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .metric_reason_codes import (  # QUALITY_FLAGS re-exported for importers
    QUALITY_FLAGS,
    validate_quality_flag,
    validate_value_xor_reason,
)

__all__ = [
    "METRICS_QUARTERLY_COLUMNS",
    "METRICS_QUARTERLY_PIPELINE_VERSION",
    "QUALITY_FLAGS",
    "QuarterMetric",
    "QuarterPoint",
    "create_metrics_quarterly_ddl",
]

METRICS_QUARTERLY_PIPELINE_VERSION = "metrics-quarterly-1.1"

@dataclass(frozen=True)
class QuarterPoint:
    """One computed metric value (or reasoned null) for a ticker-year-quarter."""

    year: int
    quarter: int
    value: float | None
    reason_code: str | None
    quality_flag: str | None
    source_era: str | None

    def __post_init__(self) -> None:
        validate_value_xor_reason(self.value, self.reason_code)
        validate_quality_flag(self.value, self.quality_flag)


@dataclass(frozen=True)
class QuarterMetric:
    """A declarative point-in-time/TTM metric: identity + a pure compute fn.

    Era purity for TTM sums is enforced inside metrics/quarterly.ttm_flow from
    field_era_semantics, so no per-metric flag is needed for that.

    `supported_eras` is a different concern: it declares the eras in which the
    metric is meaningful at all. None means every era. The builder applies it
    uniformly via metrics.quarterly.apply_era_restriction, so the declaration
    is the sole input to the single enforcement call and the two cannot drift.
    """

    metric_id: str
    version: str
    formula: str
    compute: Callable[[Any], list[QuarterPoint]]
    supported_eras: frozenset[str] | None = None
    # The `fundamentals_quarterly` fields this metric reads. Same contract and
    # same drift guard as `TrendMetric.inputs`; see that docstring.
    inputs: tuple[str, ...] = ()


METRICS_QUARTERLY_COLUMNS: tuple[str, ...] = (
    "ticker",
    "year",
    "quarter",
    "metric_id",
    "value",
    "reason_code",
    "quality_flag",
    "source_era",
    "metric_version",
    "computed_at",
    "pipeline_version",
)


def create_metrics_quarterly_ddl() -> str:
    """DDL for the metrics_quarterly table."""
    return (
        "CREATE TABLE metrics_quarterly (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  year INTEGER NOT NULL,\n"
        "  quarter INTEGER NOT NULL,\n"
        "  metric_id VARCHAR NOT NULL,\n"
        "  value DOUBLE,\n"
        "  reason_code VARCHAR,\n"
        "  quality_flag VARCHAR,\n"
        "  source_era VARCHAR,\n"
        "  metric_version VARCHAR,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, year, quarter, metric_id)\n"
        ")"
    )
