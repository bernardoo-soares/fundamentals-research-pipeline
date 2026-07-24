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
    # Total cash dividends, year-to-date. Distinct from `dvpq`, which is
    # preferred dividends only (Compustat: "Dividends - Preferred/Preference").
    "dvy",
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

# Fields that cannot be negative under any accounting treatment. A negative
# value here is a provider defect, not a business fact, so it is rejected
# rather than propagated -- a halved revenue figure is worse than a null one.
#
# Deliberately conservative: fields that CAN legitimately be negative are
# excluded, including niq and oiadpq (losses), xintq and txtq (net interest
# income, tax benefits), oancfq and capxq (net outflows/disposals), prstkcy
# (SimFin states net equity flow), req and ceqq (accumulated deficits),
# ivltq and tstkq (sign conventions vary across providers).
NON_NEGATIVE_FIELDS: tuple[str, ...] = (
    "saleq",
    "cogsq",
    "atq",
    "actq",
    "lctq",
    "ltq",
    "cheq",
    "invtq",
    "rectq",
    "ppentq",
    "gdwlq",
    "xsgaq",
    "xrdq",
    "dpq",
    "dlcq",
    "dlttq",
    "cshfdq",
    "cshoq",
    "cshopq",
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

# Provenance metadata, not raw fields: deliberately excluded from the
# CORE/SUPPORT/EXTENDED groups so unit classification is unaffected.
PROVENANCE_COLUMNS: tuple[str, ...] = ("source_era",)

# What a single provider's builder emits into its staging directory.
STAGE1_RAW_COLUMNS: tuple[str, ...] = (
    *STAGE1_KEY_COLUMNS,
    *CORE_RAW_FIELDS,
    *SUPPORT_RAW_FIELDS,
    *EXTENDED_RAW_FIELDS,
)

# What is published after era resolution and read by the warehouse loader.
# `source_era` records which provider served the row, replacing the loader's
# former practice of inferring it from the year.
STAGE1_OUTPUT_COLUMNS: tuple[str, ...] = (
    *STAGE1_RAW_COLUMNS,
    *PROVENANCE_COLUMNS,
)


def stage1_yearly_columns() -> tuple[str, ...]:
    """Return the published Stage 1 yearly CSV column order (incl. provenance)."""
    return STAGE1_OUTPUT_COLUMNS


def validate_stage1_frame_columns(columns: list[str] | tuple[str, ...]) -> None:
    """Validate that a frame contains the full Stage 1 raw-only schema."""
    missing = [column for column in STAGE1_RAW_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"Stage 1 frame missing required columns: {missing}")

    leading = tuple(columns[: len(STAGE1_KEY_COLUMNS)])
    if leading != STAGE1_KEY_COLUMNS:
        raise ValueError(
            "Stage 1 frame must start with columns "
            f"{list(STAGE1_KEY_COLUMNS)}; received {list(leading)}."
        )
