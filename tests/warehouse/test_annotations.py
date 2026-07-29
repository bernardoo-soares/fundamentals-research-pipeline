"""Tests for `manual_annotations`, the only writable table.

The guarantee that matters most is the last one: a rebuild must not destroy
notes. Every other table in the warehouse is derived and costs a re-run to
lose; a note someone typed is gone for good.
"""

from __future__ import annotations

import duckdb
import pytest

from fundamentals_pipeline.contracts.annotations_schema import (
    MAX_NOTE_LENGTH,
    AnnotationRejected,
)
from fundamentals_pipeline.warehouse import annotations


@pytest.fixture()
def warehouse(tmp_path):
    path = tmp_path / "w.duckdb"
    duckdb.connect(str(path)).close()
    return path


def test_an_unannotated_company_returns_a_neutral_annotation(warehouse):
    """Absent and empty are the same to a reader, so the caller never branches."""
    got = annotations.get(warehouse, ticker="KO")
    assert got.ticker == "KO"
    assert got.starred is False
    assert got.note == ""
    assert got.created_at is None


def test_save_then_get_round_trips(warehouse):
    annotations.save(
        warehouse, ticker="KO", starred=True, note="Wide moat; watch the payout."
    )
    got = annotations.get(warehouse, ticker="KO")
    assert got.starred is True
    assert got.note == "Wide moat; watch the payout."


def test_a_note_is_stored_verbatim(warehouse):
    """A person's own words are never parsed, trimmed or reformatted."""
    raw = "  line one\n\nline two — with an em dash & <angle brackets>  "
    annotations.save(warehouse, ticker="KO", starred=False, note=raw)
    assert annotations.get(warehouse, ticker="KO").note == raw


def test_created_at_survives_an_edit(warehouse):
    """'When did I first look at this?' must outlive editing the note."""
    first = annotations.save(warehouse, ticker="KO", starred=True, note="v1")
    second = annotations.save(warehouse, ticker="KO", starred=True, note="v2")
    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    assert second.note == "v2"


def test_an_oversized_note_is_refused_not_truncated(warehouse):
    """Storing half of what someone wrote is worse than not storing it."""
    with pytest.raises(AnnotationRejected, match="Refused rather than truncated"):
        annotations.save(
            warehouse, ticker="KO", starred=True, note="x" * (MAX_NOTE_LENGTH + 1)
        )
    assert annotations.get(warehouse, ticker="KO").note == ""


def test_a_note_at_the_limit_is_accepted(warehouse):
    annotations.save(warehouse, ticker="KO", starred=True, note="x" * MAX_NOTE_LENGTH)
    assert len(annotations.get(warehouse, ticker="KO").note) == MAX_NOTE_LENGTH


def test_unstarring_keeps_the_note(warehouse):
    """A star and a note are separate judgements."""
    annotations.save(warehouse, ticker="KO", starred=True, note="keep me")
    annotations.save(warehouse, ticker="KO", starred=False, note="keep me")
    got = annotations.get(warehouse, ticker="KO")
    assert got.starred is False
    assert got.note == "keep me"
    assert annotations.starred_tickers(warehouse) == frozenset()


def test_clear_removes_the_row(warehouse):
    annotations.save(warehouse, ticker="KO", starred=True, note="gone")
    annotations.clear(warehouse, ticker="KO")
    assert annotations.get(warehouse, ticker="KO").created_at is None


def test_watchlist_returns_only_starred(warehouse):
    annotations.save(warehouse, ticker="KO", starred=True, note="")
    annotations.save(warehouse, ticker="PEP", starred=False, note="not yet")
    assert annotations.starred_tickers(warehouse) == frozenset({"KO"})


def test_ensure_table_is_idempotent(warehouse):
    annotations.ensure_table(warehouse)
    annotations.save(warehouse, ticker="KO", starred=True, note="survive")
    annotations.ensure_table(warehouse)
    assert annotations.get(warehouse, ticker="KO").note == "survive"


# --- The guarantee that matters ---------------------------------------------


def test_carry_annotations_moves_rows_into_a_rebuild(warehouse, tmp_path):
    annotations.save(warehouse, ticker="KO", starred=True, note="do not lose me")
    annotations.save(warehouse, ticker="PEP", starred=False, note="second")

    fresh = tmp_path / "rebuilt.duckdb"
    conn = duckdb.connect(str(fresh))
    carried = annotations.carry_annotations(source=warehouse, destination=conn)
    conn.close()

    assert carried == 2
    assert annotations.get(fresh, ticker="KO").note == "do not lose me"
    assert annotations.starred_tickers(fresh) == frozenset({"KO"})


def test_carry_from_a_warehouse_without_the_table_is_not_an_error(tmp_path):
    """A first build, or a warehouse from before this feature."""
    old = tmp_path / "old.duckdb"
    duckdb.connect(str(old)).close()
    fresh = tmp_path / "new.duckdb"
    conn = duckdb.connect(str(fresh))
    assert annotations.carry_annotations(source=old, destination=conn) == 0
    conn.close()


def test_carry_from_a_nonexistent_warehouse_is_not_an_error(tmp_path):
    fresh = tmp_path / "new.duckdb"
    conn = duckdb.connect(str(fresh))
    assert (
        annotations.carry_annotations(source=tmp_path / "nope.duckdb", destination=conn)
        == 0
    )
    conn.close()


def test_a_full_rebuild_preserves_annotations(tmp_path, write_stage1_year):
    """The whole point: `rebuild_warehouse` os.replace()s the file.

    Without `carry_annotations` this would silently and permanently destroy
    every note and star -- the one loss in this system that no re-run fixes.
    """
    from fundamentals_pipeline.warehouse.rebuild import rebuild_warehouse

    warehouse = tmp_path / "rebuilt.duckdb"
    processed = tmp_path / "processed"
    reports = tmp_path / "reports"
    write_stage1_year(
        processed,
        2024,
        [
            {"ticker": "KO", "year": 2024, "quarter": q, "saleq": 10.0}
            for q in (1, 2, 3, 4)
        ],
    )

    # A first rebuild creates the file; then a note is added by hand.
    rebuild_warehouse(
        processed_dir=processed,
        warehouse_path=warehouse,
        reports_dir=reports,
        start_year=2024,
        end_year=2024,
    )
    annotations.save(
        warehouse, ticker="KO", starred=True, note="survives a rebuild"
    )

    result = rebuild_warehouse(
        processed_dir=processed,
        warehouse_path=warehouse,
        reports_dir=reports,
        start_year=2024,
        end_year=2024,
    )

    assert result["annotations_carried"] == "1"
    survivor = annotations.get(warehouse, ticker="KO")
    assert survivor.starred is True
    assert survivor.note == "survives a rebuild"


# --- Robustness against a locked warehouse ----------------------------------


def test_reading_never_requires_write_access(warehouse, monkeypatch):
    """Viewing the watchlist must not take an exclusive lock.

    An earlier draft called `ensure_table` from every read, so simply opening
    the page needed write access -- and crashed whenever a sync client held
    the file. Reads now open read-only and tolerate a missing table.
    """
    annotations.save(warehouse, ticker="KO", starred=True, note="written once")

    from fundamentals_pipeline.warehouse import connection

    real = connection.open_warehouse

    def refuse_writes(path, read_only=False, **kwargs):
        if not read_only:
            raise AssertionError("a read path asked for write access")
        return real(path, read_only=True, **kwargs)

    monkeypatch.setattr(annotations, "open_warehouse", refuse_writes)
    assert annotations.get(warehouse, ticker="KO").note == "written once"
    assert annotations.starred_tickers(warehouse) == frozenset({"KO"})
    assert len(annotations.watchlist(warehouse)) == 1


def test_a_locked_warehouse_reports_rather_than_tracebacks(warehouse, monkeypatch):
    """A save that cannot take the lock must say so and change nothing."""
    from fundamentals_pipeline.warehouse.annotations import AnnotationStoreBusy

    def busy(path, read_only=False, **kwargs):
        if not read_only:
            raise OSError("file is held by another process")
        from fundamentals_pipeline.warehouse import connection

        return connection.open_warehouse(path, read_only=True, **kwargs)

    monkeypatch.setattr(annotations, "open_warehouse", busy)
    with pytest.raises(AnnotationStoreBusy, match="Nothing was changed"):
        annotations.save(warehouse, ticker="KO", starred=True, note="blocked")


def test_reads_work_before_the_table_has_ever_been_created(warehouse):
    """A fresh warehouse must not need a write just to render the page."""
    assert annotations.get(warehouse, ticker="KO").starred is False
    assert annotations.watchlist(warehouse).empty
    assert annotations.starred_tickers(warehouse) == frozenset()
