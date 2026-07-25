"""The metrics_quarterly slice-1 registry (design section 2.1).

Each entry is one declarative QuarterMetric: identity + a pure compute function
wired to canonical field names. Adding a metric is one entry here; there is no
dispatcher to edit (AGENTS.md S2.2).
"""

from __future__ import annotations

from ..contracts.metrics_quarterly_schema import QuarterMetric
from .quarterly import (
    debt_to_equity_adj_metric,
    presence_flag,
    stock_over_ttm,
    stock_ratio,
    ttm_over_stock,
    ttm_ratio,
)

TREASURY_PRESENCE_THRESHOLD = 0.0

QUARTERLY_REGISTRY: tuple[QuarterMetric, ...] = (
    QuarterMetric(
        "net_margin", "1", "niq_ttm / saleq_ttm", ttm_ratio("niq", "saleq")
    ),
    QuarterMetric("roa", "1", "niq_ttm / atq_latest", ttm_over_stock("niq", "atq")),
    QuarterMetric("roe", "1", "niq_ttm / ceqq_latest", ttm_over_stock("niq", "ceqq")),
    QuarterMetric(
        "debt_to_equity_adj",
        "1",
        "ltq / (ceqq + tstkq)",
        debt_to_equity_adj_metric(),
    ),
    QuarterMetric(
        "current_ratio", "1", "actq_latest / lctq_latest", stock_ratio("actq", "lctq")
    ),
    QuarterMetric(
        "st_lt_debt_ratio",
        "1",
        "dlcq_latest / dlttq_latest",
        stock_ratio("dlcq", "dlttq"),
    ),
    QuarterMetric(
        "lt_debt_payback_years",
        "1",
        "dlttq_latest / niq_ttm",
        stock_over_ttm("dlttq", "niq"),
    ),
    QuarterMetric(
        "interest_pct_operating_income",
        "1",
        "xintq_ttm / oiadpq_ttm",
        ttm_ratio("xintq", "oiadpq"),
    ),
    QuarterMetric(
        "treasury_stock_present",
        "1",
        "1 if tstkq_latest > 0 else 0",
        presence_flag("tstkq", threshold=TREASURY_PRESENCE_THRESHOLD),
    ),
)


def validate_quarterly_registry(
    registry: tuple[QuarterMetric, ...] = QUARTERLY_REGISTRY,
) -> None:
    """Reject a registry with duplicate metric ids."""
    seen: set[str] = set()
    for metric in registry:
        if metric.metric_id in seen:
            raise ValueError(f"Duplicate metric_id in registry: {metric.metric_id}")
        seen.add(metric.metric_id)


validate_quarterly_registry()
