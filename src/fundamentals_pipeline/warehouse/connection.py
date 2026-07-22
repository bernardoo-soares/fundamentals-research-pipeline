"""Single access seam for the DuckDB warehouse.

This is the ONLY module that opens the `.duckdb` file. Every other warehouse
module receives an open connection or goes through `query`.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


@contextmanager
def open_warehouse(
    db_path: str | Path,
    *,
    read_only: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open the warehouse DB, yielding a connection that is always closed."""
    path = Path(db_path)
    if read_only and not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


def query(
    db_path: str | Path,
    sql: str,
    params: Sequence[Any] | None = None,
) -> pd.DataFrame:
    """Run a read-only query and return the result as a DataFrame."""
    with open_warehouse(db_path, read_only=True) as conn:
        return conn.execute(sql, list(params) if params is not None else []).df()
