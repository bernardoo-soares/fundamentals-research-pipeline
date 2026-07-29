"""The console's design tokens and stylesheet, declared once.

DIRECTION: "Assay"
------------------
The subject is verification. This project's Prime Directive is *no false
numbers*; its defining act is measuring rather than assuming. The visual world
that belongs to that is the assay office -- hallmarks, tolerance bands, audit
opinions -- not the finance-dashboard convention of green arrows.

One rule makes the palette a system rather than decoration:

    GOLD MEANS MEASURED.

Nothing unverified is ever rendered in `ASSAY`. `PEWTER` is not "a muted grey
for less important things"; it means *this number is not backed by evidence*.
A reader who learns one thing about this interface should learn that.

Typography is monospace-forward because digit alignment is a correctness
feature here, not a style: these are columns of figures compared down the page.
System stacks only, no webfont -- a local research instrument must not change
appearance when the network is down.
"""

from __future__ import annotations

# --- Palette -----------------------------------------------------------------
PAPER = "#F2F4F6"  # cool porcelain; deliberately not cream
PANEL = "#FFFFFF"
RULE = "#D6DBE0"
INK = "#171A1F"
PEWTER = "#737C88"  # unmeasured / absent
ASSAY = "#A67C00"  # measured and verified
OXIDE = "#A6392F"  # checklist fail

# --- Type --------------------------------------------------------------------
MONO_STACK = (
    '"Cascadia Mono", "SF Mono", "JetBrains Mono", "Consolas", '
    '"DejaVu Sans Mono", monospace'
)
PROSE_STACK = (
    '"Segoe UI Variable Text", "Segoe UI", Inter, -apple-system, '
    "system-ui, sans-serif"
)

# --- Layout ------------------------------------------------------------------
# A precision instrument, so radii stay near-square: 2px reads as machined,
# 8px+ reads as consumer software.
RADIUS = "2px"

# How many ranking rows render at once. The full FY2024 universe is 384; paging
# keeps the page responsive and, more usefully, makes "how far down am I
# looking?" a question with an answer.
PAGE_SIZE = 40


def stylesheet() -> str:
    """Return the console's full CSS, wrapped in a <style> tag."""
    return f"""
<style>
  :root {{
    --paper: {PAPER};
    --panel: {PANEL};
    --rule: {RULE};
    --ink: {INK};
    --pewter: {PEWTER};
    --assay: {ASSAY};
    --oxide: {OXIDE};
    --mono: {MONO_STACK};
    --prose: {PROSE_STACK};
    --radius: {RADIUS};
  }}

  .stApp {{ background: var(--paper); }}
  /* Streamlit's toolbar is fixed over the top of the page, so the masthead
     needs clearance or its cap-height is sliced off. */
  .block-container {{ padding-top: 4.2rem; max-width: 1500px; }}
  html, body, [class*="css"] {{ font-family: var(--prose); color: var(--ink); }}

  /* The deploy button and running-man are host chrome, not part of the
     instrument. */
  [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"] {{ display: none !important; }}
  #MainMenu, footer {{ visibility: hidden; }}

  /* Widget accent colour comes from .streamlit/config.toml, not from CSS aimed
     at BaseWeb's internal DOM -- that is the supported seam and it does not
     break when Streamlit renames a data-testid. Only the numerals are restyled
     here, so slider readouts share the tabular figures of everything else. */
  [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"],
  [data-testid="stThumbValue"] {{
    font-family: var(--mono) !important;
    font-size: 10.5px !important;
    font-variant-numeric: tabular-nums;
  }}
  .stButton button[kind="primary"] {{
    background: var(--ink);
    border: 1px solid var(--ink);
    border-radius: var(--radius);
    font-family: var(--mono);
    font-size: 12px;
  }}
  .stButton button[kind="primary"]:hover {{
    background: var(--assay);
    border-color: var(--assay);
  }}

  /* ---- Masthead ---------------------------------------------------------- */
  .assay-masthead {{
    border-bottom: 2px solid var(--ink);
    padding-bottom: .7rem;
    margin-bottom: .35rem;
  }}
  .assay-wordmark {{
    font-family: var(--mono);
    font-size: 25px;
    font-weight: 700;
    letter-spacing: -.02em;
    line-height: 1;
  }}
  .assay-wordmark .mark {{ color: var(--assay); }}
  .assay-tagline {{
    font-family: var(--prose);
    font-size: 12.5px;
    color: var(--pewter);
    margin-top: .35rem;
  }}

  /* Eyebrow: the small-caps mono label that titles every block. */
  .assay-eyebrow {{
    font-family: var(--mono);
    font-size: 10.5px;
    letter-spacing: .13em;
    text-transform: uppercase;
    color: var(--pewter);
    margin: 1.5rem 0 .5rem;
    border-bottom: 1px solid var(--rule);
    padding-bottom: .3rem;
  }}

  /* ---- Horizon banner ---------------------------------------------------- */
  /* Permanently visible (platform spec 8): the reader must never have to
     remember how old the data is. */
  .assay-horizon {{
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--pewter);
    background: var(--panel);
    border: 1px solid var(--rule);
    border-left: 3px solid var(--assay);
    border-radius: var(--radius);
    padding: .5rem .7rem;
    margin-bottom: .4rem;
  }}
  .assay-horizon b {{ color: var(--ink); font-weight: 600; }}

  /* ---- Evidence bar (the signature) -------------------------------------- */
  /* Bar length is the composite; the solid gold portion is the share backed by
     measured criteria. A high score on thin evidence reads hollow. */
  /* The bar is deliberately slight. Composites cluster between 78 and 94, so
     25 thick bars at full saturation read as one mustard block and stop
     discriminating -- the opposite of the point. A 7px rule carries the same
     information and lets the row breathe. */
  .ev-wrap {{ display: flex; align-items: center; gap: .6rem; }}
  .ev-track {{
    position: relative;
    flex: 1;
    height: 7px;
    background: rgba(115,124,136,.09);
    border-radius: var(--radius);
    overflow: hidden;
    min-width: 90px;
  }}
  /* The unmeasured remainder. Solid pewter rather than a faint hatch: the
     discrimination that matters most here is 0.95 against 1.00, and a hatch
     at 5% of a 7px bar is invisible. */
  .ev-total {{
    position: absolute; inset: 0 auto 0 0;
    background: rgba(115,124,136,.42);
  }}
  .ev-solid {{
    position: absolute; inset: 0 auto 0 0;
    background: var(--assay);
  }}
  /* A hairline at the measured/unmeasured seam, so a 2-point deficit still
     has an edge the eye can catch. */
  .ev-seam {{
    position: absolute; top: -3px; bottom: -3px;
    width: 1px;
    background: var(--ink);
    opacity: .55;
  }}
  .ev-score {{
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 700;
    width: 3.2rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }}

  /* ---- Ranking rows ------------------------------------------------------ */
  .rank-row {{
    display: grid;
    grid-template-columns: 2.4rem 4.4rem 1fr 4.4rem 4.2rem 4.2rem;
    align-items: center;
    gap: .8rem;
    padding: .42rem .55rem;
    border-bottom: 1px solid rgba(214,219,224,.55);
    font-family: var(--mono);
    font-size: 12.5px;
    font-variant-numeric: tabular-nums;
  }}
  .rank-row:hover {{
    background: var(--panel);
    box-shadow: inset 2px 0 0 var(--assay);
  }}
  .rank-head {{
    font-size: 10px;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--pewter);
    border-bottom: 1px solid var(--ink);
    padding-bottom: .3rem;
  }}
  .rank-n {{ color: var(--pewter); }}
  .rank-ticker {{ font-weight: 700; font-size: 13.5px; }}
  .rank-num {{ text-align: right; }}
  .rank-thin {{ color: var(--pewter); }}

  /* ---- Panels and stats -------------------------------------------------- */
  .assay-panel {{
    background: var(--panel);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    padding: .8rem .9rem;
  }}
  .stat-label {{
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: .11em;
    text-transform: uppercase;
    color: var(--pewter);
  }}
  .stat-value {{
    font-family: var(--mono);
    font-size: 21px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: -.01em;
    line-height: 1.25;
  }}
  .stat-value.measured {{ color: var(--assay); }}
  .stat-value.absent {{ color: var(--pewter); font-weight: 400; font-size: 15px; }}
  .stat-note {{ font-family: var(--mono); font-size: 10.5px; color: var(--pewter); }}

  /* ---- Flags ------------------------------------------------------------- */
  /* Deliberately NOT coloured chips. Measured 2026-07-29, 96.6% of FY2024 rows
     carry `unreliable_input`; a warning that fires on everything is read as
     decoration. These are set as quiet mono annotations that stay legible when
     universal, and the actual discrimination is carried by the evidence bar. */
  .flag {{
    font-family: var(--mono);
    font-size: 10.5px;
    color: var(--pewter);
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    padding: .06rem .34rem;
    margin-right: .28rem;
    white-space: nowrap;
    display: inline-block;
  }}
  .flag.rare {{ color: var(--oxide); border-color: var(--oxide); }}

  .verdict-pass {{ color: var(--assay); font-weight: 700; }}
  .verdict-fail {{ color: var(--oxide); }}
  .verdict-na {{ color: var(--pewter); }}

  /* ---- Criterion ledger -------------------------------------------------- */
  .led {{
    border-bottom: 1px solid var(--rule);
    padding: .5rem .1rem;
    font-family: var(--mono);
    font-size: 12px;
  }}
  /* The right-hand cell is allowed to wrap. A "not measured" explanation can
     run to a full sentence, and clipping the reason is the one thing this
     interface must never do. */
  .led-top {{
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 1.4rem;
  }}
  .led-name {{ font-weight: 700; flex: 0 0 auto; }}
  .led-right {{ text-align: right; min-width: 0; }}
  .led-formula {{
    color: var(--pewter);
    font-size: 11px;
    margin-top: .22rem;
    white-space: pre-wrap;
    line-height: 1.45;
    max-width: 92ch;  /* a readable measure; full text is in the expander */
  }}
  .led-val {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}

  /* The drilldown header's bar. Left unconstrained it stretches the full
     content width and pushes its own score against the right edge. */
  .ev-header {{ max-width: 720px; margin: .1rem 0 1rem; }}

  /* ---- Inputs grid ------------------------------------------------------- */
  /* The audit trail: raw Stage 1 operands by fiscal period. Figures are
     tabular so a reader can add them up by eye, which is the point -- the
     console deliberately re-derives no total of its own. */
  table.inputs {{
    width: 100%;
    border-collapse: collapse;
    font-family: var(--mono);
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    margin: .5rem 0 .2rem;
  }}
  table.inputs th, table.inputs td {{
    border-bottom: 1px solid var(--rule);
    padding: .22rem .4rem;
    text-align: right;
    white-space: nowrap;
  }}
  table.inputs thead th {{
    color: var(--pewter);
    font-weight: 400;
    font-size: 10px;
    letter-spacing: .06em;
    border-bottom: 1px solid var(--ink);
  }}
  table.inputs th.fld {{ text-align: left; font-weight: 700; }}
  /* The provider row marks where the era boundary falls inside the window --
     the seam that makes a value carry mixed_era_window. */
  table.inputs tr.era td, table.inputs tr.era th {{
    color: var(--pewter);
    font-size: 10px;
    border-bottom: none;
  }}

  /* ---- Absence ----------------------------------------------------------- */
  /* A metric with no data states the absence. An empty chart frame reads as a
     bug rather than as "the source stopped providing this". */
  .assay-absent {{
    border: 1px dashed var(--rule);
    border-radius: var(--radius);
    padding: 1rem;
    text-align: center;
    font-family: var(--mono);
    font-size: 11.5px;
    color: var(--pewter);
    background:
      repeating-linear-gradient(-45deg,
        rgba(115,124,136,.05) 0 6px, transparent 6px 12px);
  }}

  /* ---- Streamlit chrome -------------------------------------------------- */
  section[data-testid="stSidebar"] {{
    background: var(--panel);
    border-right: 1px solid var(--rule);
  }}
  section[data-testid="stSidebar"] .stMarkdown {{ font-family: var(--prose); }}
  div[data-testid="stMetricValue"] {{
    font-family: var(--mono);
    font-variant-numeric: tabular-nums;
  }}
  .stDataFrame {{ font-family: var(--mono); }}
  /* Expander headers are labels in this interface, not prose. */
  [data-testid="stExpander"] summary {{
    font-family: var(--mono);
    font-size: 11.5px;
  }}
  [data-testid="stExpander"] details {{
    border: 1px solid var(--rule);
    border-radius: var(--radius);
    background: var(--panel);
  }}

  /* Quality floor, not announced: visible keyboard focus and honoured
     reduced-motion. */
  a:focus-visible, button:focus-visible, [tabindex]:focus-visible {{
    outline: 2px solid var(--assay);
    outline-offset: 2px;
  }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ animation: none !important; transition: none !important; }}
  }}
</style>
"""
