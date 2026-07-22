from __future__ import annotations

import pandas as pd

from fundamentals_pipeline.warehouse.annualize import build_fundamentals_annual
from fundamentals_pipeline.warehouse.connection import open_warehouse
from fundamentals_pipeline.warehouse.fundamentals_loader import (
    load_fundamentals_quarterly,
)
from fundamentals_pipeline.warehouse.schema import create_all_tables
from fundamentals_pipeline.warehouse.validation import build_health_report


def _row(ticker, year, quarter, **fields):
    return {"ticker": ticker, "year": year, "quarter": quarter, **fields}


def _build(tmp_path, write_stage1_year, rows):
    processed = tmp_path / "processed"
    write_stage1_year(processed, 2024, rows)
    db_path = tmp_path / "research.duckdb"
    reports = tmp_path / "reports"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        load_fundamentals_quarterly(
            conn,
            processed_dir=processed,
            start_year=2024,
            end_year=2024,
            pipeline_version="test",
        )
        build_fundamentals_annual(conn, pipeline_version="test")
        path = build_health_report(
            conn, reports_dir=reports, start_year=2024, end_year=2024
        )
    return pd.read_csv(path)


def test_reconciliation_breach_flagged(tmp_path, write_stage1_year) -> None:
    # atq=100 but ltq+ceqq=200 -> residual 100% > 5%
    rows = [_row("BAD", 2024, 4, atq=100.0, ltq=150.0, ceqq=50.0)]
    report = _build(tmp_path, write_stage1_year, rows)
    recon = report[report["check"] == "balance_reconciliation"]
    assert len(recon) == 1
    assert recon.iloc[0]["ticker"] == "BAD"


def test_clean_row_not_flagged_and_null_inputs_skipped(
    tmp_path, write_stage1_year
) -> None:
    rows = [
        _row("OK", 2024, 4, atq=100.0, ltq=60.0, ceqq=40.0),  # residual 0
        _row("NUL", 2024, 4, atq=100.0, ltq=None, ceqq=40.0),  # skipped: null input
    ]
    report = _build(tmp_path, write_stage1_year, rows)
    recon = report[report["check"] == "balance_reconciliation"]
    assert recon.empty


def test_report_has_completeness_rows(tmp_path, write_stage1_year) -> None:
    rows = [_row("AAPL", 2024, q, saleq=1.0) for q in (1, 2, 3, 4)]
    report = _build(tmp_path, write_stage1_year, rows)
    comp = report[report["check"] == "completeness"]
    assert len(comp) == 1
    assert comp.iloc[0]["value"] == 1  # one complete ticker-year
