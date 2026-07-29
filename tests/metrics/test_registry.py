from __future__ import annotations

import pandas as pd
import pytest

from fundamentals_pipeline.contracts.metric_reason_codes import ReasonCode
from fundamentals_pipeline.metrics.registry import (
    REGISTRY,
    operand_totals_for,
)
from fundamentals_pipeline.metrics.windows import gross_margin_series, is_era_guarded


def test_registry_ids_and_shape() -> None:
    ids = [m.metric_id for m in REGISTRY]
    assert ids == [
        "revenue_cagr_2y",
        "revenue_cagr_4y",
        "revenue_cagr_10y",
        "retained_earnings_cagr_10y",
        "eps_up_year_fraction_10y",
        "net_income_up_year_fraction_10y",
        "net_margin_ge20_years_10y",
        "buyback_years_10y",
        "dividend_payer_years_10y",
        "gross_margin_ge40_years_10y",
        "negative_equity_strong_earnings",
        "capex_pct_net_income_avg10y",
        "receivables_pct_sales_trend_10y",
        "inventory_earnings_correspondence_10y",
        "goodwill_trend",
        # Derived intermediates: the per-year value a threshold metric tests,
        # and the masked window sums behind a ratio of sums. Published so the
        # drilldown shows them rather than deriving them (S2.6).
        "net_margin_annual",
        "gross_margin_annual",
        "receivables_pct_sales_annual",
        "capex_window_sum_10y",
        "net_income_window_sum_10y",
    ]
    assert len(ids) == len(set(ids))  # unique
    for m in REGISTRY:
        assert m.version and m.formula and callable(m.compute)
        # 1 for a per-year series, which is a single-year "window".
        assert m.window_length in (1, 2, 4, 10)


def test_trend_operand_totals_attach_by_subset() -> None:
    """The masked sums must reach the metric whose mask they were built under."""
    by_id = {m.metric_id: m for m in REGISTRY}
    assert set(operand_totals_for(by_id["capex_pct_net_income_avg10y"])) == {
        "capex_window_sum_10y",
        "net_income_window_sum_10y",
    }
    assert operand_totals_for(by_id["net_margin_ge20_years_10y"]) == (
        "net_margin_annual",
    )
    # A CAGR has no hidden intermediate: its two endpoints are already in the
    # operand grid, so it must not be given one.
    assert operand_totals_for(by_id["revenue_cagr_10y"]) == ()


def test_a_masked_sum_declares_its_partner_leg() -> None:
    """The partner decides which years are summed, so it is a real input.

    Declaring only the summed leg would put a grid on screen that does not
    explain the number above it.
    """
    by_id = {m.metric_id: m for m in REGISTRY}
    assert set(by_id["net_income_window_sum_10y"].inputs) == {
        "capxy_annual",
        "niq_annual",
    }


def test_registry_metric_computes_expected_value() -> None:
    # revenue growing 100->...; revenue_cagr_10y at 2022 from 100 (2012) to ~259.37
    rows = [{"fiscal_year": 2012 + i, "saleq_annual": 100.0 * (1.1**i)} for i in range(11)]
    frame = pd.DataFrame(rows)
    rev10 = next(m for m in REGISTRY if m.metric_id == "revenue_cagr_10y")
    pts = {p.as_of_year: p for p in rev10.compute(frame)}
    assert abs(pts[2022].value - 0.10) < 1e-6


def _metric(metric_id: str):
    return next(m for m in REGISTRY if m.metric_id == metric_id)


def test_dividend_metric_reads_dvy_not_dvpq() -> None:
    """dvpq is preferred dividends; dvy is total. Version bumps on the change."""
    metric = _metric("dividend_payer_years_10y")
    assert "dvy_annual" in metric.formula
    assert "dvpq" not in metric.formula
    assert metric.version == "2"


def test_dividend_metric_caveat_removed() -> None:
    """The cross-era caveat described a defect that is now fixed."""
    assert "KNOWN LIMITATION" not in _metric("dividend_payer_years_10y").formula


def test_eps_metric_carries_derivation_caveat() -> None:
    """epspxq is as-reported in legacy but derived in SimFin -- irreducible."""
    assert "derived" in _metric("eps_up_year_fraction_10y").formula.lower()


def test_buyback_metric_carries_era_divergence_note() -> None:
    """prstkcy is gross repurchase in legacy but net equity flow in SimFin."""
    assert "net" in _metric("buyback_years_10y").formula.lower()


def test_divergent_input_metrics_carry_measured_caveats():
    """A known defect ships with a visible caveat carrying real numbers.

    Neither metric is era-restricted: the effect is 1-2 years out of 10,
    where require_single_era would cost ~91% of coverage at FY2024. The
    caveats must therefore quantify what the reader is accepting.
    """
    buyback = _metric("buyback_years_10y").formula
    assert "13.0%" in buyback          # verdict flip rate at FY2023
    assert "LOW" in buyback            # directional bias, 39:1
    eps = _metric("eps_up_year_fraction_10y").formula
    assert "5.7%" in eps               # direction flip rate
    assert "0.23%" in eps              # median relative difference


def test_era_guarded_metrics_are_declared_and_enforced():
    """A metric declaring `requires_single_era` must actually be wrapped.

    Supersedes an earlier assertion that NO metric set the flag, which was true
    only while the mechanism was unused. Four metrics now opt in, each because
    its inputs are not comparable across the provider boundary.

    `validate_registry` enforces the declaration/wrapper match at import time;
    this pins which metrics opt in, so adding one is a deliberate act with a
    measurable coverage cost rather than an accident.
    """
    guarded = {m.metric_id for m in REGISTRY if m.requires_single_era}
    assert guarded == {
        "gross_margin_ge40_years_10y",  # gross-profit arithmetic is era-specific
        "capex_pct_net_income_avg10y",  # capxy CONTRADICTED at 0.551
        "receivables_pct_sales_trend_10y",  # rectq CONTRADICTED at 0.566
        # The intermediates inherit the guard of the metric they explain: an
        # unguarded intermediate would show a value beside a nulled metric.
        "gross_margin_annual",
        "receivables_pct_sales_annual",
        "capex_window_sum_10y",
        "net_income_window_sum_10y",
        "goodwill_trend",  # gdwlq is 0/758 populated in the SimFin era
    }
    for metric in REGISTRY:
        assert is_era_guarded(metric.compute) == metric.requires_single_era, (
            metric.metric_id
        )


def test_gross_margin_window_nulls_across_the_provider_boundary():
    """The guard must bite on a mixed window and pass a pure one."""
    metric = _metric("gross_margin_ge40_years_10y")
    def _rows(eras):
        return pd.DataFrame(
            [
                {
                    "fiscal_year": 2013 + i,
                    "saleq_annual": 1000.0,
                    "cogsq_annual": 400.0,
                    "dpq_annual": 50.0,
                    "source_era": era,
                }
                for i, era in enumerate(eras)
            ]
        )
    # gross margin = (1000-400-50)/1000 = 0.55 > 0.40 in every year
    pure = {p.as_of_year: p for p in metric.compute(_rows(["legacy_compustat"] * 10))}
    assert pure[2022].value == pytest.approx(1.0)
    mixed = {
        p.as_of_year: p
        for p in metric.compute(_rows(["legacy_compustat"] * 9 + ["simfin"]))
    }
    assert mixed[2022].value is None
    assert mixed[2022].reason_code == ReasonCode.MIXED_ERA_WINDOW


def test_gross_margin_series_subtracts_depreciation():
    """Guards the root-caused defect at the trend grain.

    Compustat states cogsq before depreciation, so the uncorrected
    (saleq - cogsq)/saleq overstates published gross margin by a median 4.09pp.
    Here the corrected margin is 0.55 and the uncorrected 0.60, which straddles
    nothing -- but with a 0.40 threshold the difference decides membership for
    companies between the two, which is 12.8% of the corpus.
    """
    frame = pd.DataFrame(
        [
            {
                "fiscal_year": 2020,
                "saleq_annual": 1000.0,
                "cogsq_annual": 400.0,
                "dpq_annual": 50.0,
            }
        ]
    )
    series = gross_margin_series()(frame)
    assert series.loc[2020] == pytest.approx(0.55)
    assert series.loc[2020] != pytest.approx(0.60)


# --- Golden tests: real warehouse corpus, hand-verified (S4.4) ---

# AutoZone 2013-2022: negative book equity in every year, from sustained
# buybacks, alongside a profit in every year. The book's durable-advantage
# special case in its textbook form.
_AZO = [
    (2013, -1687.319, 1016.480), (2014, -1621.857, 1069.744),
    (2015, -1701.390, 1160.241), (2016, -1787.538, 1241.007),
    (2017, -1428.377, 1280.869), (2018, -1520.355, 1337.536),
    (2019, -1713.851, 1617.221), (2020, -877.977, 1732.972),
    (2021, -1797.536, 2170.314), (2022, -3538.913, 2429.604),
]

# Coca-Cola 2013-2022 capital intensity. 2017's low net income is the
# Tax-Cuts-and-Jobs-Act charge year, and is real.
_KO_CAPEX = [
    (2013, 2550.0, 8584.0), (2014, 2406.0, 7098.0), (2015, 2553.0, 7351.0),
    (2016, 2262.0, 6527.0), (2017, 1675.0, 1248.0), (2018, 1347.0, 6434.0),
    (2019, 2054.0, 8920.0), (2020, 1177.0, 7747.0), (2021, 1367.0, 9771.0),
    (2022, 1484.0, 9542.0),
]


def _legacy_frame(rows, **names):
    """Annual frame in the legacy era, so era-guarded metrics compute."""
    first, second = names["first"], names["second"]
    return pd.DataFrame(
        [
            {
                "fiscal_year": year,
                first: a,
                second: b,
                "source_era": "legacy_compustat",
            }
            for (year, a, b) in rows
        ]
    )


def test_golden_negative_equity_strong_earnings_azo() -> None:
    """AZO FY2022: equity -3,538.913 with 10 of 10 profitable years -> 1.0."""
    frame = _legacy_frame(_AZO, first="ceqq_q4", second="niq_annual")
    metric = _metric("negative_equity_strong_earnings")
    point = {p.as_of_year: p for p in metric.compute(frame)}[2022]
    assert point.value == pytest.approx(1.0)
    assert point.window_years_present == 10


def test_golden_negative_equity_requires_the_profit_record_azo() -> None:
    """The same negative equity WITHOUT the profit record must not qualify.

    Guards the conjunction: negative equity alone is not the signal.
    """
    weakened = [(y, e, -1.0 if y >= 2019 else n) for (y, e, n) in _AZO]
    frame = _legacy_frame(weakened, first="ceqq_q4", second="niq_annual")
    metric = _metric("negative_equity_strong_earnings")
    point = {p.as_of_year: p for p in metric.compute(frame)}[2022]
    assert point.value == pytest.approx(0.0), "6 of 10 profitable years fails the 8 floor"


def test_golden_capex_pct_net_income_ko_fy2022() -> None:
    """KO 2013-2022: 18,875 / 73,222 = 0.257778.

    Coca-Cola reinvests about a quarter of earnings in fixed assets, which sits
    just above the platform spec's '< 25% great' anchor and well inside its
    '< 50% good' one -- the expected shape for a low-capital-intensity brand.
    """
    frame = _legacy_frame(_KO_CAPEX, first="capxy_annual", second="niq_annual")
    metric = _metric("capex_pct_net_income_avg10y")
    point = {p.as_of_year: p for p in metric.compute(frame)}[2022]
    assert point.value == pytest.approx(18875.0 / 73222.0)
    assert point.value == pytest.approx(0.257778, abs=1e-6)


def test_golden_capex_pct_nulls_across_the_provider_boundary() -> None:
    """capxy is CONTRADICTED at 0.551, so a mixed window must not sum."""
    rows = [(y, c, n) for (y, c, n) in _KO_CAPEX]
    frame = _legacy_frame(rows, first="capxy_annual", second="niq_annual")
    frame.loc[frame["fiscal_year"] == 2022, "source_era"] = "simfin"
    metric = _metric("capex_pct_net_income_avg10y")
    point = {p.as_of_year: p for p in metric.compute(frame)}[2022]
    assert point.value is None
    assert point.reason_code == ReasonCode.MIXED_ERA_WINDOW
