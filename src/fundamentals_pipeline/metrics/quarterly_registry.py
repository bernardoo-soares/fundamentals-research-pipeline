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
    gross_margin_metric,
    presence_flag,
    stock_over_ttm,
    stock_ratio,
    ttm_over_gross_profit,
    ttm_over_stock,
    ttm_ratio,
)

TREASURY_PRESENCE_THRESHOLD = 0.0
_VALID_ERAS = frozenset(SourceEra)
_LEGACY_ONLY = frozenset({SourceEra.LEGACY})

# Shared by every gross-profit-denominated metric: Compustat states cogsq and
# xsgaq BEFORE depreciation, so gross profit is saleq - cogsq - dpq and the
# arithmetic is legacy-specific (SimFin's Cost of Revenue already includes D&A).
# Full evidence in metrics/quarterly.ttm_gross_profit and spec
# 2026-07-26_SP3_METRIC_CATALOG_COMPLETION_DESIGN section 2.
_GROSS_PROFIT_ERA_NOTE = (
    "LEGACY ERA ONLY: gross profit is saleq_ttm - cogsq_ttm - dpq_ttm because "
    "Compustat states cogsq before depreciation (the identity saleq - (cogsq + "
    "xsgaq) = oibdpq holds for 99.69% of 9,035 legacy quarters). SimFin's Cost "
    "of Revenue already includes D&A, so the correct arithmetic differs by era "
    "and one formula must not span both (S4.3). SimFin-era rows are null with "
    "era_not_supported rather than false. Conservative bias: dpq includes D&A "
    "allocated to SG&A, understating gross profit by a measured 0.14-0.44pp of "
    "revenue (exact for AAPL and KO FY2021)."
)

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
    QuarterMetric(
        "gross_margin",
        "1",
        "(saleq_ttm - cogsq_ttm - dpq_ttm) / saleq_ttm. "
        + _GROSS_PROFIT_ERA_NOTE
        + " Golden: KO FY2021 (38655 - 13905 - 1452) / 38655 = 23298 / 38655 = "
        "0.602716, exactly Coca-Cola's published gross margin; the uncorrected "
        "(saleq - cogsq) form gives 0.640279, overstated by 3.76pp.",
        gross_margin_metric(),
        supported_eras=_LEGACY_ONLY,
    ),
    QuarterMetric(
        "sga_pct_gross_profit",
        "1",
        "xsgaq_ttm / gross_profit_ttm. "
        + _GROSS_PROFIT_ERA_NOTE
        + " Second, smaller bias in the same direction: xsgaq is ALSO stated "
        "before depreciation, so it understates published SG&A (KO FY2021 "
        "11,964 against a published 12,144, a 1.5% shortfall).",
        ttm_over_gross_profit("xsgaq"),
        supported_eras=_LEGACY_ONLY,
    ),
    QuarterMetric(
        "rd_pct_gross_profit",
        "1",
        "xrdq_ttm / gross_profit_ttm. " + _GROSS_PROFIT_ERA_NOTE,
        ttm_over_gross_profit("xrdq"),
        supported_eras=_LEGACY_ONLY,
    ),
    QuarterMetric(
        "dep_pct_gross_profit",
        "1",
        "dpq_ttm / gross_profit_ttm. "
        + _GROSS_PROFIT_ERA_NOTE
        + " Golden: KO FY2021 1452 / 23298 = 0.062323, which reproduces the "
        "platform spec's own book anchor for this metric ('low is better, KO "
        "approx 6%'). That anchor is NOT reproducible with the catalog's "
        "uncorrected gross-profit denominator (1452 / 24750 = 0.058667), so the "
        "catalog's anchor and its formula disagreed with each other.",
        ttm_over_gross_profit("dpq"),
        supported_eras=_LEGACY_ONLY,
    ),
)


def validate_quarterly_registry(
    registry: tuple[QuarterMetric, ...] = QUARTERLY_REGISTRY,
) -> None:
    """Reject a registry with duplicate metric ids or an inert era restriction.

    `supported_eras=None` means every era and always passes. A non-None value
    must be a non-empty set of valid `SourceEra` members: a typo'd era value
    would never match any row's `source_era`, so `apply_era_restriction`
    would silently null every row of that metric with `era_not_supported`
    (a total coverage wipe) instead of raising. An empty frozenset is
    rejected for the same reason -- it nulls every row by construction.
    """
    seen: set[str] = set()
    for metric in registry:
        if metric.metric_id in seen:
            raise ValueError(f"Duplicate metric_id in registry: {metric.metric_id}")
        seen.add(metric.metric_id)
        if metric.supported_eras is not None:
            if not metric.supported_eras:
                raise ValueError(
                    f"{metric.metric_id}: supported_eras is an empty set, which "
                    "would null every row of this metric with era_not_supported."
                )
            unknown = metric.supported_eras - _VALID_ERAS
            if unknown:
                raise ValueError(
                    f"{metric.metric_id}: supported_eras contains values that "
                    f"are not valid SourceEra members: {sorted(unknown)}."
                )


validate_quarterly_registry()
