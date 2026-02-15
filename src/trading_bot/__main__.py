"""Command-line interface entrypoint for trading bot pipeline stages."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core.logging import configure_logging, get_logger
from .core.settings import get_settings
from .steps.legacy_fundamentals import build_legacy_fundamentals
from .steps.sec_fundamentals import (
    build_sec_cik_mapping,
    normalize_sec_facts_long,
    run_sec_raw_ingestion,
)
from .steps.sec_submissions import (
    build_sec_fiscal_calendar,
    run_sec_submissions_ingestion,
)
from .steps.universe import build_sp500_current_universe
from .workflows.full_run import run_full_pipeline

LOG = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Construct CLI parser and all supported subcommands.

    Returns:
        Fully configured `ArgumentParser` instance.
    """
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="trading-bot",
        description="S&P 500 universe and legacy fundamentals pipeline.",
    )
    parser.add_argument(
        "--log-level",
        default=settings.log_level,
        help="Runtime log level (for example DEBUG, INFO, WARNING).",
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

    sec_map_parser = subparsers.add_parser(
        "sec-map-cik",
        help="Build SEC ticker-to-CIK mapping for current universe.",
    )
    sec_map_parser.add_argument(
        "--universe-path",
        default=str(Path(settings.data_root) / settings.universe_filename),
    )
    sec_map_parser.add_argument(
        "--output-path",
        default=str(Path(settings.reports_data_dir) / "sec_cik_mapping.csv"),
    )

    sec_ingest_parser = subparsers.add_parser(
        "sec-ingest-raw",
        help="Fetch SEC companyfacts JSON for mapped tickers.",
    )
    sec_ingest_parser.add_argument(
        "--mapping-path",
        default=str(Path(settings.reports_data_dir) / "sec_cik_mapping.csv"),
    )
    sec_ingest_parser.add_argument(
        "--raw-dir",
        default=str(Path(settings.raw_data_dir) / "sec" / "companyfacts"),
    )
    sec_ingest_parser.add_argument(
        "--log-path",
        default=str(Path(settings.reports_data_dir) / "sec_ingestion_log.csv"),
    )
    sec_ingest_parser.add_argument("--run-id", default=None)

    sec_submissions_ingest_parser = subparsers.add_parser(
        "sec-ingest-submissions",
        help="Fetch SEC submissions JSON for mapped tickers.",
    )
    sec_submissions_ingest_parser.add_argument(
        "--mapping-path",
        default=str(Path(settings.reports_data_dir) / "sec_cik_mapping.csv"),
    )
    sec_submissions_ingest_parser.add_argument(
        "--raw-dir",
        default=str(Path(settings.raw_data_dir) / "sec" / "submissions"),
    )
    sec_submissions_ingest_parser.add_argument(
        "--log-path",
        default=str(Path(settings.reports_data_dir) / "sec_submissions_ingestion_log.csv"),
    )
    sec_submissions_ingest_parser.add_argument("--run-id", default=None)

    sec_fiscal_calendar_parser = subparsers.add_parser(
        "sec-build-fiscal-calendar",
        help="Build fiscal calendar table from SEC submissions payloads.",
    )
    sec_fiscal_calendar_parser.add_argument(
        "--submissions-dir",
        default=str(Path(settings.raw_data_dir) / "sec" / "submissions"),
    )
    sec_fiscal_calendar_parser.add_argument(
        "--mapping-path",
        default=str(Path(settings.reports_data_dir) / "sec_cik_mapping.csv"),
    )
    sec_fiscal_calendar_parser.add_argument(
        "--output-path",
        default=str(Path(settings.reports_data_dir) / "sec_fiscal_calendar.csv"),
    )

    sec_norm_parser = subparsers.add_parser(
        "sec-normalize-long",
        help="Normalize SEC companyfacts into long canonical facts (2023-2025).",
    )
    sec_norm_parser.add_argument(
        "--raw-dir",
        default=str(Path(settings.raw_data_dir) / "sec" / "companyfacts"),
    )
    sec_norm_parser.add_argument(
        "--mapping-path",
        default=str(Path("src") / "trading_bot" / "contracts" / "sec_metric_map.yml"),
    )
    sec_norm_parser.add_argument(
        "--output-path",
        default=str(Path(settings.processed_data_dir) / "sec_facts_long_2023_2025.csv"),
    )
    sec_norm_parser.add_argument("--start-year", type=int, default=2023)
    sec_norm_parser.add_argument("--end-year", type=int, default=2025)

    return parser


def main() -> None:
    """CLI dispatcher that routes commands to pipeline step functions."""
    settings = get_settings()
    parser = _build_parser()
    args = parser.parse_args()
    configure_logging(str(args.log_level).upper())
    LOG.info("CLI command received: %s", args.command)

    if args.command == "universe":
        LOG.info(
            "Running universe build: output_dir=%s filename=%s as_of_date=%s",
            args.output_dir,
            args.filename,
            args.as_of_date,
        )
        df = build_sp500_current_universe(
            output_dir=args.output_dir,
            as_of_date=args.as_of_date,
            filename=args.filename,
        )
        LOG.info("Universe build completed with %d rows.", len(df))
        print(f"universe_rows={len(df)}")
        return

    if args.command == "legacy-fundamentals":
        LOG.info(
            "Running legacy fundamentals build: universe_path=%s raw_dir=%s output_dir=%s "
            "start_date=%s end_date=%s canonical_filename=%s",
            args.universe_path,
            args.raw_dir,
            args.output_dir,
            args.start_date,
            args.end_date,
            args.canonical_filename,
        )
        df = build_legacy_fundamentals(
            universe_path=args.universe_path,
            raw_dir=args.raw_dir,
            output_dir=args.output_dir,
            canonical_filename=args.canonical_filename,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        LOG.info("Legacy fundamentals build completed with %d rows.", len(df))
        print(f"canonical_rows={len(df)}")
        return

    if args.command == "full-run":
        LOG.info(
            "Running full pipeline: data_root=%s as_of_date=%s start_date=%s end_date=%s",
            args.data_root,
            args.as_of_date,
            args.start_date,
            args.end_date,
        )
        summary = run_full_pipeline(
            data_root=args.data_root,
            as_of_date=args.as_of_date,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        LOG.info("Full pipeline completed: %s", summary)
        for key, value in summary.items():
            print(f"{key}={value}")
        return

    if args.command == "sec-map-cik":
        LOG.info(
            "Running SEC CIK mapping: universe_path=%s output_path=%s",
            args.universe_path,
            args.output_path,
        )
        df = build_sec_cik_mapping(
            universe_path=args.universe_path,
            output_path=args.output_path,
        )
        LOG.info("SEC CIK mapping completed with %d rows.", len(df))
        print(f"mapping_rows={len(df)}")
        return

    if args.command == "sec-ingest-raw":
        LOG.info(
            "Running SEC raw ingestion: mapping_path=%s raw_dir=%s log_path=%s run_id=%s",
            args.mapping_path,
            args.raw_dir,
            args.log_path,
            args.run_id,
        )
        df = run_sec_raw_ingestion(
            mapping_path=args.mapping_path,
            raw_dir=args.raw_dir,
            log_path=args.log_path,
            run_id=args.run_id,
        )
        LOG.info("SEC raw ingestion completed with %d log rows.", len(df))
        print(f"ingestion_rows={len(df)}")
        return

    if args.command == "sec-normalize-long":
        LOG.info(
            "Running SEC long normalization: raw_dir=%s mapping_path=%s output_path=%s "
            "start_year=%d end_year=%d",
            args.raw_dir,
            args.mapping_path,
            args.output_path,
            args.start_year,
            args.end_year,
        )
        df = normalize_sec_facts_long(
            raw_dir=args.raw_dir,
            mapping_path=args.mapping_path,
            output_path=args.output_path,
            start_year=args.start_year,
            end_year=args.end_year,
        )
        LOG.info("SEC long normalization completed with %d rows.", len(df))
        print(f"normalized_rows={len(df)}")
        return

    if args.command == "sec-ingest-submissions":
        LOG.info(
            "Running SEC submissions ingestion: mapping_path=%s raw_dir=%s log_path=%s run_id=%s",
            args.mapping_path,
            args.raw_dir,
            args.log_path,
            args.run_id,
        )
        df = run_sec_submissions_ingestion(
            mapping_path=args.mapping_path,
            raw_dir=args.raw_dir,
            log_path=args.log_path,
            run_id=args.run_id,
        )
        LOG.info("SEC submissions ingestion completed with %d log rows.", len(df))
        print(f"submissions_ingestion_rows={len(df)}")
        return

    if args.command == "sec-build-fiscal-calendar":
        LOG.info(
            "Running SEC fiscal calendar build: submissions_dir=%s mapping_path=%s output_path=%s",
            args.submissions_dir,
            args.mapping_path,
            args.output_path,
        )
        df = build_sec_fiscal_calendar(
            submissions_dir=args.submissions_dir,
            mapping_path=args.mapping_path,
            output_path=args.output_path,
        )
        LOG.info("SEC fiscal calendar build completed with %d rows.", len(df))
        print(f"fiscal_calendar_rows={len(df)}")
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
