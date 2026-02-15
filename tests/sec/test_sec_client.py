from __future__ import annotations

import requests
import pytest

from trading_bot.connectors.sec import SecClient
from trading_bot.core.exceptions import SecRequestError


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(f"status={self.status_code}", response=response)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses: list[_Response]):
        self.responses = list(responses)
        self.headers: dict[str, str] = {}

    def get(self, url: str, timeout: int):
        if not self.responses:
            raise RuntimeError("No fake responses remaining.")
        return self.responses.pop(0)


def _build_client(session: _Session, monkeypatch) -> SecClient:
    monkeypatch.setattr("trading_bot.connectors.sec.time.sleep", lambda *_: None)
    monkeypatch.setattr("trading_bot.connectors.sec.random.uniform", lambda *_: 0.0)
    client = SecClient(
        base_url="https://data.sec.gov",
        user_agent="UnitTest/1.0",
        timeout_seconds=5,
        rate_limit_per_second=1000.0,
        max_retries=2,
        session=session,
    )
    return client


def test_fetch_companyfacts_success(monkeypatch) -> None:
    session = _Session([_Response(200, {"ok": True})])
    client = _build_client(session, monkeypatch)
    payload = client.fetch_companyfacts("320193")
    assert payload == {"ok": True}
    assert client.last_status_code == 200
    assert client.last_attempts == 1


def test_fetch_companyfacts_retry_then_success(monkeypatch) -> None:
    session = _Session([_Response(429, {}), _Response(200, {"ok": True})])
    client = _build_client(session, monkeypatch)
    payload = client.fetch_companyfacts("320193")
    assert payload["ok"] is True
    assert client.last_attempts == 2


def test_fetch_companyfacts_raises_after_retries(monkeypatch) -> None:
    session = _Session([_Response(500, {}), _Response(503, {}), _Response(429, {})])
    client = _build_client(session, monkeypatch)
    with pytest.raises(SecRequestError):
        client.fetch_companyfacts("320193")


def test_fetch_companyfacts_non_retryable_fails_fast(monkeypatch) -> None:
    session = _Session([_Response(404, {}), _Response(200, {"ok": True})])
    client = _build_client(session, monkeypatch)
    with pytest.raises(SecRequestError):
        client.fetch_companyfacts("320193")


def test_fetch_submissions_success(monkeypatch) -> None:
    session = _Session([_Response(200, {"fiscalYearEnd": "1231"})])
    client = _build_client(session, monkeypatch)
    payload = client.fetch_submissions("320193")
    assert payload["fiscalYearEnd"] == "1231"
    assert client.last_status_code == 200
    assert client.last_attempts == 1


def test_fetch_submissions_retry_then_success(monkeypatch) -> None:
    session = _Session([_Response(429, {}), _Response(200, {"name": "Apple"})])
    client = _build_client(session, monkeypatch)
    payload = client.fetch_submissions("320193")
    assert payload["name"] == "Apple"
    assert client.last_attempts == 2


def test_fetch_submissions_raises_after_retries(monkeypatch) -> None:
    session = _Session([_Response(500, {}), _Response(503, {}), _Response(429, {})])
    client = _build_client(session, monkeypatch)
    with pytest.raises(SecRequestError):
        client.fetch_submissions("320193")
