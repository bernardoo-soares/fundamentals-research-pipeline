"""Provider-agnostic Stage 1 canonical raw fundamentals contract.

This module defines the raw-only quarterly schema used before any ratios or
derived features are computed. The contract is intentionally independent of any
single provider implementation.
"""

from __future__ import annotations


CORE_RAW_FIELDS: tuple[str, ...] = (
    "saleq",
    "niq",
    "oiadpq",
    "xintq",
    "txtq",
    "epspxq",
    "actq",
    "lctq",
    "ppentq",
    "gdwlq",
    "ivltq",
    "atq",
    "ceqq",
    "dlcq",
    "dlttq",
    "req",
    "tstkq",
    "oancfq",
    "prstkcq",
    "capxq",
    "cheq",
    "dvpq",
    "cshfdq",
)

SUPPORT_RAW_FIELDS: tuple[str, ...] = (
    "oancfy",
    "capxy",
    "prstkcy",
    "cshopq",
    "cshoq",
)

EXTENDED_RAW_FIELDS: tuple[str, ...] = (
    "cogsq",
    "xsgaq",
    "xrdq",
    "dpq",
    "ltq",
    "invtq",
    "rectq",
)

PER_SHARE_FIELDS: tuple[str, ...] = ("epspxq",)
SHARE_COUNT_FIELDS: tuple[str, ...] = (
    "cshfdq",
    "cshopq",
    "cshoq",
)
MONETARY_RAW_FIELDS: tuple[str, ...] = tuple(
    field
    for field in (*CORE_RAW_FIELDS, *SUPPORT_RAW_FIELDS, *EXTENDED_RAW_FIELDS)
    if field not in (*PER_SHARE_FIELDS, *SHARE_COUNT_FIELDS)
)
PUBLISHED_UNIT_SCALE_NAME = "legacy_millions_scale"

STAGE1_KEY_COLUMNS: tuple[str, ...] = ("ticker", "year", "quarter")
STAGE1_OUTPUT_COLUMNS: tuple[str, ...] = (
    *STAGE1_KEY_COLUMNS,
    *CORE_RAW_FIELDS,
    *SUPPORT_RAW_FIELDS,
    *EXTENDED_RAW_FIELDS,
)


def stage1_yearly_columns() -> tuple[str, ...]:
    """Return the canonical Stage 1 yearly CSV column order."""
    return STAGE1_OUTPUT_COLUMNS


def validate_stage1_frame_columns(columns: list[str] | tuple[str, ...]) -> None:
    """Validate that a frame contains the full Stage 1 raw-only schema."""
    missing = [column for column in STAGE1_OUTPUT_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"Stage 1 frame missing required columns: {missing}")

    leading = tuple(columns[: len(STAGE1_KEY_COLUMNS)])
    if leading != STAGE1_KEY_COLUMNS:
        raise ValueError(
            "Stage 1 frame must start with columns "
            f"{list(STAGE1_KEY_COLUMNS)}; received {list(leading)}."
        )
