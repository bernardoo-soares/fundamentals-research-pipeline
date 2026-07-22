from __future__ import annotations

from fundamentals_pipeline.contracts.fundamentals_annual_schema import (
    ANNUAL_VALUE_COLUMNS,
)
from fundamentals_pipeline.contracts.stage1_fundamentals_schema import (
    STAGE1_OUTPUT_COLUMNS,
)
from fundamentals_pipeline.warehouse.connection import open_warehouse
from fundamentals_pipeline.warehouse.schema import create_all_tables


def _columns(conn, table: str) -> list[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()
    return [r[0] for r in rows]


def test_create_all_tables_makes_three_tables(tmp_path) -> None:
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
    assert {"fundamentals_quarterly", "fundamentals_annual", "build_log"} <= tables


def test_quarterly_columns_match_stage1_plus_provenance(tmp_path) -> None:
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        cols = _columns(conn, "fundamentals_quarterly")
    assert cols == [
        *STAGE1_OUTPUT_COLUMNS,
        "source_era",
        "computed_at",
        "pipeline_version",
    ]


def test_annual_columns_match_contract(tmp_path) -> None:
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        cols = _columns(conn, "fundamentals_annual")
    assert cols == [
        "ticker",
        "fiscal_year",
        *ANNUAL_VALUE_COLUMNS,
        "quarters_present",
        "has_q4",
        "computed_at",
        "pipeline_version",
    ]
