"""SEC submissions ingestion and fiscal calendar reference steps.

This module provides two pipeline stages:
1. Download raw SEC submissions JSON per mapped company.
2. Build a fiscal calendar reference table from downloaded submissions files.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from ..connectors.sec_client import SecClient
from ..core.exceptions import SecRequestError
from ..core.logging import get_logger, utc_now_iso
from ..core.settings import get_settings

LOG = get_logger(__name__)

# Keep submissions ingestion log schema aligned with the raw companyfacts log.
SUBMISSIONS_INGESTION_LOG_COLUMNS = [
    "run_id",
    "ticker",
    "cik",
    "status",
    "http_code",
    "attempts",
    "latency_ms",
    "file_path",
    "error",
    "fetched_at_utc",
]


def _build_client() -> SecClient:
    """Create a SEC client using runtime settings."""
    settings = get_settings()
    return SecClient(
        base_url=settings.sec_data_url,
        user_agent=settings.user_agent,
        timeout_seconds=settings.request_timeout_seconds,
        rate_limit_per_second=settings.sec_rate_limit_per_second,
        max_retries=settings.sec_max_retries,
    )


def _parse_file_name(path: Path) -> tuple[str, str]:
    """Parse `<ticker>_<cik>.json` filename into normalized identifiers."""
    stem = path.stem
    if "_" not in stem:
        raise ValueError(
            f"SEC submissions filename must be '<ticker>_<cik>.json': {path.name}"
        )

    ticker, cik = stem.rsplit("_", 1)
    ticker = ticker.strip().upper()
    cik = str(cik).strip().zfill(10)
    if not ticker or not cik.isdigit():
        raise ValueError(f"Invalid SEC submissions filename: {path.name}")
    return ticker, cik


def run_sec_submissions_ingestion(
    mapping_path: str | Path = "data/reports/sec_cik_mapping.csv",
    raw_dir: str | Path = "data/raw/sec/submissions",
    log_path: str | Path = "data/reports/sec_submissions_ingestion_log.csv",
    run_id: str | None = None,
    client: SecClient | None = None,
) -> pd.DataFrame:
    """Fetch SEC submissions JSON payloads for mapped companies.

    Args:
        mapping_path: Ticker-to-CIK mapping CSV.
        raw_dir: Destination directory for submissions JSON files.
        log_path: Output CSV for ingestion diagnostics.
        run_id: Optional run identifier for auditability.
        client: Optional injected SEC client (testability hook).

    Returns:
        DataFrame with one log row per mapped company ingestion attempt.
    """
    LOG.info(
        "Starting SEC submissions ingestion: mapping_path=%s raw_dir=%s log_path=%s run_id=%s",
        mapping_path,
        raw_dir,
        log_path,
        run_id,
    )
    if run_id is None:
        run_id = utc_now_iso()

    mapping_df = pd.read_csv(mapping_path, dtype=str)
    required = {"ticker", "cik", "mapping_status"}
    if not required.issubset(mapping_df.columns):
        missing = sorted(required.difference(mapping_df.columns))
        raise ValueError(f"Mapping file missing required columns: {missing}")

    mapped_df = mapping_df[mapping_df["mapping_status"] == "mapped"].copy()
    mapped_df["ticker"] = mapped_df["ticker"].fillna("").astype(str).str.strip().str.upper()
    mapped_df["cik"] = mapped_df["cik"].fillna("").astype(str).str.strip().str.zfill(10)
    mapped_df = mapped_df[(mapped_df["ticker"] != "") & (mapped_df["cik"] != "")]
    LOG.info(
        "SEC submissions ingestion input prepared: mapping_rows=%d mapped_rows=%d",
        len(mapping_df),
        len(mapped_df),
    )

    raw_dir_path = Path(raw_dir)
    raw_dir_path.mkdir(parents=True, exist_ok=True)
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if client is None:
        client = _build_client()
        LOG.info("Using default SEC client from runtime settings.")
    else:
        LOG.info("Using injected SEC client instance.")

    rows: list[dict[str, Any]] = []
    total = len(mapped_df)
    success_count = 0
    error_count = 0
    for index, (_, row) in enumerate(mapped_df.iterrows(), start=1):
        ticker = row["ticker"]
        cik = row["cik"]
        LOG.info(
            "Submissions ingestion progress %d/%d: ticker=%s cik=%s",
            index,
            total,
            ticker,
            cik,
        )
        started = time.perf_counter()
        status = "ok"
        http_code: int | None = None
        attempts = 0
        file_path = ""
        error = ""

        try:
            payload = client.fetch_submissions(cik)
            http_code = client.last_status_code
            attempts = client.last_attempts
            out_path = raw_dir_path / f"{ticker}_{cik}.json"
            out_path.write_text(
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                encoding="utf-8",
            )
            file_path = str(out_path)
            LOG.info("Fetched SEC submissions for %s (%s)", ticker, cik)
            success_count += 1
        except SecRequestError as exc:
            status = "error"
            http_code = exc.status_code
            attempts = exc.attempts or client.last_attempts
            error = str(exc)
            LOG.error("Failed SEC submissions for %s (%s): %s", ticker, cik, error)
            error_count += 1
        except Exception as exc:  # pragma: no cover - safety guard
            status = "error"
            http_code = client.last_status_code
            attempts = client.last_attempts
            error = f"Unexpected error: {exc}"
            LOG.exception("Unexpected submissions ingestion error for %s (%s)", ticker, cik)
            error_count += 1

        rows.append(
            {
                "run_id": run_id,
                "ticker": ticker,
                "cik": cik,
                "status": status,
                "http_code": http_code,
                "attempts": attempts,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "file_path": file_path,
                "error": error,
                "fetched_at_utc": utc_now_iso(),
            }
        )

    out = pd.DataFrame(rows, columns=SUBMISSIONS_INGESTION_LOG_COLUMNS)
    out.to_csv(log_path, index=False)
    LOG.info(
        "SEC submissions ingestion completed: total=%d success=%d error=%d output_log=%s",
        total,
        success_count,
        error_count,
        log_path,
    )
    return out


def build_sec_fiscal_calendar(
    submissions_dir: str | Path = "data/raw/sec/submissions",
    mapping_path: str | Path = "data/reports/sec_cik_mapping.csv",
    output_path: str | Path = "data/reports/sec_fiscal_calendar.csv",
) -> pd.DataFrame:
    """Build fiscal calendar table from raw submissions JSON files.

    Output columns:
    - ticker
    - cik
    - fiscal_year_end_mmdd
    - company_name
    - exchange
    """
    LOG.info(
        "Starting fiscal calendar build: submissions_dir=%s mapping_path=%s output_path=%s",
        submissions_dir,
        mapping_path,
        output_path,
    )
    submissions_dir = Path(submissions_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mapping_df = pd.read_csv(mapping_path, dtype=str)
    required = {"ticker", "cik", "mapping_status"}
    if not required.issubset(mapping_df.columns):
        missing = sorted(required.difference(mapping_df.columns))
        raise ValueError(f"Mapping file missing required columns: {missing}")

    mapped = mapping_df[mapping_df["mapping_status"] == "mapped"].copy()
    mapped["ticker"] = mapped["ticker"].fillna("").astype(str).str.strip().str.upper()
    mapped["cik"] = mapped["cik"].fillna("").astype(str).str.strip().str.zfill(10)
    mapped["exchange"] = mapped.get("exchange", pd.Series(index=mapped.index)).fillna(
        ""
    ).astype(str).str.strip()
    mapped = mapped[(mapped["ticker"] != "") & (mapped["cik"] != "")]
    mapped = mapped.drop_duplicates(subset=["ticker", "cik"], keep="last")

    parsed: dict[tuple[str, str], dict[str, str]] = {}
    json_files = sorted(submissions_dir.glob("*.json"))
    LOG.info("Submissions files discovered for fiscal calendar: %d", len(json_files))
    for file_path in json_files:
        ticker, cik = _parse_file_name(file_path)
        payload = json.loads(file_path.read_text(encoding="utf-8"))

        fiscal_year_end = str(payload.get("fiscalYearEnd", "")).strip()
        company_name = str(payload.get("name", "")).strip()
        exchanges = payload.get("exchanges", [])
        exchange_from_payload = ""
        if isinstance(exchanges, list) and exchanges:
            exchange_from_payload = str(exchanges[0]).strip()

        parsed[(ticker, cik)] = {
            "fiscal_year_end_mmdd": fiscal_year_end,
            "company_name": company_name,
            "exchange_from_payload": exchange_from_payload,
        }

    rows: list[dict[str, str]] = []
    found_count = 0
    for _, row in mapped.iterrows():
        ticker = row["ticker"]
        cik = row["cik"]
        exchange = row["exchange"]
        meta = parsed.get((ticker, cik), {})
        if meta:
            found_count += 1

        # Prefer mapping exchange for consistency with universe mapping output.
        exchange_out = exchange or meta.get("exchange_from_payload", "")
        rows.append(
            {
                "ticker": ticker,
                "cik": cik,
                "fiscal_year_end_mmdd": meta.get("fiscal_year_end_mmdd", ""),
                "company_name": meta.get("company_name", ""),
                "exchange": exchange_out,
            }
        )

    out = pd.DataFrame(
        rows,
        columns=[
            "ticker",
            "cik",
            "fiscal_year_end_mmdd",
            "company_name",
            "exchange",
        ],
    )
    out = out.sort_values(["ticker", "cik"], kind="mergesort").reset_index(drop=True)
    out.to_csv(output_path, index=False)
    LOG.info(
        "Fiscal calendar build completed: mapped_rows=%d matched_submissions=%d output=%s",
        len(out),
        found_count,
        output_path,
    )
    return out
