from __future__ import annotations


def test_cli_warehouse_rebuild_invokes_step(monkeypatch, capsys) -> None:
    from fundamentals_pipeline import __main__ as cli

    captured: dict[str, object] = {}

    def _fake_rebuild(**kwargs):
        captured.update(kwargs)
        return {
            "warehouse_path": "data/warehouse/research.duckdb",
            "health_report_path": "data/reports/warehouse_health_2006_2025.csv",
        }

    monkeypatch.setattr(cli, "rebuild_warehouse", _fake_rebuild)
    monkeypatch.setattr(
        "sys.argv",
        [
            "fundamentals-pipeline",
            "warehouse-rebuild",
            "--processed-dir",
            "data/processed",
            "--warehouse-path",
            "data/warehouse/research.duckdb",
            "--reports-dir",
            "data/reports",
            "--start-year",
            "2006",
            "--end-year",
            "2025",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "warehouse_path=" in out
    assert "health_report_path=" in out
    assert captured["start_year"] == 2006
    assert captured["end_year"] == 2025
