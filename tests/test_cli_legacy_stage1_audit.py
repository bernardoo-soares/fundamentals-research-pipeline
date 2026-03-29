from __future__ import annotations

from trading_bot import __main__ as cli


def test_cli_legacy_stage1_audit_invokes_runner(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "summary_output": "data/reports/legacy_stage1_audit_summary_2006_2010.csv",
        }

    monkeypatch.setattr(cli, "run_legacy_stage1_audit", _fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "trading-bot",
            "legacy-stage1-audit",
            "--start-year",
            "2006",
            "--end-year",
            "2010",
        ],
    )

    cli.main()
    out = capsys.readouterr().out
    assert "summary_output=data/reports/legacy_stage1_audit_summary_2006_2010.csv" in out
    assert captured["start_year"] == 2006
    assert captured["end_year"] == 2010
