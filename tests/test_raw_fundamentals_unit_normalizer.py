from __future__ import annotations

import pandas as pd

from trading_bot.steps.raw_fundamentals_unit_normalizer import (
    UNIT_NORMALIZATION_REPORT_COLUMNS,
    build_unit_normalization_report,
    normalize_raw_fundamentals_units,
)


def test_normalize_raw_fundamentals_units_scales_simfin_money_and_shares_only() -> None:
    before = pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "year": 2023,
                "quarter": 1,
                "saleq": 120_000_000.0,
                "oancfq": 30_000_000.0,
                "cshfdq": 12_000_000.0,
                "cshoq": 11_000_000.0,
                "epspxq": 2.5,
            }
        ]
    )

    after = normalize_raw_fundamentals_units(before, source_system="simfin")

    row = after.iloc[0]
    assert row["saleq"] == 120.0
    assert row["oancfq"] == 30.0
    assert row["cshfdq"] == 12.0
    assert row["cshoq"] == 11.0
    assert row["epspxq"] == 2.5


def test_normalize_raw_fundamentals_units_keeps_legacy_values_unchanged() -> None:
    before = pd.DataFrame(
        [
            {
                "ticker": "MSFT",
                "year": 2022,
                "quarter": 4,
                "saleq": 50_000.0,
                "cshfdq": 7_500.0,
                "epspxq": 2.2,
            }
        ]
    )

    after = normalize_raw_fundamentals_units(
        before,
        source_system="legacy_processed_fundamentals",
    )

    assert after.equals(before)


def test_build_unit_normalization_report_records_divisors_and_magnitudes() -> None:
    before = pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "year": 2023,
                "quarter": 1,
                "saleq": 120_000_000.0,
                "cshfdq": 12_000_000.0,
                "epspxq": 2.5,
            }
        ]
    )
    after = normalize_raw_fundamentals_units(before, source_system="simfin")

    report = build_unit_normalization_report(before, after, source_system="simfin")

    assert tuple(report.columns) == UNIT_NORMALIZATION_REPORT_COLUMNS

    saleq = report[report["field_name"] == "saleq"].iloc[0]
    assert saleq["field_class"] == "monetary"
    assert saleq["scale_divisor_applied"] == 1_000_000.0
    assert saleq["max_abs_before"] == 120_000_000.0
    assert saleq["max_abs_after"] == 120.0

    shares = report[report["field_name"] == "cshfdq"].iloc[0]
    assert shares["field_class"] == "shares"
    assert shares["scale_divisor_applied"] == 1_000_000.0
    assert shares["max_abs_after"] == 12.0

    eps = report[report["field_name"] == "epspxq"].iloc[0]
    assert eps["field_class"] == "per_share"
    assert eps["scale_divisor_applied"] == 1.0
    assert eps["max_abs_after"] == 2.5
