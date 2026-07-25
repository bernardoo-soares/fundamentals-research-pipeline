from __future__ import annotations


def test_cli_metrics_quarterly_build_invokes_builder(monkeypatch, capsys) -> None:
    from fundamentals_pipeline import __main__ as cli

    captured: dict[str, object] = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return {
            "metrics_quarterly_rows": 42,
            "metric_count": 9,
            "per_metric_counts": {},
            "reason_code_counts": {"missing_input": 3},
        }

    monkeypatch.setattr(cli, "build_metrics_quarterly", _fake_build)
    monkeypatch.setattr(
        "sys.argv",
        [
            "fundamentals-pipeline",
            "metrics-quarterly-build",
            "--warehouse-path",
            "data/warehouse/research.duckdb",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "metrics_quarterly_rows=42" in out
    assert "metric_count=9" in out
    assert "reason_code_counts=" in out
    assert str(captured["warehouse_path"]) == "data/warehouse/research.duckdb"
