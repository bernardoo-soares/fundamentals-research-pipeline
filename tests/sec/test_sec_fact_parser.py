from __future__ import annotations

from trading_bot.connectors.sec import iter_companyfacts_rows


def test_iter_companyfacts_rows_flattens_payload() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 100.0,
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-05-01",
                                "accn": "0001",
                                "frame": "CY2024Q1",
                            }
                        ]
                    }
                }
            }
        }
    }

    rows = list(iter_companyfacts_rows(payload, ticker="aapl", cik="320193"))
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "AAPL"
    assert row["cik"] == "0000320193"
    assert row["taxonomy"] == "us-gaap"
    assert row["tag"] == "Revenues"
    assert row["unit"] == "USD"
    assert row["value"] == 100.0
    assert row["form"] == "10-Q"
