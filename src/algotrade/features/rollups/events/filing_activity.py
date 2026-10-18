"""``filing_activity@v1``: SEC 8-K filings through the previous session and earnings reports in
the last 5 sessions, as known on the session (the no-news filter of the volume-shock edge,
ADR 0050).

Inputs: ``events/filing`` (every 8-K / 8-K/A row known on or before the session: the
loader's ``known_from <= S`` rule, ``known_from`` being the acceptance's New York session),
``filings/walk`` (the filings task's clean daily-index walks of the sessions up to S, whose
``walked_to`` says how far the stored filings are complete), ``events/earnings`` read as
``earnings@v1`` reads it (``earnings.valid_events``; the 8-K results rows are filings, counted
by the first column) and ``price_stats@v2`` for the names traded on the session. One row per
operating company with a ``price_stats@v2`` row.

    filing_count_5d  8-K and 8-K/A filings of the instrument accepted through the previous
                     session's index cut-off (17:30 New York time on S-1), over the 5 sessions
                     ending at S-1: the span ends at S-1, never at S; 0: none
    earnings_in_5d   whether an earnings report's reaction window (E-1 to E+1,
                     ``earnings_reaction``) touches the last 5 sessions: a report dated on or
                     after the session before the window and on or before the session

Why the filing span ends at S-1: the nightly starts about 18:00 New York time and reads SEC's
daily index of a day only once it is published. A filing accepted 17:30 to 22:00 is listed in
the next day's index, so on the night of S the index of S is usually unread and S's own 8-Ks
are not stored (and the filings step is not critical: a failed night stores none). Counting
through S would read 0 where a later run reads 1. Through S-1's cut-off the stored filings are
complete once the walk has read S-1's index, and a recompute after later nights gives the same
value (``feature.news_free_5d`` therefore means no 8-K through S-1 and no earnings window in the
last 5 sessions).

``filing_count_5d`` is null (UNKNOWN), never zero, when the filings table cannot say "none"
(fail closed): no clean walk of a session up to S reached S-1 (``walked_to < S-1``, or none),
no filing is stored at all, the table's first ``known_from`` is after the span's first
session (the backfill had not reached it), or the instrument has no filing stored by then
(nothing for it: never fetched, or never filed). ``earnings_in_5d`` is null when the
instrument has no earnings report known by the session at all. A report that was not yet known
on the session never counts. The windows (5) are part of the definition: changing one is a new
version. ``feature.news_free_5d`` combines the two columns.
"""

from datetime import date, time

import pandas as pd

from algotrade.core.time.calendar import local_deadline, sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.corporate.dividends import PRICE_STATS

NAME = "filing_activity"
VERSION = 1
FILINGS = "events/filing"
WALK = "filings/walk"
KNOWN_FROM = earnings.KNOWN_FROM
WINDOW = 5  # sessions of the window, the session included

_NO_TABLE = (
    "no clean filings walk reached the previous session, no filing is stored, the filings "
    "backfill starts after the span, or the instrument has no filing stored by then (nothing "
    "for it)"
)

FEATURES = (
    Feature(
        "filing_count_5d", "int", "count",
        f"8-K and 8-K/A filings of the company accepted in the {WINDOW} sessions ending at the "
        "previous session (through its 17:30 New York index cut-off), as known on the session "
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


INDEX_CUTOFF = time(17, 30)  # New York: later acceptances are listed in the next day's index
EXCHANGE_ZONE = "America/New_York"


def index_cutoff(day: date) -> pd.Timestamp:
    """The instant after which an acceptance on ``day`` is listed in the next day's index."""
    return pd.Timestamp(local_deadline(day, INDEX_CUTOFF, EXCHANGE_ZONE))


def filing_counts(
    filings: pd.DataFrame | None, walks: pd.DataFrame | None, session: date
) -> pd.Series:
    """Per instrument seen in ``filings``: its filings accepted from the span's first session
    through ``S-1``'s index cut-off (the module doc's rule); empty when no clean walk reached
    ``S-1``, the table is absent, or it starts after the span, so that nobody gets a zero it
    cannot know."""
    empty = pd.Series(dtype="int64")
    grid = sessions_ending(session, WINDOW + 1)
    start, previous = grid[0], sessions_ending(session, 2)[0]
    if filings is None or filings.empty or walks is None or walks.empty:
        return empty
    reached = pd.to_datetime(walks["walked_to"]).dt.date[
        pd.to_datetime(walks["session_date"]).dt.date <= session
    ]
    if reached.empty or reached.max() < previous:
        return empty
    known = _known_days(filings)
    accepted = pd.to_datetime(filings["ts"], utc=True)
    complete = filings[(known <= previous) & (accepted <= index_cutoff(previous))]
    if complete.empty or _known_days(complete).min() > start:
        return empty
    in_span = (_known_days(complete) >= start).to_numpy()
    counts = complete.assign(_in=in_span).groupby(complete["instrument_id"].astype(str), sort=True)[
        "_in"
    ]
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
    counts = filing_counts(inputs.get(FILINGS), inputs.get(WALK), session)
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
        Input(FILINGS, required=False),
        Input(WALK, required=False),
        Input(earnings.EVENTS, required=False),
    ),
    FEATURES,
    compute,
    applies_to="operating_company",
)
