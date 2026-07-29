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
    gross_profit_ttm_metric,
    presence_flag,
    stock_over_ttm,
    stock_ratio,
    ttm_over_gross_profit,
    ttm_over_stock,
    ttm_ratio,
    ttm_sum,
)

TREASURY_PRESENCE_THRESHOLD = 0.0
_VALID_ERAS = frozenset(SourceEra)
_LEGACY_ONLY = frozenset({SourceEra.LEGACY})

# Shared by every gross-profit-denominated metric. Full evidence in
# metrics/gross_profit.py and specs 2026-07-26_SP3_METRIC_CATALOG_COMPLETION
# _DESIGN section 2.2.1 and 2026-07-28_GROSS_PROFIT_ERA_AND_RELIABILITY_FLAGS
# _DESIGN.
_GROSS_PROFIT_ERA_NOTE = (
    "ERA-DISPATCHED ARITHMETIC (both eras supported since 2026-07-28): legacy "
    "gross profit is saleq_ttm - cogsq_ttm - dpq_ttm because Compustat states "
    "cogsq before depreciation (saleq - (cogsq + xsgaq) = oibdpq holds for "
    "99.69% of 9,035 legacy quarters); SimFin gross profit is saleq_ttm - "
    "cogsq_ttm because SimFin's Cost of Revenue IS the as-reported line. The "
    "concept is single, only the arithmetic differs, and a window spanning the "
    "boundary is nulled mixed_era_window so no value mixes the two (S4.3). "
    "Legacy rows carry the da_allocation_assumed quality flag: Compustat "
    "normalises away the filer's own D&A allocation, so a = 1 is assumed -- "
    "exact for the 34.4% of filers who fold all D&A into COGS, understating by "
    "a median 13.46pp for the 26.4% who present it outside. One-directional, so "
    "it can never manufacture a false '>40%' pass. SimFin rows need no flag."
)

# Shared by the operand totals below: they are published so the console can
# show the derived figure a ratio actually used, without re-deriving the TTM
# rule a second time (AGENTS.md S2.6). They are deliberately NOT
# era-restricted: each is the sum of one provider's own field, and per-field
# era purity inside `ttm_flow` already nulls a window that spans the boundary
# on a non-equivalent field. Where a CONSUMING ratio is era-restricted
# (interest_pct_operating_income is legacy-only), the operand total may still
# be present while the ratio is null -- which is the honest reading: the
# operand exists, the comparison does not.
_OPERAND_TOTAL_NOTE = (
    " Published as an operand total: three or more shipped metrics use it, and "
    "the console shows it as the derived figure behind them rather than "
    "recomputing the TTM rule in a view."
)

QUARTERLY_REGISTRY: tuple[QuarterMetric, ...] = (
    QuarterMetric(
        "net_margin", "1", "niq_ttm / saleq_ttm", ttm_ratio("niq", "saleq"), inputs=("niq", "saleq")
    ),
    QuarterMetric("roa", "1", "niq_ttm / atq_latest", ttm_over_stock("niq", "atq"), inputs=("niq", "atq")),
    QuarterMetric("roe", "1", "niq_ttm / ceqq_latest", ttm_over_stock("niq", "ceqq"), inputs=("niq", "ceqq")),
    QuarterMetric(
        "debt_to_equity_adj",
        "1",
        "ltq / (ceqq + tstkq)",
        debt_to_equity_adj_metric(),
        inputs=("ltq", "ceqq", "tstkq"),
    ),
    QuarterMetric(
        "current_ratio", "1", "actq_latest / lctq_latest", stock_ratio("actq", "lctq"), inputs=("actq", "lctq")
    ),
    QuarterMetric(
        "st_lt_debt_ratio",
        "1",
        "dlcq_latest / dlttq_latest",
        stock_ratio("dlcq", "dlttq"),
        inputs=("dlcq", "dlttq"),
    ),
    QuarterMetric(
        "lt_debt_payback_years",
        "1",
        "dlttq_latest / niq_ttm",
        stock_over_ttm("dlttq", "niq"),
        inputs=("dlttq", "niq"),
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
        supported_eras=_LEGACY_ONLY,
        inputs=("xintq", "oiadpq"),
    ),
    QuarterMetric(
        "eps_ttm",
        "1",
        "sum of the 4 most recent quarterly epspxq. Documented approximation "
        "(platform spec 6.1): it ignores intra-year share-count drift, which is "
        "acceptable because EPS is used for trend, consistency and valuation "
        "ratios rather than for per-share precision. epspxq is declared "
        "non-equivalent across the provider boundary (SimFin publishes no EPS "
        "column, so the SimFin-era value is derived from Net Income (Common) / "
        "Shares (Basic)), so a window spanning the boundary is nulled "
        "mixed_era_window by per-field purity.",
        ttm_sum("epspxq"),
        inputs=("epspxq",),
        is_operand_total=True,
    ),
    QuarterMetric(
        "net_income_ttm",
        "1",
        "sum of the 4 most recent quarterly niq, in millions. Consumed by the "
        "valuation layer INSTEAD of eps_ttm: SimFin's prices are "
        "split-adjusted while epspxq is as-reported, so price / eps mixes two "
        "share bases and is wrong wherever they differ (BKNG FY2024 reads a "
        "close of 198.74 against a real ~4,900). market_cap / net_income is "
        "invariant to split adjustment because the same basis cancels.",
        ttm_sum("niq"),
        inputs=("niq",),
        is_operand_total=True,
    ),
    QuarterMetric(
        "treasury_stock_present",
        "1",
        "1 if tstkq_latest > 0 else 0",
        presence_flag("tstkq", threshold=TREASURY_PRESENCE_THRESHOLD),
        inputs=("tstkq",),
    ),
    QuarterMetric(
        "gross_margin",
        "2",
        "(saleq_ttm - cogsq_ttm - dpq_ttm) / saleq_ttm. "
        + _GROSS_PROFIT_ERA_NOTE
        + " Golden: KO FY2021 (38655 - 13905 - 1452) / 38655 = 23298 / 38655 = "
        "0.602716, exactly Coca-Cola's published gross margin; the uncorrected "
        "(saleq - cogsq) form gives 0.640279, overstated by 3.76pp.",
        gross_margin_metric(),
        inputs=("saleq", "cogsq", "dpq"),
    ),
    QuarterMetric(
        "sga_pct_gross_profit",
        "2",
        "xsgaq_ttm / gross_profit_ttm. "
        + _GROSS_PROFIT_ERA_NOTE
        + " Second, smaller bias in the same direction: xsgaq is ALSO stated "
        "before depreciation, so it understates published SG&A (KO FY2021 "
        "11,964 against a published 12,144, a 1.5% shortfall).",
        ttm_over_gross_profit("xsgaq"),
        inputs=("xsgaq", "saleq", "cogsq", "dpq"),
    ),
    QuarterMetric(
        "rd_pct_gross_profit",
        "2",
        "xrdq_ttm / gross_profit_ttm. " + _GROSS_PROFIT_ERA_NOTE,
        ttm_over_gross_profit("xrdq"),
        inputs=("xrdq", "saleq", "cogsq", "dpq"),
    ),
    QuarterMetric(
        "dep_pct_gross_profit",
        "2",
        "dpq_ttm / gross_profit_ttm. "
        + _GROSS_PROFIT_ERA_NOTE
        + " Golden: KO FY2021 1452 / 23298 = 0.062323, which reproduces the "
        "platform spec's own book anchor for this metric ('low is better, KO "
        "approx 6%'). That anchor is NOT reproducible with the catalog's "
        "uncorrected gross-profit denominator (1452 / 24750 = 0.058667), so the "
        "catalog's anchor and its formula disagreed with each other.",
        ttm_over_gross_profit("dpq"),
        inputs=("dpq", "saleq", "cogsq"),
    ),
    # --- Operand totals ----------------------------------------------------
    # See _OPERAND_TOTAL_NOTE. Named for what they mean in the domain, not for
    # the column they sum (AGENTS.md S2.7).
    QuarterMetric(
        "revenue_ttm",
        "1",
        "sum of the 4 most recent quarterly saleq." + _OPERAND_TOTAL_NOTE,
        ttm_sum("saleq"),
        inputs=("saleq",),
        is_operand_total=True,
    ),
    QuarterMetric(
        "cost_of_revenue_ttm",
        "1",
        "sum of the 4 most recent quarterly cogsq. NOTE: Compustat states "
        "cogsq BEFORE depreciation while SimFin's Cost of Revenue is the "
        "as-reported line, so this total is NOT comparable across the provider "
        "boundary; per-field era purity nulls a window that spans it."
        + _OPERAND_TOTAL_NOTE,
        ttm_sum("cogsq"),
        inputs=("cogsq",),
        is_operand_total=True,
    ),
    QuarterMetric(
        "depreciation_ttm",
        "1",
        "sum of the 4 most recent quarterly dpq." + _OPERAND_TOTAL_NOTE,
        ttm_sum("dpq"),
        inputs=("dpq",),
        is_operand_total=True,
    ),
    QuarterMetric(
        "sga_ttm",
        "1",
        "sum of the 4 most recent quarterly xsgaq. NOTE: Compustat's xsgaq "
        "absorbs R&D while SimFin reports the two separately, so legacy xsgaq "
        "must be compared against SimFin xsgaq + xrdq, never xsgaq alone."
        + _OPERAND_TOTAL_NOTE,
        ttm_sum("xsgaq"),
        inputs=("xsgaq",),
        is_operand_total=True,
    ),
    QuarterMetric(
        "rd_ttm",
        "1",
        "sum of the 4 most recent quarterly xrdq." + _OPERAND_TOTAL_NOTE,
        ttm_sum("xrdq"),
        inputs=("xrdq",),
        is_operand_total=True,
    ),
    QuarterMetric(
        "interest_expense_ttm",
        "1",
        "sum of the 4 most recent quarterly xintq. NOTE: SimFin reports xintq "
        "net of interest income and sign-inverted (89.8% sign-flip), so the "
        "two eras do not mean the same thing; the consuming ratio "
        "interest_pct_operating_income is legacy-only for that reason, while "
        "this total is published in both eras as each provider's own figure."
        + _OPERAND_TOTAL_NOTE,
        ttm_sum("xintq"),
        inputs=("xintq",),
        is_operand_total=True,
    ),
    QuarterMetric(
        "operating_income_ttm",
        "1",
        "sum of the 4 most recent quarterly oiadpq. NOTE: oiadpq is a "
        "per-company classification boundary across the provider changeover "
        "(44.6% agreement, no remapping above 0.474)." + _OPERAND_TOTAL_NOTE,
        ttm_sum("oiadpq"),
        inputs=("oiadpq",),
        is_operand_total=True,
    ),
    QuarterMetric(
        "gross_profit_ttm",
        "1",
        "ERA-DISPATCHED: saleq_ttm - cogsq_ttm - dpq_ttm in the legacy era, "
        "saleq_ttm - cogsq_ttm in the SimFin era. "
        + _GROSS_PROFIT_ERA_NOTE
        + _OPERAND_TOTAL_NOTE
        + " Golden: KO FY2021 38655 - 13905 - 1452 = 23298.",
        gross_profit_ttm_metric(),
        inputs=("saleq", "cogsq", "dpq"),
        is_operand_total=True,
    ),
)


def operand_totals_for(
    metric: QuarterMetric,
    registry: tuple[QuarterMetric, ...] = None,
) -> tuple[str, ...]:
    """Return the operand-total metric ids that belong beneath `metric`.

    A total belongs to a metric when everything the total reads is also read by
    the metric. That subset rule replaces a field->metric lookup table, so
    there is nothing to keep in step: adding an operand total wires it up
    everywhere it applies, and `gross_profit_ttm` attaches to the three ratios
    built on it without a special case.

    A total never lists itself.
    """
    pool = QUARTERLY_REGISTRY if registry is None else registry
    wanted = set(metric.inputs)
    return tuple(
        total.metric_id
        for total in pool
        if total.is_operand_total
        and total.metric_id != metric.metric_id
        and set(total.inputs) <= wanted
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
        if not metric.inputs:
            raise ValueError(
                f"{metric.metric_id}: declares no inputs. The console publishes "
                "that list as the value's audit trail; an empty one would "
                "render a number with no visible provenance."
            )
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
