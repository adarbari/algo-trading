"""Analyst snapshots (``analyst/estimate_snapshots``, ADR 0068) for feature inputs and checks.

The table is our own point-in-time history of what FMP and Finnhub said: each night appends the
rows of the names it asked, in the partition of the session it is for. ``ts`` is the fetch
instant and ``knowledge_ts`` the publish instant of the run, never a vendor date. ``kind`` is
``estimates_annual`` (one row per fiscal year end, ``period``), ``price_target`` and ``grades``
(``period = "current"``), ``recommendation`` (a month) or ``coverage``: a marker row, one per
vendor and attempt, whose ``status`` is OK, EMPTY, NOT_COVERED (the vendor refuses the name) or
FAILED. A table stored before the markers has no ``status`` column: the reads add it, empty.

**A version** is one row per (``instrument_id``, ``source``, ``kind``, ``period``,
``session_date``); the latest stored version wins, ties broken by (``knowledge_ts``, ``ts``,
``run_id``), and a null in a key column equals another null. Runs merge in the store, so a
re-run of a night replaces that night's earlier row of the same key.

**What a session sees.** A snapshot row counts for session S only when its ``session_date`` is
on or before S AND its ``knowledge_ts`` is before the OPEN OF THE NEXT SESSION after S
(``visible_from``: the later of ``session_date`` and the last session opened at the instant the
run published, ``calendar.last_opened_session``). A re-run published days later therefore never
reaches back into the sessions before it: at those sessions the name has no row (the store
keeps only the re-run's version), which reads as "not asked", never as the later value.

``stored_snapshots`` reads the versions (all sessions, or those ``through`` S);
``SnapshotWindow`` is the feature input: the rows each session of a run sees.
"""

from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import last_opened_session, sessions_ending
from algotrade.storage.tables.readers import StoreReader

TABLE = "analyst/estimate_snapshots"
ESTIMATES, TARGET, GRADES, RECOMMENDATION = (
    "estimates_annual",
    "price_target",
    "grades",
    "recommendation",
)
COVERAGE = "coverage"  # a marker row: the vendor's answer to an attempt, in ``status``
KINDS = (ESTIMATES, TARGET, GRADES, RECOMMENDATION, COVERAGE)
KEY = ["instrument_id", "source", "kind", "period", "session_date"]
LATEST_BY = ["knowledge_ts", "ts", "run_id"]
ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))
VISIBLE = "visible_from"


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=[*KEY, *LATEST_BY, "status", VISIBLE])


def _first_session(published: pd.Series) -> pd.Series:
    """The session each publish instant first reaches: the last one opened by then (one lookup
    per distinct instant)."""
    instants = pd.to_datetime(published, utc=True)
    known = {t: last_opened_session(t.to_pydatetime()) for t in instants.unique()}
    return instants.map(known)


def _versions(
    reader: StoreReader,
    as_of: datetime | None,
    kinds: tuple[str, ...],
    instruments: list[str] | None,
    since: date | None,
) -> pd.DataFrame:
    """Every stored version of the rows of ``kinds``, with ``visible_from``, oldest first."""
    start = since or ALL_TIME[0]
    frame = reader.table_range(TABLE, start, ALL_TIME[1], as_of, instruments)
    if frame is None or frame.empty:
        return _empty()
    frame = frame[frame["kind"].isin(kinds)].copy()
    if frame.empty:
        return _empty()
    if "status" not in frame.columns:
        frame["status"] = None
    frame["period"] = frame["period"].astype(object).where(frame["period"].notna(), None)
    stored = pd.to_datetime(frame["session_date"]).dt.date
    frame["session_date"] = stored
    reached = _first_session(frame["knowledge_ts"])
    frame[VISIBLE] = [max(a, b) for a, b in zip(stored, reached, strict=True)]
    return frame.sort_values(LATEST_BY, kind="stable").reset_index(drop=True)


def latest_versions(frame: pd.DataFrame) -> pd.DataFrame:
    """The latest version of each ``KEY`` row of ``frame`` (oldest first by ``LATEST_BY``), in
    key order."""
    frame = frame.sort_values(LATEST_BY, kind="stable").drop_duplicates(KEY, keep="last")
    return frame.sort_values(KEY, kind="stable", na_position="first").reset_index(drop=True)


def stored_snapshots(
    reader: StoreReader,
    as_of: datetime | None,
    kinds: tuple[str, ...],
    instruments: list[str] | None = None,
    *,
    since: date | None = None,
    through: date | None = None,
) -> pd.DataFrame:
    """The latest version of each snapshot row of ``kinds`` stored as of ``as_of`` (``None``:
    now), for ``instruments`` (``None``: all) with a ``session_date`` from ``since``; with
    ``through`` only the rows session ``through`` may see (module doc). Date columns are
    ``date`` objects; empty when none."""
    frame = _versions(reader, as_of, kinds, instruments, since)
    if through is not None:
        frame = frame[frame[VISIBLE] <= through]
    return latest_versions(frame)


@dataclass(frozen=True)
class SnapshotWindow:
    """The versions read once, with the day each becomes visible and the day of its session
    (``visible``, ``made``: datetime64[D], one per row of ``frame``); ``at`` is what a session
    sees: the latest visible version of each row from the last ``lookback`` sessions."""

    frame: pd.DataFrame
    visible: np.ndarray
    made: np.ndarray

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        today = np.datetime64(session, "D")
        oldest = np.datetime64(sessions_ending(session, lookback + 1)[0], "D")
        rows = self.frame[(self.visible <= today) & (self.made >= oldest)]
        return latest_versions(rows) if len(rows) else None


def snapshot_window(
    reader: StoreReader, kinds: tuple[str, ...], first: date, instruments: list[str] | None = None
) -> SnapshotWindow:
    """The versions of ``kinds`` with a ``session_date`` from ``first`` on, for ``at``."""
    frame = _versions(reader, None, kinds, instruments, first)
    visible = pd.to_datetime(frame[VISIBLE]).to_numpy(dtype="datetime64[D]")
    made = pd.to_datetime(frame["session_date"]).to_numpy(dtype="datetime64[D]")
    return SnapshotWindow(frame, visible, made)
