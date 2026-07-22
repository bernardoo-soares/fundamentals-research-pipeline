from __future__ import annotations

import pandas as pd

from fundamentals_pipeline.metrics.registry import REGISTRY


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
