"""Load a rollup's inputs through ``algotrade.data`` (never storage) for a range of sessions,
and hand each session only the rows it may see (point in time).

Each input table has one loader (``LOADERS``). A loader reads once for the whole range and
answers ``at(session, lookback)`` with a frame sorted by ``session_date``:

- ``bars/1d``          ``data.prices.session_bars``: split-adjusted as of each session (never
                       total return), the session plus ``lookback`` earlier sessions; ``None``
                       when the session has no bars stored
- ``events/earnings``  ``data.events.stored_events``: every calendar snapshot stored on or
                       before the session (what was known then); ``None`` when there is none
- ``chains/*``         ``data.chains``: the session's own partition, read per session (chains
                       are large; a lookback is not supported)
- ``events/dividend``, ``events/split``
                       ``data.events.read_events`` by EVENT date: events with an event date
                       from ``lookback`` sessions before the session up to the session (never a
                       later one, e.g. a declared future ex-date); ``event_date`` added, the
                       stored partition date dropped (it says when we learned it, not when it
                       happened); an empty frame when there are none
- ``instruments/shares``
                       ``data.shares.share_facts``: every stored share-count fact FILED on
                       or before the session (point in time by filing date, whenever it was
                       stored), sorted by ``filed``; ``None`` when there is none
- ``rates/treasury``   ``data.rates.curve``: the curve the session sees (latest on or before;
                       ``curve_date`` and ``pre_snapshot`` added); ``None`` when none is stored
- ``rollups/instrument/<name>@v<N>``
                       another rollup's output (``data.rollups``) for the session plus
                       ``lookback`` earlier sessions; ``None`` when the session has no rows.
                       Rows this run computed (``produced``) replace stored ones for their
                       sessions, so a dependency computed in memory is used without a write.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import numpy as np
import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.data.chains import chain_status, option_quotes, underlying_quotes
from algotrade.data.events import read_events, stored_events
from algotrade.data.prices import SessionBars, session_bars
from algotrade.data.rates import TABLE as TREASURY
from algotrade.data.rates import curve
from algotrade.data.rollups import rollup_rows
from algotrade.data.shares import TABLE as SHARES
from algotrade.data.shares import share_facts
from algotrade.features.framework.graph import is_rollup_table


class Loaded(Protocol):
    def at(self, session: date, lookback: int) -> pd.DataFrame | None: ...


type Loader = Callable[[StoreReader, Sequence[date], int], Loaded]
# Frames computed in this run, by rollup table and session (``None``: computed, no rows).
type Produced = Mapping[str, Mapping[date, pd.DataFrame | None]]


def sessions_before(day: date, n: int) -> date:
    """The exchange session ``n`` sessions before ``day`` (``day`` itself when ``n`` is 0)."""
    return sessions_ending(day, n + 1)[0]


@dataclass(frozen=True)
class _Bars:
    bars: SessionBars | None

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        if self.bars is None:
            return None
        window = self.bars.window(sessions_before(session, lookback), session)
        if window.empty or window["session_date"].iloc[-1] != session:
            return None
        return window


def _bars(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    try:
        loaded = session_bars(reader, sessions_before(sessions[0], lookback), sessions[-1])
    except MissingDataError:
        loaded = None
    return _Bars(loaded)


@dataclass(frozen=True)
class _Snapshots:
    frame: pd.DataFrame  # sorted by session_date
    days: np.ndarray

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        end = np.searchsorted(self.days, np.datetime64(session, "D"), side="right")
        return self.frame.iloc[:end] if end else None


def _event_snapshots(table: str) -> Loader:
    def load(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
        frame = stored_events(reader, table, sessions[-1])
        days = pd.to_datetime(frame["session_date"]).to_numpy(dtype="datetime64[D]")
        return _Snapshots(frame, days)

    return load


def _share_facts(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    frame = share_facts(reader)
    return _Snapshots(frame, _days(frame["filed"]) if len(frame) else np.array([], "datetime64[D]"))


@dataclass(frozen=True)
class _Partition:
    read: Callable[[date], pd.DataFrame | None]

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        if lookback:
            raise ValueError("chain inputs are one session's partition: lookback must be 0")
        return self.read(session)


def _partition(read: Callable[[StoreReader, date], pd.DataFrame | None]) -> Loader:
    def load(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
        return _Partition(lambda session: read(reader, session))

    return load


@dataclass(frozen=True)
class _Window:
    """Rows sorted by a date (``days``); ``at`` slices ``lookback`` sessions up to the session."""

    frame: pd.DataFrame
    days: np.ndarray  # datetime64[D], one per row, ascending
    need_session: bool  # None unless the session itself has rows

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        first = np.datetime64(sessions_before(session, lookback), "D")
        lo = int(np.searchsorted(self.days, first, side="left"))
        hi = int(np.searchsorted(self.days, np.datetime64(session, "D"), side="right"))
        if self.need_session and (hi == lo or self.days[hi - 1] != np.datetime64(session, "D")):
            return None
        return self.frame.iloc[lo:hi]


def _days(values: pd.Series) -> np.ndarray:
    return pd.to_datetime(values).to_numpy(dtype="datetime64[D]")


def _events_by_date(table: str) -> Loader:
    def load(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
        first = sessions_before(sessions[0], lookback)
        frame = read_events(reader, table, first, sessions[-1]).frame
        frame = frame.drop(columns=[c for c in ("session_date",) if c in frame.columns])
        frame = frame.assign(event_date=pd.to_datetime(frame["ts"], utc=True).dt.date)
        frame = frame.sort_values(["event_date", "instrument_id"], kind="stable")
        frame = frame.reset_index(drop=True)
        return _Window(frame, _days(frame["event_date"]), need_session=False)

    return load


def _treasury(reader: StoreReader, session: date) -> pd.DataFrame | None:
    try:
        seen = curve(reader, session)
    except MissingDataError:
        return None
    return seen.frame.assign(curve_date=seen.curve_date, pre_snapshot=seen.pre_snapshot)


def _rollup_rows(
    reader: StoreReader, table: str, sessions: Sequence[date], lookback: int, produced: Produced
) -> Loaded:
    stored = rollup_rows(reader, table, sessions_before(sessions[0], lookback), sessions[-1])
    mine = produced.get(table, {})
    parts = [] if stored is None else [stored[~stored["session_date"].isin(list(mine))]]
    parts += [f.assign(session_date=day) for day, f in sorted(mine.items()) if f is not None]
    parts = [p for p in parts if not p.empty]
    if not parts:
        empty = pd.DataFrame({"instrument_id": [], "session_date": []})
        return _Window(empty, np.array([], dtype="datetime64[D]"), need_session=True)
    frame = pd.concat(parts, ignore_index=True)
    frame = frame.sort_values(["session_date", "instrument_id"], kind="stable")
    frame = frame.reset_index(drop=True)
    return _Window(frame, _days(frame["session_date"]), need_session=True)


LOADERS: Mapping[str, Loader] = {
    "bars/1d": _bars,
    "events/earnings": _event_snapshots("events/earnings"),
    "chains/status": _partition(chain_status),
    "chains/option_quotes": _partition(option_quotes),
    "chains/underlying_quotes": _partition(underlying_quotes),
    "events/dividend": _events_by_date("events/dividend"),
    "events/split": _events_by_date("events/split"),
    TREASURY: _partition(_treasury),
    SHARES: _share_facts,
}


def has_loader(table: str) -> bool:
    """Whether the framework can load ``table`` (a ``LOADERS`` table or any rollup table)."""
    return table in LOADERS or is_rollup_table(table)


def load_input(
    reader: StoreReader,
    table: str,
    sessions: Sequence[date],
    lookback: int,
    produced: Produced | None = None,
) -> Loaded:
    if is_rollup_table(table):
        return _rollup_rows(reader, table, sessions, lookback, produced or {})
    if table not in LOADERS:
        raise KeyError(f"no input loader for {table!r}; add one to features/framework/inputs.py")
    return LOADERS[table](reader, sessions, lookback)
