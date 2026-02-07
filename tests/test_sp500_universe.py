from __future__ import annotations

import pandas as pd

from trading_bot.pipelines import sp500_universe


class _FakeConstituents:
    def get_sp500_current(self) -> list[str]:
        return ["aapl", "MSFT", " msft ", "BRK.B"]


def test_build_sp500_current_universe_writes_normalized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sp500_universe, "SP500Constituents", _FakeConstituents)

    df = sp500_universe.build_sp500_current_universe(
        output_dir=tmp_path,
        as_of_date="2026-02-07",
    )

    assert list(df.columns) == ["as_of_date", "year", "ticker"]
    assert df["ticker"].tolist() == ["AAPL", "BRK.B", "MSFT"]
    assert (df["as_of_date"] == "2026-02-07").all()
    assert (df["year"] == 2026).all()

    out_path = tmp_path / "universe_current.csv"
    written = pd.read_csv(out_path)
    assert written["ticker"].tolist() == ["AAPL", "BRK.B", "MSFT"]
