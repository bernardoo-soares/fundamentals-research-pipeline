from __future__ import annotations

import math

from fundamentals_pipeline.warehouse.annualize import build_fundamentals_annual
from fundamentals_pipeline.warehouse.connection import open_warehouse
from fundamentals_pipeline.warehouse.fundamentals_loader import (
    load_fundamentals_quarterly,
)
from fundamentals_pipeline.warehouse.schema import create_all_tables


def _row(ticker, year, quarter, **fields):
    return {"ticker": ticker, "year": year, "quarter": quarter, **fields}


def _build(tmp_path, write_stage1_year, rows_by_year):
    processed = tmp_path / "processed"
    for year, rows in rows_by_year.items():
        write_stage1_year(processed, year, rows)
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        load_fundamentals_quarterly(
            conn,
            processed_dir=processed,
            start_year=min(rows_by_year),
            end_year=max(rows_by_year),
            pipeline_version="test",
        )
        build_fundamentals_annual(conn, pipeline_version="test")
        return conn.execute(
            "SELECT * FROM fundamentals_annual WHERE ticker = 'AAPL' "
            "AND fiscal_year = 2024"
        ).df()


def test_flow_sums_four_quarters_stock_takes_q4(tmp_path, write_stage1_year) -> None:
    rows = [
        _row("AAPL", 2024, 1, saleq=90.0, atq=350.0, capxy=2.5),
        _row("AAPL", 2024, 2, saleq=85.0, atq=340.0, capxy=5.1),
        _row("AAPL", 2024, 3, saleq=94.0, atq=360.0, capxy=8.0),
        _row("AAPL", 2024, 4, saleq=120.0, atq=365.0, capxy=10.5),
    ]
    result = _build(tmp_path, write_stage1_year, {2024: rows}).iloc[0]
    assert result["saleq_annual"] == 389.0          # flow: sum of 4
    assert result["atq_q4"] == 365.0                 # stock: Q4 value
    assert result["capxy_annual"] == 10.5            # ytd: Q4 full-year value
    assert result["quarters_present"] == 4
    assert bool(result["has_q4"]) is True


def test_flow_null_when_a_quarter_missing(tmp_path, write_stage1_year) -> None:
    rows = [
        _row("AAPL", 2024, 1, saleq=90.0, atq=350.0),
        _row("AAPL", 2024, 3, saleq=94.0, atq=360.0),
        _row("AAPL", 2024, 4, saleq=120.0, atq=365.0),
    ]
    result = _build(tmp_path, write_stage1_year, {2024: rows}).iloc[0]
    assert math.isnan(result["saleq_annual"])        # flow needs 4/4 quarters
    assert result["atq_q4"] == 365.0                 # stock still resolves from Q4
    assert result["quarters_present"] == 3
    assert bool(result["has_q4"]) is True


def test_flow_null_when_field_null_in_one_quarter(tmp_path, write_stage1_year) -> None:
    rows = [
        _row("AAPL", 2024, 1, saleq=90.0),
        _row("AAPL", 2024, 2, saleq=85.0),
        _row("AAPL", 2024, 3),               # saleq null this quarter
        _row("AAPL", 2024, 4, saleq=120.0),
    ]
    result = _build(tmp_path, write_stage1_year, {2024: rows}).iloc[0]
    assert math.isnan(result["saleq_annual"])
    assert result["quarters_present"] == 4


def test_stock_null_when_no_q4(tmp_path, write_stage1_year) -> None:
    rows = [
        _row("AAPL", 2024, 1, atq=350.0),
        _row("AAPL", 2024, 2, atq=340.0),
        _row("AAPL", 2024, 3, atq=360.0),
    ]
    result = _build(tmp_path, write_stage1_year, {2024: rows}).iloc[0]
    assert math.isnan(result["atq_q4"])
    assert bool(result["has_q4"]) is False


def test_dvy_annual_takes_q4_value_not_sum(tmp_path, write_stage1_year) -> None:
    """Legacy dvy is cumulative year-to-date: Q4 already holds the full year.

    Summing the four quarters would roughly double-count. KO FY2023 real
    figures: the Q4 cumulative 7952 is the answer, not 101+2089+4078+7952.
    """
    rows = [
        _row("AAPL", 2024, 1, dvy=101.0),
        _row("AAPL", 2024, 2, dvy=2089.0),
        _row("AAPL", 2024, 3, dvy=4078.0),
        _row("AAPL", 2024, 4, dvy=7952.0),
    ]
    frame = _build(tmp_path, write_stage1_year, {2024: rows})
    assert frame["dvy_annual"].iloc[0] == 7952.0
