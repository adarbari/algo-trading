"""``filing_activity@v1``: SEC 8-K filings through the previous session and earnings reports in
the last 5 sessions, as known on the session (the no-news filter of the volume-shock edge,
ADR 0050).

Inputs: ``events/filing`` (the SEC event filings of the last ``LOOKBACK`` sessions, each with
``event_date``, the first session closing after its acceptance: EB H4's one read, never the
stored ``known_from``),
``filings/walk`` (the filings task's clean daily-index walks of the sessions up to S, whose
``walked_to`` says how far the stored filings are complete), ``events/earnings`` read as
``earnings@v1`` reads it (``earnings.valid_events``; the 8-K results rows are filings, counted
by the first column) and ``price_stats@v2`` for the names traded on the session. One row per
operating company with a ``price_stats@v2`` row.

    filing_count_5d  8-K and 8-K/A filings of the instrument (no other form: ``events/filing``
                     also holds late-filing notices, tender offers, Form 25 and prospectuses)
                     accepted before S-1's close, over the 5 sessions ending at S-1: the span
                     ends at S-1, never at S; 0: none
    earnings_in_5d   whether an earnings report's reaction window (E-1 to E+1,
                     ``earnings_reaction``) touches the last 5 sessions: a report dated on or
                     after the session before the window and on or before the session

Why the filing span ends at S-1: the nightly starts about 18:00 New York time and reads SEC's
daily index of a day only once it is published. SEC lists a filing accepted after 17:30 in the
next day's index, and one accepted after the close is known from the next session. So on the
night of S the index of S is usually unread and S's own 8-Ks are not stored (the filings step
is not critical: a failed night stores none). Counting through S would read 0 where a later
run reads 1. A filing known on or before S-1 was accepted before S-1's close, so S-1's index
lists it. The stored filings are complete once the walk has read S-1's index, and a
recompute after later nights gives the same value (a 16:30 acceptance on S-1 is known from S:
outside the span live and on every recompute). ``feature.news_free_5d`` therefore means no 8-K
through S-1 and no earnings window in the last 5 sessions.

``filing_count_5d`` is null (UNKNOWN), never zero, when the filings table cannot say "none"
(fail closed): neither a clean walk of a session up to S reached S-1 (``walked_to < S-1``, or
none; and the first stored filing is on or before the span's first session: the backfill
reached it) nor a full per-CIK read covers the instrument's CIK (a read of the filings task,
from the span's first session or earlier, by a run of S-1 or any later session: the filings
known on a past session do not change, so the history before the first nightly walk is
covered for the CIKs a backfill read in full, and for them only), no filing is stored in the
lookback, or the instrument has no filing in the lookback (nothing for it: never fetched, or
never filed). A session after a day SEC publishes no index (Columbus Day, Veterans Day) is
null until a walk reads past it: fail closed, no closed-day list yet. ``earnings_in_5d`` is
null when the instrument has no earnings report known by the session at all. A report that was
not yet known on the session never counts. The windows (5) are part of the definition:
changing one is a new version. ``feature.news_free_5d`` combines the two columns.

Selection effect of the per-CIK reads: they cover the CIKs a later run read (the universe of
that run), so a historical session is non-null from them only for names still in a later
universe; an early delisted name stays null (fail closed, never zero). The ledger is read
unbounded (``UNBOUNDED_INPUTS``, ADR 0007 amendment): it holds no content, and the counts come
only from ``events/filing`` rows with ``event_date`` on or before S-1.
"""

from datetime import date

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.corporate.dividends import PRICE_STATS

NAME = "filing_activity"
VERSION = 1
FILINGS = "events/filing"
WALK = "filings/walk"
READ = "filings/read"
EIGHT_K_FORMS = ("8-K", "8-K/A")
KNOWN_FROM = earnings.KNOWN_FROM
WINDOW = 5  # sessions of the window
LOOKBACK = 250  # sessions of filings read: a name with none in them is unknown, not zero

_NO_TABLE = (
    "neither a clean filings walk reached the previous session nor a full per-CIK read of the "
    "company's filings covers the span, no filing is stored, or the instrument has no filing "
    "stored by then (nothing for it)"
)

FEATURES = (
    Feature(
        "filing_count_5d", "int", "count",
        f"8-K and 8-K/A filings of the company accepted in the {WINDOW} sessions ending at the "
        "previous session (accepted before its close), as known on the session "
        "(0: it filed nothing)",
        _NO_TABLE, valid_range=(0, None), inputs=(f"{FILINGS}.accession",),
    ),
    Feature(
        "earnings_in_5d", "bool", "flag",
        f"An earnings report's reaction window (the session before it to the session after "
        f"it) touches the last {WINDOW} sessions: the company reported in them, or the day "
        "before the first of them",
        "no earnings report is known for the instrument by the session",
        inputs=(f"{earnings.EVENTS}.ts",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _known_days(rows: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(rows[KNOWN_FROM]).dt.date


def _read_ciks(reads: pd.DataFrame | None, start: date, previous: date) -> set[str]:
    """The CIKs a full per-CIK read covers over the span: read from ``start`` or earlier, by a
    run of the session ``previous`` or later (any later run: module doc)."""
    if reads is None or reads.empty:
        return set()
    ran = pd.to_datetime(reads["session_date"]).dt.date >= previous
    began = pd.to_datetime(reads["covers_since"]).dt.date <= start
    padded = (pad_cik(c) for c in reads["cik"][ran & began])
    return {c for c in padded if c}


def filing_counts(
    filings: pd.DataFrame | None,
    walks: pd.DataFrame | None,
    session: date,
    reads: pd.DataFrame | None = None,
) -> pd.Series:
    """Per instrument seen in ``filings``: its filings that became known from the span's first
    session through ``S-1`` (the module doc's rule), for the instruments the stored filings
    are complete for: all of them when a clean walk of a session up to S reached ``S-1`` and the
    backfill reached the span, else those whose CIK a full per-CIK read covers (``reads``).
    Empty for the rest (the table is absent, or nothing covers it), so that nobody gets a zero it
    cannot know."""
    empty = pd.Series(dtype="int64")
    grid = sessions_ending(session, WINDOW + 1)
    start, previous = grid[0], sessions_ending(session, 2)[0]
    if filings is None or filings.empty:
        return empty
    filings = filings[filings["form"].isin(EIGHT_K_FORMS)]  # not the other event forms
    known = pd.to_datetime(filings["event_date"]).dt.date
    complete = filings[known <= previous]
    if complete.empty:
        return empty
    reached = pd.Series(dtype="object")
    if walks is not None and not walks.empty:
        reached = pd.to_datetime(walks["walked_to"]).dt.date[
            pd.to_datetime(walks["session_date"]).dt.date <= session
        ]
    walked = (
        not reached.empty and reached.max() >= previous and known[known <= previous].min() <= start
    )
    covered = complete
    if not walked:
        ciks = _read_ciks(reads, start, previous)
        if not ciks or "cik" not in complete.columns:
            return empty
        covered = complete[complete["cik"].map(pad_cik).isin(ciks)]
        if covered.empty:
            return empty
    in_span = pd.to_datetime(covered["event_date"]).dt.date >= start
    counts = covered.assign(_in=in_span.to_numpy()).groupby(
        covered["instrument_id"].astype(str), sort=True
    )["_in"]
    return counts.sum().astype("int64")


def earnings_flags(stored: pd.DataFrame, session: date) -> pd.Series:
    """Per instrument with an earnings report known by ``session``: whether a report's
    reaction window touches the last ``WINDOW`` sessions."""
    if KNOWN_FROM in stored.columns:  # the loader's rule, kept here for the invariant
        stored = stored[_known_days(stored) <= session]
    rows = earnings.valid_events(stored, session)
    if rows.empty:
        return pd.Series(dtype="bool")
    first = sessions_ending(session, WINDOW + 1)[0]  # the session before the window
    near = (rows["report"] >= first) & (rows["report"] <= session)
    return near.groupby(rows["instrument_id"].astype(str)).any()


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stats, stored = inputs[PRICE_STATS], inputs.get(earnings.EVENTS)
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session][["instrument_id"]].astype(
        {"instrument_id": str}
    )
    counts = filing_counts(inputs.get(FILINGS), inputs.get(WALK), session, inputs.get(READ))
    out = today.assign(filing_count_5d=today["instrument_id"].map(counts))
    flags = pd.Series(dtype="bool") if stored is None else earnings_flags(stored, session)
    out["earnings_in_5d"] = today["instrument_id"].map(flags).astype(object)
    out["earnings_in_5d"] = out["earnings_in_5d"].where(out["earnings_in_5d"].notna(), None)
    count = out["filing_count_5d"].astype(object)
    out["filing_count_5d"] = count.where(count.notna(), None)
    return out[["instrument_id", *COLUMNS]].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "8-K filings through the previous session and earnings reports in the last 5 sessions, "
    "as known on the session",
    (
        Input(PRICE_STATS),
        Input(FILINGS, lookback=LOOKBACK, required=False),
        Input(WALK, required=False),
        Input(READ, required=False),
        Input(earnings.EVENTS, required=False),
    ),
    FEATURES,
    compute,
    applies_to="operating_company",
)
