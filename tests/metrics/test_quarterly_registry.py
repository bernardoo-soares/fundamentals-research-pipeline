from __future__ import annotations

import pandas as pd
import pytest

from fundamentals_pipeline.contracts.metric_reason_codes import ReasonCode
from fundamentals_pipeline.metrics.quarterly_registry import (
    QUARTERLY_REGISTRY,
    validate_quarterly_registry,
)

METRICS = {m.metric_id: m for m in QUARTERLY_REGISTRY}


def test_registry_has_the_nine_slice1_metrics() -> None:
    assert set(METRICS) == {
        "net_margin",
        "roa",
        "roe",
        "debt_to_equity_adj",
        "current_ratio",
        "st_lt_debt_ratio",
        "lt_debt_payback_years",
        "interest_pct_operating_income",
        "treasury_stock_present",
    }


def test_validate_rejects_duplicate_ids() -> None:
    dup = QUARTERLY_REGISTRY + (QUARTERLY_REGISTRY[0],)
    with pytest.raises(ValueError):
        validate_quarterly_registry(dup)


# --- Real AAPL FY2023 corpus (warehouse; matches Apple's 10-K to the $M) ---
# 2023Q1..Q4 sum to revenue 383,285 and net income 96,995 (Apple FY2023).
_AAPL = [
    # year, quarter, saleq, niq, atq, ceqq, ltq, tstkq, era
    (2022, 4, 90146.0, 20721.0, 352755.0, 50672.0, 302083.0, 0.0, "legacy_compustat"),
    (2023, 1, 117154.0, 29998.0, 346747.0, 56727.0, 290020.0, None, "simfin"),
    (2023, 2, 94836.0, 24160.0, 332160.0, 62158.0, 270002.0, None, "simfin"),
    (2023, 3, 81797.0, 19881.0, 335038.0, 60274.0, 274764.0, None, "simfin"),
    (2023, 4, 89498.0, 22956.0, 352583.0, 62146.0, 290437.0, None, "simfin"),
]


def _aapl_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAPL", "year": y, "quarter": q, "saleq": s, "niq": n,
                "atq": a, "ceqq": c, "ltq": lt, "tstkq": t, "source_era": e,
            }
            for (y, q, s, n, a, c, lt, t, e) in _AAPL
        ]
    )


def _value_at(metric_id, frame, year, quarter):
    return next(
        p
        for p in METRICS[metric_id].compute(frame)
        if p.year == year and p.quarter == quarter
    )


def test_golden_net_margin_aapl_fy2023() -> None:
    # niq_ttm 96,995 / saleq_ttm 383,285 = 0.25307 (Apple FY2023 net margin ~25.3%)
    p = _value_at("net_margin", _aapl_frame(), 2023, 4)
    assert p.value == pytest.approx(96995.0 / 383285.0)
    assert p.value == pytest.approx(0.25307, abs=1e-5)


def test_golden_roa_aapl_fy2023() -> None:
    # 96,995 / total assets 352,583 = 0.27510
    p = _value_at("roa", _aapl_frame(), 2023, 4)
    assert p.value == pytest.approx(96995.0 / 352583.0)


def test_golden_roe_aapl_fy2023() -> None:
    # 96,995 / total equity 62,146 = 1.56076 (Apple's famously high ROE)
    p = _value_at("roe", _aapl_frame(), 2023, 4)
    assert p.value == pytest.approx(96995.0 / 62146.0)


def test_golden_debt_to_equity_adj_aapl_tstk_null_flagged() -> None:
    # 2023 simfin: tstkq null -> ltq 290,437 / ceqq 62,146, flagged tstk_unavailable
    p = _value_at("debt_to_equity_adj", _aapl_frame(), 2023, 4)
    assert p.value == pytest.approx(290437.0 / 62146.0)
    assert p.quality_flag == ReasonCode.TSTK_UNAVAILABLE


def test_golden_debt_to_equity_adj_aapl_tstk_present_no_flag() -> None:
    # 2022 legacy: tstkq 0 present -> ltq 302,083 / ceqq 50,672, no flag
    p = _value_at("debt_to_equity_adj", _aapl_frame(), 2022, 4)
    assert p.value == pytest.approx(302083.0 / 50672.0)
    assert p.quality_flag is None


def test_golden_roe_negative_equity_azo() -> None:
    # AutoZone (AZO) FY2023Q4: ceqq -4,349.894 < 0 -> roe null (negative_base)
    frame = pd.DataFrame(
        [
            {"ticker": "AZO", "year": 2023, "quarter": q, "niq": 500.0,
             "ceqq": -4349.894, "source_era": "simfin"}
            for q in (1, 2, 3, 4)
        ]
    )
    p = _value_at("roe", frame, 2023, 4)
    assert p.value is None
    assert p.reason_code == ReasonCode.NEGATIVE_BASE


def test_golden_interest_pct_mixed_era_abbv() -> None:
    # AbbVie (ABBV) at 2023Q1: xintq window 2022Q2-Q4 legacy gross (556/560/566)
    # + 2023Q1 simfin net (-454). xintq non-equivalent -> mixed_era_window.
    frame = pd.DataFrame(
        [
            {"ticker": "ABBV", "year": 2022, "quarter": 2, "xintq": 556.0,
             "oiadpq": 5000.0, "source_era": "legacy_compustat"},
            {"ticker": "ABBV", "year": 2022, "quarter": 3, "xintq": 560.0,
             "oiadpq": 5000.0, "source_era": "legacy_compustat"},
            {"ticker": "ABBV", "year": 2022, "quarter": 4, "xintq": 566.0,
             "oiadpq": 5000.0, "source_era": "legacy_compustat"},
            {"ticker": "ABBV", "year": 2023, "quarter": 1, "xintq": -454.0,
             "oiadpq": 2918.0, "source_era": "simfin"},
        ]
    )
    p = _value_at("interest_pct_operating_income", frame, 2023, 1)
    assert p.value is None
    assert p.reason_code == ReasonCode.MIXED_ERA_WINDOW
