from __future__ import annotations

import argparse
from pathlib import Path

from trading_bot.config import get_settings
from trading_bot.pipelines import (
    build_legacy_fundamentals,
    build_sp500_current_universe,
    run_full_pipeline,
)


def _build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="trading-bot",
        description="S&P 500 universe and legacy fundamentals pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    universe_parser = subparsers.add_parser(
        "universe",
        help="Build current S&P 500 universe file.",
    )
    universe_parser.add_argument("--as-of-date", default=None)
    universe_parser.add_argument(
        "--output-dir",
        default=str(settings.data_root),
    )
    universe_parser.add_argument(
        "--filename",
        default=settings.universe_filename,
    )

    legacy_parser = subparsers.add_parser(
        "legacy-fundamentals",
        help="Build canonical fundamentals from local legacy CSV files.",
    )
    legacy_parser.add_argument(
        "--universe-path",
        default=str(Path(settings.data_root) / settings.universe_filename),
    )
    legacy_parser.add_argument(
        "--raw-dir",
        default=str(settings.legacy_fundamentals_dir),
    )
    legacy_parser.add_argument(
        "--output-dir",
        default=str(settings.processed_data_dir),
    )
    legacy_parser.add_argument("--start-date", default=None)
    legacy_parser.add_argument("--end-date", default=None)
    legacy_parser.add_argument(
        "--canonical-filename",
        default=settings.canonical_legacy_filename,
    )

    full_run_parser = subparsers.add_parser(
        "full-run",
        help="Run universe build and legacy fundamentals build end-to-end.",
    )
    full_run_parser.add_argument(
        "--data-root",
        default=str(settings.data_root),
    )
    full_run_parser.add_argument("--as-of-date", default=None)
    full_run_parser.add_argument("--start-date", default=None)
    full_run_parser.add_argument("--end-date", default=None)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "universe":
        df = build_sp500_current_universe(
            output_dir=args.output_dir,
            as_of_date=args.as_of_date,
            filename=args.filename,
        )
        print(f"universe_rows={len(df)}")
        return

    if args.command == "legacy-fundamentals":
        df = build_legacy_fundamentals(
            universe_path=args.universe_path,
            raw_dir=args.raw_dir,
            output_dir=args.output_dir,
            canonical_filename=args.canonical_filename,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"canonical_rows={len(df)}")
        return

    if args.command == "full-run":
        summary = run_full_pipeline(
            data_root=args.data_root,
            as_of_date=args.as_of_date,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        for key, value in summary.items():
            print(f"{key}={value}")
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
