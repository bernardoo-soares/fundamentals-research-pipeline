"""The Stage 2 slice-1 trend-metric registry (design section 3)."""

from __future__ import annotations

from ..contracts.stage2_metrics_schema import TrendMetric
from .windows import (
    cagr_metric,
    col,
    consistency_fraction_metric,
    count_years_metric,
    ratio,
    up_year_fraction_metric,
)

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
        "eps_up_year_fraction_10y", "2", 10,
        "fraction of YoY increases in epspxq_annual over the 10y window "
        "(NOTE: epspxq is as-reported basic EPS in the legacy era but is "
        "derived as NI(common)/shares(basic) in the SimFin era, which publishes "
        "no EPS column at all — an irreducible declared divergence, see "
        "contracts/field_era_semantics.py)",
        up_year_fraction_metric(col("epspxq_annual"), 10),
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
        "buyback_years_10y", "1", 10,
        "count of 10y window years with prstkcy_annual > 0 "
        "(NOTE: legacy Compustat prstkcy is gross repurchase while SimFin is "
        "net equity flow — a declared divergence with aligned magnitudes, see "
        "contracts/field_era_semantics.py)",
        count_years_metric(col("prstkcy_annual"), 0.0, 10),
    ),
    TrendMetric(
        "dividend_payer_years_10y", "2", 10,
        "count of 10y window years with dvy_annual > 0",
        count_years_metric(col("dvy_annual"), 0.0, 10),
    ),
)
