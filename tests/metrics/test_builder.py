from __future__ import annotations

import pytest

from fundamentals_pipeline.contracts.stage2_metrics_schema import REASON_CODES
from fundamentals_pipeline.metrics.builder import build_metrics_trend
from fundamentals_pipeline.warehouse.connection import open_warehouse, query
from fundamentals_pipeline.warehouse.schema import create_all_tables


def _insert_annual(conn, ticker: str, year: int, **cols) -> None:
    keys = ["ticker", "fiscal_year", *cols.keys()]
    placeholders = ", ".join(["?"] * len(keys))
    conn.execute(
        f"INSERT INTO fundamentals_annual ({', '.join(keys)}) VALUES ({placeholders})",
        [ticker, year, *cols.values()],
    )


def _warehouse_with_annual(tmp_path, rows_by_year):
    db = tmp_path / "research.duckdb"
    with open_warehouse(db) as conn:
        create_all_tables(conn)
        for year, cols in rows_by_year.items():
            _insert_annual(conn, "AAPL", year, **cols)
    return db


def test_build_writes_metrics_and_reports(tmp_path) -> None:
    # 11 years of revenue growing at 10%/yr -> revenue_cagr_10y(2022) = 0.10
    rows = {2012 + i: {"saleq_annual": 100.0 * (1.1**i)} for i in range(11)}
    db = _warehouse_with_annual(tmp_path, rows)

    result = build_metrics_trend(warehouse_path=db)

    assert result["metric_count"] == 9
    assert result["metrics_trend_rows"] > 0
    got = query(
        db,
        "SELECT value FROM metrics_trend WHERE ticker='AAPL' "
        "AND metric_id='revenue_cagr_10y' AND as_of_year=2022",
    )
    assert abs(float(got.iloc[0]["value"]) - 0.10) < 1e-6


def test_every_row_has_value_xor_reason(tmp_path) -> None:
    rows = {2012 + i: {"saleq_annual": 100.0 + i} for i in range(11)}
    db = _warehouse_with_annual(tmp_path, rows)
    build_metrics_trend(warehouse_path=db)
    table = query(db, "SELECT value, reason_code FROM metrics_trend")
    both = table["value"].notna() & table["reason_code"].notna()
    neither = table["value"].isna() & table["reason_code"].isna()
    assert not both.any()
    assert not neither.any()
    reasons = table["reason_code"].dropna().unique()
    assert set(reasons) <= set(REASON_CODES)


def test_missing_fundamentals_annual_raises(tmp_path) -> None:
    db = tmp_path / "empty.duckdb"
    with open_warehouse(db) as conn:
        conn.execute("CREATE TABLE unrelated (a INTEGER)")
    with pytest.raises(FileNotFoundError):
        build_metrics_trend(warehouse_path=db)


def test_rebuild_is_idempotent(tmp_path) -> None:
    rows = {2012 + i: {"saleq_annual": 100.0 + i} for i in range(11)}
    db = _warehouse_with_annual(tmp_path, rows)
    first = build_metrics_trend(warehouse_path=db)
    second = build_metrics_trend(warehouse_path=db)
    assert first["metrics_trend_rows"] == second["metrics_trend_rows"]
