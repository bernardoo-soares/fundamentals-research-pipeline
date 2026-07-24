"""Tests for the cross-era reconciliation audit."""

from __future__ import annotations

import pandas as pd
import pytest

from fundamentals_pipeline import __main__ as cli
from fundamentals_pipeline.core.exceptions import CrossEraContradictionError
from fundamentals_pipeline.steps.cross_era_semantic_audit import (
    Verdict,
    load_era_frame,
    reconcile_frames,
    run_cross_era_audit,
)

_N = 40  # comfortably above MIN_OVERLAP_ROWS


def _frames(legacy_values, simfin_values, field="dvy"):
    """Build two era frames sharing keys, repeated to clear the overlap floor."""
    reps = _N // len(legacy_values) + 1
    legacy_values = (list(legacy_values) * reps)[:_N]
    simfin_values = (list(simfin_values) * reps)[:_N]
    key = {
        "ticker": [f"T{i}" for i in range(_N)],
        "year": [2023] * _N,
        "quarter": [4] * _N,
    }
    return (
        pd.DataFrame({**key, field: legacy_values}),
        pd.DataFrame({**key, field: simfin_values}),
    )


def test_agreeing_field_gets_agree_verdict():
    legacy, simfin = _frames([100.0, 200.0, 300.0], [100.0, 200.0, 300.0])
    row = reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]
    assert row["verdict"] == Verdict.AGREE
    assert row["agreement_rate"] == 1.0
    assert row["n_compared"] == _N


def test_unit_error_is_flagged_as_contradiction():
    """A share count where dollars are declared -- the prstkcq defect shape."""
    legacy, simfin = _frames([38.0, 126.0, 87.0], [10114.0, 33925.0, 52079.0])
    row = reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]
    assert row["verdict"] == Verdict.CONTRADICTION
    assert row["magnitude_ratio"] < 0.1


def test_declared_divergence_is_not_a_contradiction():
    """epspxq is declared eras_equivalent=False, so disagreement is expected."""
    legacy, simfin = _frames([1.0, 2.0, 3.0], [9.0, 9.0, 9.0], field="epspxq")
    row = reconcile_frames(legacy, simfin, fields=("epspxq",)).iloc[0]
    assert row["verdict"] == Verdict.DIVERGENT_DECLARED


def test_no_overlap_is_not_reported_as_agreement():
    """Absence of evidence must never be recorded as agreement."""
    legacy = pd.DataFrame(
        {"ticker": ["A"], "year": [2023], "quarter": [4], "dvy": [1.0]}
    )
    simfin = pd.DataFrame(
        {"ticker": ["Z"], "year": [2023], "quarter": [4], "dvy": [1.0]}
    )
    row = reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]
    assert row["verdict"] == Verdict.INSUFFICIENT_OVERLAP
    assert row["agreement_rate"] is None


def test_missing_column_is_insufficient_overlap_not_agreement():
    legacy = pd.DataFrame({"ticker": ["A"], "year": [2023], "quarter": [4]})
    simfin = pd.DataFrame({"ticker": ["A"], "year": [2023], "quarter": [4]})
    row = reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]
    assert row["verdict"] == Verdict.INSUFFICIENT_OVERLAP


def test_sign_flip_is_measured():
    """Legacy gross vs SimFin net equity flow shows up as sign flips."""
    legacy, simfin = _frames([10.0, 10.0], [-10.0, 10.0], field="prstkcy")
    row = reconcile_frames(legacy, simfin, fields=("prstkcy",)).iloc[0]
    assert row["sign_flip_rate"] == pytest.approx(0.5)


def test_tolerance_boundary_counts_as_agreement():
    """A row exactly at the declared tolerance agrees; just beyond does not."""
    legacy, simfin = _frames([100.5], [100.0])  # 0.5% < 1% tolerance
    assert reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]["agreement_rate"] == 1.0
    legacy, simfin = _frames([102.0], [100.0])  # 2% > 1% tolerance
    assert reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]["agreement_rate"] == 0.0


def test_zero_denominator_does_not_leak_inf():
    legacy, simfin = _frames([5.0, 100.0], [0.0, 100.0])
    row = reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]
    assert row["median_rel_diff"] is not None
    assert pd.notna(row["median_rel_diff"])


def test_audit_writes_report_before_raising(tmp_path):
    """A failing run must still leave the evidence on disk."""
    legacy, simfin = _frames([38.0, 126.0, 87.0], [10114.0, 33925.0, 52079.0])
    with pytest.raises(CrossEraContradictionError) as excinfo:
        run_cross_era_audit(
            legacy_frame=legacy,
            simfin_frame=simfin,
            reports_dir=tmp_path,
            year=2023,
            fields=("dvy",),
        )
    report = tmp_path / "cross_era_reconciliation_2023.csv"
    assert report.exists()
    assert "dvy" in excinfo.value.fields
    assert excinfo.value.report_path == str(report)


def test_audit_returns_structured_result_when_clean(tmp_path):
    legacy, simfin = _frames([100.0, 200.0, 300.0], [100.0, 200.0, 300.0])
    result = run_cross_era_audit(
        legacy_frame=legacy,
        simfin_frame=simfin,
        reports_dir=tmp_path,
        year=2023,
        fields=("dvy",),
    )
    assert result["contradiction_count"] == 0
    assert result["fields_compared"] == 1


def test_reconcile_is_deterministic():
    """Same input, same output -- no ordering or clock dependence."""
    legacy, simfin = _frames([100.0, 250.0, 300.0], [100.0, 200.0, 300.0])
    first = reconcile_frames(legacy, simfin, fields=("dvy",))
    second = reconcile_frames(legacy, simfin, fields=("dvy",))
    pd.testing.assert_frame_equal(first, second)


def test_cli_cross_era_audit_invokes_step(monkeypatch, capsys, tmp_path):
    captured: dict[str, object] = {}

    def _fake(**kwargs):
        captured.update(kwargs)
        return {"report_path": "r.csv", "fields_compared": 3, "contradiction_count": 0}

    monkeypatch.setattr(cli, "run_cross_era_audit_from_dirs", _fake)
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "cross-era-audit",
            "--legacy-dir",
            str(tmp_path / "legacy"),
            "--simfin-dir",
            str(tmp_path / "simfin"),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--year",
            "2023",
        ],
    )
    cli.main()

    assert captured["year"] == 2023
    assert "contradiction_count=0" in capsys.readouterr().out


def test_cli_exits_nonzero_on_contradiction(monkeypatch, tmp_path):
    """The exit code lives in the CLI; the library only raises."""

    def _fake(**_kwargs):
        raise CrossEraContradictionError(
            "boom", fields=("dvy",), report_path="r.csv"
        )

    monkeypatch.setattr(cli, "run_cross_era_audit_from_dirs", _fake)
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "cross-era-audit", "--reports-dir", str(tmp_path)],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli.main()
    assert excinfo.value.code == 1


def test_load_era_frame_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="Staged Stage 1 file not found"):
        load_era_frame(tmp_path, 2023)
