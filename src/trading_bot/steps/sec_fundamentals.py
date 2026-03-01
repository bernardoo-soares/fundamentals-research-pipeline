"""SEC fundamentals pipeline steps.

This module implements three runnable stages:
1. Universe ticker -> CIK mapping report.
2. Raw SEC companyfacts ingestion with logging.
3. Contract-driven normalization into long-form canonical facts.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from ..contracts.sec_metric_contract import MetricMapping, load_sec_metric_contract
from ..connectors.sec import (
    SecClient,
    build_ticker_reference_lookup,
    fetch_sec_ticker_reference,
    iter_companyfacts_rows,
    normalize_ticker,
)
from ..core.exceptions import SecRequestError
from ..core.logging import get_logger, utc_now_iso
from ..core.settings import get_settings
from .fiscal_resolution import normalize_fiscal_year_end_mmdd, resolve_fiscal_quarter


LOG = get_logger(__name__)


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format.

    This local helper avoids importing datetime details at call sites and keeps
    mapping artifacts timestamped consistently.
    """
    return datetime.now(timezone.utc).isoformat()


def build_sec_cik_mapping(
    universe_path: str | Path = "data/universe_current.csv",
    output_path: str | Path = "data/reports/sec_cik_mapping.csv",
) -> pd.DataFrame:
    """Build ticker-to-CIK mapping report for current universe members.

    Args:
        universe_path: CSV containing at least a `ticker` column.
        output_path: Destination path for mapping report CSV.

    Returns:
        Mapping report with per-ticker status: `mapped`, `ambiguous`, `missing`.

    Raises:
        ValueError: If universe input is missing required columns.
    """
    LOG.info(
        "Starting SEC CIK mapping: universe_path=%s output_path=%s",
        universe_path,
        output_path,
    )
    settings = get_settings()
    universe = pd.read_csv(universe_path, dtype=str)
    if "ticker" not in universe.columns:
        raise ValueError(f"Universe file '{universe_path}' is missing 'ticker' column.")

    # Normalize and de-duplicate universe tickers before lookup.
    tickers = sorted(
        {
            normalized
            for normalized in (
                normalize_ticker(value) for value in universe["ticker"].tolist()
            )
            if normalized
        }
    )
    LOG.info("Universe tickers prepared for SEC lookup: %d unique tickers.", len(tickers))

    session = requests.Session()
    session.headers.update({"User-Agent": settings.user_agent})
    sec_rows = fetch_sec_ticker_reference(
        session=session,
        url=settings.sec_reference_url,
        timeout=settings.request_timeout_seconds,
    )
    LOG.info("SEC ticker reference rows fetched: %d", len(sec_rows))
    lookup = build_ticker_reference_lookup(sec_rows)
    LOG.info("SEC ticker lookup aliases built: %d", len(lookup))

    mapped_at = _utc_now_iso()
    records: list[dict[str, str]] = []
    status_counter: Counter[str] = Counter()
    for ticker in tickers:
        candidates = lookup.get(ticker, [])

        # De-duplicate SEC candidates by CIK to avoid duplicated rows from aliases.
        unique_candidates = {
            candidate["cik"]: candidate for candidate in candidates
        }
        deduped = list(unique_candidates.values())

        if len(deduped) == 1:
            match = deduped[0]
            records.append(
                {
                    "ticker": ticker,
                    "cik": match["cik"],
                    "sec_ticker": match["ticker"],
                    "sec_name": match["name"],
                    "exchange": match["exchange"],
                    "mapping_status": "mapped",
                    "mapped_at_utc": mapped_at,
                }
            )
            status_counter["mapped"] += 1
            continue

        if len(deduped) > 1:
            records.append(
                {
                    "ticker": ticker,
                    "cik": "",
                    "sec_ticker": "",
                    "sec_name": "",
                    "exchange": "",
                    "mapping_status": "ambiguous",
                    "mapped_at_utc": mapped_at,
                }
            )
            status_counter["ambiguous"] += 1
            continue

        records.append(
            {
                "ticker": ticker,
                "cik": "",
                "sec_ticker": "",
                "sec_name": "",
                "exchange": "",
                "mapping_status": "missing",
                "mapped_at_utc": mapped_at,
            }
        )
        status_counter["missing"] += 1

    output_df = pd.DataFrame(records).sort_values("ticker").reset_index(drop=True)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_path, index=False)
    LOG.info(
        "SEC CIK mapping completed: rows=%d mapped=%d ambiguous=%d missing=%d output=%s",
        len(output_df),
        status_counter.get("mapped", 0),
        status_counter.get("ambiguous", 0),
        status_counter.get("missing", 0),
        output_path,
    )
    return output_df


# Fixed schema for ingestion run logs.
INGESTION_LOG_COLUMNS = [
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
    """Instantiate `SecClient` from current runtime settings."""
    settings = get_settings()
    return SecClient(
        base_url=settings.sec_data_url,
        user_agent=settings.user_agent,
        timeout_seconds=settings.request_timeout_seconds,
        rate_limit_per_second=settings.sec_rate_limit_per_second,
        max_retries=settings.sec_max_retries,
    )


def run_sec_raw_ingestion(
    mapping_path: str | Path = "data/reports/sec_cik_mapping.csv",
    raw_dir: str | Path = "data/raw/sec/companyfacts",
    log_path: str | Path = "data/reports/sec_ingestion_log.csv",
    run_id: str | None = None,
    client: SecClient | None = None,
) -> pd.DataFrame:
    """Fetch SEC companyfacts JSON for mapped tickers and persist ingestion log.

    Args:
        mapping_path: Mapping CSV generated by `build_sec_cik_mapping`.
        raw_dir: Directory to store one JSON file per mapped ticker.
        log_path: Output CSV path for ingestion diagnostics.
        run_id: Optional run identifier; defaults to current UTC timestamp.
        client: Optional injected SEC client (useful for tests).

    Returns:
        DataFrame of ingestion log rows using `INGESTION_LOG_COLUMNS` schema.

    Raises:
        ValueError: If mapping file is missing required columns.
    """
    LOG.info(
        "Starting SEC raw ingestion: mapping_path=%s raw_dir=%s log_path=%s run_id=%s",
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
    mapped_df["ticker"] = mapped_df["ticker"].fillna("").astype(str).str.strip()
    mapped_df["cik"] = mapped_df["cik"].fillna("").astype(str).str.strip()
    mapped_df = mapped_df[(mapped_df["ticker"] != "") & (mapped_df["cik"] != "")]
    LOG.info(
        "SEC ingestion input prepared: mapping_rows=%d mapped_rows=%d",
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
        ticker = str(row["ticker"]).strip().upper()
        cik = str(row["cik"]).strip().zfill(10)
        LOG.info("Ingestion progress %d/%d: ticker=%s cik=%s", index, total, ticker, cik)
        started = time.perf_counter()
        status = "ok"
        http_code: int | None = None
        attempts = 0
        file_path = ""
        error = ""

        try:
            payload = client.fetch_companyfacts(cik)
            http_code = client.last_status_code
            attempts = client.last_attempts
            out_path = raw_dir_path / f"{ticker}_{cik}.json"
            out_path.write_text(
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                encoding="utf-8",
            )
            file_path = str(out_path)
            LOG.info("Fetched SEC companyfacts for %s (%s)", ticker, cik)
            success_count += 1
        except SecRequestError as exc:
            status = "error"
            http_code = exc.status_code
            attempts = exc.attempts or client.last_attempts
            error = str(exc)
            LOG.error("Failed SEC companyfacts for %s (%s): %s", ticker, cik, error)
            error_count += 1
        except Exception as exc:  # pragma: no cover - safety guard
            status = "error"
            http_code = client.last_status_code
            attempts = client.last_attempts
            error = f"Unexpected error: {exc}"
            LOG.exception("Unexpected ingestion error for %s (%s)", ticker, cik)
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

    out = pd.DataFrame(rows, columns=INGESTION_LOG_COLUMNS)
    out.to_csv(log_path, index=False)
    LOG.info(
        "SEC raw ingestion completed: total=%d success=%d error=%d output_log=%s",
        total,
        success_count,
        error_count,
        log_path,
    )
    return out


# Output schema for normalized long SEC facts.
LONG_FACT_COLUMNS = [
    "ticker",
    "cik",
    "fyearq",
    "fqtr",
    "period_start",
    "period_end",
    "filed_date",
    "form_type",
    "accn",
    "frame",
    "canonical_field",
    "value",
    "unit",
    "source_tag",
    "quality_tier",
    "fact_type",
    "transform_rule",
    "is_component_tag",
    "source_system",
    "source_tag_map_version",
    "fiscal_year_end_mmdd",
    "fiscal_anchor_end",
    "fiscal_day_delta",
    "source_fy",
    "source_fp",
]

# Deterministic key for duplicate fact candidate resolution.
DEDUPE_KEY = [
    "ticker",
    "canonical_field",
    "fyearq",
    "fqtr",
    "period_end",
    "form_type",
    "source_tag",
    "unit",
]

UNRESOLVED_FACT_COLUMNS = [
    "ticker",
    "cik",
    "canonical_field",
    "source_tag",
    "period_start",
    "period_end",
    "filed_date",
    "form_type",
    "accn",
    "unit",
    "value",
    "fiscal_year_end_mmdd",
    "source_fy",
    "source_fp",
    "reason",
]


def _parse_file_name(path: Path) -> tuple[str, str]:
    """Parse `<ticker>_<cik>.json` raw filename into normalized identifiers."""
    stem = path.stem
    if "_" not in stem:
        raise ValueError(f"SEC raw filename must be '<ticker>_<cik>.json': {path.name}")

    ticker, cik = stem.rsplit("_", 1)
    ticker = ticker.strip().upper()
    cik = cik.strip().zfill(10)
    if not ticker or not cik.isdigit():
        raise ValueError(f"Invalid SEC raw filename: {path.name}")
    return ticker, cik


def _coerce_year(value: Any) -> int | None:
    """Convert SEC fiscal year value to integer when possible."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _coerce_quarter_from_fp(value: Any) -> int | None:
    """Convert SEC `fp` period label (for example `Q1`) into integer quarter."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if text.startswith("Q") and len(text) >= 2 and text[1].isdigit():
        q = int(text[1])
        if 1 <= q <= 4:
            return q
    return None


def _coerce_timestamp(value: Any) -> pd.Timestamp | pd.NaT:
    """Convert timestamp-like values to pandas timestamps with tolerant parsing."""
    return pd.to_datetime(value, errors="coerce")


def _load_fiscal_calendar_lookup(
    fiscal_calendar_path: str | Path,
) -> dict[tuple[str, str], str]:
    """Load fiscal-year-end mapping keyed by `(ticker, cik)`."""
    table = pd.read_csv(fiscal_calendar_path, dtype=str).fillna("")
    required = {"ticker", "cik", "fiscal_year_end_mmdd"}
    if not required.issubset(table.columns):
        missing = sorted(required.difference(table.columns))
        raise ValueError(
            f"Fiscal calendar file missing required columns: {missing}"
        )

    table["ticker"] = table["ticker"].astype(str).str.strip().str.upper()
    table["cik"] = table["cik"].astype(str).str.strip().str.zfill(10)
    table["fiscal_year_end_mmdd"] = (
        table["fiscal_year_end_mmdd"]
        .astype(str)
        .str.strip()
        .map(normalize_fiscal_year_end_mmdd)
        .fillna("")
    )
    table = table.drop_duplicates(subset=["ticker", "cik"], keep="last")
    return {
        (str(row["ticker"]), str(row["cik"])): str(row["fiscal_year_end_mmdd"])
        for _, row in table.iterrows()
    }


def _resolve_canonical_field(
    tag_full: str,
    mapping: dict[str, MetricMapping],
) -> tuple[str, bool] | None:
    """Resolve SEC tag into canonical field and component-flag metadata.

    Returns:
        Tuple of (`canonical_field`, `is_component_tag`) or `None` when unmapped.
    """
    for canonical_name, cfg in mapping.items():
        if tag_full in cfg.tag_priority:
            return canonical_name, False
        if tag_full in cfg.component_tags:
            return canonical_name, True
    return None


def _build_row(
    *,
    source: dict[str, Any],
    canonical: str,
    cfg: MetricMapping,
    source_tag: str,
    is_component_tag: bool,
    source_tag_map_version: str,
    start_year: int,
    end_year: int,
    fiscal_year_end_mmdd: str,
    max_day_delta: int,
    strict_fiscal_resolution: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate and transform one flattened SEC observation into output row.

    Rows are rejected when form/unit/value/period constraints do not match the
    metric contract or fiscal quarter resolution policy.
    """
    form_type = str(source.get("form", "")).strip()
    if form_type not in cfg.form_priority:
        return None, "unsupported_form"

    unit = str(source.get("unit", "")).strip()
    if unit not in cfg.unit_priority:
        return None, "unsupported_unit"

    period_start = _coerce_timestamp(source.get("start"))
    period_end = _coerce_timestamp(source.get("end"))
    filed_date = _coerce_timestamp(source.get("filed"))

    value = pd.to_numeric(pd.Series([source.get("value")]), errors="coerce").iloc[0]
    if pd.isna(value):
        return None, "non_numeric_value"

    fyearq: int | None = None
    fqtr: int | None = None
    fiscal_anchor_end: pd.Timestamp | pd.NaT = pd.NaT
    fiscal_day_delta: int | None = None

    normalized_mmdd = normalize_fiscal_year_end_mmdd(fiscal_year_end_mmdd)
    if normalized_mmdd:
        resolved = resolve_fiscal_quarter(
            period_end=period_end,
            fiscal_year_end_mmdd=normalized_mmdd,
            start_year=start_year,
            end_year=end_year,
            max_day_delta=max_day_delta,
        )
        if resolved is None:
            return None, "unresolved_fiscal_period"
        fyearq = resolved.fyearq
        fqtr = resolved.fqtr
        fiscal_anchor_end = resolved.fiscal_anchor_end
        fiscal_day_delta = resolved.day_delta
    elif strict_fiscal_resolution:
        return None, "missing_fiscal_year_end"
    else:
        # Backward-compatible fallback path when fiscal calendar is not supplied.
        fyearq = _coerce_year(source.get("fy"))
        if fyearq is None and pd.notna(period_end):
            fyearq = int(period_end.year)
        if fyearq is None or fyearq < start_year or fyearq > end_year:
            return None, "out_of_year_range"

        fqtr = _coerce_quarter_from_fp(source.get("fp"))
        if fqtr is None and pd.notna(period_end):
            fqtr = int(period_end.quarter)
        if fqtr is None:
            return None, "missing_quarter"

    return {
        "ticker": str(source.get("ticker", "")).strip().upper(),
        "cik": str(source.get("cik", "")).strip().zfill(10),
        "fyearq": int(fyearq),
        "fqtr": int(fqtr),
        "period_start": period_start,
        "period_end": period_end,
        "filed_date": filed_date,
        "form_type": form_type,
        "accn": str(source.get("accn", "")).strip(),
        "frame": str(source.get("frame", "")).strip(),
        "canonical_field": canonical,
        "value": float(value),
        "unit": unit,
        "source_tag": source_tag,
        "quality_tier": cfg.quality_tier,
        "fact_type": cfg.fact_type,
        "transform_rule": cfg.transform_rule,
        "is_component_tag": is_component_tag,
        "source_system": "sec-companyfacts",
        "source_tag_map_version": source_tag_map_version,
        "fiscal_year_end_mmdd": normalized_mmdd or "",
        "fiscal_anchor_end": fiscal_anchor_end,
        "fiscal_day_delta": fiscal_day_delta,
        "source_fy": _coerce_year(source.get("fy")),
        "source_fp": str(source.get("fp", "")).strip(),
    }, None


def normalize_sec_facts_long(
    raw_dir: str | Path = "data/raw/sec/companyfacts",
    mapping_path: str | Path | None = None,
    output_path: str | Path = "data/processed/sec_facts_long_2023_2025.csv",
    *,
    fiscal_calendar_path: str | Path | None = None,
    start_year: int = 2023,
    end_year: int = 2025,
    max_day_delta: int = 30,
    unresolved_path: str | Path | None = None,
) -> pd.DataFrame:
    """Normalize raw SEC companyfacts JSON into canonical long-form facts.

    Args:
        raw_dir: Directory containing `<ticker>_<cik>.json` raw payloads.
        mapping_path: Optional contract YAML path override.
        output_path: CSV path or directory for normalized output.
        fiscal_calendar_path: Optional fiscal calendar CSV path.
        start_year: Inclusive fiscal year lower bound.
        end_year: Inclusive fiscal year upper bound.
        max_day_delta: Maximum distance in days for fiscal quarter anchor matching.
        unresolved_path: Optional unresolved-row CSV output path.

    Returns:
        Long-form canonical SEC facts DataFrame.
    """
    LOG.info(
        "Starting SEC long normalization: raw_dir=%s mapping_path=%s output_path=%s "
        "fiscal_calendar_path=%s start_year=%d end_year=%d max_day_delta=%d",
        raw_dir,
        mapping_path,
        output_path,
        fiscal_calendar_path,
        start_year,
        end_year,
        max_day_delta,
    )
    contract = load_sec_metric_contract(path=mapping_path)
    mapping = contract.metrics
    LOG.info(
        "Loaded SEC mapping contract version=%s metrics=%d",
        contract.version,
        len(mapping),
    )

    raw_dir = Path(raw_dir)
    output_path = Path(output_path)
    strict_fiscal_resolution = fiscal_calendar_path is not None
    fiscal_lookup: dict[tuple[str, str], str] = {}

    if strict_fiscal_resolution:
        fiscal_calendar_path = Path(fiscal_calendar_path)
        if not fiscal_calendar_path.exists():
            raise ValueError(f"Fiscal calendar file not found: {fiscal_calendar_path}")
        fiscal_lookup = _load_fiscal_calendar_lookup(fiscal_calendar_path)
        LOG.info(
            "Loaded fiscal calendar rows: %d from %s",
            len(fiscal_lookup),
            fiscal_calendar_path,
        )

    # Allow caller to pass either a specific CSV file or a destination directory.
    if output_path.exists() and output_path.is_dir():
        output_path = output_path / f"sec_facts_long_{start_year}_{end_year}.csv"
    elif output_path.suffix.lower() != ".csv":
        output_path.mkdir(parents=True, exist_ok=True)
        output_path = output_path / f"sec_facts_long_{start_year}_{end_year}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_files = sorted(raw_dir.glob("*.json"))
    LOG.info("SEC raw files discovered for normalization: %d", len(json_files))

    rows: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []
    total_facts_seen = 0
    unmapped_tag_facts = 0
    matched_tag_facts = 0
    accepted_rows = 0
    for file_index, json_path in enumerate(json_files, start=1):
        ticker, cik = _parse_file_name(json_path)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        file_facts_seen = 0
        file_matched = 0
        file_accepted = 0

        for fact in iter_companyfacts_rows(payload, ticker=ticker, cik=cik):
            total_facts_seen += 1
            file_facts_seen += 1
            tag_full = f"{fact['taxonomy']}:{fact['tag']}"
            resolved = _resolve_canonical_field(tag_full, mapping)
            if resolved is None:
                unmapped_tag_facts += 1
                continue
            matched_tag_facts += 1
            file_matched += 1
            canonical, is_component_tag = resolved
            cfg = mapping[canonical]
            fiscal_year_end_mmdd = fiscal_lookup.get((ticker, cik), "")

            candidate, reason = _build_row(
                source=fact,
                canonical=canonical,
                cfg=cfg,
                source_tag=tag_full,
                is_component_tag=is_component_tag,
                source_tag_map_version=contract.version,
                start_year=start_year,
                end_year=end_year,
                fiscal_year_end_mmdd=fiscal_year_end_mmdd,
                max_day_delta=max_day_delta,
                strict_fiscal_resolution=strict_fiscal_resolution,
            )
            if candidate is not None:
                rows.append(candidate)
                accepted_rows += 1
                file_accepted += 1
            elif strict_fiscal_resolution and reason in {
                "missing_fiscal_year_end",
                "unresolved_fiscal_period",
            }:
                unresolved_rows.append(
                    {
                        "ticker": str(fact.get("ticker", "")).strip().upper(),
                        "cik": str(fact.get("cik", "")).strip().zfill(10),
                        "canonical_field": canonical,
                        "source_tag": tag_full,
                        "period_start": _coerce_timestamp(fact.get("start")),
                        "period_end": _coerce_timestamp(fact.get("end")),
                        "filed_date": _coerce_timestamp(fact.get("filed")),
                        "form_type": str(fact.get("form", "")).strip(),
                        "accn": str(fact.get("accn", "")).strip(),
                        "unit": str(fact.get("unit", "")).strip(),
                        "value": fact.get("value"),
                        "fiscal_year_end_mmdd": fiscal_year_end_mmdd,
                        "source_fy": _coerce_year(fact.get("fy")),
                        "source_fp": str(fact.get("fp", "")).strip(),
                        "reason": reason,
                    }
                )

        LOG.info(
            "Normalization file %d/%d processed: ticker=%s cik=%s facts_seen=%d "
            "mapped_tag_candidates=%d accepted_rows=%d",
            file_index,
            len(json_files),
            ticker,
            cik,
            file_facts_seen,
            file_matched,
            file_accepted,
        )

    out = pd.DataFrame(rows, columns=LONG_FACT_COLUMNS)
    if strict_fiscal_resolution:
        unresolved = pd.DataFrame(unresolved_rows, columns=UNRESOLVED_FACT_COLUMNS)
        if unresolved_path is None:
            unresolved_path = (
                output_path.parent
                / f"sec_facts_long_unresolved_{start_year}_{end_year}.csv"
            )
        unresolved_path = Path(unresolved_path)
        unresolved_path.parent.mkdir(parents=True, exist_ok=True)
        unresolved.to_csv(unresolved_path, index=False)
        LOG.info(
            "Fiscal resolution unresolved rows written: rows=%d output=%s",
            len(unresolved),
            unresolved_path,
        )
    LOG.info(
        "Normalization pre-dedupe stats: files=%d total_facts=%d mapped_tag_facts=%d "
        "unmapped_tag_facts=%d accepted_rows=%d",
        len(json_files),
        total_facts_seen,
        matched_tag_facts,
        unmapped_tag_facts,
        accepted_rows,
    )
    if out.empty:
        out.to_csv(output_path, index=False)
        LOG.warning("Normalization produced no rows. Empty output written to %s", output_path)
        return out

    out["period_start"] = pd.to_datetime(out["period_start"], errors="coerce")
    out["period_end"] = pd.to_datetime(out["period_end"], errors="coerce")
    out["filed_date"] = pd.to_datetime(out["filed_date"], errors="coerce")
    out["accn"] = out["accn"].fillna("").astype(str)

    # Resolve duplicates deterministically by taking latest filing then accession.
    pre_dedupe_rows = len(out)
    out = out.sort_values(
        DEDUPE_KEY + ["filed_date", "accn"],
        kind="mergesort",
    ).drop_duplicates(subset=DEDUPE_KEY, keep="last")
    post_dedupe_rows = len(out)
    LOG.info(
        "Normalization dedupe applied: before=%d after=%d removed=%d",
        pre_dedupe_rows,
        post_dedupe_rows,
        pre_dedupe_rows - post_dedupe_rows,
    )

    out = out.sort_values(
        ["ticker", "fyearq", "fqtr", "canonical_field", "period_end", "filed_date", "accn"],
        kind="mergesort",
    ).reset_index(drop=True)

    out.to_csv(output_path, index=False)
    LOG.info("Normalization completed: final_rows=%d output=%s", len(out), output_path)
    return out


def _load_mapped_companies(
    sec_cik_mapping_path: str | Path,
) -> pd.DataFrame:
    """Load mapped ticker/CIK pairs from SEC mapping report."""
    mapping = pd.read_csv(sec_cik_mapping_path, dtype=str).fillna("")
    required = {"ticker", "cik", "mapping_status"}
    if not required.issubset(mapping.columns):
        missing = sorted(required.difference(mapping.columns))
        raise ValueError(f"SEC CIK mapping file missing required columns: {missing}")

    mapped = mapping[mapping["mapping_status"] == "mapped"].copy()
    mapped["ticker"] = mapped["ticker"].astype(str).str.strip().str.upper()
    mapped["cik"] = mapped["cik"].astype(str).str.strip().str.zfill(10)
    mapped = mapped[(mapped["ticker"] != "") & (mapped["cik"] != "")]
    mapped = mapped.drop_duplicates(subset=["ticker", "cik"], keep="last")
    return mapped[["ticker", "cik"]].sort_values(["ticker", "cik"], kind="mergesort")


def _compute_tag_rank(
    *,
    source_tag: str,
    cfg: MetricMapping,
) -> int:
    """Compute deterministic source-tag priority rank for one metric mapping."""
    try:
        return cfg.tag_priority.index(source_tag)
    except ValueError:
        pass

    try:
        return len(cfg.tag_priority) + cfg.component_tags.index(source_tag)
    except ValueError:
        return len(cfg.tag_priority) + len(cfg.component_tags) + 1_000


def _build_selected_quarterly_facts(
    *,
    long_df: pd.DataFrame,
    mapping: dict[str, MetricMapping],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select one best fact per ticker/fiscal-quarter/canonical-field."""
    if long_df.empty:
        return long_df.copy(), pd.DataFrame()

    ranked = long_df.copy()
    ranked["tag_rank"] = ranked.apply(
        lambda row: _compute_tag_rank(
            source_tag=str(row["source_tag"]),
            cfg=mapping[str(row["canonical_field"])],
        ),
        axis=1,
    )
    ranked["form_rank"] = ranked.apply(
        lambda row: (
            mapping[str(row["canonical_field"])].form_priority.index(str(row["form_type"]))
            if str(row["form_type"]) in mapping[str(row["canonical_field"])].form_priority
            else 1_000
        ),
        axis=1,
    )
    ranked["is_component_rank"] = ranked["is_component_tag"].fillna(False).astype(bool).astype(int)
    ranked["filed_date"] = pd.to_datetime(ranked["filed_date"], errors="coerce")
    ranked["accn"] = ranked["accn"].fillna("").astype(str)

    key = ["ticker", "cik", "fyearq", "fqtr", "canonical_field"]
    conflict_counts = (
        ranked.groupby(key, dropna=False)
        .size()
        .reset_index(name="candidate_count")
    )
    conflicts = conflict_counts[conflict_counts["candidate_count"] > 1].copy()
    if not conflicts.empty:
        detail = (
            ranked[key + ["source_tag", "form_type", "filed_date", "accn", "value"]]
            .sort_values(
                key + ["filed_date", "accn"],
                ascending=[True, True, True, True, True, False, False],
                kind="mergesort",
            )
            .groupby(key, dropna=False)
            .head(5)
        )
        conflicts = conflicts.merge(detail, on=key, how="left")

    ranked = ranked.sort_values(
        key + ["is_component_rank", "tag_rank", "form_rank", "filed_date", "accn"],
        ascending=[True, True, True, True, True, True, True, True, False, False],
        kind="mergesort",
    )
    selected = ranked.drop_duplicates(subset=key, keep="first").reset_index(drop=True)
    return selected, conflicts


def build_sec_processed_fundamentals(
    *,
    raw_dir: str | Path = "data/raw/sec/companyfacts",
    mapping_path: str | Path | None = None,
    fiscal_calendar_path: str | Path = "data/reports/sec_fiscal_calendar.csv",
    sec_cik_mapping_path: str | Path = "data/reports/sec_cik_mapping.csv",
    output_dir: str | Path = "data/processed",
    reports_dir: str | Path = "data/reports",
    start_year: int = 2023,
    end_year: int = 2025,
    max_day_delta: int = 30,
) -> dict[str, str]:
    """Build wide processed SEC fundamentals with fiscal-resolved quarters.

    Returns:
        Dictionary containing output artifact paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    long_output = output_dir / f"sec_facts_long_{start_year}_{end_year}.csv"
    unresolved_output = (
        reports_dir / f"sec_fiscal_resolution_unresolved_{start_year}_{end_year}.csv"
    )
    conflicts_output = reports_dir / f"sec_fundamentals_conflicts_{start_year}_{end_year}.csv"
    coverage_output = reports_dir / f"sec_processed_coverage_{start_year}_{end_year}.csv"

    long_df = normalize_sec_facts_long(
        raw_dir=raw_dir,
        mapping_path=mapping_path,
        output_path=long_output,
        fiscal_calendar_path=fiscal_calendar_path,
        start_year=start_year,
        end_year=end_year,
        max_day_delta=max_day_delta,
        unresolved_path=unresolved_output,
    )
    contract = load_sec_metric_contract(path=mapping_path)
    mapping = contract.metrics
    canonical_fields = list(mapping.keys())

    selected, conflicts = _build_selected_quarterly_facts(
        long_df=long_df,
        mapping=mapping,
    )
    conflicts.to_csv(conflicts_output, index=False)

    quarter_key = ["ticker", "cik", "fyearq", "fqtr"]
    if selected.empty:
        quarter_meta = pd.DataFrame(columns=quarter_key)
        value_wide = pd.DataFrame(columns=quarter_key + canonical_fields)
    else:
        quarter_meta = (
            selected.sort_values(
                quarter_key + ["filed_date", "accn"],
                ascending=[True, True, True, True, False, False],
                kind="mergesort",
            )
            .drop_duplicates(subset=quarter_key, keep="first")
            [
                quarter_key
                + [
                    "period_start",
                    "period_end",
                    "filed_date",
                    "form_type",
                    "accn",
                    "fiscal_year_end_mmdd",
                    "fiscal_day_delta",
                ]
            ]
        )
        value_wide = (
            selected.pivot_table(
                index=quarter_key,
                columns="canonical_field",
                values="value",
                aggfunc="first",
            )
            .reset_index()
        )
        value_wide.columns.name = None

    mapped_companies = _load_mapped_companies(sec_cik_mapping_path)
    years = pd.DataFrame(
        [{"fyearq": year, "fqtr": fqtr} for year in range(start_year, end_year + 1) for fqtr in range(1, 5)]
    )
    mapped_companies["_join"] = 1
    years["_join"] = 1
    grid = mapped_companies.merge(years, on="_join", how="inner").drop(columns="_join")

    final = grid.merge(quarter_meta, on=quarter_key, how="left")
    final = final.merge(value_wide, on=quarter_key, how="left")
    for field in canonical_fields:
        if field not in final.columns:
            final[field] = pd.NA

    ordered_columns = (
        ["fyearq", "fqtr", "ticker", "cik", "period_start", "period_end", "filed_date", "form_type", "accn"]
        + canonical_fields
        + ["fiscal_year_end_mmdd", "fiscal_day_delta"]
    )
    final = final[ordered_columns].sort_values(
        ["ticker", "fyearq", "fqtr"],
        kind="mergesort",
    ).reset_index(drop=True)

    year_outputs: dict[str, str] = {}
    coverage_rows: list[dict[str, Any]] = []
    for year in range(start_year, end_year + 1):
        year_df = final[final["fyearq"] == year].copy()
        year_output = output_dir / f"processed_fundamentals_{year}.csv"
        year_df.to_csv(year_output, index=False)
        year_outputs[str(year)] = str(year_output)

        metric_non_null = year_df[canonical_fields].notna().sum()
        coverage_row: dict[str, Any] = {
            "year": year,
            "expected_rows": int(len(mapped_companies) * 4),
            "rows_emitted": int(len(year_df)),
            "rows_with_any_metric": int(year_df[canonical_fields].notna().any(axis=1).sum()),
        }
        for field in canonical_fields:
            coverage_row[f"non_null_{field}"] = int(metric_non_null.get(field, 0))
        coverage_rows.append(coverage_row)

    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(coverage_output, index=False)

    artifacts = {
        "long_output": str(long_output),
        "unresolved_output": str(unresolved_output),
        "conflicts_output": str(conflicts_output),
        "coverage_output": str(coverage_output),
    }
    artifacts.update({f"processed_{year}": path for year, path in year_outputs.items()})
    LOG.info("SEC processed fundamentals build completed: %s", artifacts)
    return artifacts
