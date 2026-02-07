from __future__ import annotations

import pandas as pd

from trading_bot.pipelines.legacy_fundamentals import build_legacy_fundamentals


def _write_legacy_file(path, ticker: str):
    rows = [
        {"tic": ticker, "datadate": "2024-03-31", "fyearq": 2024, "fqtr": 1, "saleq": 100.0, "niq": 10.0, "oiadpq": 15.0, "xintq": 1.0, "txtq": 2.0, "epspxq": 0.5, "actq": 50.0, "lctq": 25.0, "ppentq": 1000.0, "gdwlq": 100.0, "ivltq": 50.0, "atq": 500.0, "ceqq": 200.0, "dlcq": 40.0, "dlttq": 60.0, "req": 110.0, "tstkq": 5.0, "oancfq": 15.0, "cshopq": 4.0},
        {"tic": ticker, "datadate": "2024-06-30", "fyearq": 2024, "fqtr": 2, "saleq": 110.0, "niq": 12.0, "oiadpq": 17.0, "xintq": 1.0, "txtq": 2.0, "epspxq": 0.6, "actq": 52.0, "lctq": 26.0, "ppentq": 1002.0, "gdwlq": 100.0, "ivltq": 50.0, "atq": 505.0, "ceqq": 202.0, "dlcq": 39.0, "dlttq": 59.0, "req": 112.0, "tstkq": 5.0, "oancfq": 16.0, "cshopq": 5.0},
        {"tic": ticker, "datadate": "2024-09-30", "fyearq": 2024, "fqtr": 3, "saleq": 120.0, "niq": 14.0, "oiadpq": 18.0, "xintq": 1.0, "txtq": 2.0, "epspxq": 0.7, "actq": 54.0, "lctq": 27.0, "ppentq": 1004.0, "gdwlq": 100.0, "ivltq": 50.0, "atq": 510.0, "ceqq": 204.0, "dlcq": 38.0, "dlttq": 58.0, "req": 114.0, "tstkq": 5.0, "oancfq": 17.0, "cshopq": 6.0},
        {"tic": ticker, "datadate": "2024-12-31", "fyearq": 2024, "fqtr": 4, "saleq": 130.0, "niq": 16.0, "oiadpq": 20.0, "xintq": 1.0, "txtq": 2.0, "epspxq": 0.8, "actq": 56.0, "lctq": 28.0, "ppentq": 1006.0, "gdwlq": 100.0, "ivltq": 50.0, "atq": 520.0, "ceqq": 206.0, "dlcq": 37.0, "dlttq": 57.0, "req": 116.0, "tstkq": 5.0, "oancfq": 18.0, "cshopq": 7.0},
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_build_legacy_fundamentals_filters_and_writes_outputs(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "processed"
    universe_path = tmp_path / "universe.csv"

    pd.DataFrame({"ticker": ["AAPL"]}).to_csv(universe_path, index=False)
    _write_legacy_file(raw_dir / "AAPL-001690.csv", "AAPL")
    _write_legacy_file(raw_dir / "MSFT-001111.csv", "MSFT")

    canonical = build_legacy_fundamentals(
        universe_path=universe_path,
        raw_dir=raw_dir,
        output_dir=output_dir,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )

    assert canonical["ticker"].nunique() == 1
    assert canonical["ticker"].iloc[0] == "AAPL"
    assert len(canonical) == 4

    expected_files = [
        output_dir / "canonical_legacy_q.csv",
        output_dir / "fundamentals_q_2024.csv",
        output_dir / "ratios_q_2024.csv",
    ]
    for path in expected_files:
        assert path.exists()

    ratios = pd.read_csv(output_dir / "ratios_q_2024.csv")
    assert {"operating_margin", "net_profit_margin", "roe", "roa"}.issubset(ratios.columns)
    assert ratios["operating_margin"].notna().all()
