from __future__ import annotations

import duckdb
import pandas as pd

from fundamentals_pipeline.metrics.quarterly_builder import build_metrics_quarterly


def _seed_quarterly(path, rows) -> None:
    conn = duckdb.connect(str(path))
    conn.register("seed", pd.DataFrame(rows))
    conn.execute("CREATE TABLE fundamentals_quarterly AS SELECT * FROM seed")
    conn.unregister("seed")
    conn.close()


def _aapl_rows():
    data = [
        (2023, 1, 117154.0, 29998.0), (2023, 2, 94836.0, 24160.0),
        (2023, 3, 81797.0, 19881.0), (2023, 4, 89498.0, 22956.0),
    ]
    return [
        {"ticker": "AAPL", "year": y, "quarter": q, "saleq": s, "niq": n,
         "atq": 352583.0, "ceqq": 62146.0, "ltq": 290437.0, "tstkq": None,
         "dlcq": None, "dlttq": None, "xintq": None, "oiadpq": None,
         "actq": None, "lctq": None, "source_era": "simfin"}
        for (y, q, s, n) in data
    ]


def test_build_writes_metrics_quarterly(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_quarterly(db, _aapl_rows())

    result = build_metrics_quarterly(warehouse_path=db)

    assert result["metric_count"] == 9
    assert result["metrics_quarterly_rows"] > 0

    conn = duckdb.connect(str(db), read_only=True)
    net_margin = conn.execute(
        "SELECT value, source_era FROM metrics_quarterly "
        "WHERE ticker='AAPL' AND year=2023 AND quarter=4 AND metric_id='net_margin'"
    ).fetchone()
    conn.close()
    assert abs(net_margin[0] - 96995.0 / 383285.0) < 1e-9
    assert net_margin[1] == "simfin"


def test_build_is_idempotent(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_quarterly(db, _aapl_rows())
    first = build_metrics_quarterly(warehouse_path=db)
    second = build_metrics_quarterly(warehouse_path=db)
    assert first["metrics_quarterly_rows"] == second["metrics_quarterly_rows"]


def test_no_nan_or_inf_in_stored_values(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_quarterly(db, _aapl_rows())
    build_metrics_quarterly(warehouse_path=db)
    conn = duckdb.connect(str(db), read_only=True)
    bad = conn.execute(
        "SELECT COUNT(*) FROM metrics_quarterly "
        "WHERE value IS NOT NULL AND (isinf(value) OR isnan(value))"
    ).fetchone()[0]
    conn.close()
    assert bad == 0
