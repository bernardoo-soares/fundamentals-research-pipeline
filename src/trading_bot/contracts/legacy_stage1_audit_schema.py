"""Contracts for legacy Stage 1 audit report outputs."""

from __future__ import annotations

from typing import Sequence


AUDIT_SUMMARY_COLUMNS: tuple[str, ...] = (
    "year",
    "check_name",
    "status",
    "observed_value",
    "expected_value",
    "detail",
)
SCHEMA_ISSUES_COLUMNS: tuple[str, ...] = (
    "year",
    "issue_type",
    "expected_columns",
    "observed_columns",
    "detail",
)
KEY_ISSUES_COLUMNS: tuple[str, ...] = (
    "year",
    "ticker",
    "quarter",
    "issue_type",
    "row_count",
    "detail",
)
FIELD_NULLS_COLUMNS: tuple[str, ...] = (
    "year",
    "field_name",
    "null_rows",
    "total_rows",
    "null_pct",
)
RECONCILIATION_COLUMNS: tuple[str, ...] = (
    "year",
    "ticker",
    "quarter",
    "field_name",
    "processed_value",
    "expected_value",
    "match_status",
    "source_file",
)
RECONCILIATION_SUMMARY_COLUMNS: tuple[str, ...] = (
    "year",
    "compared_rows",
    "compared_fields",
    "exact_matches",
    "mismatches",
    "mismatch_pct",
)
SUSPICIOUS_VALUES_COLUMNS: tuple[str, ...] = (
    "year",
    "ticker",
    "quarter",
    "field_name",
    "value",
    "anomaly_type",
    "detail",
)
REVIEW_SAMPLE_COLUMNS: tuple[str, ...] = (
    "year",
    "ticker",
    "quarter",
    "sample_reason",
)

REPORT_COLUMNS: dict[str, tuple[str, ...]] = {
    "summary": AUDIT_SUMMARY_COLUMNS,
    "schema_issues": SCHEMA_ISSUES_COLUMNS,
    "key_issues": KEY_ISSUES_COLUMNS,
    "field_nulls": FIELD_NULLS_COLUMNS,
    "reconciliation": RECONCILIATION_COLUMNS,
    "reconciliation_summary": RECONCILIATION_SUMMARY_COLUMNS,
    "suspicious_values": SUSPICIOUS_VALUES_COLUMNS,
    "review_sample": REVIEW_SAMPLE_COLUMNS,
}


def validate_report_columns(report_name: str, columns: Sequence[str]) -> None:
    """Validate one audit report column list against its frozen contract."""
    expected = REPORT_COLUMNS[report_name]
    if tuple(columns) != expected:
        raise ValueError(
            f"{report_name} columns must equal {list(expected)}; "
            f"received {list(columns)}."
        )
