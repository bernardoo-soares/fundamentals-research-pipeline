from __future__ import annotations

import json

from trading_bot.steps.sec_fundamentals import normalize_sec_facts_long


def test_normalize_sec_facts_long_filters_and_maps_contract_fields(tmp_path) -> None:
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
                                "frame": "CY2024Q1",
                            },
                            {
                                "val": 90.0,
                                "start": "2022-01-01",
                                "end": "2022-03-31",
                                "fy": 2022,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2022-05-01",
                                "accn": "0000",
                                "frame": "CY2022Q1",
                            },
                        ]
                    }
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {
                        "USD": [
                            {
                                "val": 50.0,
                                "end": "2024-03-31",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-05-01",
                                "accn": "0002",
                                "frame": "CY2024Q1I",
                            }
                        ]
                    }
                },
                "AssetsCurrent": {
                    "units": {
                        "USD": [
                            {
                                "val": 999.0,
                                "end": "2024-03-31",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "8-K",
                                "filed": "2024-04-01",
                                "accn": "ignored",
                            }
                        ]
                    }
                },
            }
        }
    }

    (raw_dir / "AAPL_0000320193.json").write_text(json.dumps(payload), encoding="utf-8")

    df = normalize_sec_facts_long(raw_dir=raw_dir, output_path=output_path)
    assert output_path.exists()
    assert len(df) == 2
    assert set(df["canonical_field"]) == {"saleq", "cheq"}
    assert (df["fyearq"] == 2024).all()
    assert (df["form_type"] == "10-Q").all()


def test_normalize_sec_facts_long_accepts_directory_output_path(tmp_path) -> None:
    raw_dir = tmp_path / "raw" / "sec" / "companyfacts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "data"

    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "val": 123.0,
                                "start": "2024-01-01",
                                "end": "2024-03-31",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-05-01",
                                "accn": "0001",
                            }
                        ]
                    }
                }
            }
        }
    }
    (raw_dir / "AAPL_0000320193.json").write_text(json.dumps(payload), encoding="utf-8")

    df = normalize_sec_facts_long(raw_dir=raw_dir, output_path=output_dir)
    expected_file = output_dir / "sec_facts_long_2023_2025.csv"

    assert expected_file.exists()
    assert len(df) == 1
