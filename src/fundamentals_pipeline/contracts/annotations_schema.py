"""Contract for `manual_annotations` — the only table the console writes.

Compute-free.

WHY THIS IS THE ONLY WRITABLE TABLE, AND WHY THAT MATTERS
---------------------------------------------------------
Every other table is derived: rebuildable from the raw inputs plus committed
code, and therefore disposable. This one is not. A note a person typed cannot
be recomputed, so it is the only thing in the warehouse whose loss is
permanent, and the only thing a rebuild must not touch.

Two rules follow, and both are enforced rather than documented:

1. **Nothing derived may read it.** No metric, scorer or valuation may depend
   on an annotation, or the pipeline stops being reproducible from code plus
   raw inputs (AGENTS.md S3.1). A starred company scores exactly what an
   unstarred one does.
2. **A rebuild must preserve it.** `warehouse-rebuild` drops and recreates the
   derived tables; this one is created if absent and otherwise left alone.

FREE TEXT IS STORED VERBATIM
----------------------------
Notes are a person's own words and are never parsed, summarised or
interpreted. The console escapes them when rendering, which is a display
concern; the stored value is exactly what was typed.
"""

from __future__ import annotations

ANNOTATIONS_PIPELINE_VERSION = "annotations-1.0"

ANNOTATIONS_TABLE = "manual_annotations"

MANUAL_ANNOTATIONS_COLUMNS: tuple[str, ...] = (
    "ticker",
    "starred",
    "note",
    "created_at",
    "updated_at",
)

# A note longer than this is refused rather than truncated: silently storing
# half of what someone wrote is worse than declining to store it.
MAX_NOTE_LENGTH = 4000


def create_manual_annotations_ddl() -> str:
    """DDL for `manual_annotations`.

    Grain is one row per ticker: a star and a single running note. Deliberately
    NOT one row per note -- a timestamped note history is a different feature
    with a different grain, and inventing it here would guess at what is
    wanted.

    `created_at` is preserved across updates so "when did I first look at
    this?" survives editing the note.
    """
    return (
        f"CREATE TABLE IF NOT EXISTS {ANNOTATIONS_TABLE} (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  starred BOOLEAN NOT NULL DEFAULT FALSE,\n"
        "  note VARCHAR,\n"
        "  created_at TIMESTAMP,\n"
        "  updated_at TIMESTAMP,\n"
        "  PRIMARY KEY (ticker)\n"
        ")"
    )


class AnnotationRejected(ValueError):
    """An annotation was refused rather than stored in a damaged form."""


def validate_note(note: str | None) -> None:
    """Raise `AnnotationRejected` if a note cannot be stored intact."""
    if note is not None and len(note) > MAX_NOTE_LENGTH:
        raise AnnotationRejected(
            f"Note is {len(note)} characters; the limit is {MAX_NOTE_LENGTH}. "
            "Refused rather than truncated -- storing half of what you wrote "
            "would be worse than not storing it."
        )
