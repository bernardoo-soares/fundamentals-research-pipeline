from __future__ import annotations

import pandas as pd

from trading_bot.steps import sec_fundamentals


def test_build_sec_cik_mapping_writes_report(tmp_path, monkeypatch) -> None:
    universe_path = tmp_path / "universe.csv"
    output_path = tmp_path / "reports" / "sec_cik_mapping.csv"
    pd.DataFrame({"ticker": ["AAPL", "BRK.B", "MISSING"]}).to_csv(
        universe_path,
        index=False,
    )

    def fake_fetch(*args, **kwargs):
        return [
            {
                "ticker": "AAPL",
                "cik": "320193",
                "name": "Apple",
                "exchange": "NASDAQ",
            },
            {
                "ticker": "BRK-B",
                "cik": "1067983",
                "name": "Berkshire",
                "exchange": "NYSE",
            },
        ]

    monkeypatch.setattr(sec_fundamentals, "fetch_sec_ticker_reference", fake_fetch)

    df = sec_fundamentals.build_sec_cik_mapping(
        universe_path=universe_path,
        output_path=output_path,
    )

    assert list(df["ticker"]) == ["AAPL", "BRK.B", "MISSING"]
    assert df.loc[df["ticker"] == "AAPL", "mapping_status"].item() == "mapped"
    assert df.loc[df["ticker"] == "BRK.B", "mapping_status"].item() == "mapped"
    assert df.loc[df["ticker"] == "MISSING", "mapping_status"].item() == "missing"
    assert output_path.exists()


def test_build_sec_cik_mapping_marks_ambiguous(tmp_path, monkeypatch) -> None:
    universe_path = tmp_path / "universe.csv"
    output_path = tmp_path / "reports" / "sec_cik_mapping.csv"
    pd.DataFrame({"ticker": ["ABC"]}).to_csv(universe_path, index=False)

    def fake_fetch(*args, **kwargs):
        return [
            {"ticker": "ABC", "cik": "111111", "name": "One", "exchange": "NYSE"},
            {"ticker": "ABC", "cik": "222222", "name": "Two", "exchange": "NYSE"},
        ]

    monkeypatch.setattr(sec_fundamentals, "fetch_sec_ticker_reference", fake_fetch)

    df = sec_fundamentals.build_sec_cik_mapping(
        universe_path=universe_path,
        output_path=output_path,
    )
    assert df.loc[0, "mapping_status"] == "ambiguous"
