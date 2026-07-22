from __future__ import annotations

import pytest

from fundamentals_pipeline.warehouse.connection import open_warehouse, query


def test_open_warehouse_creates_parent_and_roundtrips(tmp_path) -> None:
    db_path = tmp_path / "nested" / "research.duckdb"
    with open_warehouse(db_path) as conn:
        conn.execute("CREATE TABLE t (a INTEGER, b VARCHAR)")
        conn.execute("INSERT INTO t VALUES (1, 'x'), (2, 'y')")
    assert db_path.exists()

    frame = query(db_path, "SELECT a, b FROM t ORDER BY a")
    assert list(frame["a"]) == [1, 2]
    assert list(frame["b"]) == ["x", "y"]


def test_query_supports_parameters(tmp_path) -> None:
    db_path = tmp_path / "research.duckdb"
    with open_warehouse(db_path) as conn:
        conn.execute("CREATE TABLE t (a INTEGER)")
        conn.execute("INSERT INTO t VALUES (1), (2), (3)")
    frame = query(db_path, "SELECT a FROM t WHERE a > ? ORDER BY a", [1])
    assert list(frame["a"]) == [2, 3]


def test_read_only_missing_db_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        with open_warehouse(tmp_path / "missing.duckdb", read_only=True):
            pass
