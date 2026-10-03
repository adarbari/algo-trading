"""Event tables (``events/split``, ``events/dividend``, …) read by EVENT date.

An event is stored in the partition of the run that learned it (a backfill run on
2026-10-02 stores 2015 splits in ``date=2026-10-02``), so the partition date says nothing
about when the event happened. Readers therefore scan every partition, keep rows whose
``ts`` (the event date) is in the requested window, and keep the latest ``knowledge_ts`` per
event key. ``as_of`` pins the stored version (ADR 0007); "known at the time" for events
(declaration / announcement dates) is a later refinement.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from algotrade.storage.tables.readers import StoreReader

ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))


@dataclass(frozen=True)
class Events:
    frame: pd.DataFrame  # one row per event key, sorted by (instrument_id, ts)
    runs: list[str]  # the stored runs the rows came from (for reproducibility)


def event_key(frame: pd.DataFrame) -> list[str]:
    """``instrument_id`` + ``ts`` (+ ``change`` for tables with several kinds a day)."""
    return ["instrument_id", "ts", *(["change"] if "change" in frame.columns else [])]


def read_events(
    reader: StoreReader,
    table: str,
    start: date,
    end: date,
    instruments: Sequence[str] | None = None,
    as_of: datetime | None = None,
) -> Events:
    """Events with ``start <= ts (UTC date) <= end``, from any partition."""
    frame = reader.table_range(table, *ALL_TIME, as_of, instruments)
    if frame is None or frame.empty:
        return Events(pd.DataFrame(columns=["instrument_id", "ts"]), [])
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
    """Every stored row of ``table`` from partitions on or before ``through``, as stored.

    Unlike ``read_events`` nothing is merged: each row keeps the ``session_date`` of the run
    that stored it, so a consumer can tell what was known on each session (e.g. the earnings
    calendar as of D: the snapshots stored on or before D). Empty when nothing is stored."""
    frame = reader.table_range(table, ALL_TIME[0], through, as_of)
    if frame is None:
        return pd.DataFrame(columns=["instrument_id", "ts", "session_date"])
    return frame.sort_values(["session_date", "instrument_id", "ts"], kind="stable").reset_index(
        drop=True
    )


def events_by_event_date(
    reader: StoreReader, table: str, start: date, end: date, as_of: datetime | None = None
) -> pd.DataFrame:
    """``read_events`` for ``start..end`` with an ``event_date`` column (the UTC date of
    ``ts``), sorted by (``event_date``, ``instrument_id``). The stored partition date is
    dropped: it says when we learned of the event, not when it happened. Never a later event
    (a declared future ex-date stays out until its date)."""
    frame = read_events(reader, table, start, end, as_of=as_of).frame
    frame = frame.drop(columns=[c for c in ("session_date",) if c in frame.columns])
    frame = frame.assign(event_date=pd.to_datetime(frame["ts"], utc=True).dt.date)
    frame = frame.sort_values(["event_date", "instrument_id"], kind="stable")
    return frame.reset_index(drop=True)
