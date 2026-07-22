from __future__ import annotations


def test_cli_metrics_build_invokes_builder(monkeypatch, capsys) -> None:
    from fundamentals_pipeline import __main__ as cli

    captured: dict[str, object] = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return {"metrics_trend_rows": 42, "metric_count": 9, "per_metric_counts": {}}

    monkeypatch.setattr(cli, "build_metrics_trend", _fake_build)
    monkeypatch.setattr(
        "sys.argv",
        [
            "fundamentals-pipeline",
            "metrics-build",
            "--warehouse-path",
            "data/warehouse/research.duckdb",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "metrics_trend_rows=42" in out
    assert "metric_count=9" in out
    assert str(captured["warehouse_path"]) == "data/warehouse/research.duckdb"
