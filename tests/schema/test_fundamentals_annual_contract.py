from __future__ import annotations

from fundamentals_pipeline.contracts.fundamentals_annual_schema import (
    ANNUAL_COMPLETENESS_COLUMNS,
    ANNUAL_KEY_COLUMNS,
    ANNUAL_VALUE_COLUMNS,
    FLOW_FIELDS,
    STOCK_FIELDS,
    YTD_ANNUAL_FIELDS,
)
from fundamentals_pipeline.contracts.stage1_fundamentals_schema import (
    CORE_RAW_FIELDS,
    EXTENDED_RAW_FIELDS,
    SUPPORT_RAW_FIELDS,
)


def test_classification_partitions_all_stage1_raw_fields() -> None:
    raw = set(CORE_RAW_FIELDS) | set(SUPPORT_RAW_FIELDS) | set(EXTENDED_RAW_FIELDS)
    classified = set(FLOW_FIELDS) | set(YTD_ANNUAL_FIELDS) | set(STOCK_FIELDS)
    assert classified == raw
    # disjoint: no field in two classes
    assert len(FLOW_FIELDS) + len(YTD_ANNUAL_FIELDS) + len(STOCK_FIELDS) == len(raw)


def test_classification_counts() -> None:
    assert len(FLOW_FIELDS) == 14
    assert len(YTD_ANNUAL_FIELDS) == 3
    assert len(STOCK_FIELDS) == 18


def test_annual_value_columns_order_and_suffixes() -> None:
    expected = (
        *(f"{f}_annual" for f in FLOW_FIELDS),
        *(f"{f}_annual" for f in YTD_ANNUAL_FIELDS),
        *(f"{f}_q4" for f in STOCK_FIELDS),
    )
    assert ANNUAL_VALUE_COLUMNS == expected
    assert len(ANNUAL_VALUE_COLUMNS) == 35


def test_key_and_completeness_columns() -> None:
    assert ANNUAL_KEY_COLUMNS == ("ticker", "fiscal_year")
    assert ANNUAL_COMPLETENESS_COLUMNS == ("quarters_present", "has_q4")
