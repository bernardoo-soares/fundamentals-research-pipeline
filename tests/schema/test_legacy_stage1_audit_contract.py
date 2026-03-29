from __future__ import annotations

from trading_bot.contracts.legacy_stage1_audit_schema import (
    REPORT_COLUMNS,
    validate_report_columns,
)


def test_all_audit_reports_have_frozen_column_contracts() -> None:
    for report_name, columns in REPORT_COLUMNS.items():
        validate_report_columns(report_name, columns)
