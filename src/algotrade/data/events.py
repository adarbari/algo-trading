"""Event tables (``events/split``, ``events/dividend``, …) read by EVENT date, known as of a
session.

An event is stored in the partition of the run that learned it (a backfill run on
2026-10-02 stores 2015 splits in ``date=2026-10-02``), so the partition date says nothing
about when the event happened. Readers therefore scan every partition, keep rows whose
``ts`` (the event date) is in the requested window, and keep the latest ``knowledge_ts`` per
event key. ``as_of`` pins the stored version (ADR 0007).

**The one read rule** (ADR 0050 decision 3): as of session S a reader keeps only rows known
on or before S. A row is known from its ``known_from`` date (``schemas.KNOWN_FROM``: the
session the fact was knowable on, e.g. a backfilled report's report date), else, when the
column is absent or null, from the session that stored it (``session_date``). So a 2019
report backfilled into a 2026 partition with ``known_from = 2019-05-01`` is visible to a
2019-05-01 session, and a row without ``known_from`` is invisible before the session that
stored it. ``through`` is S; ``None`` keeps every row.

**Facts of record** (``FACTS_OF_RECORD``: splits, dividends, reference and index changes) are
applied to bars at read time (ADR 0016) and read by event date without a knowledge bound:
they carry no ``known_from``, and ``knowledge_bound`` gives them none, so a pinned past
session shows the split its own adjusted bars used.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import KNOWN_FROM

ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))
# Read by event date with no knowledge bound (module doc): applied to bars at read time.
FACTS_OF_RECORD = frozenset(
    {"events/split", "events/dividend", "events/reference_change", "events/index_change"}
)


@dataclass(frozen=True)
class Events:
    frame: pd.DataFrame  # one row per event key, sorted by (instrument_id, ts)
    runs: list[str]  # the stored runs the rows came from (for reproducibility)


def event_key(frame: pd.DataFrame) -> list[str]:
    """``instrument_id`` + ``ts`` (+ ``change`` for tables with several kinds a day)."""
    return ["instrument_id", "ts", *(["change"] if "change" in frame.columns else [])]


def known_from(frame: pd.DataFrame) -> pd.Series:
    """Each row's effective ``known_from`` as a datetime64 (midnight): the column when set,
    else the row's ``session_date`` (the one read rule, module doc)."""
    stored = pd.to_datetime(frame["session_date"])
    if KNOWN_FROM not in frame.columns:
        return stored
    return pd.to_datetime(frame[KNOWN_FROM]).fillna(stored)


def _known_by(frame: pd.DataFrame, through: date | None) -> pd.DataFrame:
    """The rows known on or before ``through`` (None: all)."""
    if through is None:
        return frame
    return frame[known_from(frame) <= pd.Timestamp(through)]


def knowledge_bound(table: str, session: date) -> date | None:
    """The ``through`` a read as of ``session`` passes for ``table``: the session, or None for
    a fact of record (module doc)."""
    return None if table in FACTS_OF_RECORD else session


def read_events(
    reader: StoreReader,
    table: str,
    start: date,
    end: date,
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
    through: date | None = None,
) -> Events:
    """Events with ``start <= ts (UTC date) <= end`` among the rows known on or before
    ``through`` (None: every row), the latest stored version of each."""
    frame = reader.table_range(table, *ALL_TIME, as_of, instruments)
    if frame is None or frame.empty:
        return Events(pd.DataFrame(columns=["instrument_id", "ts"]), [])
    frame = _known_by(frame, through)
    day = pd.to_datetime(frame["ts"], utc=True).dt.date
    frame = frame[(day >= start) & (day <= end)]
    if frame.empty:
        return Events(frame.reset_index(drop=True), [])
    frame = frame.sort_values("knowledge_ts", kind="stable").drop_duplicates(
        event_key(frame), keep="last"
    )
    frame = frame.sort_values(["instrument_id", "ts"], kind="stable").reset_index(drop=True)
    return Events(frame, sorted(map(str, frame["run_id"].unique())))


def stored_events(
    reader: StoreReader, table: str, through: date, as_of: datetime | None = None
) -> pd.DataFrame:
    """Every stored row of ``table`` known on or before ``through``, as stored, with
    ``known_from`` set to each row's effective date (the one read rule).

    Unlike ``read_events`` nothing is merged: each row keeps the ``session_date`` of the run
    that stored it, so a consumer can tell what was known on each session (e.g. the earnings
    calendar as of D: the snapshots stored on or before D, and the reports backfilled later
    but known by D). Sorted by ``known_from`` then ``session_date``; empty when nothing is
    stored."""
    frame = reader.table_range(table, *ALL_TIME, as_of)
    if frame is None:
        return pd.DataFrame(columns=["instrument_id", "ts", "session_date", KNOWN_FROM])
    frame = _known_by(frame, through)
    frame = frame.assign(**{KNOWN_FROM: known_from(frame).dt.date})
    order = [KNOWN_FROM, "session_date", "instrument_id", "ts"]
    return frame.sort_values(order, kind="stable").reset_index(drop=True)


def events_by_event_date(
    reader: StoreReader,
    table: str,
    start: date,
    end: date,
    as_of: datetime | None = None,
    through: date | None = None,
) -> pd.DataFrame:
    """``read_events`` for ``start..end`` (known on or before ``through``; None: every row)
    with an ``event_date`` column (the UTC date of ``ts``), sorted by (``event_date``,
    ``instrument_id``). The stored partition date is dropped: it says when we learned of the
    event, not when it happened. Never a later event (a declared future ex-date stays out
    until its date)."""
    frame = read_events(reader, table, start, end, as_of=as_of, through=through).frame
    frame = frame.drop(columns=[c for c in ("session_date",) if c in frame.columns])
    frame = frame.assign(event_date=pd.to_datetime(frame["ts"], utc=True).dt.date)
    frame = frame.sort_values(["event_date", "instrument_id"], kind="stable")
    return frame.reset_index(drop=True)
