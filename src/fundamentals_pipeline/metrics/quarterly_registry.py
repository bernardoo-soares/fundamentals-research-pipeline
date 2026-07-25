"""The metrics_quarterly slice-1 registry (design section 2.1).

Each entry is one declarative QuarterMetric: identity + a pure compute function
wired to canonical field names. Adding a metric is one entry here; there is no
dispatcher to edit (AGENTS.md S2.2).
"""

from __future__ import annotations

from ..contracts.era_resolution import SourceEra
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
        "2",
        "xintq_ttm / oiadpq_ttm (LEGACY ERA ONLY: both legs diverge across "
        "the provider boundary. SimFin reports xintq net of interest income "
        "and sign-inverted (89.8% sign-flip), and oiadpq is a per-company "
        "classification boundary (44.6% agreement, no remapping above 0.474). "
        "Measured on 286 dual-era tickers: median step 1.906 across the "
        "switch year, 29.0% flip the <15% verdict. SimFin-era rows are null "
        "with era_not_supported rather than false.)",
        ttm_ratio("xintq", "oiadpq"),
        supported_eras=frozenset({SourceEra.LEGACY}),
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
