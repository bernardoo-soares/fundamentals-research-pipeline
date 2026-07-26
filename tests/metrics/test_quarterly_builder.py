from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from fundamentals_pipeline.contracts.era_resolution import SourceEra
from fundamentals_pipeline.contracts.metric_reason_codes import ReasonCode
from fundamentals_pipeline.metrics.quarterly_builder import build_metrics_quarterly
from fundamentals_pipeline.metrics.quarterly_registry import QUARTERLY_REGISTRY


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
         "actq": None, "lctq": None, "cogsq": None, "dpq": None,
         "xsgaq": None, "xrdq": None, "source_era": "simfin"}
        for (y, q, s, n) in data
    ]


def test_build_writes_metrics_quarterly(tmp_path) -> None:
    db = tmp_path / "research.duckdb"
    _seed_quarterly(db, _aapl_rows())

    result = build_metrics_quarterly(warehouse_path=db)

    assert result["metric_count"] == len(QUARTERLY_REGISTRY)
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


def test_builder_applies_era_restriction(tmp_path):
    """A SimFin-era row is nulled era_not_supported; legacy keeps its value.

    Golden (real corpus, KO FY2019, legacy era):
      xintq TTM  = 245 + 236 + 230 + 235   =    946
      oiadpq TTM = 2560 + 3080 + 2623 + 2278 = 10541
      946 / 10541 = 0.089744806
    """
    db = tmp_path / "research.duckdb"
    ko = [
        {"ticker": "KO", "year": 2019, "quarter": q, "xintq": x, "oiadpq": o,
         "saleq": None, "niq": None, "atq": None, "ceqq": None, "ltq": None,
         "cogsq": None, "dpq": None, "xsgaq": None, "xrdq": None,
         "tstkq": None, "dlcq": None, "dlttq": None, "actq": None,
         "lctq": None, "source_era": str(SourceEra.LEGACY)}
        for q, x, o in [(1, 245.0, 2560.0), (2, 236.0, 3080.0),
                        (3, 230.0, 2623.0), (4, 235.0, 2278.0)]
    ]
    agilent = [
        {"ticker": "A", "year": 2023, "quarter": q, "xintq": 10.0,
         "oiadpq": 500.0, "saleq": None, "niq": None, "atq": None,
         "cogsq": None, "dpq": None, "xsgaq": None, "xrdq": None,
         "ceqq": None, "ltq": None, "tstkq": None, "dlcq": None,
         "dlttq": None, "actq": None, "lctq": None,
         "source_era": str(SourceEra.SIMFIN)}
        for q in (1, 2, 3, 4)
    ]
    _seed_quarterly(db, ko + agilent)

    build_metrics_quarterly(warehouse_path=db)
    conn = duckdb.connect(str(db), read_only=True)
    rows = conn.execute(
        "SELECT ticker, value, reason_code FROM metrics_quarterly "
        "WHERE metric_id = 'interest_pct_operating_income' AND quarter = 4 "
        "ORDER BY ticker"
    ).fetchall()
    conn.close()

    by_ticker = {row[0]: row for row in rows}
    assert by_ticker["A"][1] is None
    assert by_ticker["A"][2] == ReasonCode.ERA_NOT_SUPPORTED
    assert by_ticker["KO"][1] == pytest.approx(0.089744806, abs=1e-9)
    assert by_ticker["KO"][2] is None


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
