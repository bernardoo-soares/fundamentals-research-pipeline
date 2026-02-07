from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from trading_bot.config import get_settings

CANONICAL_RAW_FIELDS = [
    "saleq",
    "niq",
    "oiadpq",
    "xintq",
    "txtq",
    "epspxq",
    "actq",
    "lctq",
    "ppentq",
    "gdwlq",
    "ivltq",
    "atq",
    "ceqq",
    "dlcq",
    "dlttq",
    "req",
    "tstkq",
    "oancfq",
    "prstkcq",
]

DERIVED_FIELDS = [
    "operating_margin",
    "net_profit_margin",
    "current_ratio",
    "debt_to_equity",
    "short_term_debt",
    "healthy_long_term_debt",
    "book_value",
    "treasury_adjusted_debt_to_equity",
    "share_repurchases",
    "retained_earnings_growth",
    "roa",
    "roe",
]


def _normalize_ticker(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    return text


def _coerce_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    safe_denominator = denominator.where(denominator != 0)
    return numerator / safe_denominator


def _load_universe_tickers(universe_path: str | Path) -> set[str]:
    df = pd.read_csv(universe_path, dtype=str)
    if "ticker" not in df.columns:
        raise ValueError(f"Universe file '{universe_path}' is missing 'ticker' column.")
    return {
        ticker
        for ticker in (_normalize_ticker(value) for value in df["ticker"].tolist())
        if ticker is not None
    }


def _legacy_input_columns() -> set[str]:
    return {
        "tic",
        "datadate",
        "fyearq",
        "fqtr",
        "tstkcq",
        "tstkq",
        "cshopq",
        "prstkcy",
        *CANONICAL_RAW_FIELDS,
    }


def _coerce_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _load_legacy_file(path: Path, ticker_fallback: str) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=lambda column: column in _legacy_input_columns())
    if df.empty:
        return pd.DataFrame()

    if "tic" in df.columns:
        df["ticker"] = df["tic"].map(_normalize_ticker).fillna(ticker_fallback)
    else:
        df["ticker"] = ticker_fallback

    if "tstkq" not in df.columns and "tstkcq" in df.columns:
        df["tstkq"] = df["tstkcq"]

    if "prstkcq" not in df.columns:
        if "cshopq" in df.columns:
            df["prstkcq"] = df["cshopq"]
        elif "prstkcy" in df.columns:
            df["prstkcq"] = pd.to_numeric(df["prstkcy"], errors="coerce") / 4.0
        else:
            df["prstkcq"] = pd.NA

    if "datadate" in df.columns:
        df["period_end"] = pd.to_datetime(df["datadate"], errors="coerce")
    else:
        df["period_end"] = pd.NaT

    df = _coerce_numeric_columns(df, ["fyearq", "fqtr", *CANONICAL_RAW_FIELDS])

    if "fyearq" not in df.columns:
        df["fyearq"] = pd.NA
    if "fqtr" not in df.columns:
        df["fqtr"] = pd.NA

    has_period_end = df["period_end"].notna()
    df.loc[has_period_end & df["fyearq"].isna(), "fyearq"] = df.loc[
        has_period_end & df["fyearq"].isna(), "period_end"
    ].dt.year
    df.loc[has_period_end & df["fqtr"].isna(), "fqtr"] = df.loc[
        has_period_end & df["fqtr"].isna(), "period_end"
    ].dt.quarter

    df = df.dropna(subset=["ticker", "fyearq", "fqtr"])
    if df.empty:
        return pd.DataFrame()

    df["fyearq"] = df["fyearq"].astype("int64")
    df["fqtr"] = df["fqtr"].astype("int64")
    df["source_system"] = "legacy_processed_fundamentals"
    df["source_tag_map_version"] = "legacy-v1"
    df["filed_date"] = pd.NaT
    df["form_type"] = pd.NA

    for field in CANONICAL_RAW_FIELDS:
        if field not in df.columns:
            df[field] = pd.NA

    keep_columns = [
        "ticker",
        "fyearq",
        "fqtr",
        "period_end",
        "filed_date",
        "form_type",
        "source_system",
        "source_tag_map_version",
        *CANONICAL_RAW_FIELDS,
    ]
    df = df[keep_columns]

    df = df.sort_values(["period_end", "fyearq", "fqtr"])
    df = df.drop_duplicates(subset=["ticker", "fyearq", "fqtr"], keep="last")
    return df


def _apply_date_filter(
    df: pd.DataFrame,
    start_date: date | None,
    end_date: date | None,
) -> pd.DataFrame:
    if start_date is None and end_date is None:
        return df

    filtered = df.copy()
    if "period_end" not in filtered.columns and not {"fyearq", "fqtr"}.issubset(
        filtered.columns
    ):
        return filtered

    if "period_end" in filtered.columns:
        period_dates = pd.to_datetime(filtered["period_end"], errors="coerce")
    else:
        period_dates = pd.Series(pd.NaT, index=filtered.index)

    # Fall back to fiscal year/quarter when period_end is missing.
    if {"fyearq", "fqtr"}.issubset(filtered.columns):
        fq_year = pd.to_numeric(filtered["fyearq"], errors="coerce")
        fq_quarter = pd.to_numeric(filtered["fqtr"], errors="coerce")
        valid_fiscal = fq_year.notna() & fq_quarter.notna()
        if valid_fiscal.any():
            fallback_period = pd.PeriodIndex.from_fields(
                year=fq_year[valid_fiscal].astype("int64"),
                quarter=fq_quarter[valid_fiscal].astype("int64"),
                freq="Q",
            ).to_timestamp(how="end")
            fallback_series = pd.Series(
                fallback_period,
                index=filtered.index[valid_fiscal],
            )
            period_dates.loc[valid_fiscal] = period_dates.loc[valid_fiscal].fillna(
                fallback_series
            )

    if start_date is not None:
        filtered = filtered[period_dates.notna() & (period_dates.dt.date >= start_date)]
        period_dates = period_dates.loc[filtered.index]
    if end_date is not None:
        filtered = filtered[period_dates.notna() & (period_dates.dt.date <= end_date)]

    return filtered


def _compute_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.sort_values(["ticker", "fyearq", "fqtr"]).reset_index(drop=True)

    total_debt = out[["dlcq", "dlttq"]].sum(axis=1, min_count=1)
    out["operating_margin"] = _safe_divide(out["oiadpq"], out["saleq"])
    out["net_profit_margin"] = _safe_divide(out["niq"], out["saleq"])
    out["current_ratio"] = _safe_divide(out["actq"], out["lctq"])
    out["debt_to_equity"] = _safe_divide(total_debt, out["ceqq"])
    out["short_term_debt"] = _safe_divide(out["dlcq"], total_debt)
    out["healthy_long_term_debt"] = _safe_divide(out["dlttq"], out["ceqq"])
    out["book_value"] = out["ceqq"]

    treasury_adjusted_equity = out["ceqq"] - out["tstkq"].abs()
    out["treasury_adjusted_debt_to_equity"] = _safe_divide(
        total_debt,
        treasury_adjusted_equity,
    )

    out["share_repurchases"] = out["prstkcq"]

    out["retained_earnings_growth"] = out.groupby("ticker", sort=False)["req"].transform(
        lambda series: _safe_divide(series, series.shift(4)) - 1.0
    )

    ttm_niq = out.groupby("ticker", sort=False)["niq"].transform(
        lambda series: series.rolling(4, min_periods=4).sum()
    )
    avg4q_assets = out.groupby("ticker", sort=False)["atq"].transform(
        lambda series: series.rolling(4, min_periods=4).mean()
    )
    avg4q_equity = out.groupby("ticker", sort=False)["ceqq"].transform(
        lambda series: series.rolling(4, min_periods=4).mean()
    )
    out["roa"] = _safe_divide(ttm_niq, avg4q_assets)
    out["roe"] = _safe_divide(ttm_niq, avg4q_equity)
    return out


def _write_year_partitions(df: pd.DataFrame, output_dir: Path) -> None:
    for year, frame in df.groupby("fyearq"):
        year = int(year)
        fundamentals_path = output_dir / f"fundamentals_q_{year}.csv"
        ratios_path = output_dir / f"ratios_q_{year}.csv"

        frame.to_csv(fundamentals_path, index=False)

        ratio_frame = frame[
            [
                "ticker",
                "fyearq",
                "fqtr",
                "period_end",
                *DERIVED_FIELDS,
            ]
        ]
        ratio_frame.to_csv(ratios_path, index=False)


def build_legacy_fundamentals(
    universe_path: str | Path = "data/universe_current.csv",
    raw_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    canonical_filename: str | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> pd.DataFrame:
    settings = get_settings()
    tickers = _load_universe_tickers(universe_path)

    resolved_raw_dir = Path(raw_dir) if raw_dir else settings.legacy_fundamentals_dir
    resolved_output_dir = Path(output_dir) if output_dir else settings.processed_data_dir
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    canonical_filename = canonical_filename or settings.canonical_legacy_filename

    if not resolved_raw_dir.exists():
        raise FileNotFoundError(f"Legacy fundamentals directory not found: {resolved_raw_dir}")

    start_date = _coerce_date(start_date)
    end_date = _coerce_date(end_date)

    frames: list[pd.DataFrame] = []
    for path in sorted(resolved_raw_dir.glob("*.csv")):
        ticker = _normalize_ticker(path.stem.split("-")[0])
        if ticker is None or ticker not in tickers:
            continue
        frame = _load_legacy_file(path=path, ticker_fallback=ticker)
        if not frame.empty:
            frames.append(frame)

    if not frames:
        raise RuntimeError(
            "No legacy fundamentals matched the provided universe tickers."
        )

    canonical = pd.concat(frames, ignore_index=True)
    canonical = _apply_date_filter(canonical, start_date=start_date, end_date=end_date)
    canonical = canonical.sort_values(["ticker", "fyearq", "fqtr"]).reset_index(drop=True)
    canonical = canonical.drop_duplicates(subset=["ticker", "fyearq", "fqtr"], keep="last")

    canonical = _compute_derived_metrics(canonical)
    canonical.to_csv(resolved_output_dir / canonical_filename, index=False)
    _write_year_partitions(canonical, resolved_output_dir)
    return canonical
