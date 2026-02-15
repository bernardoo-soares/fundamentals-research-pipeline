from __future__ import annotations

import json

from trading_bot.steps.sec_fundamentals import normalize_sec_facts_long


def test_normalize_sec_facts_long_dedupes_deterministically(tmp_path) -> None:
    raw_dir = tmp_path / "raw" / "sec" / "companyfacts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = tmp_path / "processed" / "sec_facts_long_2023_2025.csv"

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
                            },
                            {
                                "val": 110.0,
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-05-05",
                                "accn": "0002",
                            },
                            {
                                "val": 120.0,
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-05-05",
                                "accn": "0003",
                            },
                        ]
                    }
                }
            }
        }
    }

    (raw_dir / "AAPL_0000320193.json").write_text(json.dumps(payload), encoding="utf-8")
    df = normalize_sec_facts_long(raw_dir=raw_dir, output_path=output_path)

    assert len(df) == 1
    assert float(df.loc[0, "value"]) == 120.0
    assert df.loc[0, "accn"] == "0003"
