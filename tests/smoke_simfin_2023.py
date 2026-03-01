from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd


def _find_repo_root(start: Path) -> Path:
    """Locate repo root by walking upward until `data/universe_current.csv` exists."""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "data" / "universe_current.csv").exists():
            return candidate
    return start.resolve() if start.is_dir() else start.resolve().parent


def _pick_column(columns: list[str], candidates: list[str]) -> str:
    """Return the first matching column name using case-insensitive matching."""
    direct = {c: c for c in columns}
    lowered = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate in direct:
            return candidate
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    raise ValueError(
        f"Could not find any of {candidates!r} in available columns: {columns!r}"
    )


def _load_universe_tickers(universe_path: Path) -> list[str]:
    df = pd.read_csv(universe_path, dtype=str)
    if "ticker" not in df.columns:
        raise ValueError(f"Universe file missing 'ticker' column: {universe_path}")
    tickers = (
        df["ticker"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    tickers = sorted({ticker for ticker in tickers if ticker})
    if not tickers:
        raise ValueError(f"No tickers found in universe file: {universe_path}")
    return tickers


def _load_key_from_env_file(
    *,
    env_key: str,
    search_start: Path,
) -> str:
    """Best-effort .env loader without extra dependencies.

    Searches current path and its parents for `.env`, then parses simple
    `KEY=VALUE` lines (quotes supported).
    """
    candidates: list[Path] = []
    current = search_start.resolve()
    if current.is_file():
        candidates.append(current)
    else:
        candidates.append(current / ".env")
    for parent in current.parents:
        candidates.append(parent / ".env")

    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if not path.exists() or not path.is_file():
            continue

        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key != env_key:
                continue
            value = value.strip().strip("'").strip('"')
            if value:
                return value
    return ""


def _prepare_statement_frame(
    df: pd.DataFrame,
    *,
    year: int,
) -> pd.DataFrame:
    frame = df.reset_index()
    ticker_col = _pick_column(
        list(frame.columns),
        ["Ticker", "ticker", "Symbol", "symbol"],
    )
    report_date_col = _pick_column(
        list(frame.columns),
        ["Report Date", "report_date", "Date", "date"],
    )
    period_col: str | None = None
    try:
        period_col = _pick_column(
            list(frame.columns),
            ["Fiscal Period", "fiscal_period", "FiscalPeriod"],
        )
    except ValueError:
        period_col = None

    frame[ticker_col] = (
        frame[ticker_col]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    frame[report_date_col] = pd.to_datetime(frame[report_date_col], errors="coerce")
    frame = frame[frame[ticker_col] != ""].copy()
    frame = frame[frame[report_date_col].notna()].copy()
    frame = frame[frame[report_date_col].dt.year == year].copy()

    keep_cols = [ticker_col, report_date_col]
    if period_col is not None:
        keep_cols.append(period_col)
    frame = frame[keep_cols].rename(
        columns={
            ticker_col: "ticker",
            report_date_col: "report_date",
            **({period_col: "fiscal_period"} if period_col is not None else {}),
        }
    )
    return frame


def _load_union_statement_frame(
    *,
    loaders: list[Any],
    year: int,
) -> pd.DataFrame:
    """Load and union multiple SimFin statement families for one period."""
    frames: list[pd.DataFrame] = []
    for loader in loaders:
        raw = loader(variant="quarterly", market="us")
        prepared = _prepare_statement_frame(raw, year=year)
        if not prepared.empty:
            frames.append(prepared)
    if not frames:
        return pd.DataFrame(columns=["ticker", "report_date", "fiscal_period"])
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(subset=["ticker", "report_date", "fiscal_period"])


def _ticker_quarter_counts(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="int64")

    if "fiscal_period" in frame.columns:
        fiscal = frame["fiscal_period"].fillna("").astype(str).str.upper()
        is_quarter = fiscal.str.fullmatch(r"Q[1-4]")
        frame = frame[is_quarter].copy()
        if frame.empty:
            return pd.Series(dtype="int64")
        frame["quarter_key"] = (
            frame["report_date"].dt.year.astype(str)
            + "-"
            + frame["fiscal_period"].astype(str)
        )
    else:
        frame["quarter_key"] = frame["report_date"].dt.to_period("Q").astype(str)

    counts = frame.groupby("ticker")["quarter_key"].nunique()
    return counts.astype("int64")


def _apply_ticker_aliases(
    *,
    counts: pd.Series,
    alias_map: dict[str, str],
) -> tuple[pd.Series, set[str]]:
    """Map coverage from source ticker aliases to requested universe symbols."""
    out = counts.copy()
    applied: set[str] = set()
    for target, source in alias_map.items():
        target_u = str(target).strip().upper()
        source_u = str(source).strip().upper()
        if not target_u or not source_u:
            continue
        if target_u in out.index:
            continue
        if source_u in out.index:
            out.loc[target_u] = int(out.loc[source_u])
            applied.add(target_u)
    return out.astype("int64"), applied


def _statement_summary(
    *,
    name: str,
    counts: pd.Series,
    universe_tickers: list[str],
) -> dict[str, Any]:
    universe_set = set(universe_tickers)
    covered_any = int((counts >= 1).sum())
    covered_4q = int((counts >= 4).sum())
    not_covered = int(len(universe_set) - covered_any)
    return {
        "statement": name,
        "universe_tickers": len(universe_tickers),
        "tickers_with_any_2023_quarter": covered_any,
        "tickers_with_4_or_more_2023_quarters": covered_4q,
        "tickers_with_zero_2023_quarters": not_covered,
        "coverage_any_pct": round(covered_any / len(universe_tickers) * 100.0, 2),
        "coverage_4q_pct": round(covered_4q / len(universe_tickers) * 100.0, 2),
        "median_quarters_per_covered_ticker": float(counts[counts > 0].median())
        if covered_any > 0
        else 0.0,
        "min_quarters_per_covered_ticker": int(counts[counts > 0].min())
        if covered_any > 0
        else 0,
        "max_quarters_per_covered_ticker": int(counts.max()) if covered_any > 0 else 0,
    }


def main() -> int:
    repo_root = _find_repo_root(Path(__file__))

    parser = argparse.ArgumentParser(
        description=(
            "SimFin smoke test for 2023 quarterly fundamentals coverage over "
            "tickers in universe_current.csv."
        )
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("SIMFIN_API_KEY", "").strip(),
        help="SimFin API key. Defaults to env SIMFIN_API_KEY.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help=(
            "Optional path to .env file. If omitted and --api-key is empty, "
            "script auto-searches for .env in current directory and parents."
        ),
    )
    parser.add_argument(
        "--universe-path",
        type=Path,
        default=repo_root / "data" / "universe_current.csv",
        help="Path to universe CSV with ticker column.",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2023,
        help="Fiscal/report year to test (default: 2023).",
    )
    parser.add_argument(
        "--simfin-data-dir",
        type=Path,
        default=repo_root / "data" / "raw" / "vendor" / "simfin_cache",
        help="Local cache dir for SimFin downloads.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "data" / "reports",
        help="Directory to write smoke-test reports.",
    )
    args = parser.parse_args()

    api_key = str(args.api_key or "").strip()
    if not api_key:
        if args.env_file is not None:
            api_key = _load_key_from_env_file(
                env_key="SIMFIN_API_KEY",
                search_start=args.env_file,
            )
        else:
            api_key = _load_key_from_env_file(
                env_key="SIMFIN_API_KEY",
                search_start=Path.cwd(),
            )

    if not api_key:
        print(
            "Missing API key. Provide --api-key, set SIMFIN_API_KEY, or pass --env-file.",
            file=sys.stderr,
        )
        return 2

    try:
        import simfin as sf
    except Exception as exc:
        print(
            "Could not import simfin package. Install with: pip install simfin",
            file=sys.stderr,
        )
        print(f"Import error: {exc}", file=sys.stderr)
        return 2

    universe_tickers = _load_universe_tickers(args.universe_path)

    args.simfin_data_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sf.set_api_key(api_key)
    sf.set_data_dir(str(args.simfin_data_dir))

    default_alias_map = {
        "GOOGL": "GOOG",
        "BRK.B": "BRK-A",
        "BF.B": "BF-A",
        "FOXA": "FOX",
        "NWSA": "NWS",
    }

    print(
        f"Loading SimFin quarterly statements for market=us, year={args.year}, "
        f"universe_tickers={len(universe_tickers)} ..."
    )
    income_2023 = _load_union_statement_frame(
        loaders=[
            sf.load_income,
            sf.load_income_banks,
            sf.load_income_insurance,
        ],
        year=args.year,
    )
    balance_2023 = _load_union_statement_frame(
        loaders=[
            sf.load_balance,
            sf.load_balance_banks,
            sf.load_balance_insurance,
        ],
        year=args.year,
    )
    cashflow_2023 = _load_union_statement_frame(
        loaders=[
            sf.load_cashflow,
            sf.load_cashflow_banks,
            sf.load_cashflow_insurance,
        ],
        year=args.year,
    )

    income_counts_raw = _ticker_quarter_counts(income_2023)
    balance_counts_raw = _ticker_quarter_counts(balance_2023)
    cashflow_counts_raw = _ticker_quarter_counts(cashflow_2023)

    income_counts, income_alias_applied = _apply_ticker_aliases(
        counts=income_counts_raw,
        alias_map=default_alias_map,
    )
    balance_counts, balance_alias_applied = _apply_ticker_aliases(
        counts=balance_counts_raw,
        alias_map=default_alias_map,
    )
    cashflow_counts, cashflow_alias_applied = _apply_ticker_aliases(
        counts=cashflow_counts_raw,
        alias_map=default_alias_map,
    )

    # Restrict counts to current universe to avoid out-of-scope symbols.
    income_counts = income_counts[income_counts.index.isin(universe_tickers)]
    balance_counts = balance_counts[balance_counts.index.isin(universe_tickers)]
    cashflow_counts = cashflow_counts[cashflow_counts.index.isin(universe_tickers)]

    summary = {
        "year": args.year,
        "universe_path": str(args.universe_path),
        "simfin_data_dir": str(args.simfin_data_dir),
        "alias_map_used": default_alias_map,
        "alias_hits": {
            "income": sorted(income_alias_applied),
            "balance": sorted(balance_alias_applied),
            "cashflow": sorted(cashflow_alias_applied),
        },
        "reports": [
            _statement_summary(
                name="income_quarterly",
                counts=income_counts,
                universe_tickers=universe_tickers,
            ),
            _statement_summary(
                name="balance_quarterly",
                counts=balance_counts,
                universe_tickers=universe_tickers,
            ),
            _statement_summary(
                name="cashflow_quarterly",
                counts=cashflow_counts,
                universe_tickers=universe_tickers,
            ),
        ],
    }

    detail = pd.DataFrame({"ticker": universe_tickers})
    detail["income_q_count"] = detail["ticker"].map(income_counts).fillna(0).astype(int)
    detail["balance_q_count"] = (
        detail["ticker"].map(balance_counts).fillna(0).astype(int)
    )
    detail["cashflow_q_count"] = (
        detail["ticker"].map(cashflow_counts).fillna(0).astype(int)
    )
    detail["all_3_statements_have_4q"] = (
        (detail["income_q_count"] >= 4)
        & (detail["balance_q_count"] >= 4)
        & (detail["cashflow_q_count"] >= 4)
    )
    detail["any_statement_missing_2023"] = (
        (detail["income_q_count"] == 0)
        | (detail["balance_q_count"] == 0)
        | (detail["cashflow_q_count"] == 0)
    )

    summary_path = args.output_dir / f"simfin_smoke_summary_{args.year}.json"
    detail_path = args.output_dir / f"simfin_smoke_ticker_coverage_{args.year}.csv"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    detail.to_csv(detail_path, index=False)

    print(f"summary_json={summary_path}")
    print(f"detail_csv={detail_path}")
    for report in summary["reports"]:
        print(
            f"{report['statement']}: "
            f"any={report['tickers_with_any_2023_quarter']}/{report['universe_tickers']} "
            f"({report['coverage_any_pct']}%), "
            f"four_q={report['tickers_with_4_or_more_2023_quarters']}/{report['universe_tickers']} "
            f"({report['coverage_4q_pct']}%)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
