from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "data" / "universe_current.csv").exists():
            return candidate
    return current


def _load_key_from_env_file(search_start: Path) -> str:
    candidates: list[Path] = []
    current = search_start.resolve()
    if current.is_file():
        candidates.append(current)
    else:
        candidates.append(current / ".env")
    candidates.extend(parent / ".env" for parent in current.parents)

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
            if key.strip() != "SIMFIN_API_KEY":
                continue
            value = value.strip().strip("'").strip('"')
            if value:
                return value
    return ""


def _pick_column(columns: list[str], candidates: list[str]) -> str:
    direct = {c: c for c in columns}
    lowered = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate in direct:
            return candidate
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    raise ValueError(f"Missing expected column among: {candidates}")


def _normalize_statement_frame(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.reset_index().copy()
    columns = list(frame.columns)

    ticker_col = _pick_column(columns, ["Ticker", "ticker", "Symbol", "symbol"])
    report_date_col = _pick_column(columns, ["Report Date", "report_date", "Date", "date"])
    fiscal_year_col = _pick_column(columns, ["Fiscal Year", "fiscal_year"])
    fiscal_period_col = _pick_column(columns, ["Fiscal Period", "fiscal_period"])

    frame[ticker_col] = frame[ticker_col].fillna("").astype(str).str.strip().str.upper()
    frame[report_date_col] = pd.to_datetime(frame[report_date_col], errors="coerce")
    frame[fiscal_year_col] = pd.to_numeric(frame[fiscal_year_col], errors="coerce")
    frame[fiscal_period_col] = frame[fiscal_period_col].fillna("").astype(str).str.upper()

    frame = frame.rename(
        columns={
            ticker_col: "ticker",
            report_date_col: "report_date",
            fiscal_year_col: "fiscal_year",
            fiscal_period_col: "fiscal_period",
        }
    )
    return frame


def _load_ticker_statement(
    *,
    ticker: str,
    year: int,
    loaders: list[tuple[str, Callable[..., pd.DataFrame]]],
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for source_name, loader in loaders:
        raw = loader(variant="quarterly", market="us")
        frame = _normalize_statement_frame(raw)
        frame = frame[
            (frame["ticker"] == ticker)
            & (frame["fiscal_year"] == year)
            & (frame["fiscal_period"].isin(["Q1", "Q2", "Q3", "Q4"]))
            & (frame["report_date"].notna())
        ].copy()
        if frame.empty:
            continue
        frame["statement_source"] = source_name
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    # Keep first source by loader order when duplicate quarter rows exist.
    out = out.sort_values(["report_date", "fiscal_period", "statement_source"])
    out = out.drop_duplicates(subset=["ticker", "fiscal_year", "fiscal_period", "report_date"], keep="first")
    return out.reset_index(drop=True)


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    return num.where(den != 0) / den.where(den != 0)


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


@dataclass(frozen=True)
class FieldRule:
    canonical_field: str
    source_statement: str
    source_column: str
    transform: str


def _apply_field_rule(
    *,
    base: pd.DataFrame,
    rule: FieldRule,
) -> pd.Series:
    column = rule.source_column
    if column not in base.columns:
        return pd.Series([float("nan")] * len(base), index=base.index, dtype="float64")
    raw = _to_number(base[column])

    if rule.transform == "direct":
        return raw
    if rule.transform == "negate":
        return -raw
    if rule.transform == "cash_outflow_as_positive":
        # SimFin cash-flow lines are usually negative for outflows.
        # Canonical uses positive spend for capex/buybacks/dividends.
        return (-raw).clip(lower=0)
    if rule.transform == "eps_from_net_income_common_over_basic_shares":
        if "Shares (Basic)" not in base.columns or "Net Income (Common)" not in base.columns:
            return pd.Series([float("nan")] * len(base), index=base.index, dtype="float64")
        return _safe_div(base["Net Income (Common)"], base["Shares (Basic)"])
    raise ValueError(f"Unsupported transform: {rule.transform}")


def main() -> int:
    repo_root = _find_repo_root(Path(__file__))

    parser = argparse.ArgumentParser(
        description=(
            "Fetch one ticker from SimFin free quarterly statements and map to the "
            "canonical fields used in specs/CANONICAL_SCHEMA.md."
        )
    )
    parser.add_argument(
        "--ticker",
        default="AAPL",
        help="Ticker to fetch (default: AAPL).",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2023,
        help="Fiscal year to fetch (default: 2023).",
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
        help="Optional .env path. Used only if --api-key is empty.",
    )
    parser.add_argument(
        "--simfin-data-dir",
        type=Path,
        default=repo_root / "data" / "raw" / "vendor" / "simfin_cache",
        help="Directory for SimFin cache files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "data" / "reports",
        help="Directory for output CSV/JSON files.",
    )
    args = parser.parse_args()

    ticker = str(args.ticker).strip().upper()
    year = int(args.year)

    api_key = str(args.api_key or "").strip()
    if not api_key:
        if args.env_file is not None:
            api_key = _load_key_from_env_file(args.env_file)
        else:
            api_key = _load_key_from_env_file(Path.cwd())
    if not api_key:
        print(
            "Missing API key. Provide --api-key, set SIMFIN_API_KEY, or pass --env-file.",
            file=sys.stderr,
        )
        return 2

    try:
        import simfin as sf
    except Exception as exc:
        print("Could not import simfin package. Install with: pip install simfin", file=sys.stderr)
        print(f"Import error: {exc}", file=sys.stderr)
        return 2

    args.simfin_data_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sf.set_api_key(api_key)
    sf.set_data_dir(str(args.simfin_data_dir))

    print(f"Fetching SimFin quarterly statements for ticker={ticker}, year={year} ...")
    income = _load_ticker_statement(
        ticker=ticker,
        year=year,
        loaders=[
            ("income", sf.load_income),
            ("income_banks", sf.load_income_banks),
            ("income_insurance", sf.load_income_insurance),
        ],
    )
    balance = _load_ticker_statement(
        ticker=ticker,
        year=year,
        loaders=[
            ("balance", sf.load_balance),
            ("balance_banks", sf.load_balance_banks),
            ("balance_insurance", sf.load_balance_insurance),
        ],
    )
    cashflow = _load_ticker_statement(
        ticker=ticker,
        year=year,
        loaders=[
            ("cashflow", sf.load_cashflow),
            ("cashflow_banks", sf.load_cashflow_banks),
            ("cashflow_insurance", sf.load_cashflow_insurance),
        ],
    )

    if income.empty and balance.empty and cashflow.empty:
        print(f"No quarterly rows found for ticker={ticker}, year={year}.", file=sys.stderr)
        if ticker == "APPL":
            print("Did you mean AAPL?", file=sys.stderr)
        return 1

    quarter_key = ["ticker", "fiscal_year", "fiscal_period", "report_date"]
    base = (
        income.merge(balance, on=quarter_key, how="outer", suffixes=("_inc", "_bal"))
        .merge(cashflow, on=quarter_key, how="outer", suffixes=("", "_cf"))
        .sort_values(["report_date", "fiscal_period"])
        .reset_index(drop=True)
    )

    # Canonical fields from specs/CANONICAL_SCHEMA.md (fetch-only + helper).
    rules = [
        FieldRule("saleq", "income", "Revenue", "direct"),
        FieldRule("niq", "income", "Net Income", "direct"),
        FieldRule("oiadpq", "income", "Operating Income (Loss)", "direct"),
        FieldRule("xintq", "income", "Interest Expense, Net", "direct"),
        FieldRule("txtq", "income", "Income Tax (Expense) Benefit, Net", "direct"),
        FieldRule("epspxq", "income", "Net Income (Common)", "eps_from_net_income_common_over_basic_shares"),
        FieldRule("actq", "balance", "Total Current Assets", "direct"),
        FieldRule("lctq", "balance", "Total Current Liabilities", "direct"),
        FieldRule("ppentq", "balance", "Property, Plant & Equipment, Net", "direct"),
        FieldRule("gdwlq", "balance", "Goodwill", "direct"),
        FieldRule("ivltq", "balance", "Long Term Investments & Receivables", "direct"),
        FieldRule("atq", "balance", "Total Assets", "direct"),
        FieldRule("ceqq", "balance", "Total Equity", "direct"),
        FieldRule("dlcq", "balance", "Short Term Debt", "direct"),
        FieldRule("dlttq", "balance", "Long Term Debt", "direct"),
        FieldRule("req", "balance", "Retained Earnings", "direct"),
        FieldRule("tstkq", "balance", "Treasury Stock", "direct"),
        FieldRule("oancfq", "cashflow", "Net Cash from Operating Activities", "direct"),
        FieldRule("prstkcq", "cashflow", "Cash from (Repurchase of) Equity", "cash_outflow_as_positive"),
        FieldRule("capxq", "cashflow", "Change in Fixed Assets & Intangibles", "cash_outflow_as_positive"),
        FieldRule("cheq", "balance", "Cash, Cash Equivalents & Short Term Investments", "direct"),
        FieldRule("dvpq", "cashflow", "Dividends Paid", "cash_outflow_as_positive"),
        FieldRule("cshfdq", "income", "Shares (Diluted)", "direct"),
        FieldRule("oancfy", "cashflow", "Net Cash from Operating Activities", "direct"),
        FieldRule("capxy", "cashflow", "Change in Fixed Assets & Intangibles", "cash_outflow_as_positive"),
        FieldRule("prstkcy", "cashflow", "Cash from (Repurchase of) Equity", "cash_outflow_as_positive"),
        FieldRule("cshoq", "income", "Shares (Basic)", "direct"),
        FieldRule("cshopq", "cashflow", "Cash from (Repurchase of) Equity", "cash_outflow_as_positive"),
    ]

    out = base[quarter_key].copy()
    audit_rows: list[dict[str, object]] = []
    for rule in rules:
        values = _apply_field_rule(base=base, rule=rule)
        out[rule.canonical_field] = values
        for i, row in out.iterrows():
            audit_rows.append(
                {
                    "ticker": row["ticker"],
                    "fiscal_year": row["fiscal_year"],
                    "fiscal_period": row["fiscal_period"],
                    "report_date": row["report_date"],
                    "canonical_field": rule.canonical_field,
                    "value": values.iloc[i],
                    "source_statement": rule.source_statement,
                    "source_column": rule.source_column,
                    "transform": rule.transform,
                    "source_column_present": bool(rule.source_column in base.columns),
                }
            )

    # Simple test ratios (computed locally from canonical fields).
    out["operating_margin"] = _safe_div(out["oiadpq"], out["saleq"])
    out["net_margin"] = _safe_div(out["niq"], out["saleq"])
    out["current_ratio"] = _safe_div(out["actq"], out["lctq"])
    out["debt_to_equity"] = _safe_div(out["dlcq"] + out["dlttq"], out["ceqq"])
    out["roa"] = _safe_div(out["niq"], out["atq"])
    out["roe"] = _safe_div(out["niq"], out["ceqq"])
    out["free_cash_flow"] = _to_number(out["oancfq"]) - _to_number(out["capxq"])

    out = out.sort_values(["report_date", "fiscal_period"]).reset_index(drop=True)
    audit_df = pd.DataFrame(audit_rows).sort_values(
        ["report_date", "fiscal_period", "canonical_field"]
    )

    base_name = f"simfin_{ticker}_{year}"
    quarterly_path = args.output_dir / f"{base_name}_quarterly_canonical.csv"
    audit_path = args.output_dir / f"{base_name}_audit_long.csv"
    summary_path = args.output_dir / f"{base_name}_summary.json"

    out.to_csv(quarterly_path, index=False)
    audit_df.to_csv(audit_path, index=False)

    summary = {
        "ticker": ticker,
        "year": year,
        "rows": int(len(out)),
        "quarters_present": out["fiscal_period"].dropna().astype(str).tolist(),
        "paths": {
            "quarterly_canonical_csv": str(quarterly_path),
            "audit_long_csv": str(audit_path),
        },
        "missing_core_fields": [
            field
            for field in [
                "saleq",
                "niq",
                "actq",
                "lctq",
                "atq",
                "ceqq",
                "oancfq",
                "capxq",
            ]
            if out[field].isna().all()
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"quarterly_csv={quarterly_path}")
    print(f"audit_csv={audit_path}")
    print(f"summary_json={summary_path}")
    display_columns = [
        "ticker",
        "fiscal_year",
        "fiscal_period",
        "report_date",
        "saleq",
        "niq",
        "actq",
        "lctq",
        "atq",
        "ceqq",
        "oancfq",
        "capxq",
        "operating_margin",
        "net_margin",
        "current_ratio",
        "debt_to_equity",
        "roa",
        "roe",
        "free_cash_flow",
    ]
    print(out[display_columns].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
