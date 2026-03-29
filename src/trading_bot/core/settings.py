"""Centralized runtime settings sourced from environment variables.

This module isolates all environment lookups so the rest of the codebase can
operate on a typed `AppSettings` object with deterministic defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_dotenv_candidates() -> list[Path]:
    """Return likely `.env` locations ordered from nearest to fallback."""
    cwd = Path.cwd().resolve()
    candidates = [cwd / ".env", *[parent / ".env" for parent in cwd.parents]]
    repo_root = Path(__file__).resolve().parents[3]
    repo_env = repo_root / ".env"
    if repo_env not in candidates:
        candidates.append(repo_env)
    return candidates


def _load_dotenv_into_environ() -> None:
    """Populate `os.environ` from the first available `.env` file.

    Existing environment variables win over `.env` entries.
    """
    for env_path in _load_dotenv_candidates():
        if not env_path.exists() or not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip("'").strip('"')
        return


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable with fallback to `default`.

    Args:
        name: Environment variable name.
        default: Value returned when the variable is unset.

    Returns:
        Parsed integer value.
    """
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable with fallback to `default`.

    Args:
        name: Environment variable name.
        default: Value returned when the variable is unset.

    Returns:
        Parsed float value.
    """
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


@dataclass(frozen=True)
class AppSettings:
    """Typed container for all runtime configuration values.

    Using a frozen dataclass prevents accidental in-process mutation of settings
    after they are loaded.
    """

    wiki_url: str
    sec_reference_url: str
    sec_data_url: str
    request_timeout_seconds: int
    sec_rate_limit_per_second: float
    sec_max_retries: int
    user_agent: str
    log_level: str
    data_root: Path
    raw_data_dir: Path
    processed_data_dir: Path
    reports_data_dir: Path
    legacy_fundamentals_dir: Path
    simfin_data_dir: Path
    simfin_api_key: str | None
    universe_filename: str
    canonical_legacy_filename: str


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Build and cache application settings from environment variables.

    Returns:
        A singleton `AppSettings` instance for the current process.
    """
    _load_dotenv_into_environ()

    # Resolve root-relative paths first so downstream defaults stay consistent.
    data_root = Path(os.getenv("DATA_ROOT", "data"))
    raw_data_dir = Path(os.getenv("RAW_DATA_DIR", str(data_root / "raw")))
    processed_data_dir = Path(
        os.getenv("PROCESSED_DATA_DIR", str(data_root / "processed"))
    )
    reports_data_dir = Path(
        os.getenv("REPORTS_DATA_DIR", str(data_root / "reports"))
    )
    legacy_fundamentals_dir = Path(
        os.getenv(
            "LEGACY_FUNDAMENTALS_DIR",
            str(data_root / "raw" / "Processed-Fundamentals"),
        )
    )
    simfin_data_dir = Path(
        os.getenv(
            "SIMFIN_DATA_DIR",
            str(data_root / "raw" / "vendor" / "simfin_cache"),
        )
    )

    return AppSettings(
        wiki_url=os.getenv(
            "WIKI_URL",
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        ),
        sec_reference_url=os.getenv(
            "SEC_REFERENCE_URL",
            "https://www.sec.gov/files/company_tickers.json",
        ),
        sec_data_url=os.getenv("SEC_DATA_URL", "https://data.sec.gov"),
        request_timeout_seconds=_env_int("REQUEST_TIMEOUT_SECONDS", 30),
        sec_rate_limit_per_second=_env_float("SEC_RATE_LIMIT_PER_SECOND", 3.0),
        sec_max_retries=_env_int("SEC_MAX_RETRIES", 4),
        user_agent=os.getenv(
            "USER_AGENT",
            "TradingBot/0.2 (research workflow; contact: local-user)",
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        data_root=data_root,
        raw_data_dir=raw_data_dir,
        processed_data_dir=processed_data_dir,
        reports_data_dir=reports_data_dir,
        legacy_fundamentals_dir=legacy_fundamentals_dir,
        simfin_data_dir=simfin_data_dir,
        simfin_api_key=os.getenv("SIMFIN_API_KEY"),
        universe_filename=os.getenv("UNIVERSE_FILENAME", "universe_current.csv"),
        canonical_legacy_filename=os.getenv(
            "CANONICAL_LEGACY_FILENAME",
            "canonical_legacy_q.csv",
        ),
    )
