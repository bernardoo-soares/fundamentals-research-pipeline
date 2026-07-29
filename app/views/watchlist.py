"""Page 5 — watchlist.

The only page that writes. Everything it stores is a person's own judgement,
which is why it is stored verbatim and why nothing derived may read it: a
starred company scores exactly what an unstarred one does.
"""

from __future__ import annotations

import html

import streamlit as st

from fundamentals_pipeline.contracts.annotations_schema import (
    MAX_NOTE_LENGTH,
    AnnotationRejected,
)
from fundamentals_pipeline.warehouse import annotations
from fundamentals_pipeline.warehouse.annotations import AnnotationStoreBusy

from .. import components as C


def render(warehouse_path, ranked) -> None:
    """Draw the watchlist and the star/note editor."""
    tickers = ranked["ticker"].tolist()
    names = dict(
        zip(ranked["ticker"], ranked["company_name"], strict=False)
    )

    with st.sidebar:
        C.eyebrow("Annotate")
        current = st.session_state.get("ticker")
        index = tickers.index(current) if current in tickers else 0
        chosen = st.selectbox("Company", tickers, index=index)

    existing = annotations.get(warehouse_path, ticker=chosen)
    label = names.get(chosen)
    subtitle = "" if C._is_absent(label) else str(label)

    st.markdown(
        f'<div class="assay-wordmark" style="font-size:28px">'
        f"{html.escape(chosen)}</div>"
        f'<div class="assay-tagline">{html.escape(subtitle)}</div>',
        unsafe_allow_html=True,
    )

    starred = st.checkbox("On the watchlist", value=existing.starred)
    note = st.text_area(
        "Note",
        value=existing.note,
        height=140,
        max_chars=MAX_NOTE_LENGTH,
        placeholder="What you concluded, and what would change your mind.",
    )

    saved, cleared = st.columns([1, 1])
    with saved:
        if st.button("Save", type="primary", width="stretch"):
            try:
                annotations.save(
                    warehouse_path, ticker=chosen, starred=starred, note=note
                )
            except AnnotationRejected as error:
                # Refused, not truncated: storing half of what someone wrote
                # is worse than declining to store it.
                st.error(str(error))
            except AnnotationStoreBusy as error:
                # DuckDB writes take an exclusive lock, so a sync client
                # holding the file blocks a save. Say so plainly; nothing
                # was changed.
                st.error(str(error))
            else:
                st.success(f"Saved for {chosen}.")
    with cleared:
        if st.button("Remove entirely", width="stretch"):
            try:
                annotations.clear(warehouse_path, ticker=chosen)
            except AnnotationStoreBusy as error:
                st.error(str(error))
            else:
                st.success(f"Removed {chosen}.")

    if existing.created_at is not None:
        st.markdown(
            f'<div class="stat-note">First noted '
            f"{C.datestr(existing.created_at)} · last edited "
            f"{C.datestr(existing.updated_at)}</div>",
            unsafe_allow_html=True,
        )

    C.eyebrow("On the watchlist")
    frame = annotations.watchlist(warehouse_path)
    if frame.empty:
        C.absent_block(
            "Nothing starred yet",
            "Tick 'On the watchlist' above to add a company.",
        )
        return

    for _, row in frame.iterrows():
        ticker = str(row["ticker"])
        name = names.get(ticker)
        title = ticker if C._is_absent(name) else f"{ticker} · {name}"
        body = str(row["note"] or "").strip() or "(no note)"
        st.markdown(
            f'<div class="led"><div class="led-top">'
            f'<span class="led-name">{html.escape(title)}</span>'
            f'<span class="led-right rank-thin">'
            f'{html.escape(C.datestr(row["updated_at"]))}</span></div>'
            f'<div class="led-formula">{html.escape(body)}</div></div>',
            unsafe_allow_html=True,
        )

    st.download_button(
        "Download the watchlist as CSV",
        frame.to_csv(index=False).encode("utf-8"),
        file_name="watchlist.csv",
        mime="text/csv",
    )
