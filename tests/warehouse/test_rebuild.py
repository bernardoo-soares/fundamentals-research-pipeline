from __future__ import annotations

import pytest

from fundamentals_pipeline.warehouse.connection import query
from fundamentals_pipeline.warehouse.rebuild import rebuild_warehouse


def _row(ticker, year, quarter, **fields):
    return {"ticker": ticker, "year": year, "quarter": quarter, **fields}


def test_rebuild_builds_all_tables(tmp_path, write_stage1_year) -> None:
    processed = tmp_path / "processed"
    write_stage1_year(
        processed,
        2024,
        [_row("AAPL", 2024, q, saleq=10.0, atq=100.0) for q in (1, 2, 3, 4)],
    )
    warehouse = tmp_path / "warehouse" / "research.duckdb"

    artifacts = rebuild_warehouse(
        processed_dir=processed,
        warehouse_path=warehouse,
        reports_dir=tmp_path / "reports",
        start_year=2024,
        end_year=2024,
    )

    assert warehouse.exists()
    assert artifacts["warehouse_path"] == str(warehouse)
    quarterly = query(warehouse, "SELECT COUNT(*) AS n FROM fundamentals_quarterly")
    annual = query(warehouse, "SELECT saleq_annual FROM fundamentals_annual")
    log = query(warehouse, "SELECT gate_status, quarterly_rows FROM build_log")
    assert int(quarterly.iloc[0]["n"]) == 4
    assert float(annual.iloc[0]["saleq_annual"]) == 40.0
    assert log.iloc[0]["gate_status"] == "passed"
    assert int(log.iloc[0]["quarterly_rows"]) == 4


def test_failed_rebuild_leaves_existing_db_intact(
    tmp_path, write_stage1_year
) -> None:
    processed = tmp_path / "processed"
    write_stage1_year(processed, 2024, [_row("AAPL", 2024, 1, saleq=10.0)])
    warehouse = tmp_path / "warehouse" / "research.duckdb"

    # First, a good rebuild for 2024.
    rebuild_warehouse(
        processed_dir=processed,
        warehouse_path=warehouse,
        reports_dir=tmp_path / "reports",
        start_year=2024,
        end_year=2024,
    )
    good_rows = int(
        query(warehouse, "SELECT COUNT(*) AS n FROM fundamentals_quarterly").iloc[0][
            "n"
        ]
    )

    # Now a rebuild whose range needs a missing 2025 file -> must fail.
    with pytest.raises(FileNotFoundError):
        rebuild_warehouse(
            processed_dir=processed,
            warehouse_path=warehouse,
            reports_dir=tmp_path / "reports",
            start_year=2024,
            end_year=2025,
        )

    # Existing DB is untouched and no temp file is left behind.
    assert warehouse.exists()
    assert not warehouse.with_suffix(warehouse.suffix + ".tmp").exists()
    still = int(
        query(warehouse, "SELECT COUNT(*) AS n FROM fundamentals_quarterly").iloc[0][
            "n"
        ]
    )
    assert still == good_rows
