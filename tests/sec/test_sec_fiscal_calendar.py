from __future__ import annotations

import json

import pandas as pd

from trading_bot.steps.sec_submissions import build_sec_fiscal_calendar


def test_build_sec_fiscal_calendar_parses_submissions_and_writes_output(tmp_path) -> None:
    submissions_dir = tmp_path / "raw" / "sec" / "submissions"
    submissions_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = tmp_path / "reports" / "sec_cik_mapping.csv"
    output_path = tmp_path / "reports" / "sec_fiscal_calendar.csv"

    pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "cik": "0000320193",
                "mapping_status": "mapped",
                "exchange": "NASDAQ",
            },
            {
                "ticker": "MSFT",
                "cik": "0000789019",
                "mapping_status": "mapped",
                "exchange": "",
            },
            {
                "ticker": "MISS",
                "cik": "0000000001",
                "mapping_status": "missing",
                "exchange": "NYSE",
            },
        ]
    ).to_csv(mapping_path, index=False)

    (submissions_dir / "AAPL_0000320193.json").write_text(
        json.dumps(
            {
                "name": "Apple Inc.",
                "fiscalYearEnd": "0927",
                "exchanges": ["Nasdaq"],
            }
        ),
        encoding="utf-8",
    )
    (submissions_dir / "MSFT_0000789019.json").write_text(
        json.dumps(
            {
                "name": "Microsoft Corp.",
                "fiscalYearEnd": "0630",
                "exchanges": ["Nasdaq"],
            }
        ),
        encoding="utf-8",
    )

    df = build_sec_fiscal_calendar(
        submissions_dir=submissions_dir,
        mapping_path=mapping_path,
        output_path=output_path,
    )

    assert output_path.exists()
    assert list(df.columns) == [
        "ticker",
        "cik",
        "fiscal_year_end_mmdd",
        "company_name",
        "exchange",
    ]
    assert list(df["ticker"]) == ["AAPL", "MSFT"]
    assert df.loc[df["ticker"] == "AAPL", "fiscal_year_end_mmdd"].item() == "0927"
    assert df.loc[df["ticker"] == "AAPL", "company_name"].item() == "Apple Inc."
    # Mapping exchange should take precedence when present.
    assert df.loc[df["ticker"] == "AAPL", "exchange"].item() == "NASDAQ"
    # Payload exchange should be used when mapping exchange is blank.
    assert df.loc[df["ticker"] == "MSFT", "exchange"].item() == "Nasdaq"
