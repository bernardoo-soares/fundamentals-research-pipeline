"""Ad-hoc coverage script for strict 2025 Q4 SEC filled-value analysis.

This script is intentionally placed under `tests/sec/` as a utility-style
"test script" that can be run directly:

    python tests/sec/test_2025q4_fill_coverage.py

It produces one output CSV with, per mapped company:
1. ticker
2. cik
3. filled_value_count (unique tags with non-empty values)
4. filled_value_names (semicolon-separated tag list)
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


Q4_2025_START = "20251001"
Q4_2025_END = "20251231"


def normalize_cik(cik: str) -> str:
    """Normalize CIK values to 10-digit, zero-padded representation."""
    return str(cik or "").strip().zfill(10)


def is_q4_2025_date_yyyymmdd(value: str) -> bool:
    """Check whether a YYYYMMDD string belongs to calendar 2025 Q4."""
    text = str(value or "").strip()
    return text.isdigit() and len(text) == 8 and Q4_2025_START <= text <= Q4_2025_END


def load_mapping(mapping_path: Path) -> dict[str, str]:
    """Load mapped ticker/CIK pairs from SEC mapping report.

    Args:
        mapping_path: Path to `sec_cik_mapping.csv`.

    Returns:
        Dictionary mapping `cik10 -> ticker` for rows where mapping_status=mapped.
    """
    cik_to_ticker: dict[str, str] = {}
    with mapping_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("mapping_status") or "").strip().lower() != "mapped":
                continue
            ticker = (row.get("ticker") or "").strip().upper()
            cik = normalize_cik(row.get("cik") or "")
            if not ticker or not cik.isdigit():
                continue
            cik_to_ticker[cik] = ticker
    return cik_to_ticker


def load_q4_submissions(sub_path: Path) -> dict[str, str]:
    """Load eligible submissions for strict 2025 Q4 report periods.

    Rule:
    - `sub.period` must be in [20251001, 20251231].

    Args:
        sub_path: Path to `sub.txt`.

    Returns:
        Dictionary mapping `adsh -> cik10` for eligible submissions.
    """
    adsh_to_cik: dict[str, str] = {}
    with sub_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            adsh = (row.get("adsh") or "").strip()
            period = (row.get("period") or "").strip()
            if not adsh or not is_q4_2025_date_yyyymmdd(period):
                continue
            adsh_to_cik[adsh] = normalize_cik(row.get("cik") or "")
    return adsh_to_cik


def collect_company_tag_fills(
    num_path: Path,
    adsh_to_cik: dict[str, str],
    mapped_ciks: set[str],
) -> tuple[dict[str, set[str]], set[str]]:
    """Collect unique filled tags per company for strict 2025 Q4 facts.

    Rules:
    - `num.adsh` must be in eligible Q4 submissions (`sub.period` filtered).
    - `num.ddate` must be in [20251001, 20251231].
    - `num.value` must be non-empty.
    - CIK must exist in mapped CIK set.

    Args:
        num_path: Path to `num.txt`.
        adsh_to_cik: Eligible `adsh -> cik10` map from `sub.txt`.
        mapped_ciks: CIKs available in `sec_cik_mapping.csv` with status mapped.

    Returns:
        Tuple:
        1. `cik -> set(tag)` for tags with filled values.
        2. Set of CIKs found in submissions but missing from mapping file.
    """
    cik_to_tags: dict[str, set[str]] = {}
    unmapped_ciks: set[str] = set()

    with num_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            adsh = (row.get("adsh") or "").strip()
            if adsh not in adsh_to_cik:
                continue

            if not is_q4_2025_date_yyyymmdd(row.get("ddate") or ""):
                continue

            value = (row.get("value") or "").strip()
            if value == "":
                continue

            cik = adsh_to_cik[adsh]
            if cik not in mapped_ciks:
                unmapped_ciks.add(cik)
                continue

            tag = (row.get("tag") or "").strip()
            if not tag:
                continue

            if cik not in cik_to_tags:
                cik_to_tags[cik] = set()
            cik_to_tags[cik].add(tag)

    return cik_to_tags, unmapped_ciks


def build_output_rows(
    cik_to_ticker: dict[str, str],
    cik_to_tags: dict[str, set[str]],
) -> list[dict[str, str | int]]:
    """Build report rows sorted by highest coverage first.

    Args:
        cik_to_ticker: Mapping `cik -> ticker`.
        cik_to_tags: Mapping `cik -> unique filled tags`.

    Returns:
        List of output rows for CSV export.
    """
    rows: list[dict[str, str | int]] = []
    for cik, tags in cik_to_tags.items():
        ticker = cik_to_ticker.get(cik, "")
        sorted_tags = sorted(tags)
        rows.append(
            {
                "ticker": ticker,
                "cik": cik,
                "filled_value_count": len(sorted_tags),
                "filled_value_names": ";".join(sorted_tags),
            }
        )

    rows.sort(key=lambda item: (-int(item["filled_value_count"]), str(item["ticker"])))
    return rows


def write_output(rows: list[dict[str, str | int]], output_path: Path) -> None:
    """Write result rows to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ticker", "cik", "filled_value_count", "filled_value_names"]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(
    cik_to_ticker: dict[str, str],
    rows: list[dict[str, str | int]],
    unmapped_ciks: set[str],
) -> None:
    """Print human-readable summary after report generation."""
    covered = len(rows)
    total_mapped = len(cik_to_ticker)
    missing = total_mapped - covered
    print(f"mapped_companies_total={total_mapped}")
    print(f"companies_with_2025q4_fills={covered}")
    print(f"mapped_companies_without_2025q4_fills={missing}")
    print(f"unmapped_ciks_seen_in_q4_submissions={len(unmapped_ciks)}")
    print("top10_by_filled_value_count:")
    for row in rows[:10]:
        print(
            f"  {row['ticker']} ({row['cik']}): "
            f"{row['filled_value_count']} unique filled tags"
        )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the Q4 coverage utility."""
    parser = argparse.ArgumentParser(
        description=(
            "Compute strict 2025 Q4 company fill coverage from SEC 2025q4 "
            "sub/num files and mapping report."
        )
    )
    parser.add_argument(
        "--sub-path",
        type=Path,
        default=Path("2025q4/sub.txt"),
        help="Path to SEC sub.txt file.",
    )
    parser.add_argument(
        "--num-path",
        type=Path,
        default=Path("2025q4/num.txt"),
        help="Path to SEC num.txt file.",
    )
    parser.add_argument(
        "--mapping-path",
        type=Path,
        default=Path("data/reports/sec_cik_mapping.csv"),
        help="Path to SEC CIK mapping CSV.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("data/reports/sec_2025q4_company_filled_values.csv"),
        help="Path to output coverage CSV.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the strict 2025 Q4 fill coverage pipeline and emit CSV output."""
    args = parse_args()

    for required_path in (args.sub_path, args.num_path, args.mapping_path):
        if not required_path.exists():
            raise FileNotFoundError(f"Required input file not found: {required_path}")

    cik_to_ticker = load_mapping(args.mapping_path)
    if not cik_to_ticker:
        raise RuntimeError("No mapped CIK rows found in mapping file.")

    adsh_to_cik = load_q4_submissions(args.sub_path)
    if not adsh_to_cik:
        raise RuntimeError("No strict 2025 Q4 submissions found in sub.txt.")

    cik_to_tags, unmapped_ciks = collect_company_tag_fills(
        num_path=args.num_path,
        adsh_to_cik=adsh_to_cik,
        mapped_ciks=set(cik_to_ticker.keys()),
    )
    rows = build_output_rows(cik_to_ticker, cik_to_tags)

    write_output(rows, args.output_path)
    print(f"output_csv={args.output_path}")
    print_summary(cik_to_ticker, rows, unmapped_ciks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
