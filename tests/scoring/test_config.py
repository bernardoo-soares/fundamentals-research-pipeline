"""Contract tests for the scorecard configuration loader."""

from __future__ import annotations

import pytest
import yaml

from fundamentals_pipeline.scoring.config import (
    DEFAULT_CONFIG_PATH,
    canonical_hash,
    load_scorecard_config,
)

_MINIMAL = {
    "scorer_name": "t",
    "scorer_version": "1",
    "policy": {
        "min_component_coverage": 0.5,
        "low_confidence_coverage": 0.6,
        "max_staleness_quarters": 4,
        "negative_equity_override_points": 100.0,
        "negative_equity_annotation": "n",
    },
    "components": [
        {
            "id": "c1",
            "weight": 1.0,
            "criteria": [
                {
                    "id": "k1",
                    "metric_id": "m1",
                    "ramp": [[0.0, 0], [1.0, 100]],
                    "checklist": {"op": ">", "threshold": 0.5},
                }
            ],
        }
    ],
}


def _write(tmp_path, payload):
    path = tmp_path / "scorecard.yml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _mutate(**overrides):
    """A deep-ish copy of the minimal config with top-level overrides."""
    import copy

    payload = copy.deepcopy(_MINIMAL)
    payload.update(overrides)
    return payload


def test_shipped_config_is_valid():
    """The committed scorecard must load and validate."""
    config = load_scorecard_config()
    assert config.scorer_name == "buffett_heuristic"
    assert len(config.components) == 5
    assert len(config.criteria()) == 23


def test_shipped_config_component_weights_match_the_spec():
    """Weights are the spec's section 7.2 table, and must sum to 1.0."""
    config = load_scorecard_config()
    weights = {c.component_id: c.weight for c in config.components}
    assert weights == {
        "profitability_moat": 0.30,
        "earnings_consistency": 0.20,
        "debt_discipline": 0.25,
        "capital_allocation": 0.15,
        "growth_context": 0.10,
    }
    assert sum(weights.values()) == pytest.approx(1.0)


def test_weights_not_summing_to_one_are_rejected(tmp_path):
    """A silent shortfall would rescale every composite."""
    payload = _mutate()
    payload["components"][0]["weight"] = 0.9
    with pytest.raises(ValueError, match="sum to 1.0"):
        load_scorecard_config(_write(tmp_path, payload))


def test_non_monotonic_ramp_is_rejected(tmp_path):
    """A value falling in two segments would have ambiguous points."""
    payload = _mutate()
    payload["components"][0]["criteria"][0]["ramp"] = [[1.0, 0], [0.0, 100]]
    with pytest.raises(ValueError, match="strictly increasing"):
        load_scorecard_config(_write(tmp_path, payload))


def test_single_anchor_ramp_is_rejected(tmp_path):
    payload = _mutate()
    payload["components"][0]["criteria"][0]["ramp"] = [[1.0, 50]]
    with pytest.raises(ValueError, match="at least two anchors"):
        load_scorecard_config(_write(tmp_path, payload))


def test_out_of_scale_points_are_rejected(tmp_path):
    payload = _mutate()
    payload["components"][0]["criteria"][0]["ramp"] = [[0.0, 0], [1.0, 150]]
    with pytest.raises(ValueError, match="within"):
        load_scorecard_config(_write(tmp_path, payload))


def test_unknown_checklist_operator_is_rejected(tmp_path):
    """A silently-skipped rule would read as a passing one."""
    payload = _mutate()
    payload["components"][0]["criteria"][0]["checklist"] = {
        "op": "!=",
        "threshold": 1,
    }
    with pytest.raises(ValueError, match="unknown checklist operator"):
        load_scorecard_config(_write(tmp_path, payload))


def test_duplicate_criterion_id_is_rejected(tmp_path):
    payload = _mutate()
    payload["components"][0]["criteria"].append(
        dict(payload["components"][0]["criteria"][0])
    )
    payload["components"][0]["weight"] = 1.0
    with pytest.raises(ValueError, match="Duplicate criterion id"):
        load_scorecard_config(_write(tmp_path, payload))


@pytest.mark.parametrize("floor", [0.0, -0.1, 1.5])
def test_out_of_range_coverage_floor_is_rejected(tmp_path, floor):
    payload = _mutate()
    payload["policy"]["min_component_coverage"] = floor
    with pytest.raises(ValueError, match="min_component_coverage"):
        load_scorecard_config(_write(tmp_path, payload))


def test_config_hash_ignores_formatting_but_tracks_values(tmp_path):
    """The hash pins VALUES, not bytes.

    Hashing file bytes would change on a comment or whitespace edit, making the
    reproducibility key useless for telling whether scoring actually changed.
    """
    spaced = tmp_path / "a.yml"
    spaced.write_text(
        "# a comment\n\n" + yaml.safe_dump(_MINIMAL) + "\n", encoding="utf-8"
    )
    compact = tmp_path / "b.yml"
    compact.write_text(yaml.safe_dump(_MINIMAL), encoding="utf-8")
    assert (
        load_scorecard_config(spaced).config_hash
        == load_scorecard_config(compact).config_hash
    )

    changed = _mutate()
    changed["components"][0]["criteria"][0]["checklist"]["threshold"] = 0.6
    assert (
        load_scorecard_config(_write(tmp_path, changed)).config_hash
        != load_scorecard_config(compact).config_hash
    ), "a threshold change must move the hash"


def test_canonical_hash_is_order_independent():
    """Key order in the YAML must not change the reproducibility key."""
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_shipped_config_survives_a_yaml_round_trip(tmp_path):
    """Re-serialising the shipped config must not move its hash."""
    original = load_scorecard_config()
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    round_tripped = tmp_path / "rt.yml"
    round_tripped.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert load_scorecard_config(round_tripped).config_hash == original.config_hash
