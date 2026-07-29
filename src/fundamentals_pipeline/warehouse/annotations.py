"""Read and write `manual_annotations` — the console's only write path.

Deliberately the ONLY module in the codebase that opens the warehouse
read-write on the console's behalf. `queries.py` stays read-only and knows
nothing about writing, so "the console cannot write" remains true of every
path except this one, and this one is small enough to read in full.

See `contracts/annotations_schema.py` for why this table is different from
every other table in the warehouse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..contracts.annotations_schema import (
    ANNOTATIONS_TABLE,
    MANUAL_ANNOTATIONS_COLUMNS,
    create_manual_annotations_ddl,
    validate_note,
)
from .connection import open_warehouse


@dataclass(frozen=True)
class Annotation:
    """One company's star and note."""

    ticker: str
    starred: bool
    note: str
    created_at: datetime | None
    updated_at: datetime | None


EMPTY_NOTE = ""


class AnnotationStoreBusy(RuntimeError):
    """The warehouse could not be opened for writing.

    DuckDB takes an exclusive lock to write, so a sync client holding the
    file (Dropbox, OneDrive) or another process with it open will block a
    save. The console reports that and stays usable read-only, rather than
    showing a traceback where a note should be.
    """


def ensure_table(warehouse_path: str | Path) -> None:
    """Create the table if absent; never drop or recreate it.

    Takes a WRITE lock, so it is called only from the write paths. An
    earlier draft called it from every read, which made viewing the
    watchlist require exclusive access and crashed the page whenever a
    sync client held the file.
    """
    try:
        with open_warehouse(Path(warehouse_path), read_only=False) as conn:
            conn.execute(create_manual_annotations_ddl())
    except Exception as error:  # noqa: BLE001 - re-raised as a typed error
        raise AnnotationStoreBusy(
            f"Could not open {warehouse_path} for writing: {error}"
        ) from error


def _table_exists(conn) -> bool:
    """Whether the annotations table has been created yet."""
    return bool(
        conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = ?",
            [ANNOTATIONS_TABLE],
        ).fetchone()[0]
    )


def get(warehouse_path: str | Path, *, ticker: str) -> Annotation:
    """Return one company's annotation, or an empty one if it has none.

    An absent row and an empty note are the same thing to a reader, so this
    returns a neutral `Annotation` rather than None: the caller never has to
    branch on "never annotated" versus "annotation cleared".
    """
    with open_warehouse(Path(warehouse_path), read_only=True) as conn:
        if not _table_exists(conn):
            return Annotation(ticker, False, EMPTY_NOTE, None, None)
        row = conn.execute(
            f"SELECT ticker, starred, note, created_at, updated_at "
            f"FROM {ANNOTATIONS_TABLE} WHERE ticker = ?",
            [ticker],
        ).fetchone()
    if row is None:
        return Annotation(ticker, False, EMPTY_NOTE, None, None)
    return Annotation(row[0], bool(row[1]), row[2] or EMPTY_NOTE, row[3], row[4])


def save(
    warehouse_path: str | Path,
    *,
    ticker: str,
    starred: bool,
    note: str = EMPTY_NOTE,
) -> Annotation:
    """Insert or update one company's annotation.

    `created_at` is preserved on update, so "when did I first look at this?"
    survives editing the note. A note that cannot be stored intact raises
    rather than being truncated.
    """
    validate_note(note)
    now = datetime.now(UTC).replace(tzinfo=None)
    existing = get(warehouse_path, ticker=ticker)
    created = existing.created_at or now

    try:
        with open_warehouse(Path(warehouse_path), read_only=False) as conn:
            conn.execute(create_manual_annotations_ddl())
            conn.execute(
                f"DELETE FROM {ANNOTATIONS_TABLE} WHERE ticker = ?", [ticker]
            )
            conn.execute(
                f"INSERT INTO {ANNOTATIONS_TABLE} "
                "(ticker, starred, note, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [ticker, bool(starred), note, created, now],
            )
    except Exception as error:  # noqa: BLE001 - re-raised as a typed error
        raise AnnotationStoreBusy(
            f"Could not save: {warehouse_path} is open for writing "
            f"elsewhere ({error}). Nothing was changed."
        ) from error
    return Annotation(ticker, bool(starred), note, created, now)


def clear(warehouse_path: str | Path, *, ticker: str) -> None:
    """Remove one company's annotation entirely."""
    try:
        with open_warehouse(Path(warehouse_path), read_only=False) as conn:
            conn.execute(create_manual_annotations_ddl())
            conn.execute(
                f"DELETE FROM {ANNOTATIONS_TABLE} WHERE ticker = ?", [ticker]
            )
    except Exception as error:  # noqa: BLE001 - re-raised as a typed error
        raise AnnotationStoreBusy(
            f"Could not remove: {warehouse_path} is open for writing "
            f"elsewhere ({error}). Nothing was changed."
        ) from error


def watchlist(warehouse_path: str | Path) -> pd.DataFrame:
    """Every starred company, most recently updated first."""
    with open_warehouse(Path(warehouse_path), read_only=True) as conn:
        if not _table_exists(conn):
            return pd.DataFrame(columns=list(MANUAL_ANNOTATIONS_COLUMNS))
        return conn.execute(
            f"SELECT ticker, starred, note, created_at, updated_at "
            f"FROM {ANNOTATIONS_TABLE} WHERE starred "
            "ORDER BY updated_at DESC, ticker"
        ).fetchdf()


def starred_tickers(warehouse_path: str | Path) -> frozenset[str]:
    """The starred set, for marking rows elsewhere in the console."""
    frame = watchlist(warehouse_path)
    return frozenset(frame["ticker"].tolist()) if not frame.empty else frozenset()


def carry_annotations(*, source: str | Path, destination) -> int:
    """Copy annotations from an existing warehouse into a rebuild in progress.

    `rebuild_warehouse` builds into a temp file and `os.replace`s it over the
    old one. Every other table survives that because it is derived and can be
    rebuilt; this one cannot, so without this step a rebuild would silently and
    permanently destroy every note and star.

    `destination` is the open connection to the temp warehouse. Returns the
    number of rows carried. A source with no annotations table -- a first
    build, or a warehouse from before this feature -- carries nothing and is
    not an error.
    """
    destination.execute(create_manual_annotations_ddl())

    path = Path(source)
    if not path.exists():
        return 0

    with open_warehouse(path, read_only=True) as old:
        present = old.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [ANNOTATIONS_TABLE],
        ).fetchone()[0]
        if not present:
            return 0
        rows = old.execute(
            f"SELECT ticker, starred, note, created_at, updated_at "
            f"FROM {ANNOTATIONS_TABLE}"
        ).fetchall()

    for row in rows:
        destination.execute(
            f"INSERT INTO {ANNOTATIONS_TABLE} "
            "(ticker, starred, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            list(row),
        )
    return len(rows)
