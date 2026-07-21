from __future__ import annotations

import pytest

from trading_bot.contracts.stage1_fundamentals_schema import (
    CORE_RAW_FIELDS,
    MONETARY_RAW_FIELDS,
    PER_SHARE_FIELDS,
    PUBLISHED_UNIT_SCALE_NAME,
    SHARE_COUNT_FIELDS,
    STAGE1_KEY_COLUMNS,
    STAGE1_OUTPUT_COLUMNS,
    SUPPORT_RAW_FIELDS,
    stage1_yearly_columns,
    validate_stage1_frame_columns,
)


def test_stage1_output_columns_start_with_provider_agnostic_key() -> None:
    assert STAGE1_KEY_COLUMNS == ("ticker", "year", "quarter")
    assert STAGE1_OUTPUT_COLUMNS[:3] == STAGE1_KEY_COLUMNS


def test_stage1_output_columns_include_core_and_support_fields_only() -> None:
    assert STAGE1_OUTPUT_COLUMNS == (
        *STAGE1_KEY_COLUMNS,
        *CORE_RAW_FIELDS,
        *SUPPORT_RAW_FIELDS,
    )
    assert "capxy" in SUPPORT_RAW_FIELDS
    assert "Operating_Margin" not in STAGE1_OUTPUT_COLUMNS
    assert "period_end" not in STAGE1_OUTPUT_COLUMNS


def test_stage1_yearly_columns_returns_canonical_order() -> None:
    assert stage1_yearly_columns() == STAGE1_OUTPUT_COLUMNS


def test_validate_stage1_frame_columns_accepts_full_schema() -> None:
    validate_stage1_frame_columns(list(STAGE1_OUTPUT_COLUMNS))


def test_validate_stage1_frame_columns_rejects_missing_columns() -> None:
    columns = list(STAGE1_OUTPUT_COLUMNS[:-1])
    with pytest.raises(ValueError, match="missing required columns"):
        validate_stage1_frame_columns(columns)


def test_validate_stage1_frame_columns_rejects_wrong_leading_order() -> None:
    columns = list(STAGE1_OUTPUT_COLUMNS)
    columns[:3] = ["year", "ticker", "quarter"]
    with pytest.raises(ValueError, match="must start with columns"):
        validate_stage1_frame_columns(columns)


def test_all_published_raw_fields_have_exactly_one_unit_class() -> None:
    classified = set(MONETARY_RAW_FIELDS + SHARE_COUNT_FIELDS + PER_SHARE_FIELDS)
    raw_fields = set(CORE_RAW_FIELDS + SUPPORT_RAW_FIELDS)
    assert classified == raw_fields
    assert set(MONETARY_RAW_FIELDS).isdisjoint(SHARE_COUNT_FIELDS)
    assert set(MONETARY_RAW_FIELDS).isdisjoint(PER_SHARE_FIELDS)
    assert set(SHARE_COUNT_FIELDS).isdisjoint(PER_SHARE_FIELDS)


def test_published_scale_uses_legacy_million_convention() -> None:
    assert PUBLISHED_UNIT_SCALE_NAME == "legacy_millions_scale"
    assert "saleq" in MONETARY_RAW_FIELDS
    assert "cshfdq" in SHARE_COUNT_FIELDS
    assert PER_SHARE_FIELDS == ("epspxq",)
