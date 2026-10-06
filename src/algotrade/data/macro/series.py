"""Macro series and index levels (``macro/series``, ADR 0048) for consumers, point in time by
vintage.

The table holds every vintage of every observation: one row per (``instrument_id``,
``obs_date``, ``vintage_date``), stored in increments (each run of the ``macro`` task adds the
vintages it found; a backfill stores decades of them in one partition). A read unions every
partition and keeps the latest stored version of each row.

Point in time is the VINTAGE date, not the partition or ``knowledge_ts``: a 2008 vintage that a
2026 backfill stored was public in 2008. ``series_as_of`` gives each observation's value as a
session knew it: the latest vintage with ``vintage_date`` on or before the session, never a
later revision. Values are end-of-night like ``bars/1d``: ``vintage_date <= session`` means
known by the session's nightly run, so a fill at the session's close must not use them. Feature
groups read the same rows through ``data.feature_inputs``, which applies the same rule
(``known_window``) per session.
"""

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import MACRO_SERIES

TABLE = MACRO_SERIES.name
KEY = list(MACRO_SERIES.key)
COLUMNS = ["instrument_id", "series", "obs_date", "vintage_date", "value", "vintage_kind"]
STAMPS = ["session_date", "knowledge_ts", "source", "run_id"]
ALL_TIME = (date(1900, 1, 1), date(9999, 12, 31))


def stored_vintages(
    reader: StoreReader, ids: Sequence[str] | None = None, as_of: datetime | None = None
) -> pd.DataFrame:
    """Every stored vintage of ``ids`` (every series when ``None`` or empty), the latest
    stored version per key, without the stamp columns; ``obs_date`` and ``vintage_date`` are
    ``date`` objects; sorted by ``vintage_date`` (then id and observation). Empty when none."""
    frame = reader.table_range(TABLE, *ALL_TIME, as_of, instruments=list(ids) if ids else None)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=COLUMNS)
    for column in ("obs_date", "vintage_date"):
        frame[column] = pd.to_datetime(frame[column]).dt.date
    frame = frame.sort_values("knowledge_ts", kind="stable").drop_duplicates(KEY, keep="last")
    frame = frame.drop(columns=[c for c in STAMPS if c in frame.columns])
    order = ["vintage_date", "instrument_id", "obs_date"]
    return frame.sort_values(order, kind="stable").reset_index(drop=True)


def latest_vintages(vintages: pd.DataFrame, session: date) -> pd.DataFrame:
    """The rows of ``vintages`` a ``session`` knew (``vintage_date`` on or before it), only the
    latest vintage per (``instrument_id``, ``obs_date``); sorted by id and observation."""
    known = vintages[vintages["vintage_date"] <= session]
    known = known.sort_values("vintage_date", kind="stable")
    known = known.drop_duplicates(["instrument_id", "obs_date"], keep="last")
    return known.sort_values(["instrument_id", "obs_date"], kind="stable").reset_index(drop=True)


def series_as_of(
    reader: StoreReader,
    ids: Sequence[str] | None,
    session: date,
    lookback: int,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    """Each observation of ``ids`` (every series when ``None`` or empty) as ``session`` knew
    it: the latest vintage with ``vintage_date <= session``. Returned: the observations dated
    from ``lookback`` exchange sessions before the session on, and always each series' latest
    known observation (a monthly or lagged series has none in a short window: ``lookback`` 0
    still gives the latest UNRATE). Columns ``COLUMNS``, one row per (``instrument_id``,
    ``obs_date``), sorted by both, so ``frame.pivot(index="obs_date", columns="instrument_id",
    values="value")`` gives one column per series. ``as_of`` pins what the store held
    (``knowledge_ts``), as for every table."""
    known = known_window(stored_vintages(reader, ids, as_of), session, lookback)
    return known.reindex(columns=COLUMNS).reset_index(drop=True)


def known_window(vintages: pd.DataFrame, session: date, lookback: int) -> pd.DataFrame:
    """``series_as_of``'s rule over rows already read (``stored_vintages``' shape): the latest
    vintage a ``session`` knew of each observation dated from ``lookback`` exchange sessions
    before the session on, plus each series' latest known observation however old; sorted by
    id and observation. Pure: the feature input ``macro/series`` applies it per session."""
    if lookback < 0:
        raise ValueError(f"lookback must be >= 0, got {lookback}")
    first = sessions_ending(session, lookback + 1)[0]
    known = vintages[vintages["vintage_date"] <= session]
    newest = known.groupby("instrument_id")["obs_date"].transform("max")
    window = known[(known["obs_date"] >= first) | (known["obs_date"] == newest)]
    return latest_vintages(window, session)
