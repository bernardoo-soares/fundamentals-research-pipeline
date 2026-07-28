from __future__ import annotations

import pytest


def _run(monkeypatch, argv, result):
    from fundamentals_pipeline import __main__ as cli

    captured: dict[str, object] = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return result

    monkeypatch.setattr(cli, "build_scores", _fake_build)
    monkeypatch.setattr("sys.argv", argv)
    cli.main()
    return captured


_RESULT = {
    "scores_rows": 8423,
    "score_components_rows": 42115,
    "score_criteria_rows": 193729,
    "null_composites": 12,
    "badge_counts": {"low_confidence": 900},
    "component_exclusions": {"profitability_moat": 357},
    "scorer_name": "buffett_heuristic",
    "scorer_version": "1",
    "config_hash": "abc123",
}


def test_cli_scores_build_invokes_builder(monkeypatch, capsys) -> None:
    captured = _run(
        monkeypatch,
        [
            "fundamentals-pipeline",
            "scores-build",
            "--warehouse-path",
            "data/warehouse/research.duckdb",
        ],
        _RESULT,
    )

    out = capsys.readouterr().out
    assert "scores_rows=8423" in out
    assert "null_composites=12" in out
    assert "config_hash=abc123" in out
    assert "component_exclusions=" in out
    assert str(captured["warehouse_path"]) == "data/warehouse/research.duckdb"
    assert captured["config_path"] is None


def test_cli_scores_build_forwards_an_explicit_config(monkeypatch, capsys) -> None:
    captured = _run(
        monkeypatch,
        [
            "fundamentals-pipeline",
            "scores-build",
            "--warehouse-path",
            "data/warehouse/research.duckdb",
            "--config-path",
            "custom_scorecard.yml",
        ],
        _RESULT,
    )

    assert captured["config_path"] == "custom_scorecard.yml"


def test_cli_scores_build_defaults_the_warehouse_path(monkeypatch, capsys) -> None:
    captured = _run(
        monkeypatch, ["fundamentals-pipeline", "scores-build"], _RESULT
    )

    assert str(captured["warehouse_path"]).endswith("research.duckdb")


def test_cli_rejects_an_unknown_scores_flag(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv", ["fundamentals-pipeline", "scores-build", "--nope"]
    )
    from fundamentals_pipeline import __main__ as cli

    with pytest.raises(SystemExit):
        cli.main()
