"""Feature inputs: what a feature group reads, asked for by table name, point in time.

The feature framework (``features/framework/runner.py``) never reads storage or a domain
reader itself: it calls ``load_input(reader, table, sessions, lookback)`` once per chunk of
sessions and then ``at(session, lookback)`` per session, which returns a frame sorted by
``session_date`` holding only rows the session may see (or ``None``). Each table's read lives
in its owner here in ``algotrade.data``; ``INPUTS`` maps the table to it:

- ``bars/1d``          ``prices.session_bars``: split-adjusted as of each session (never total
                       return), the session plus ``lookback`` earlier sessions; ``None`` when
                       the session has no bars stored; ``MissingDataError`` when a session in
                       the window (on or after the first stored one) has no bars: a rollup
                       never computes over a gap (ADR 0039). With ``symbols`` (``Input.symbols``)
                       only the ids those tickers resolve to in the reference snapshot each
                       session of the chunk sees (``reference.ids_for_symbols``, the union: a
                       superset of each session's), so a market group reading a few tickers
                       does not load every instrument (ADR 0047); ``None`` only when the session
                       has no bars stored, as for a whole read (an empty frame when none of the
                       tickers resolves or has bars)
- ``bars/1d`` windows  ``prices.window_closes`` (``Input.windows``: fixed date ranges, handed to
                       ``compute`` as ``bars/1d#windows``): the closes of each window from its
                       first session to the earlier of its last and the session, column-pruned
                       and compact, ``window`` / ``day`` / ``instrument_id`` / ``close``, of
                       the instruments with a bar in the chunk; a window before the stored
                       history has no rows; ``MissingDataError`` when a session of a window
                       (on or after the first stored one) has no bars (ADR 0039); ``None`` when
                       no window has a row yet. For a history years back that a trailing
                       lookback would load whole (every instrument's every column)
- ``events/earnings``  ``events.stored_events``: every calendar snapshot stored on or before
                       the session (what was known then); ``None`` when there is none
- ``chains/*``         ``chains``: the session's own partition, read per session (chains are
                       large; a lookback is not supported)
- ``events/dividend``, ``events/split``
                       ``events.events_by_event_date``: events with an event date from
                       ``lookback`` sessions before the session up to the session (never a
                       later one, e.g. a declared future ex-date), with ``event_date``; an
                       empty frame when there are none
- ``instruments/shares``
                       ``shares.share_facts``: every stored share-count and financial (revenue,
                       net income, diluted EPS) fact FILED on or before the session (point in
                       time by filing date), sorted by ``filed``; ``None`` when there is none
- ``instruments/reference``
                       ``reference.instruments``: the snapshot the session sees, only
                       ``instrument_id`` and ``security_type`` (read per session); ``None`` when
                       there is none
- ``universe``         ``reference.load_universe``: the universe snapshot the session sees
                       (read per session); ``None`` when there is none, or when the only one
                       was taken after the session (``pre_snapshot``: a later list of names
                       would count today's survivors; ADR 0047)
- ``instruments/symbol_ids``
                       ``reference.symbol_ids``: ``symbol`` -> ``instrument_id`` (and
                       ``pre_snapshot``) from the reference snapshot the session sees, so a
                       market-entity group finds SPY without building an id (read per
                       session); ``None`` when no reference is stored. A lookup only, never
                       a population: it may come from a later snapshot (``pre_snapshot``), so
                       a group counts names over ``universe``, never over these rows
- ``rates/treasury``   ``rates.curve_as_rows``: the curve the session sees (latest on or before;
                       ``curve_date`` and ``pre_snapshot`` added); ``None`` when none is stored
- ``volatility/ibkr_iv30``
                       ``volatility.ibkr_iv30``: IBKR's vols for the session plus ``lookback``
                       earlier sessions; ``None`` when the session has no rows (no IBKR run)
- ``macro/series``     ``macro.series.stored_vintages``: every vintage of the group's series
                       (``Input.ids``; all when empty) with ``vintage_date`` on or before the
                       session (point in time by vintage, ADR 0048), sorted by
                       ``vintage_date`` (the group keeps the latest vintage per observation);
                       ``None`` when there is none
- ``rollups/instrument/<name>@v<N>``, ``rollups/market/<name>@v<N>``
                       another group's stored output (``rollups.rollup_rows``) for the session
                       plus ``lookback`` earlier sessions; ``None`` when the session has no
                       rows. Rows this run computed (``produced``) replace stored ones for their
                       sessions, so a dependency computed in memory is used without a write.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import numpy as np
import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import group_of_table
from algotrade.core.time.calendar import sessions_between, sessions_ending
from algotrade.data.chains import chain_status, option_quotes, underlying_quotes
from algotrade.data.events import events_by_event_date, stored_events
from algotrade.data.macro.series import TABLE as MACRO_SERIES
from algotrade.data.macro.series import stored_vintages
from algotrade.data.prices import DateWindow, SessionBars, session_bars, window_closes
from algotrade.data.rates import TABLE as TREASURY
from algotrade.data.rates import curve_as_rows
from algotrade.data.reference import (
    UNIVERSE_TABLE,
    ids_for_symbols,
    instruments,
    load_universe,
    symbol_ids,
)
from algotrade.data.rollups import rollup_rows
from algotrade.data.shares import TABLE as SHARES
from algotrade.data.shares import share_facts
from algotrade.data.volatility import IBKR_IV30, ibkr_iv30
from algotrade.storage.tables.readers import StoreReader


class Loaded(Protocol):
    def at(self, session: date, lookback: int) -> pd.DataFrame | None: ...


type Loader = Callable[[StoreReader, Sequence[date], int], Loaded]
# A loader that reads only some instruments (``Input.ids``; all when empty).
type IdLoader = Callable[[StoreReader, Sequence[date], int, Sequence[str]], Loaded]
# Frames computed in this run, by group table and session (``None``: computed, no rows).
type Produced = Mapping[str, Mapping[date, pd.DataFrame | None]]


def sessions_before(day: date, n: int) -> date:
    """The exchange session ``n`` sessions before ``day`` (``day`` itself when ``n`` is 0)."""
    return sessions_ending(day, n + 1)[0]


def _days(values: pd.Series) -> np.ndarray:
    return pd.to_datetime(values).to_numpy(dtype="datetime64[D]")


@dataclass(frozen=True)
class _Bars:
    bars: SessionBars | None
    stored: frozenset[date] = frozenset()  # every session with a bars partition
    # Narrowed to some instruments (``symbols``): the session has input when it has a bars
    # partition, even if those instruments have no bar on it (as for a whole-store read).
    narrowed: bool = False

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        if self.bars is None:
            return None
        window = self.bars.window(sessions_before(session, lookback), session)
        if self.narrowed:
            if session not in self.stored:
                return None
        elif window.empty or window["session_date"].iloc[-1] != session:
            return None
        first = min(self.stored)
        missing = [
            d for d in sessions_ending(session, lookback + 1) if d >= first and d not in self.stored
        ]
        if missing:
            days = ", ".join(d.isoformat() for d in missing)
            raise MissingDataError(
                "bars/1d",
                f"no bars for {days} in the {lookback + 1}-session window of {session}",
                f"algotrade-ingest bars --date {missing[0].isoformat()}",
            )
        return window


BARS = "bars/1d"


def _bars(
    reader: StoreReader,
    sessions: Sequence[date],
    lookback: int,
    instruments: Sequence[str] | None = None,
) -> Loaded:
    first = sessions_before(sessions[0], lookback)
    stored = frozenset(reader.dates(BARS))
    narrowed = instruments is not None
    empty = _Bars(SessionBars.empty(), stored, narrowed) if narrowed and stored else _Bars(None)
    if narrowed and not instruments:
        return empty  # never a read filtered on no ids (a typed empty filter fails in Parquet)
    try:
        loaded = session_bars(reader, first, sessions[-1], instruments)
    except MissingDataError:
        return empty
    return _Bars(loaded, stored, narrowed)


@dataclass(frozen=True)
class _Snapshots:
    """Rows sorted by a known-on date (``days``); ``at`` keeps those on or before the session."""

    frame: pd.DataFrame
    days: np.ndarray

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        end = np.searchsorted(self.days, np.datetime64(session, "D"), side="right")
        return self.frame.iloc[:end] if end else None


@dataclass(frozen=True)
class _Closes:
    """Window closes sorted by ``day``: ``at`` is the prefix on or before the session."""

    frame: pd.DataFrame
    days: np.ndarray  # datetime64[D], one per row, ascending

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        end = int(np.searchsorted(self.days, np.datetime64(session, "D"), side="right"))
        return self.frame.iloc[:end] if end else None


def _bar_windows(
    reader: StoreReader, sessions: Sequence[date], windows: Sequence[DateWindow]
) -> Loaded:
    """The windows' closes through the last session of the chunk, of the instruments with a bar
    in the chunk (a name gone before it has no row to compute). A window with a session
    missing (on or after the first stored one) is a gap: ADR 0039."""
    stored = frozenset(reader.dates("bars/1d"))
    if stored:
        for first, last in windows:
            end = min(last, sessions[-1])
            missing = [d for d in sessions_between(max(first, min(stored)), end) if d not in stored]
            if missing:
                raise MissingDataError(
                    "bars/1d",
                    f"no bars for {missing[0]} in the window {first}..{end}",
                    f"algotrade-ingest bars --date {missing[0].isoformat()}",
                )
    present = reader.table_range("bars/1d", sessions[0], sessions[-1], None, None, ("close",))
    alive = [] if present is None else sorted(present["instrument_id"].astype(str).unique())
    frame = window_closes(reader, windows, sessions[-1], alive)
    return _Closes(frame, frame["day"].to_numpy(dtype="datetime64[D]"))


def _event_snapshots(table: str) -> Loader:
    def load(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
        frame = stored_events(reader, table, sessions[-1])
        return _Snapshots(frame, _days(frame["session_date"]))

    return load


def _share_facts(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    frame = share_facts(reader)
    return _Snapshots(frame, _days(frame["filed"]) if len(frame) else np.array([], "datetime64[D]"))


def _macro_series(
    reader: StoreReader, sessions: Sequence[date], lookback: int, ids: Sequence[str]
) -> Loaded:
    frame = stored_vintages(reader, ids)
    days = _days(frame["vintage_date"]) if len(frame) else np.array([], "datetime64[D]")
    return _Snapshots(frame, days)


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


def _events_by_date(table: str) -> Loader:
    def load(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
        first = sessions_before(sessions[0], lookback)
        frame = events_by_event_date(reader, table, first, sessions[-1])
        return _Window(frame, _days(frame["event_date"]), need_session=False)

    return load


def _security_types(reader: StoreReader, session: date) -> pd.DataFrame | None:
    try:
        frame = instruments(reader, session)
    except MissingDataError:
        return None
    return frame[["instrument_id", "security_type"]] if "security_type" in frame.columns else None


def _universe(reader: StoreReader, session: date) -> pd.DataFrame | None:
    try:
        universe = load_universe(reader, session)
    except MissingDataError:
        return None
    return None if universe.pre_snapshot else universe.frame


def _ibkr_vols(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    frame = ibkr_iv30(reader, sessions_before(sessions[0], lookback), sessions[-1])
    return _Window(frame, _days(frame["session_date"]), need_session=True)


def _group_rows(
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


INPUTS: Mapping[str, Loader] = {
    BARS: _bars,
    "events/earnings": _event_snapshots("events/earnings"),
    "chains/status": _partition(chain_status),
    "chains/option_quotes": _partition(option_quotes),
    "chains/underlying_quotes": _partition(underlying_quotes),
    "events/dividend": _events_by_date("events/dividend"),
    "events/split": _events_by_date("events/split"),
    TREASURY: _partition(curve_as_rows),
    SHARES: _share_facts,
    "instruments/reference": _partition(_security_types),
    "instruments/symbol_ids": _partition(symbol_ids),
    UNIVERSE_TABLE: _partition(_universe),
    IBKR_IV30: _ibkr_vols,
}


ID_INPUTS: Mapping[str, IdLoader] = {MACRO_SERIES: _macro_series}

# Tables that also serve fixed windows (``Input.windows``) rather than a trailing lookback.
type WindowLoader = Callable[[StoreReader, Sequence[date], Sequence[DateWindow]], Loaded]
WINDOW_INPUTS: Mapping[str, WindowLoader] = {"bars/1d": _bar_windows}


def is_group_table(table: str) -> bool:
    """A stored feature group's table (``rollups/instrument/<name>@v<N>`` or, a market-entity
    group, ``rollups/market/<name>@v<N>``: ADR 0047)."""
    return group_of_table(table) is not None


def has_input(table: str) -> bool:
    """Whether ``table`` can be a feature input (an ``INPUTS`` table or any group table)."""
    return table in INPUTS or table in ID_INPUTS or is_group_table(table)


def load_input(
    reader: StoreReader,
    table: str,
    sessions: Sequence[date],
    lookback: int,
    produced: Produced | None = None,
    ids: Sequence[str] = (),
    symbols: Sequence[str] = (),
    windows: Sequence[DateWindow] = (),
) -> Loaded:
    """``table`` for ``sessions`` (ascending) and ``lookback`` earlier sessions, read once.
    ``ids``: only these instruments, for a table that reads by id (``ID_INPUTS``);
    ``symbols``: only the ids these tickers resolve to (``bars/1d`` only);
    ``windows``: fixed date ranges instead of a lookback (``WINDOW_INPUTS``)."""
    if windows:
        if table not in WINDOW_INPUTS:
            raise ValueError(f"{table!r} has no fixed windows: only {sorted(WINDOW_INPUTS)}")
        return WINDOW_INPUTS[table](reader, sessions, windows)
    if symbols:
        if table != BARS or ids:
            raise ValueError(f"{table!r}: symbols are only for {BARS!r}, and never with ids")
        return _bars(reader, sessions, lookback, ids_for_symbols(reader, sessions, symbols))
    if table in ID_INPUTS:
        return ID_INPUTS[table](reader, sessions, lookback, ids)
    if ids:
        raise ValueError(f"{table!r} is read whole: ids are only for {sorted(ID_INPUTS)}")
    if is_group_table(table):
        return _group_rows(reader, table, sessions, lookback, produced or {})
    if table not in INPUTS:
        raise KeyError(f"no feature input for {table!r}; add its read to data/feature_inputs.py")
    return INPUTS[table](reader, sessions, lookback)
