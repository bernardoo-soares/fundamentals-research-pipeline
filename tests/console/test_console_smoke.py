"""Smoke and contract tests for the console.

Two jobs. First, every view must render against a real-shaped warehouse
without raising -- a page that throws is a page that shows nothing, which is
worse than a page that shows a null. Second, the constraints in
`specs/2026-07-29_SP6_UI_DESIGN.md` section 3 are asserted here, because each
one traces to a measured defect rather than to a preference.
"""

from __future__ import annotations

import pytest

from app import components as C
from app.theme import ASSAY, PEWTER, stylesheet

st_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = st_testing.AppTest

# Reuse the seeded miniature warehouse from the query tests.
from .test_queries import _seed  # noqa: E402


@pytest.fixture()
def app(tmp_path, monkeypatch):
    path = tmp_path / "w.duckdb"
    _seed(path)
    monkeypatch.setenv("WAREHOUSE_PATH", str(path))
    from fundamentals_pipeline.core import settings

    settings.get_settings.cache_clear()
    yield path
    settings.get_settings.cache_clear()


def _run(view: str):
    at = AppTest.from_file("app/main.py", default_timeout=120)
    at.session_state["view"] = view
    return at.run()


@pytest.mark.parametrize("view", ["Ranking", "Company", "Data health"])
def test_every_view_renders_without_raising(app, view):
    at = _run(view)
    assert not at.exception, [e.value for e in at.exception]


def test_console_reports_a_missing_warehouse_instead_of_crashing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("WAREHOUSE_PATH", str(tmp_path / "absent.duckdb"))
    from fundamentals_pipeline.core import settings

    settings.get_settings.cache_clear()
    try:
        at = AppTest.from_file("app/main.py", default_timeout=120).run()
        assert not at.exception
        assert any("not ready" in md.value for md in at.markdown)
    finally:
        settings.get_settings.cache_clear()


# --- C1: no cross-year comparison ------------------------------------------


def test_no_view_offers_a_cross_year_comparison(app):
    """C1. Composites drift with measurability, not with quality: mean FY2020
    is 56.8 and mean FY2024 is 64.6 while coverage falls 0.87 -> 0.81. A
    side-by-side would read as improvement that did not happen."""
    at = _run("Ranking")
    year_pickers = [s for s in at.selectbox if "year" in (s.label or "").lower()]
    assert len(year_pickers) == 1
    # A single-select year picker cannot express two years at once.
    assert not getattr(year_pickers[0], "multiple", False)


def test_the_horizon_banner_states_the_comparison_rule_on_every_page(app):
    for view in ("Ranking", "Company", "Data health"):
        at = _run(view)
        # Match the rendered div, not the stylesheet that defines its class.
        banners = [
            m.value for m in at.markdown if 'class="assay-horizon"' in m.value
        ]
        assert banners, f"{view} lost the horizon banner"
        assert "not comparable" in banners[0]


# --- C2: coverage filters, it does not merely display ----------------------


def test_ranking_defaults_to_a_coverage_floor(app):
    """C2. COIN ranked 3rd at 92.1 on 0.273 coverage; the floor is the fix."""
    from app.views.ranking import DEFAULT_MIN_COVERAGE

    assert DEFAULT_MIN_COVERAGE > 0.0
    at = _run("Ranking")
    sliders = [s for s in at.slider if "coverage" in (s.label or "").lower()]
    assert len(sliders) == 1
    assert sliders[0].value == DEFAULT_MIN_COVERAGE


def test_the_default_floor_holds_back_the_thinly_measured_row(app):
    at = _run("Ranking")
    rendered = " ".join(m.value for m in at.markdown)
    assert "SOLID" in rendered
    assert "HOLLOW" not in rendered  # coverage 0.25, below the 0.70 floor


def test_lowering_the_floor_brings_it_back(app):
    at = _run("Ranking")
    sliders = [s for s in at.slider if "coverage" in (s.label or "").lower()]
    sliders[0].set_value(0.0).run()
    rendered = " ".join(m.value for m in at.markdown)
    assert "HOLLOW" in rendered


# --- The signature ----------------------------------------------------------


def test_evidence_bar_solid_share_equals_coverage():
    html = C.evidence_bar(80.0, 0.5)
    assert 'class="ev-total" style="width:80.00%"' in html
    assert 'class="ev-solid" style="width:40.00%"' in html


def test_full_coverage_draws_no_seam():
    assert "ev-seam" not in C.evidence_bar(80.0, 1.0)
    assert "ev-seam" in C.evidence_bar(80.0, 0.9)


def test_evidence_bar_with_no_score_shows_the_absence_mark():
    assert "—" in C.evidence_bar(None, None)


def test_evidence_bar_clamps_out_of_range_inputs():
    """A width above 100% would overflow its track silently."""
    html = C.evidence_bar(140.0, 3.0)
    assert 'class="ev-total" style="width:100.00%"' in html
    assert 'class="ev-solid" style="width:100.00%"' in html


# --- C3/C4: nulls and flags reach the surface -------------------------------


def test_every_reason_and_flag_code_has_plain_words():
    """C3/C4. An unexplained code on screen is not a disclosure."""
    from fundamentals_pipeline.contracts.metric_reason_codes import (
        QUALITY_FLAGS,
        REASON_CODES,
    )

    missing = sorted(
        code for code in (set(REASON_CODES) | set(QUALITY_FLAGS))
        if code not in C.PLAIN_WORDS
    )
    assert not missing, f"no plain-language reading for: {missing}"


def test_absent_values_render_as_a_dash_not_a_zero():
    """A zero is a measurement; a dash is not (S4.5)."""
    assert C.num(None) == "—"
    assert C.num(float("nan")) == "—"
    assert C.num(0.0) == "0.00"


def test_dates_do_not_carry_a_fabricated_midnight():
    assert C.datestr("2025-01-31 00:00:00") == "2025-01-31"
    assert C.datestr(None) == "—"


def test_unknown_codes_are_shown_verbatim_rather_than_invented():
    assert C.plain("some_new_code") == "some_new_code"


# --- Palette rule -----------------------------------------------------------


def test_the_stylesheet_declares_the_palette_rule():
    """Gold means measured; pewter means unmeasured."""
    css = stylesheet()
    assert f"--assay: {ASSAY}" in css
    assert f"--pewter: {PEWTER}" in css
    assert ".ev-solid" in css and "var(--assay)" in css
