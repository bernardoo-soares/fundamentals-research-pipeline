from __future__ import annotations

import pandas as pd
import pytest

from fundamentals_pipeline.contracts.metric_reason_codes import ReasonCode
from fundamentals_pipeline.metrics.registry import REGISTRY
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
    ]
    assert len(ids) == len(set(ids))  # unique
    for m in REGISTRY:
        assert m.version and m.formula and callable(m.compute)
        assert m.window_length in (2, 4, 10)


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
    only while the mechanism was unused. `gross_margin_ge40_years_10y` is the
    first user: its gross-profit arithmetic is legacy-specific, so a window
    spanning the provider boundary must null rather than compute.

    `validate_registry` enforces the declaration/wrapper match at import time;
    this pins which metrics opt in, so adding one is a deliberate act with a
    measurable coverage cost rather than an accident.
    """
    guarded = {m.metric_id for m in REGISTRY if m.requires_single_era}
    assert guarded == {"gross_margin_ge40_years_10y"}
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
