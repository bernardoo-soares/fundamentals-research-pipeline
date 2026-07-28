from __future__ import annotations

from fundamentals_pipeline.contracts.fundamentals_annual_schema import (
    ANNUAL_VALUE_COLUMNS,
)
from fundamentals_pipeline.contracts.scorecard_schema import (
    SCORE_COMPONENTS_COLUMNS,
    SCORE_CRITERIA_COLUMNS,
    SCORES_COLUMNS,
)
from fundamentals_pipeline.contracts.stage1_fundamentals_schema import (
    STAGE1_RAW_COLUMNS,
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


def _tables(tmp_path) -> set[str]:
    with open_warehouse(tmp_path / "research.duckdb") as conn:
        create_all_tables(conn)
        return {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }


def test_create_all_tables_makes_the_fundamentals_tables(tmp_path) -> None:
    assert {
        "fundamentals_quarterly",
        "fundamentals_annual",
        "build_log",
    } <= _tables(tmp_path)


def test_create_all_tables_makes_the_score_tables(tmp_path) -> None:
    """An empty scores table means "not scored yet"; a missing one means broken."""
    assert {"scores", "score_components", "score_criteria"} <= _tables(tmp_path)


def test_score_columns_match_the_contract(tmp_path) -> None:
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        assert tuple(_columns(conn, "scores")) == SCORES_COLUMNS
        assert tuple(_columns(conn, "score_components")) == SCORE_COMPONENTS_COLUMNS
        assert tuple(_columns(conn, "score_criteria")) == SCORE_CRITERIA_COLUMNS


def test_quarterly_columns_match_stage1_plus_provenance(tmp_path) -> None:
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        cols = _columns(conn, "fundamentals_quarterly")
    assert cols == [
        *STAGE1_RAW_COLUMNS,
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
        "source_era",
        "computed_at",
        "pipeline_version",
    ]
