"""The Stage 2 slice-1 trend-metric registry (design section 3)."""

from __future__ import annotations

from ..contracts.stage2_metrics_schema import ReasonCode, TrendMetric
from .windows import (
    cagr_metric,
    col,
    consistency_fraction_metric,
    count_years_metric,
    direction_correspondence_metric,
    flag_mixed_era,
    gross_margin_series,
    is_era_guarded,
    negative_equity_with_strong_earnings_metric,
    ratio,
    require_single_era,
    slope_metric,
    sum_ratio_metric,
    up_year_fraction_metric,
)

GROSS_MARGIN_THRESHOLD = 0.40
GROSS_MARGIN_WINDOW = 10
STANDARD_WINDOW = 10

# An N-year window's endpoints are N-1 years apart, so an era guard or flag over
# a 10-year window spans 9. Named once rather than spelled `STANDARD_WINDOW - 1`
# at each use (AGENTS.md S1.1).
STANDARD_WINDOW_SPAN = STANDARD_WINDOW - 1

# The catalog states a hard floor for capex_pct_net_income_avg10y ("both present,
# >= 8 required") rather than the 0.8*n floor the other combinators apply.
CAPEX_MIN_WINDOW_YEARS = 8

# The book's durable-advantage special case: negative equity is a strength only
# alongside a long profit record. 8 of 10 years, per platform spec 6.2.
NEGATIVE_EQUITY_MIN_PROFITABLE_YEARS = 8

REGISTRY: tuple[TrendMetric, ...] = (
    TrendMetric(
        "revenue_cagr_2y", "1", 2, "CAGR_2(saleq_annual)",
        cagr_metric(col("saleq_annual"), 2),
    ),
    TrendMetric(
        "revenue_cagr_4y", "1", 4, "CAGR_4(saleq_annual)",
        cagr_metric(col("saleq_annual"), 4),
    ),
    TrendMetric(
        "revenue_cagr_10y", "1", 10, "CAGR_10(saleq_annual)",
        cagr_metric(col("saleq_annual"), 10),
    ),
    TrendMetric(
        "retained_earnings_cagr_10y", "1", 10, "CAGR_10(req_q4)",
        cagr_metric(col("req_q4"), 10),
    ),
    TrendMetric(
        "eps_up_year_fraction_10y", "3", 10,
        "fraction of YoY increases in epspxq_annual over the 10y window.\n"
        "SPLIT BASIS (fixed 2026-07-29, the reason for version 3): Compustat "
        "publishes EPS as-reported and never restates it after a split, so the "
        "legacy series changed basis at every split and a split registered as "
        "a collapse in earnings. The error was ONE-DIRECTIONAL -- a split can "
        "only ever invent a down year -- and companies split because the price "
        "compounded, so this systematically penalised serial compounders. "
        "Measured on 431 tickers: 11.1% carried a wrong value, median "
        "understatement 0.111, worst 0.444 (AAPL read 0.333 against a true "
        "0.778) and 1.6% flipped a >=0.80 verdict. Stage 1 now divides the "
        "legacy series by ajexq, which reproduces published restated EPS "
        "exactly (AAPL FY2020 3.2975 vs 3.31; GOOGL FY2022 4.5950 vs 4.59).\n"
        "RESIDUAL, flagged not fixed: SimFin publishes no adjustment factor "
        "and restates share counts inconsistently (15 of 20 boundary splitters "
        "agree with the ajexq-adjusted basis, 5 do not), so a window reaching "
        "into that era carries eps_basis_unverified. No heuristic detector is "
        "used: a share-count step cannot tell a split from merger-funded "
        "issuance, and EQT, TFC and SJM step >1.4x in FY2024 for that reason.\n"
        "ALSO: epspxq is as-reported in the legacy era but derived as "
        "NI(common)/shares(basic) in the SimFin era. Measured FY2023: the "
        "2022->2023 direction flips for 5.7% of tickers at a median relative "
        "difference of 0.23%, affecting at most 1 of ~9 pairs in the window.",
        flag_mixed_era(
            up_year_fraction_metric(col("epspxq_annual"), 10),
            STANDARD_WINDOW_SPAN,
            flag=ReasonCode.EPS_BASIS_UNVERIFIED,
        ),
    ),
    TrendMetric(
        "net_income_up_year_fraction_10y", "1", 10,
        "fraction of YoY increases in niq_annual over the 10y window",
        up_year_fraction_metric(col("niq_annual"), 10),
    ),
    TrendMetric(
        "net_margin_ge20_years_10y", "1", 10,
        "fraction of 10y window years with niq_annual/saleq_annual > 0.20",
        consistency_fraction_metric(ratio("niq_annual", "saleq_annual"), 0.20, 10),
    ),
    TrendMetric(
        "buyback_years_10y", "2", 10,
        "count of 10y window years with prstkcy_annual > 0 "
        "(NOTE: legacy Compustat prstkcy is GROSS repurchase while SimFin "
        "is NET equity flow, and SimFin publishes no gross leg, so this "
        "cannot be reconciled. Measured FY2023: the >0 verdict flips for "
        "13.0% of tickers, 39:1 biased toward legacy seeing a buyback that "
        "SimFin does not, so the count reads LOW by up to 2 of 10 years for "
        "SimFin-served tickers. Post-2022 this counts net equity return, "
        "not repurchase.) Version 2 attaches that measured, one-directional "
        "bias to the row as cross_era_window rather than leaving it in this "
        "docstring, where the UI could not see it.",
        flag_mixed_era(
            count_years_metric(col("prstkcy_annual"), 0.0, 10),
            STANDARD_WINDOW_SPAN,
            flag=ReasonCode.CROSS_ERA_WINDOW,
        ),
    ),
    TrendMetric(
        "dividend_payer_years_10y", "2", 10,
        "count of 10y window years with dvy_annual > 0",
        count_years_metric(col("dvy_annual"), 0.0, 10),
    ),
    TrendMetric(
        "gross_margin_ge40_years_10y", "1", GROSS_MARGIN_WINDOW,
        "fraction of 10y window years with "
        "(saleq_annual - cogsq_annual - dpq_annual) / saleq_annual > 0.40 "
        "(NOTE: depreciation is subtracted because Compustat states cogsq "
        "BEFORE it -- the identity saleq - (cogsq + xsgaq) = oibdpq holds for "
        "99.69% of 9,035 legacy quarters. The uncorrected (saleq - cogsq) form "
        "overstates published gross margin by a median 4.09pp against this "
        "metric's own 0.40 threshold; KO FY2021 corrected is 0.6027, exactly "
        "Coca-Cola's published figure, versus 0.6403 uncorrected. "
        "ERA-GUARDED: the arithmetic is legacy-specific because SimFin's Cost "
        "of Revenue already includes D&A, and 12.8% of companies cross the 0.40 "
        "line by provider alone even after the correction, so any window "
        "spanning the provider boundary is nulled mixed_era_window.)",
        require_single_era(
            consistency_fraction_metric(
                gross_margin_series(), GROSS_MARGIN_THRESHOLD, GROSS_MARGIN_WINDOW
            ),
            GROSS_MARGIN_WINDOW - 1,
        ),
        requires_single_era=True,
    ),
    TrendMetric(
        "negative_equity_strong_earnings", "1", STANDARD_WINDOW,
        "1 if ceqq_q4 < 0 AND niq_annual > 0 in at least 8 of the 10 window "
        "years, else 0. The book's durable-advantage special case: negative "
        "book equity created by buybacks or dividends alongside a long profit "
        "record is a strength, not distress. A conjunction rather than two "
        "metrics so the negative-equity leg cannot be read alone as a negative "
        "signal. 0.0 is a real answer; nulls mean a missing equity reading "
        "(missing_input) or too little earnings history "
        "(insufficient_history). Not era-guarded: ceqq agrees 0.964 and niq "
        "0.949 across the provider boundary, both at median 0.0000.",
        negative_equity_with_strong_earnings_metric(
            col("ceqq_q4"),
            col("niq_annual"),
            STANDARD_WINDOW,
            min_profitable_years=NEGATIVE_EQUITY_MIN_PROFITABLE_YEARS,
        ),
    ),
    TrendMetric(
        "capex_pct_net_income_avg10y", "1", STANDARD_WINDOW,
        "sum(capxy_annual) / sum(niq_annual) over the 10y window years where "
        "BOTH are present, at least 8 required. Both-present is required so the "
        "ratio has one consistent basis: summing capex over 10 years against "
        "earnings over 8 would overstate it by construction. A non-positive "
        "earnings sum yields negative_base/zero_denominator rather than a "
        "signed percentage. ERA-GUARDED: capxy is declared cross-era equivalent "
        "but the FY2023 audit CONTRADICTS it at 0.551 agreement, so a window "
        "summing capex across the provider boundary is nulled "
        "mixed_era_window.",
        require_single_era(
            sum_ratio_metric(
                col("capxy_annual"),
                col("niq_annual"),
                STANDARD_WINDOW,
                min_present=CAPEX_MIN_WINDOW_YEARS,
            ),
            STANDARD_WINDOW - 1,
        ),
        requires_single_era=True,
    ),
    TrendMetric(
        "receivables_pct_sales_trend_10y", "1", STANDARD_WINDOW,
        "ordinary-least-squares slope per year of rectq_q4 / saleq_annual over "
        "the 10y window's present years. Negative means receivables are "
        "shrinking relative to sales, which the book reads as good. Pins the "
        "catalog's underspecified 'trend of'; OLS rather than last-minus-first "
        "because the latter is decided by two points and inverts on a single "
        "outlier year. ERA-GUARDED: rectq is declared cross-era equivalent but "
        "the FY2023 audit CONTRADICTS it at 0.566, so a window spanning the "
        "provider boundary is nulled mixed_era_window.",
        require_single_era(
            slope_metric(ratio("rectq_q4", "saleq_annual"), STANDARD_WINDOW),
            STANDARD_WINDOW - 1,
        ),
        requires_single_era=True,
    ),
    TrendMetric(
        "inventory_earnings_correspondence_10y", "1", STANDARD_WINDOW,
        "fraction of consecutive present year-pairs in the 10y window where "
        "invtq_q4 and niq_annual move in the SAME direction. The book's check "
        "that inventory and earnings rise together. A zero change on either "
        "side counts as NOT corresponding: a flat series has no direction, and "
        "counting it as agreement would let a dormant inventory line read as "
        "tracking earnings. General family in practice -- financials report no "
        "inventory, so they null missing_input. Not era-guarded: invtq agrees "
        "0.901 at median 0.0000 and niq 0.949.",
        direction_correspondence_metric(
            col("invtq_q4"), col("niq_annual"), STANDARD_WINDOW
        ),
    ),
    TrendMetric(
        "goodwill_trend", "1", STANDARD_WINDOW,
        "fraction of consecutive present year-pairs in the 10y window where "
        "gdwlq_q4 INCREASED. Pins the catalog's 'YoY changes in gdwlq_q4', "
        "which names a series rather than a value; the fraction of rising years "
        "answers how often the company adds goodwill, i.e. serial "
        "acquisitiveness, which is the book's concern. LEGACY ERA IN FACT: "
        "gdwlq is 0 of 758 populated in the SimFin era (SimFin's balance file "
        "has no goodwill column at all), so SimFin-era years contribute "
        "nothing; ERA-GUARDED so a window straddling the boundary nulls "
        "mixed_era_window rather than silently reporting a legacy-only "
        "sub-window as a 10-year result.",
        require_single_era(
            up_year_fraction_metric(col("gdwlq_q4"), STANDARD_WINDOW),
            STANDARD_WINDOW - 1,
        ),
        requires_single_era=True,
    ),
)


def validate_registry(registry: tuple[TrendMetric, ...] = REGISTRY) -> None:
    """Reject a registry whose declarations do not match its compute functions.

    `requires_single_era` is a declaration; `windows.require_single_era` is the
    enforcement. If a metric declares the constraint but is not wrapped, the
    flag would be inert and the metric would silently compute across the
    provider boundary -- exactly the failure the flag exists to prevent.
    """
    seen: set[str] = set()
    for metric in registry:
        if metric.metric_id in seen:
            raise ValueError(f"Duplicate metric_id in registry: {metric.metric_id}")
        seen.add(metric.metric_id)
        if metric.requires_single_era and not is_era_guarded(metric.compute):
            raise ValueError(
                f"{metric.metric_id}: requires_single_era=True but its compute "
                "function is not wrapped by windows.require_single_era, so the "
                "declaration would have no effect."
            )


validate_registry()
