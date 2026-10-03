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
from algotrade.data.events import stored_events
from algotrade.data.prices import SessionBars, session_bars


class Loaded(Protocol):
    def at(self, session: date, lookback: int) -> pd.DataFrame | None: ...


type Loader = Callable[[StoreReader, Sequence[date], int], Loaded]


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


LOADERS: Mapping[str, Loader] = {
    "bars/1d": _bars,
    "events/earnings": _event_snapshots("events/earnings"),
    "chains/status": _partition(chain_status),
    "chains/option_quotes": _partition(option_quotes),
    "chains/underlying_quotes": _partition(underlying_quotes),
}


def load_input(reader: StoreReader, table: str, sessions: Sequence[date], lookback: int) -> Loaded:
    if table not in LOADERS:
        raise KeyError(f"no input loader for {table!r}; add one to features/framework/inputs.py")
    return LOADERS[table](reader, sessions, lookback)
