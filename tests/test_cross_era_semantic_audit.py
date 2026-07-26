"""Tests for the cross-era reconciliation audit."""

from __future__ import annotations

import pandas as pd
import pytest

from fundamentals_pipeline import __main__ as cli
from fundamentals_pipeline.contracts.source_families import (
    POOLED_FAMILY,
    SOURCE_FAMILY_COLUMN,
)
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


def _family_frames(spec, field="dvy"):
    """Build era frames whose SimFin side carries a `source_family` column.

    `spec` maps a family name to `(n_rows, n_agreeing)`. Agreeing rows are
    identical on both sides; disagreeing rows are 50% apart, far outside the
    1% tolerance. Used to construct the masking scenario: a pooled rate that
    clears its threshold while one family sits below it.
    """
    tickers, families, legacy_values, simfin_values = [], [], [], []
    index = 0
    for family, (rows, agreeing) in spec.items():
        for position in range(rows):
            tickers.append(f"T{index}")
            families.append(family)
            simfin_values.append(100.0)
            legacy_values.append(100.0 if position < agreeing else 150.0)
            index += 1
    total = len(tickers)
    key = {"ticker": tickers, "year": [2023] * total, "quarter": [4] * total}
    return (
        pd.DataFrame({**key, field: legacy_values}),
        pd.DataFrame({**key, field: simfin_values, SOURCE_FAMILY_COLUMN: families}),
    )


def test_family_below_threshold_raises_even_when_pooled_agrees(tmp_path):
    """The masking regression: a family must be judged on its own rows.

    This is the exact shape that let `oiadpq` (banks 0.000) and then `saleq`
    (banks 0.000 on a passing pooled 0.869) reach the warehouse. Pooled here is
    130/140 = 0.929, clearing dvy's 0.90, while insurance sits at 0.50.
    """
    legacy, simfin = _family_frames({"general": (120, 120), "insurance": (20, 10)})
    with pytest.raises(CrossEraContradictionError) as error:
        run_cross_era_audit(
            legacy_frame=legacy,
            simfin_frame=simfin,
            reports_dir=tmp_path,
            year=2023,
            fields=("dvy",),
        )
    assert error.value.fields == ("dvy",)
    report = pd.read_csv(tmp_path / "cross_era_reconciliation_2023.csv")
    pooled = report[report[SOURCE_FAMILY_COLUMN] == POOLED_FAMILY].iloc[0]
    insurance = report[report[SOURCE_FAMILY_COLUMN] == "insurance"].iloc[0]
    assert pooled["verdict"] == Verdict.AGREE, "pooled behaviour must be unchanged"
    assert insurance["verdict"] == Verdict.CONTRADICTION


def test_family_rows_carry_a_verdict():
    """Per-family rows previously carried `verdict = None` by design."""
    legacy, simfin = _family_frames({"general": (30, 30), "insurance": (30, 30)})
    report = reconcile_frames(legacy, simfin, fields=("dvy",))
    families = report[report[SOURCE_FAMILY_COLUMN] != POOLED_FAMILY]
    assert len(families) == 2
    assert families["verdict"].notna().all()
    assert set(families["verdict"]) == {Verdict.AGREE}


def test_family_below_the_overlap_floor_does_not_raise(tmp_path):
    """An unmeasurable family reports insufficient_overlap and never fails.

    A family whose data was deliberately nulled (banks `saleq`, n=0) must not
    raise -- there is nothing to compare, which is the correct outcome, not a
    contradiction.
    """
    legacy, simfin = _family_frames({"general": (120, 120), "insurance": (5, 0)})
    result = run_cross_era_audit(
        legacy_frame=legacy,
        simfin_frame=simfin,
        reports_dir=tmp_path,
        year=2023,
        fields=("dvy",),
    )
    assert result["contradiction_count"] == 0
    report = pd.read_csv(tmp_path / "cross_era_reconciliation_2023.csv")
    insurance = report[report[SOURCE_FAMILY_COLUMN] == "insurance"].iloc[0]
    assert insurance["verdict"] == Verdict.INSUFFICIENT_OVERLAP


def test_contradiction_details_name_the_failing_family(tmp_path):
    """Attribution must be diagnosable: which family failed, not just which field."""
    legacy, simfin = _family_frames({"general": (120, 120), "insurance": (20, 10)})
    with pytest.raises(CrossEraContradictionError):
        run_cross_era_audit(
            legacy_frame=legacy,
            simfin_frame=simfin,
            reports_dir=tmp_path,
            year=2023,
            fields=("dvy",),
        )
    report = pd.read_csv(tmp_path / "cross_era_reconciliation_2023.csv")
    failing = report[report["verdict"] == Verdict.CONTRADICTION]
    assert list(failing[SOURCE_FAMILY_COLUMN]) == ["insurance"]


def test_contradiction_fields_are_deduplicated_across_rows(tmp_path):
    """A field failing both pooled and per-family must be named once."""
    legacy, simfin = _family_frames({"general": (60, 0), "insurance": (60, 0)})
    with pytest.raises(CrossEraContradictionError) as error:
        run_cross_era_audit(
            legacy_frame=legacy,
            simfin_frame=simfin,
            reports_dir=tmp_path,
            year=2023,
            fields=("dvy",),
        )
    assert error.value.fields == ("dvy",)
    result_details = pd.read_csv(tmp_path / "cross_era_reconciliation_2023.csv")
    failing = result_details[result_details["verdict"] == Verdict.CONTRADICTION]
    assert len(failing) == 3, "pooled + both families all fail"


def test_declared_family_override_suppresses_only_its_own_family():
    """A declared override must scope to its family, not the field.

    `saleq` declares insurance at 0.50. An insurance family at 0.60 must pass
    while a general family at the same rate still fails against the 0.80
    field-level threshold -- otherwise the override would silently relax the
    field everywhere, which is the muting failure mode the contract guards.
    """
    legacy, simfin = _family_frames(
        {"general": (20, 12), "insurance": (20, 12)}, field="saleq"
    )
    report = reconcile_frames(legacy, simfin, fields=("saleq",)).set_index(
        SOURCE_FAMILY_COLUMN
    )
    assert report.loc["insurance", "agreement_rate"] == 0.60
    assert report.loc["general", "agreement_rate"] == 0.60
    assert report.loc["insurance", "verdict"] == Verdict.AGREE
    assert report.loc["general", "verdict"] == Verdict.CONTRADICTION


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
    assert result["contradiction_details"] == ()


def test_result_attributes_each_contradiction_to_its_family(tmp_path):
    """`contradiction_details` is the diagnosable half of the result contract.

    `contradiction_fields` alone cannot distinguish a whole-field divergence
    from a single-family one, which is the distinction PRs #9 and #10 turned on.
    """
    legacy, simfin = _family_frames({"general": (120, 120), "insurance": (20, 10)})
    with pytest.raises(CrossEraContradictionError):
        run_cross_era_audit(
            legacy_frame=legacy,
            simfin_frame=simfin,
            reports_dir=tmp_path,
            year=2023,
            fields=("dvy",),
        )
    # Re-run against a clean frame to inspect the returned mapping directly.
    legacy, simfin = _family_frames({"general": (60, 60), "insurance": (60, 60)})
    result = run_cross_era_audit(
        legacy_frame=legacy,
        simfin_frame=simfin,
        reports_dir=tmp_path,
        year=2023,
        fields=("dvy",),
    )
    assert result["contradiction_details"] == ()
    assert result["fields_compared"] == 1, "pooled row count, not total rows"


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


def test_ytd_fields_are_compared_at_q4_only():
    """Legacy YTD accumulates; SimFin broadcasts the annual total.

    Comparing Q1-Q3 would fabricate a contradiction. Only Q4 represents the
    same full-year quantity in both conventions -- and it is the value
    annualization consumes.
    """
    n = 30
    key = {
        "ticker": [f"T{i}" for i in range(n) for _ in range(4)],
        "year": [2023] * (4 * n),
        "quarter": [1, 2, 3, 4] * n,
    }
    # legacy accumulates to 7952; simfin repeats 7952 in every quarter
    legacy = pd.DataFrame({**key, "dvy": [101.0, 2089.0, 4078.0, 7952.0] * n})
    simfin = pd.DataFrame({**key, "dvy": [7952.0] * (4 * n)})

    row = reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]
    assert row["n_compared"] == n  # Q4 rows only, not 4*n
    assert row["agreement_rate"] == 1.0
    assert row["verdict"] == Verdict.AGREE


def test_point_in_time_fields_use_all_quarters():
    """Only YTD fields get the Q4 restriction."""
    n = 30
    key = {
        "ticker": [f"T{i}" for i in range(n) for _ in range(4)],
        "year": [2023] * (4 * n),
        "quarter": [1, 2, 3, 4] * n,
    }
    legacy = pd.DataFrame({**key, "atq": [1.0] * (4 * n)})
    simfin = pd.DataFrame({**key, "atq": [1.0] * (4 * n)})
    row = reconcile_frames(legacy, simfin, fields=("atq",)).iloc[0]
    assert row["n_compared"] == 4 * n


def test_zero_denominator_rows_count_against_agreement():
    """Regression: rows where SimFin reports 0 and legacy reports a real
    value used to be dropped from the rate, so a field could disagree on most
    of the corpus and still score AGREE."""
    n = 40
    key = {"ticker": [f"T{i}" for i in range(n)], "year": [2023] * n, "quarter": [4] * n}
    # 60% of rows: legacy has a value, SimFin reports exactly zero
    legacy_vals = [100.0] * 24 + [50.0] * 16
    simfin_vals = [0.0] * 24 + [50.0] * 16
    legacy = pd.DataFrame({**key, "dvy": legacy_vals})
    simfin = pd.DataFrame({**key, "dvy": simfin_vals})

    row = reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]
    assert row["n_compared"] == n
    assert row["agreement_rate"] == pytest.approx(16 / 40)
    assert row["verdict"] == Verdict.CONTRADICTION


def test_both_zero_counts_as_agreement():
    n = 40
    key = {"ticker": [f"T{i}" for i in range(n)], "year": [2023] * n, "quarter": [4] * n}
    legacy = pd.DataFrame({**key, "dvy": [0.0] * n})
    simfin = pd.DataFrame({**key, "dvy": [0.0] * n})
    row = reconcile_frames(legacy, simfin, fields=("dvy",)).iloc[0]
    assert row["agreement_rate"] == 1.0


def test_reconcile_reports_per_family_rows():
    """Pooling hid a 0.000-agreement family inside a 42% field.

    Each family must independently clear MIN_OVERLAP_ROWS (20) so its rate is
    a genuine measurement rather than an insufficient_overlap floor artifact
    -- a family fixture below the floor would fail for the wrong reason.
    """
    general_tickers = [f"G{i}" for i in range(_N // 2)]
    banks_tickers = [f"B{i}" for i in range(_N // 2)]
    tickers = general_tickers + banks_tickers
    legacy = pd.DataFrame(
        {
            "ticker": tickers,
            "year": [2023] * _N,
            "quarter": [1] * _N,
            "oiadpq": [100.0] * _N,
        }
    )
    simfin = pd.DataFrame(
        {
            "ticker": tickers,
            "year": [2023] * _N,
            "quarter": [1] * _N,
            # general agrees exactly; banks disagrees well outside tolerance.
            "oiadpq": [100.0] * len(general_tickers) + [900.0] * len(banks_tickers),
            "source_family": ["general"] * len(general_tickers)
            + ["banks"] * len(banks_tickers),
        }
    )
    report = reconcile_frames(legacy, simfin, fields=("oiadpq",))

    families = dict(
        zip(report["source_family"], report["agreement_rate"], strict=True)
    )
    assert families["all"] == 0.5, "pooled rate still reported"
    assert families["general"] == 1.0
    assert families["banks"] == 0.0


def test_fields_compared_counts_distinct_fields_not_report_rows(tmp_path):
    """Regression: per-family rows must not inflate the operator-facing count.

    `run_cross_era_audit` emits one pooled row per field plus one row per
    SimFin family. `fields_compared` must report the number of distinct
    fields actually compared (1 here), not `len(report)` (which is 1 pooled +
    2 family rows = 3 for this fixture) -- the CLI prints this number to the
    operator, so it must describe what was compared, not how many rows the
    report happens to contain.
    """
    general_tickers = [f"G{i}" for i in range(_N // 2)]
    banks_tickers = [f"B{i}" for i in range(_N // 2)]
    tickers = general_tickers + banks_tickers
    legacy = pd.DataFrame(
        {
            "ticker": tickers,
            "year": [2023] * _N,
            "quarter": [1] * _N,
            "oiadpq": [100.0] * _N,
        }
    )
    simfin = pd.DataFrame(
        {
            "ticker": tickers,
            "year": [2023] * _N,
            "quarter": [1] * _N,
            "oiadpq": [100.0] * len(general_tickers) + [900.0] * len(banks_tickers),
            "source_family": ["general"] * len(general_tickers)
            + ["banks"] * len(banks_tickers),
        }
    )
    result = run_cross_era_audit(
        legacy_frame=legacy,
        simfin_frame=simfin,
        reports_dir=tmp_path,
        year=2023,
        fields=("oiadpq",),
    )
    report = pd.read_csv(tmp_path / "cross_era_reconciliation_2023.csv")
    assert len(report) == 3, "sanity: one pooled row + two family rows"
    assert result["fields_compared"] == 1


def test_reconcile_without_source_family_reports_pooled_only():
    """The column is optional; absence must not break the audit."""
    frame = pd.DataFrame(
        {"ticker": ["AAPL"], "year": [2023], "quarter": [1], "oiadpq": [100.0]}
    )
    report = reconcile_frames(frame, frame, fields=("oiadpq",))
    assert list(report["source_family"]) == ["all"]
