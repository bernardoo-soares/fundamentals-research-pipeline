from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.stage1_fundamentals_schema import (
    CORE_RAW_FIELDS,
    EXTENDED_RAW_FIELDS,
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


def test_stage1_output_columns_include_core_support_and_extended_fields_only() -> None:
    assert STAGE1_OUTPUT_COLUMNS == (
        *STAGE1_KEY_COLUMNS,
        *CORE_RAW_FIELDS,
        *SUPPORT_RAW_FIELDS,
        *EXTENDED_RAW_FIELDS,
    )
    assert "capxy" in SUPPORT_RAW_FIELDS
    assert "Operating_Margin" not in STAGE1_OUTPUT_COLUMNS
    assert "period_end" not in STAGE1_OUTPUT_COLUMNS


def test_extended_raw_fields_are_appended_after_support_fields() -> None:
    assert EXTENDED_RAW_FIELDS == (
        "cogsq",
        "xsgaq",
        "xrdq",
        "dpq",
        "ltq",
        "invtq",
        "rectq",
    )
    support_end = 3 + len(CORE_RAW_FIELDS) + len(SUPPORT_RAW_FIELDS)
    assert STAGE1_OUTPUT_COLUMNS[support_end:] == EXTENDED_RAW_FIELDS


def test_extended_raw_fields_are_all_monetary() -> None:
    for field in EXTENDED_RAW_FIELDS:
        assert field in MONETARY_RAW_FIELDS


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
    raw_fields = set(CORE_RAW_FIELDS + SUPPORT_RAW_FIELDS + EXTENDED_RAW_FIELDS)
    assert classified == raw_fields
    assert set(MONETARY_RAW_FIELDS).isdisjoint(SHARE_COUNT_FIELDS)
    assert set(MONETARY_RAW_FIELDS).isdisjoint(PER_SHARE_FIELDS)
    assert set(SHARE_COUNT_FIELDS).isdisjoint(PER_SHARE_FIELDS)


def test_published_scale_uses_legacy_million_convention() -> None:
    assert PUBLISHED_UNIT_SCALE_NAME == "legacy_millions_scale"
    assert "saleq" in MONETARY_RAW_FIELDS
    assert "cshfdq" in SHARE_COUNT_FIELDS
    assert PER_SHARE_FIELDS == ("epspxq",)


def test_dvy_is_published_support_field() -> None:
    """Total cash dividends, distinct from preferred-only `dvpq`."""
    assert "dvy" in SUPPORT_RAW_FIELDS
    assert "dvy" in STAGE1_OUTPUT_COLUMNS


def test_dvy_is_monetary() -> None:
    """dvy is a currency amount, so unit normalization must apply to it."""
    assert "dvy" in MONETARY_RAW_FIELDS
