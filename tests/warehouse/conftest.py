from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fundamentals_pipeline.contracts.stage1_fundamentals_schema import (
    STAGE1_OUTPUT_COLUMNS,
)


@pytest.fixture
def write_stage1_year():
    """Write a raw_fundamentals_<year>.csv from a list of partial row dicts.

    Missing Stage 1 columns are filled with NA, and columns are ordered to the
    Stage 1 contract.
    """

    def _write(processed_dir, year: int, rows: list[dict]) -> Path:
        directory = Path(processed_dir)
        directory.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(rows)
        for column in STAGE1_OUTPUT_COLUMNS:
            if column not in frame.columns:
                frame[column] = pd.NA
        frame = frame[list(STAGE1_OUTPUT_COLUMNS)]
        path = directory / f"raw_fundamentals_{year}.csv"
        frame.to_csv(path, index=False)
        return path

    return _write
