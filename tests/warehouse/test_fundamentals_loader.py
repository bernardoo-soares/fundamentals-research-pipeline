from __future__ import annotations

import pandas as pd
import pytest

from fundamentals_pipeline.warehouse.connection import open_warehouse
from fundamentals_pipeline.warehouse.fundamentals_loader import (
    load_fundamentals_quarterly,
)
from fundamentals_pipeline.warehouse.schema import create_all_tables


def _row(ticker: str, year: int, quarter: int, **fields) -> dict:
    return {"ticker": ticker, "year": year, "quarter": quarter, **fields}


def test_loads_rows_and_preserves_published_source_era(
    tmp_path, write_stage1_year
) -> None:
    """The loader reads recorded provenance; it never infers it from the year.

    Inferring it is what discarded usable legacy data for FY2023. Here FY2023
    is legacy-served, which the old year-based rule could not represent.
    """
    processed = tmp_path / "processed"
    write_stage1_year(
        processed,
        2022,
        [_row("AAPL", 2022, 1, saleq=90.0, source_era="legacy_compustat")],
    )
    write_stage1_year(
        processed,
        2023,
        [_row("AAPL", 2023, 1, saleq=100.0, source_era="legacy_compustat")],
    )

    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        loaded = load_fundamentals_quarterly(
            conn,
            processed_dir=processed,
            start_year=2022,
            end_year=2023,
            pipeline_version="test",
        )
        frame = conn.execute(
            "SELECT ticker, year, quarter, saleq, source_era "
            "FROM fundamentals_quarterly ORDER BY year"
        ).df()

    assert loaded == 2
    assert list(frame["source_era"]) == ["legacy_compustat", "legacy_compustat"]
    assert list(frame["saleq"]) == [90.0, 100.0]


def test_missing_year_file_raises(tmp_path, write_stage1_year) -> None:
    processed = tmp_path / "processed"
    write_stage1_year(processed, 2023, [_row("AAPL", 2023, 1, saleq=1.0)])
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        with pytest.raises(FileNotFoundError):
            load_fundamentals_quarterly(
                conn,
                processed_dir=processed,
                start_year=2023,
                end_year=2024,  # 2024 file absent
                pipeline_version="test",
            )


def test_wrong_columns_raise(tmp_path) -> None:
    processed = tmp_path / "processed"
    processed.mkdir(parents=True)
    # deliberately wrong schema (not the Stage 1 contract)
    pd.DataFrame({"ticker": ["AAPL"], "year": [2024], "quarter": [1]}).to_csv(
        processed / "raw_fundamentals_2024.csv", index=False
    )
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        with pytest.raises(ValueError, match="columns"):
            load_fundamentals_quarterly(
                conn,
                processed_dir=processed,
                start_year=2024,
                end_year=2024,
                pipeline_version="test",
            )


def test_duplicate_key_raises(tmp_path, write_stage1_year) -> None:
    processed = tmp_path / "processed"
    write_stage1_year(
        processed,
        2024,
        [_row("AAPL", 2024, 1, saleq=1.0), _row("AAPL", 2024, 1, saleq=2.0)],
    )
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        create_all_tables(conn)
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            load_fundamentals_quarterly(
                conn,
                processed_dir=processed,
                start_year=2024,
                end_year=2024,
                pipeline_version="test",
            )
