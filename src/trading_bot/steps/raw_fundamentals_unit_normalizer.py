"""Normalize published raw fundamentals values to a consistent scale.

The currently published historical legacy files use:
- monetary values in USD millions
- share-count values in millions of shares
- per-share values unchanged

This helper keeps that published convention explicit and applies the required
post-extraction normalization for source systems that arrive in base units.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..contracts.stage1_fundamentals_schema import (
    MONETARY_RAW_FIELDS,
    PER_SHARE_FIELDS,
    PUBLISHED_UNIT_SCALE_NAME,
    SHARE_COUNT_FIELDS,
)


UNIT_NORMALIZATION_REPORT_COLUMNS: tuple[str, ...] = (
    "source_system",
    "field_name",
    "field_class",
    "source_unit_scale",
    "published_unit_scale",
    "scale_divisor_applied",
    "non_null_before",
    "non_null_after",
    "max_abs_before",
    "max_abs_after",
    "min_year",
    "max_year",
)

SIMFIN_PUBLISHED_SCALE_DIVISOR = 1_000_000.0
LEGACY_PUBLISHED_SCALE_DIVISOR = 1.0

SOURCE_UNIT_METADATA: dict[str, dict[str, Any]] = {
    "legacy_processed_fundamentals": {
        "monetary": "usd_millions",
        "shares": "share_millions",
        "per_share": "usd_per_share",
        "scale_divisor": LEGACY_PUBLISHED_SCALE_DIVISOR,
    },
    "simfin": {
        "monetary": "usd",
        "shares": "shares",
        "per_share": "usd_per_share",
        "scale_divisor": SIMFIN_PUBLISHED_SCALE_DIVISOR,
    },
}


def _empty_numeric_series(length: int) -> pd.Series:
    """Return an all-null numeric series of the requested length."""
    return pd.Series([float("nan")] * length, dtype="float64")


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric series for a column, or nulls if absent."""
    if column not in frame.columns:
        return _empty_numeric_series(len(frame))
    return pd.to_numeric(frame[column], errors="coerce")


def _require_supported_source_system(source_system: str) -> dict[str, Any]:
    """Return unit metadata for a supported source system."""
    try:
        return SOURCE_UNIT_METADATA[source_system]
    except KeyError as exc:
        raise ValueError(f"Unsupported source_system for unit normalization: {source_system}") from exc


def normalize_raw_fundamentals_units(
    frame: pd.DataFrame,
    *,
    source_system: str,
) -> pd.DataFrame:
    """Normalize a raw fundamentals frame to the published legacy-compatible scale."""
    metadata = _require_supported_source_system(source_system)
    divisor = float(metadata["scale_divisor"])
    normalized = frame.copy()

    for field in (*MONETARY_RAW_FIELDS, *SHARE_COUNT_FIELDS):
        if field not in normalized.columns:
            continue
        values = pd.to_numeric(normalized[field], errors="coerce")
        if divisor != 1.0:
            values = values / divisor
        normalized[field] = values

    for field in PER_SHARE_FIELDS:
        if field in normalized.columns:
            normalized[field] = pd.to_numeric(normalized[field], errors="coerce")

    return normalized


def build_unit_normalization_report(
    before: pd.DataFrame,
    after: pd.DataFrame,
    *,
    source_system: str,
) -> pd.DataFrame:
    """Build a field-level summary of the applied unit normalization."""
    metadata = _require_supported_source_system(source_system)
    divisor = float(metadata["scale_divisor"])
    min_year = (
        int(pd.to_numeric(before["year"], errors="coerce").min())
        if "year" in before.columns and not before.empty
        else pd.NA
    )
    max_year = (
        int(pd.to_numeric(before["year"], errors="coerce").max())
        if "year" in before.columns and not before.empty
        else pd.NA
    )

    rows: list[dict[str, Any]] = []
    field_groups = (
        ("monetary", MONETARY_RAW_FIELDS, metadata["monetary"]),
        ("shares", SHARE_COUNT_FIELDS, metadata["shares"]),
        ("per_share", PER_SHARE_FIELDS, metadata["per_share"]),
    )

    for field_class, fields, source_unit_scale in field_groups:
        field_divisor = 1.0 if field_class == "per_share" else divisor
        for field in fields:
            before_values = _numeric_series(before, field)
            after_values = _numeric_series(after, field)
            rows.append(
                {
                    "source_system": source_system,
                    "field_name": field,
                    "field_class": field_class,
                    "source_unit_scale": source_unit_scale,
                    "published_unit_scale": PUBLISHED_UNIT_SCALE_NAME,
                    "scale_divisor_applied": field_divisor,
                    "non_null_before": int(before_values.notna().sum()),
                    "non_null_after": int(after_values.notna().sum()),
                    "max_abs_before": float(before_values.abs().max())
                    if before_values.notna().any()
                    else pd.NA,
                    "max_abs_after": float(after_values.abs().max())
                    if after_values.notna().any()
                    else pd.NA,
                    "min_year": min_year,
                    "max_year": max_year,
                }
            )

    return pd.DataFrame(rows, columns=UNIT_NORMALIZATION_REPORT_COLUMNS)
