from __future__ import annotations

from trading_bot.connectors.sec import (
    build_ticker_reference_lookup,
    build_ticker_to_cik_index,
    fetch_sec_ticker_reference,
    normalize_ticker,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.calls: list[tuple[str, int]] = []

    def get(self, url: str, timeout: int):
        self.calls.append((url, timeout))
        return _FakeResponse(self._payload)


def test_normalize_ticker() -> None:
    assert normalize_ticker(" brk.b ") == "BRK.B"
    assert normalize_ticker("bf/b") == "BF-B"


def test_fetch_sec_ticker_reference_from_dict_payload() -> None:
    payload = {
        "1": {"ticker": "MSFT", "cik_str": 789019, "title": "MICROSOFT"},
        "0": {"ticker": "AAPL", "cik_str": 320193, "title": "APPLE"},
    }
    session = _FakeSession(payload)
    rows = fetch_sec_ticker_reference(
        session=session,
        url="https://www.sec.gov/files/company_tickers.json",
        timeout=30,
    )
    assert session.calls == [("https://www.sec.gov/files/company_tickers.json", 30)]
    assert [row["ticker"] for row in rows] == ["AAPL", "MSFT"]


def test_build_ticker_to_cik_index_zero_pads() -> None:
    rows = [
        {"ticker": "AAPL", "cik": "320193"},
        {"ticker": "MSFT", "cik": "789019"},
    ]
    index = build_ticker_to_cik_index(rows)
    assert index["AAPL"] == "0000320193"
    assert index["MSFT"] == "0000789019"


def test_build_ticker_reference_lookup_supports_dot_dash_aliases() -> None:
    rows = [
        {"ticker": "BRK-B", "cik": "1067983", "name": "Berkshire", "exchange": "NYSE"}
    ]
    lookup = build_ticker_reference_lookup(rows)
    assert "BRK-B" in lookup
    assert "BRK.B" in lookup
    assert lookup["BRK.B"][0]["cik"] == "0001067983"
