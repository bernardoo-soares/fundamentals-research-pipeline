"""Load fundamentals_quarterly from the published Stage 1 CSVs, with hard gates."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from ..contracts.stage1_fundamentals_schema import STAGE1_OUTPUT_COLUMNS
from .plausibility import apply_non_negative_gate
from .schema import QUARTERLY_RAW_FIELDS

_INSERT_COLUMNS = (
    "ticker",
    "year",
    "quarter",
    *QUARTERLY_RAW_FIELDS,
    "source_era",
    "computed_at",
    "pipeline_version",
)


def _validate_columns(frame: pd.DataFrame, path: Path) -> None:
    if list(frame.columns) != list(STAGE1_OUTPUT_COLUMNS):
        raise ValueError(
            f"{path} columns do not match the Stage 1 contract "
            f"{list(STAGE1_OUTPUT_COLUMNS)}."
        )


def _validate_unique_keys(frame: pd.DataFrame) -> None:
    duplicated = frame.duplicated(subset=["ticker", "year", "quarter"])
    if bool(duplicated.any()):
        offenders = (
            frame.loc[duplicated, ["ticker", "year", "quarter"]]
            .drop_duplicates()
            .to_dict("records")
        )
        raise ValueError(f"Duplicate (ticker, year, quarter) rows: {offenders}")


def load_fundamentals_quarterly(
    conn: duckdb.DuckDBPyConnection,
    *,
    processed_dir: str | Path,
    start_year: int,
    end_year: int,
    pipeline_version: str,
) -> tuple[int, pd.DataFrame]:
    """Read Stage 1 yearly CSVs, validate, and insert into fundamentals_quarterly.

    Returns the inserted row count and a frame of plausibility violations --
    impossible values that were nulled on the way in (see
    `warehouse/plausibility.py`). The caller is responsible for persisting the
    violations so the rejection stays auditable.
    """
    if start_year > end_year:
        raise ValueError("start_year must be <= end_year.")

    directory = Path(processed_dir)
    frames: list[pd.DataFrame] = []
    for year in range(start_year, end_year + 1):
        path = directory / f"raw_fundamentals_{year}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Stage 1 file not found: {path}")
        frame = pd.read_csv(path)
        _validate_columns(frame, path)
        # `source_era` is published by steps/stage1_era_resolution.py. The
        # loader reads the recorded provenance rather than inferring it from
        # the year, which is what discarded usable legacy data for FY2023.
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    _validate_unique_keys(combined)
    gated = apply_non_negative_gate(combined)
    combined = gated.frame
    combined["computed_at"] = datetime.now(UTC).replace(tzinfo=None)
    combined["pipeline_version"] = pipeline_version
    combined = combined[list(_INSERT_COLUMNS)]

    conn.register("staging_quarterly", combined)
    try:
        columns = ", ".join(_INSERT_COLUMNS)
        conn.execute(
            f"INSERT INTO fundamentals_quarterly ({columns}) "
            f"SELECT {columns} FROM staging_quarterly"
        )
    finally:
        conn.unregister("staging_quarterly")
    return int(len(combined)), gated.violations
