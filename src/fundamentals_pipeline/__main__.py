"""Command-line interface entrypoint for trading bot pipeline stages."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core.logging import configure_logging, get_logger
from .core.settings import get_settings
from .steps.legacy_processed_fundamentals_builder import (
    build_legacy_fundamentals,
    build_legacy_raw_stage1,
)
from .steps.legacy_stage1_output_audit import run_legacy_stage1_audit
from .steps.sec_companyfacts_pipeline import (
    build_sec_cik_mapping,
    build_sec_processed_fundamentals,
    normalize_sec_facts_long,
    run_sec_raw_ingestion,
)
from .steps.sec_submissions_pipeline import (
    build_sec_fiscal_calendar,
    run_sec_submissions_ingestion,
)
from .steps.simfin_raw_fundamentals_builder import build_simfin_raw_fundamentals
from .steps.sp500_universe_builder import build_sp500_current_universe
from .steps.stage1_extension_coverage_audit import run_stage1_extension_coverage_audit

LOG = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Construct CLI parser and all supported subcommands.

    Returns:
        Fully configured `ArgumentParser` instance.
    """
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="fundamentals-pipeline",
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

    legacy_raw_parser = subparsers.add_parser(
        "legacy-raw-stage1",
        help="Build raw-only yearly canonical fundamentals from local legacy CSV files.",
    )
    legacy_raw_parser.add_argument(
        "--universe-path",
        default=str(Path(settings.data_root) / settings.universe_filename),
    )
    legacy_raw_parser.add_argument(
        "--raw-dir",
        default=str(settings.legacy_fundamentals_dir),
    )
    legacy_raw_parser.add_argument(
        "--output-dir",
        default=str(settings.processed_data_dir),
    )
    legacy_raw_parser.add_argument(
        "--reports-dir",
        default=str(settings.reports_data_dir),
    )
    legacy_raw_parser.add_argument("--start-year", type=int, default=2006)
    legacy_raw_parser.add_argument("--end-year", type=int, default=2023)

    simfin_raw_parser = subparsers.add_parser(
        "simfin-raw-fundamentals",
        help="Build yearly raw fundamentals CSVs from SimFin quarterly data.",
    )
    simfin_raw_parser.add_argument(
        "--universe-path",
        default=str(Path(settings.data_root) / settings.universe_filename),
    )
    simfin_raw_parser.add_argument(
        "--output-dir",
        default=str(settings.processed_data_dir),
    )
    simfin_raw_parser.add_argument(
        "--reports-dir",
        default=str(settings.reports_data_dir),
    )
    simfin_raw_parser.add_argument("--start-year", type=int, default=2023)
    simfin_raw_parser.add_argument("--end-year", type=int, default=2025)
    simfin_raw_parser.add_argument(
        "--refresh-quarterly-cache",
        action="store_true",
        help="Refresh SimFin quarterly datasets through the provider even if cache files exist.",
    )
    simfin_raw_parser.add_argument(
        "--quarterly-refresh-days",
        type=int,
        default=0,
        help=(
            "Value passed to SimFin refresh_days for quarterly datasets when "
            "refresh is enabled. Use 0 to force refresh."
        ),
    )

    legacy_audit_parser = subparsers.add_parser(
        "legacy-stage1-audit",
        help="Audit published raw_fundamentals_<year>.csv against legacy source files.",
    )
    legacy_audit_parser.add_argument(
        "--universe-path",
        default=str(Path(settings.data_root) / settings.universe_filename),
    )
    legacy_audit_parser.add_argument(
        "--raw-dir",
        default=str(settings.legacy_fundamentals_dir),
    )
    legacy_audit_parser.add_argument(
        "--processed-dir",
        default=str(settings.processed_data_dir),
    )
    legacy_audit_parser.add_argument(
        "--reports-dir",
        default=str(settings.reports_data_dir),
    )
    legacy_audit_parser.add_argument("--start-year", type=int, default=2006)
    legacy_audit_parser.add_argument("--end-year", type=int, default=2023)

    extension_audit_parser = subparsers.add_parser(
        "stage1-extension-audit",
        help="Audit extension-field coverage in published raw fundamentals CSVs.",
    )
    extension_audit_parser.add_argument(
        "--processed-dir",
        default=str(settings.processed_data_dir),
    )
    extension_audit_parser.add_argument(
        "--reports-dir",
        default=str(settings.reports_data_dir),
    )
    extension_audit_parser.add_argument("--start-year", type=int, default=2006)
    extension_audit_parser.add_argument("--end-year", type=int, default=2025)
    extension_audit_parser.add_argument(
        "--simfin-cache-dir",
        default=str(settings.simfin_data_dir),
    )

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
        default=str(Path("src") / "fundamentals_pipeline" / "contracts" / "sec_metric_mapping.yml"),
    )
    sec_norm_parser.add_argument(
        "--output-path",
        default=str(Path(settings.processed_data_dir) / "sec_facts_long_2023_2025.csv"),
    )
    sec_norm_parser.add_argument("--start-year", type=int, default=2023)
    sec_norm_parser.add_argument("--end-year", type=int, default=2025)
    sec_norm_parser.add_argument("--fiscal-calendar-path", default=None)
    sec_norm_parser.add_argument("--max-day-delta", type=int, default=30)
    sec_norm_parser.add_argument("--unresolved-path", default=None)

    sec_processed_parser = subparsers.add_parser(
        "sec-build-processed",
        help="Build fiscal-resolved processed SEC fundamentals (yearly wide CSVs).",
    )
    sec_processed_parser.add_argument(
        "--raw-dir",
        default=str(Path(settings.raw_data_dir) / "sec" / "companyfacts"),
    )
    sec_processed_parser.add_argument(
        "--mapping-path",
        default=str(Path("src") / "fundamentals_pipeline" / "contracts" / "sec_metric_mapping.yml"),
    )
    sec_processed_parser.add_argument(
        "--fiscal-calendar-path",
        default=str(Path(settings.reports_data_dir) / "sec_fiscal_calendar.csv"),
    )
    sec_processed_parser.add_argument(
        "--sec-cik-mapping-path",
        default=str(Path(settings.reports_data_dir) / "sec_cik_mapping.csv"),
    )
    sec_processed_parser.add_argument(
        "--output-dir",
        default=str(settings.processed_data_dir),
    )
    sec_processed_parser.add_argument(
        "--reports-dir",
        default=str(settings.reports_data_dir),
    )
    sec_processed_parser.add_argument("--start-year", type=int, default=2023)
    sec_processed_parser.add_argument("--end-year", type=int, default=2025)
    sec_processed_parser.add_argument("--max-day-delta", type=int, default=30)

    return parser


def main() -> None:
    """CLI dispatcher that routes commands to pipeline step functions."""
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

    if args.command == "legacy-raw-stage1":
        LOG.info(
            "Running legacy raw Stage 1 build: universe_path=%s raw_dir=%s output_dir=%s "
            "reports_dir=%s start_year=%d end_year=%d",
            args.universe_path,
            args.raw_dir,
            args.output_dir,
            args.reports_dir,
            args.start_year,
            args.end_year,
        )
        artifacts = build_legacy_raw_stage1(
            universe_path=args.universe_path,
            raw_dir=args.raw_dir,
            output_dir=args.output_dir,
            reports_dir=args.reports_dir,
            start_year=args.start_year,
            end_year=args.end_year,
        )
        LOG.info("Legacy raw Stage 1 build completed: %s", artifacts)
        for key, value in artifacts.items():
            print(f"{key}={value}")
        return

    if args.command == "legacy-stage1-audit":
        LOG.info(
            "Running legacy Stage 1 audit: universe_path=%s raw_dir=%s processed_dir=%s "
            "reports_dir=%s start_year=%d end_year=%d",
            args.universe_path,
            args.raw_dir,
            args.processed_dir,
            args.reports_dir,
            args.start_year,
            args.end_year,
        )
        artifacts = run_legacy_stage1_audit(
            universe_path=args.universe_path,
            raw_dir=args.raw_dir,
            processed_dir=args.processed_dir,
            reports_dir=args.reports_dir,
            start_year=args.start_year,
            end_year=args.end_year,
        )
        LOG.info("Legacy Stage 1 audit completed: %s", artifacts)
        for key, value in artifacts.items():
            print(f"{key}={value}")
        return

    if args.command == "stage1-extension-audit":
        LOG.info(
            "Running Stage 1 extension coverage audit: processed_dir=%s reports_dir=%s "
            "start_year=%d end_year=%d simfin_cache_dir=%s",
            args.processed_dir,
            args.reports_dir,
            args.start_year,
            args.end_year,
            args.simfin_cache_dir,
        )
        artifacts = run_stage1_extension_coverage_audit(
            processed_dir=args.processed_dir,
            reports_dir=args.reports_dir,
            start_year=args.start_year,
            end_year=args.end_year,
            simfin_cache_dir=args.simfin_cache_dir,
        )
        LOG.info("Stage 1 extension coverage audit completed: %s", artifacts)
        for key, value in artifacts.items():
            print(f"{key}={value}")
        return

    if args.command == "simfin-raw-fundamentals":
        LOG.info(
            "Running SimFin raw fundamentals build: universe_path=%s output_dir=%s "
            "reports_dir=%s start_year=%d end_year=%d refresh_quarterly=%s "
            "quarterly_refresh_days=%d",
            args.universe_path,
            args.output_dir,
            args.reports_dir,
            args.start_year,
            args.end_year,
            args.refresh_quarterly_cache,
            args.quarterly_refresh_days,
        )
        artifacts = build_simfin_raw_fundamentals(
            universe_path=args.universe_path,
            output_dir=args.output_dir,
            reports_dir=args.reports_dir,
            start_year=args.start_year,
            end_year=args.end_year,
            refresh_quarterly=args.refresh_quarterly_cache,
            quarterly_refresh_days=args.quarterly_refresh_days,
        )
        LOG.info("SimFin raw fundamentals build completed: %s", artifacts)
        for key, value in artifacts.items():
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
            "fiscal_calendar_path=%s start_year=%d end_year=%d max_day_delta=%d unresolved_path=%s",
            args.raw_dir,
            args.mapping_path,
            args.output_path,
            args.fiscal_calendar_path,
            args.start_year,
            args.end_year,
            args.max_day_delta,
            args.unresolved_path,
        )
        df = normalize_sec_facts_long(
            raw_dir=args.raw_dir,
            mapping_path=args.mapping_path,
            output_path=args.output_path,
            fiscal_calendar_path=args.fiscal_calendar_path,
            start_year=args.start_year,
            end_year=args.end_year,
            max_day_delta=args.max_day_delta,
            unresolved_path=args.unresolved_path,
        )
        LOG.info("SEC long normalization completed with %d rows.", len(df))
        print(f"normalized_rows={len(df)}")
        return

    if args.command == "sec-build-processed":
        LOG.info(
            "Running SEC processed build: raw_dir=%s mapping_path=%s fiscal_calendar_path=%s "
            "sec_cik_mapping_path=%s output_dir=%s reports_dir=%s start_year=%d end_year=%d max_day_delta=%d",
            args.raw_dir,
            args.mapping_path,
            args.fiscal_calendar_path,
            args.sec_cik_mapping_path,
            args.output_dir,
            args.reports_dir,
            args.start_year,
            args.end_year,
            args.max_day_delta,
        )
        artifacts = build_sec_processed_fundamentals(
            raw_dir=args.raw_dir,
            mapping_path=args.mapping_path,
            fiscal_calendar_path=args.fiscal_calendar_path,
            sec_cik_mapping_path=args.sec_cik_mapping_path,
            output_dir=args.output_dir,
            reports_dir=args.reports_dir,
            start_year=args.start_year,
            end_year=args.end_year,
            max_day_delta=args.max_day_delta,
        )
        LOG.info("SEC processed build completed: %s", artifacts)
        for key, value in artifacts.items():
            print(f"{key}={value}")
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
