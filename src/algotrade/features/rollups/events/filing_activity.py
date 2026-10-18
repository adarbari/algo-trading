"""``filing_activity@v1``: SEC 8-K filings and earnings reports in the last 5 sessions, as known
on the session (the no-news filter of the volume-shock edge, ADR 0050).

Inputs: ``events/filing`` (every 8-K / 8-K/A row known on or before the session: the
loader's ``known_from <= S`` rule, ``known_from`` being the acceptance's New York session),
``events/earnings`` read as ``earnings@v1`` reads it (``earnings.valid_events``; the 8-K
results rows are filings, counted by the first column) and ``price_stats@v2`` for the names
traded on the session. One row per operating company with a ``price_stats@v2`` row.

    filing_count_5d  8-K and 8-K/A filings of the instrument with ``known_from`` in the last 5
                     exchange sessions, the session included (0: none)
    earnings_in_5d   whether an earnings report's reaction window (E-1 to E+1,
                     ``earnings_reaction``) touches the last 5 sessions: a report dated on or
                     after the session before the window and on or before the session

``filing_count_5d`` is null (UNKNOWN), never zero, when the filings table cannot say "none":
no filing is stored at all, the table's first ``known_from`` is after the window's first
session (the backfill had not reached it), or the instrument has no filing known by the
session (filings are fetched for the event-study scope only, so no row may mean not asked).
``earnings_in_5d`` is null when the instrument has no earnings report known by the session at
all. A report that was not yet known on the session never counts, so a session recomputed
after later nights changes nothing it knew. The window (5) is part of the definition:
changing it is a new version. ``feature.news_free_5d`` combines the two columns.
"""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings
from algotrade.features.rollups.corporate.dividends import PRICE_STATS

NAME = "filing_activity"
VERSION = 1
FILINGS = "events/filing"
KNOWN_FROM = earnings.KNOWN_FROM
WINDOW = 5  # sessions of the window, the session included

_NO_TABLE = (
    "no filing is stored, the filings backfill starts after the window, or the instrument has "
    "no filing known by the session (filings are fetched for the event-study scope only)"
)

FEATURES = (
    Feature(
        "filing_count_5d", "int", "count",
        f"8-K and 8-K/A filings of the company accepted in the last {WINDOW} sessions, the "
        "session included, as known on the session (0: it filed nothing)",
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


def filing_counts(filings: pd.DataFrame | None, session: date) -> pd.Series:
    """Per instrument seen in ``filings``: its filings known in the window (the module doc's
    rule); empty when the table is absent, or starts after the window, so that nobody
    gets a zero it cannot know."""
    if filings is None or filings.empty:
        return pd.Series(dtype="int64")
    known = _known_days(filings)
    known = known[known <= session]  # the loader's rule, kept here for the invariant
    start = sessions_ending(session, WINDOW)[0]
    if known.empty or known.min() > start:
        return pd.Series(dtype="int64")
    seen = filings.loc[known.index]
    in_window = known >= start
    counts = seen.assign(_in=in_window.to_numpy()).groupby(
        seen["instrument_id"].astype(str), sort=True
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
    counts = filing_counts(inputs.get(FILINGS), session)
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
    "8-K filings and earnings reports in the last 5 sessions, as known on the session",
    (
        Input(PRICE_STATS),
        Input(FILINGS, required=False),
        Input(earnings.EVENTS, required=False),
    ),
    FEATURES,
    compute,
    applies_to="operating_company",
)
