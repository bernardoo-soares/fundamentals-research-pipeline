"""Tests for the Stage 1 era resolution policy and publish-boundary merge."""

from __future__ import annotations

import pandas as pd
import pytest

from fundamentals_pipeline.contracts.era_resolution import (
    SourceEra,
    resolve_ticker_year_provider,
)
from fundamentals_pipeline.contracts.stage1_fundamentals_schema import (
    STAGE1_OUTPUT_COLUMNS,
    STAGE1_RAW_COLUMNS,
)
from fundamentals_pipeline.steps.stage1_era_resolution import (
    resolve_era_frames,
    resolve_stage1_era,
)


def _frame(ticker: str, year: int, quarters: list[int], saleq: float) -> pd.DataFrame:
    rows = []
    for quarter in quarters:
        row = {column: 0.0 for column in STAGE1_RAW_COLUMNS}
        row.update(
            {"ticker": ticker, "year": year, "quarter": quarter, "saleq": saleq}
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=list(STAGE1_RAW_COLUMNS))


def test_simfin_wins_when_it_covers_the_ticker():
    """Preferring SimFin keeps its era contiguous; legacy only fills gaps."""
    assert (
        resolve_ticker_year_provider(legacy_quarters=4, simfin_quarters=4)
        == SourceEra.SIMFIN
    )


def test_legacy_fills_tickers_simfin_lacks():
    """This is what recovers BA, C, COP and ~109 others for FY2023."""
    assert (
        resolve_ticker_year_provider(legacy_quarters=4, simfin_quarters=0)
        == SourceEra.LEGACY
    )


def test_incomplete_year_is_not_selected():
    assert resolve_ticker_year_provider(legacy_quarters=2, simfin_quarters=0) is None
    assert resolve_ticker_year_provider(legacy_quarters=0, simfin_quarters=3) is None


def test_partial_simfin_falls_back_to_complete_legacy():
    assert (
        resolve_ticker_year_provider(legacy_quarters=4, simfin_quarters=2)
        == SourceEra.LEGACY
    )


def test_resolution_is_whole_ticker_year_never_mixed():
    """Mixing providers inside a fiscal year would corrupt every flow field,
    because annualization sums four quarters."""
    legacy = _frame("BA", 2023, [1, 2, 3, 4], saleq=1.0)
    simfin = _frame("BA", 2023, [1, 2], saleq=9.0)
    resolved, _ = resolve_era_frames(
        legacy_frame=legacy, simfin_frame=simfin, year=2023
    )
    assert set(resolved["source_era"]) == {SourceEra.LEGACY.value}
    assert (resolved["saleq"] == 1.0).all()
    assert len(resolved) == 4


def test_resolution_records_provenance_per_row():
    legacy = _frame("BA", 2023, [1, 2, 3, 4], saleq=1.0)
    simfin = _frame("KO", 2023, [1, 2, 3, 4], saleq=2.0)
    resolved, decisions = resolve_era_frames(
        legacy_frame=legacy, simfin_frame=simfin, year=2023
    )
    by_ticker = dict(zip(resolved["ticker"], resolved["source_era"], strict=False))
    assert by_ticker["BA"] == SourceEra.LEGACY.value
    assert by_ticker["KO"] == SourceEra.SIMFIN.value
    assert set(decisions["ticker"]) == {"BA", "KO"}


def test_resolved_frame_matches_published_contract():
    legacy = _frame("BA", 2023, [1, 2, 3, 4], saleq=1.0)
    resolved, _ = resolve_era_frames(
        legacy_frame=legacy, simfin_frame=pd.DataFrame(), year=2023
    )
    assert tuple(resolved.columns) == STAGE1_OUTPUT_COLUMNS


def test_ticker_with_no_complete_year_is_absent_not_partial():
    """Never partially fill: an incomplete year is simply not published."""
    legacy = _frame("XYZ", 2023, [1, 2], saleq=1.0)
    resolved, decisions = resolve_era_frames(
        legacy_frame=legacy, simfin_frame=pd.DataFrame(), year=2023
    )
    assert resolved.empty
    assert decisions.iloc[0]["chosen_era"] is None
    assert "no complete year" in decisions.iloc[0]["reason"]


def test_empty_inputs_yield_empty_published_frame():
    resolved, decisions = resolve_era_frames(
        legacy_frame=pd.DataFrame(), simfin_frame=pd.DataFrame(), year=2023
    )
    assert resolved.empty
    assert tuple(resolved.columns) == STAGE1_OUTPUT_COLUMNS
    assert decisions.empty


def test_resolution_is_deterministic():
    legacy = _frame("BA", 2023, [1, 2, 3, 4], saleq=1.0)
    simfin = _frame("KO", 2023, [1, 2, 3, 4], saleq=2.0)
    first, _ = resolve_era_frames(
        legacy_frame=legacy, simfin_frame=simfin, year=2023
    )
    second, _ = resolve_era_frames(
        legacy_frame=legacy, simfin_frame=simfin, year=2023
    )
    pd.testing.assert_frame_equal(first, second)


def test_resolve_stage1_era_writes_published_csv_and_decision_log(tmp_path):
    legacy_dir = tmp_path / "legacy"
    simfin_dir = tmp_path / "simfin"
    legacy_dir.mkdir()
    simfin_dir.mkdir()
    _frame("BA", 2023, [1, 2, 3, 4], saleq=1.0).to_csv(
        legacy_dir / "raw_fundamentals_2023.csv", index=False
    )
    _frame("KO", 2023, [1, 2, 3, 4], saleq=2.0).to_csv(
        simfin_dir / "raw_fundamentals_2023.csv", index=False
    )

    artifacts = resolve_stage1_era(
        legacy_dir=legacy_dir,
        simfin_dir=simfin_dir,
        output_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
        start_year=2023,
        end_year=2023,
    )

    published = pd.read_csv(artifacts["processed_2023"])
    assert tuple(published.columns) == STAGE1_OUTPUT_COLUMNS
    assert set(published["ticker"]) == {"BA", "KO"}
    assert artifacts["rows_by_era"] == {"legacy_compustat": 4, "simfin": 4}

    decisions = pd.read_csv(artifacts["decisions_2023"])
    assert set(decisions["ticker"]) == {"BA", "KO"}


def test_missing_staged_file_is_an_empty_contribution_not_an_error(tmp_path):
    """A provider legitimately covers only part of the horizon."""
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    _frame("BA", 2023, [1, 2, 3, 4], saleq=1.0).to_csv(
        legacy_dir / "raw_fundamentals_2023.csv", index=False
    )

    artifacts = resolve_stage1_era(
        legacy_dir=legacy_dir,
        simfin_dir=tmp_path / "absent",
        output_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
        start_year=2023,
        end_year=2023,
    )
    published = pd.read_csv(artifacts["processed_2023"])
    assert set(published["ticker"]) == {"BA"}


def test_resolve_stage1_era_rejects_inverted_window(tmp_path):
    with pytest.raises(ValueError, match="start_year must be <= end_year"):
        resolve_stage1_era(
            legacy_dir=tmp_path,
            simfin_dir=tmp_path,
            output_dir=tmp_path,
            reports_dir=tmp_path,
            start_year=2024,
            end_year=2023,
        )


def test_cli_stage1_resolve_era_invokes_step(monkeypatch, capsys, tmp_path):
    from fundamentals_pipeline import __main__ as cli

    captured: dict[str, object] = {}

    def _fake(**kwargs):
        captured.update(kwargs)
        return {"rows_by_era": {"legacy_compustat": 4, "simfin": 8}}

    monkeypatch.setattr(cli, "resolve_stage1_era", _fake)
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "stage1-resolve-era",
            "--legacy-dir",
            str(tmp_path / "legacy"),
            "--simfin-dir",
            str(tmp_path / "simfin"),
            "--output-dir",
            str(tmp_path / "processed"),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--start-year",
            "2023",
            "--end-year",
            "2023",
        ],
    )
    cli.main()

    assert captured["start_year"] == 2023
    assert "rows_by_era=" in capsys.readouterr().out
