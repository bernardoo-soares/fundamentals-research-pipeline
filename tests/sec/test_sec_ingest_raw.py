from __future__ import annotations

import json

import pandas as pd

from trading_bot.core.exceptions import SecRequestError
from trading_bot.steps.sec_fundamentals import run_sec_raw_ingestion


class _FakeClient:
    def __init__(self, fail_ticker: str | None = None):
        self.fail_ticker = fail_ticker
        self.last_status_code: int | None = None
        self.last_attempts: int = 0

    def fetch_companyfacts(self, cik: str) -> dict:
        self.last_attempts += 1
        if self.fail_ticker and cik.endswith("1111111"):
            self.last_status_code = 429
            raise SecRequestError(
                "rate-limited",
                status_code=429,
                attempts=self.last_attempts,
            )
        self.last_status_code = 200
        return {"cik": cik, "facts": {"us-gaap": {}}}


def test_run_sec_raw_ingestion_writes_json_and_log(tmp_path) -> None:
    mapping_path = tmp_path / "sec_cik_mapping.csv"
    raw_dir = tmp_path / "raw" / "sec" / "companyfacts"
    log_path = tmp_path / "reports" / "sec_ingestion_log.csv"

    pd.DataFrame(
        [
            {"ticker": "AAPL", "cik": "0000320193", "mapping_status": "mapped"},
            {"ticker": "MISS", "cik": "", "mapping_status": "missing"},
        ]
    ).to_csv(mapping_path, index=False)

    client = _FakeClient()
    df = run_sec_raw_ingestion(
        mapping_path=mapping_path,
        raw_dir=raw_dir,
        log_path=log_path,
        run_id="run-1",
        client=client,
    )

    assert len(df) == 1
    assert df.loc[0, "status"] == "ok"
    assert log_path.exists()
    json_path = raw_dir / "AAPL_0000320193.json"
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["cik"] == "0000320193"


def test_run_sec_raw_ingestion_logs_error_rows(tmp_path) -> None:
    mapping_path = tmp_path / "sec_cik_mapping.csv"
    raw_dir = tmp_path / "raw" / "sec" / "companyfacts"
    log_path = tmp_path / "reports" / "sec_ingestion_log.csv"

    pd.DataFrame(
        [
            {"ticker": "ERR", "cik": "0001111111", "mapping_status": "mapped"},
        ]
    ).to_csv(mapping_path, index=False)

    client = _FakeClient(fail_ticker="ERR")
    df = run_sec_raw_ingestion(
        mapping_path=mapping_path,
        raw_dir=raw_dir,
        log_path=log_path,
        run_id="run-2",
        client=client,
    )

    assert len(df) == 1
    assert df.loc[0, "status"] == "error"
    assert int(df.loc[0, "http_code"]) == 429
    assert "rate-limited" in df.loc[0, "error"]
