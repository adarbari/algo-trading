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
- ``events/earnings``  ``events.stored_events``: every calendar row known on or before the
                       session (``known_from``, else the session that stored it: ADR 0050),
                       as stored (what was known then); ``None`` when there is none
- ``events/fund_nav``  ``events.stored_events``: every closed-end fund NAV row known on or before
                       the session (``known_from``: the session after the NAV date, later for a
                       restated NAV), as stored, so a compute reads NAVs by their own date
                       (``cef_nav@v1``; the Tiingo licence is personal, ADR 0028); ``None`` when
                       none is stored
- ``holdings/etf_shares``
                       ``funds.shares.share_versions``: every iShares shares-outstanding row (every
                       version of a restated count) known on or before the session, sorted by
                       ``known_from``; a compute keeps the latest version of each fund and
                       ``as_of`` (``etf_flows@v1``); ``None`` when none is stored
- ``filings/walk``     ``events.filing_walks``: the clean daily-index walks of the filings task
                       (``session_date`` of the run, ``walked_to``), only runs of sessions on or
                       before the session; ``None`` when there is none. How far the stored
                       filings are complete, which a row cannot say
- ``chains/*``         ``chains``: the session's own partition, read per session (chains are
                       large; a lookback is not supported)
- ``events/dividend_declared``
                       ``events/dividend`` by KNOWLEDGE date (``events.stored_events``): every
                       row stored in a partition on or before the session, as stored (what was
                       known then, including a declared future ex-date), with an ex-date on or
                       after the chunk's first session; ``None`` when there is none. The same
                       table as ``events/dividend``, a second read of it
- ``events/dividend``, ``events/split``, ``events/index_change``
                       ``events.events_by_event_date``: events with an event date from
                       ``lookback`` sessions before the session up to the session (never a
                       later one, e.g. a declared future ex-date), with ``event_date``; an
                       empty frame when there are none
- ``events/filing``    ``events.events_by_acceptance``: the SEC event filings that became known
                       (the first session closing after SEC's acceptance, recomputed from the
                       stored instant, not the stored ``known_from``) from ``lookback``
                       sessions before the session up to it, with ``event_date`` that session
                       (``filing_events@v1``; ADR 0050 amendment, EB H4); an empty frame when
                       there are none
- ``events/insider_transaction``
                       ``insiders.buyer_histories``: per session, the open-market lines (codes P
                       and S) known by it of each (issuer, owner) with a purchase known in the
                       last 30 calendar days, each session read as the one rule says (a restated
                       line shows its old version until its own ``known_from``), tagged
                       ``as_of``; ``at(session)`` returns the session's own view only (lookback
                       is not supported; ``insider_buys@v1``, EB E6)
- ``events/short_interest``
                       FINRA short interest by the session it became public (``known_from``, set
                       from the publication schedule at ingestion), from ``lookback`` sessions
                       before the session up to it; an empty frame when none
                       (``short_interest@v1``, EB E6; the table is no_ml)
- ``instruments/shares``
                       ``shares.share_facts``: every stored share-count and financial (revenue,
                       net income, diluted EPS) fact FILED on or before the session (point in
                       time by filing date), sorted by ``filed``; ``None`` when there is none
- ``instruments/shares_accepted``
                       the same facts counted from the session each became public (``shares.
                       known_from``: the first session whose close is after SEC's
                       acceptance of the filing, else the session after ``filed``), sorted by it
                       (``financials@v3``, ``fundamentals@v4``; ADR 0067 amendment)
- ``instruments/statements``
                       ``statements.reading.statement_facts``: every stored statement line (cost
                       of revenue, operating income, cash flow, balance sheet..., one row per
                       tag, period and filing) FILED on or before the session (point in time by
                       filing date, ADR 0067), sorted by ``filed``, without the stamp columns;
                       ``None`` when there is none
- ``instruments/statements_accepted``
                       the statement lines counted from ``known_from`` as above
- ``analyst/estimate_snapshots``
                       ``analyst.reading.snapshot_window``: our own history of analyst data
                       (ADR 0068), every kind with its coverage markers, for the session plus
                       ``lookback`` earlier sessions: the latest version of each row the session
                       may see (``session_date`` on or before it and published before the next
                       session's open, so a late re-run never reaches back); ``None`` when none
- ``instruments/reference``
                       ``reference.instruments``: the snapshot the session sees, only
                       ``instrument_id``, ``security_type`` and, when stored, the fund facts
                       ``symbol``, ``name``, ``is_leveraged`` and ``is_inverse`` (read per
                       session); ``None`` when there is none
- ``holdings/etf``     ``funds.holdings.funds_holdings``: the latest stored holdings on or before
                       the session (public by then: ``as_of`` and ``filed``) of the leveraged and
                       inverse funds of the reference snapshot the session sees, by fund and rank
                       (read per session); ``None`` when none has holdings stored
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
- ``instruments/company``
                       ``reference.company_sectors``: ``instrument_id``, ``sector``,
                       ``industry`` and ``sic`` from the company snapshot on or before the session
                       (read per session); ``None`` before the first snapshot (a later one
                       would show company facts not known then)
- ``rates/treasury``   ``rates.curve_as_rows``: the curve the session sees (latest on or before;
                       ``curve_date`` and ``pre_snapshot`` added); ``None`` when none is stored
- ``volatility/ibkr_iv30``
                       ``volatility.ibkr_iv30``: IBKR's vols for the session plus ``lookback``
                       earlier sessions; ``None`` when the session has no rows (no IBKR run)
- ``volatility/vx_futures``
                       ``volatility.vx_futures``: the VIX futures curves the session knew
                       (``known_from <= session``, the latest version per contract and trade
                       date) of the ``lookback`` sessions before it; ``None`` when none
- ``macro/series``     ``macro.series.known_window`` over the group's series (``Input.ids``;
                       all when empty): each observation as the session knew it (the latest
                       vintage with ``vintage_date`` on or before the session: point in time
                       by vintage, ADR 0048), dated within ``lookback`` sessions, plus each
                       series' latest known observation however old; sorted by id and
                       observation; ``None`` when no vintage is known by the session
- ``rollups/instrument/<name>@v<N>``, ``rollups/market/<name>@v<N>``
                       another group's stored output (``rollups.rollup_rows``) for the session
                       plus ``lookback`` earlier sessions; ``None`` when the session has no
                       rows. Rows this run computed (``produced``) replace stored ones for their
                       sessions, so a dependency computed in memory is used without a write.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.fields import COMPANY_TABLE, group_of_table
from algotrade.core.time.calendar import sessions_between, sessions_ending
from algotrade.data.analyst.reading import KINDS as ANALYST_KINDS
from algotrade.data.analyst.reading import TABLE as ANALYST
from algotrade.data.analyst.reading import snapshot_window
from algotrade.data.chains import chain_status, option_quotes, underlying_quotes
from algotrade.data.events import (
    events_by_acceptance,
    events_by_event_date,
    filing_walks,
    read_events,
    stored_events,
)
from algotrade.data.funds.holdings import TABLE as HOLDINGS
from algotrade.data.funds.holdings import funds_holdings
from algotrade.data.funds.shares import TABLE as ETF_SHARES
from algotrade.data.funds.shares import share_versions
from algotrade.data.insiders.reading import TABLE as INSIDERS
from algotrade.data.insiders.reading import buyer_histories
from algotrade.data.macro.series import TABLE as MACRO_SERIES
from algotrade.data.macro.series import known_window, stored_vintages
from algotrade.data.prices import DateWindow, SessionBars, session_bars, window_closes
from algotrade.data.rates import TABLE as TREASURY
from algotrade.data.rates import curve_as_rows
from algotrade.data.reference import (
    UNIVERSE_TABLE,
    company_sectors,
    ids_for_symbols,
    instruments,
    load_universe,
    symbol_ids,
)
from algotrade.data.rollups import rollup_rows
from algotrade.data.shares import TABLE as SHARES
from algotrade.data.shares import known_from, share_facts
from algotrade.data.statements.reading import TABLE as STATEMENTS
from algotrade.data.statements.reading import statement_facts
from algotrade.data.volatility import IBKR_IV30, VX_FUTURES, ibkr_iv30, known_vx, vx_futures
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import KNOWN_FROM


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


def first_stored_session(reader: StoreReader, table: str) -> date | None:
    """The first session with a stored partition of ``table`` (None: never stored): when an input
    of a feature began, which a study of old sessions needs to tell a value known then from one
    a later snapshot would put on it."""
    return min(reader.dates(table), default=None)


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


def _event_snapshots(table: str, from_first_session: bool = False) -> Loader:
    """Every row of ``table`` known on or before each session (ADR 0050). With
    ``from_first_session`` only rows whose event date (``ts``) is on or after the chunk's
    first session are kept: a consumer that reads declared future events (the next ex-date)
    never needs an event before the sessions it computes."""

    def load(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
        frame = stored_events(reader, table, sessions[-1])
        if from_first_session and len(frame):
            first = pd.Timestamp(sessions[0], tz="UTC")
            frame = frame[pd.to_datetime(frame["ts"], utc=True) >= first].reset_index(drop=True)
        return _Snapshots(frame, _days(frame[KNOWN_FROM]))  # known on or before

    return load


def _etf_share_versions(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    """Every version of every fund's shares-outstanding row known by the chunk's last session,
    ordered by ``known_from``: ``at`` keeps those known by the session (ADR 0050)."""
    frame = share_versions(reader, sessions[-1])
    return _Snapshots(frame, _days(frame["known_from"]) if len(frame) else np.array([], "M8[D]"))


def _filing_walks(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    frame = filing_walks(reader)
    return _Snapshots(frame, _days(frame["session_date"]) if len(frame) else np.array([], "M8[D]"))


def _share_facts(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    frame = share_facts(reader)
    return _Snapshots(frame, _days(frame["filed"]) if len(frame) else np.array([], "datetime64[D]"))


def _by_known_from(frame: pd.DataFrame) -> _Snapshots:
    """``frame`` ordered by the session each fact became public (``shares.known_from``)."""
    if frame.empty:
        return _Snapshots(frame, np.array([], "datetime64[D]"))
    days = _days(known_from(frame))
    order = np.argsort(days, kind="stable")
    return _Snapshots(frame.iloc[order].reset_index(drop=True), days[order])


def _share_facts_accepted(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    return _by_known_from(share_facts(reader))


def _statement_facts_accepted(
    reader: StoreReader, sessions: Sequence[date], lookback: int
) -> Loaded:
    frame = statement_facts(reader, sessions[-1], columns=[*STATEMENT_COLUMNS, "accepted_ts"])
    return _by_known_from(frame)


def _statement_facts(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    frame = statement_facts(reader, sessions[-1], columns=STATEMENT_COLUMNS)
    return _Snapshots(frame, _days(frame["filed"]) if len(frame) else np.array([], "datetime64[D]"))


def _analyst_snapshots(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    return snapshot_window(reader, ANALYST_KINDS, sessions_before(sessions[0], lookback))


@dataclass(frozen=True)
class _Vintages:
    """Every stored vintage, read once, sorted by ``vintage_date`` (``days``); ``at`` is what
    the session knew (``macro.series.known_window``: the latest vintage per observation, the
    observations of the last ``lookback`` sessions and each series' latest)."""

    frame: pd.DataFrame
    days: np.ndarray

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        end = int(np.searchsorted(self.days, np.datetime64(session, "D"), side="right"))
        return known_window(self.frame.iloc[:end], session, lookback) if end else None


def _macro_series(
    reader: StoreReader, sessions: Sequence[date], lookback: int, ids: Sequence[str]
) -> Loaded:
    frame = stored_vintages(reader, ids)
    days = _days(frame["vintage_date"]) if len(frame) else np.array([], "datetime64[D]")
    return _Vintages(frame, days)


@dataclass(frozen=True)
class _VxCurves:
    """Every stored version of the VIX futures, read once; ``at`` is the curves the session
    knew (``known_from <= session``, the latest version per contract and trade date) over its
    ``lookback`` sessions of trade dates; ``None`` when none."""

    frame: pd.DataFrame

    def at(self, session: date, lookback: int) -> pd.DataFrame | None:
        first = sessions_before(session, lookback)
        window = self.frame[
            (self.frame["session_date"] >= first) & (self.frame["session_date"] <= session)
        ]
        rows = known_vx(window, session)
        return (
            None
            if rows.empty
            else rows.sort_values(["session_date", "expiry"]).reset_index(drop=True)
        )


def _vx_curves(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    first = sessions_before(sessions[0], lookback)
    return _VxCurves(vx_futures(reader, first, sessions[-1], versions=True))


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


def _filings(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    first = sessions_before(sessions[0], lookback)
    frame = events_by_acceptance(reader, "events/filing", first, sessions[-1])
    return _Window(frame, _days(frame["event_date"]), need_session=False)


def _insider_views(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    frame = buyer_histories(reader, sessions)
    return _Window(frame, _days(frame["as_of"]), need_session=False)


SHORT_INTEREST_MARGIN = timedelta(days=15)  # a settlement date precedes its publication


def _short_interest(reader: StoreReader, sessions: Sequence[date], lookback: int) -> Loaded:
    first = sessions_before(sessions[0], lookback)
    stored = read_events(
        reader, "events/short_interest", first - SHORT_INTEREST_MARGIN, sessions[-1],
        through=sessions[-1],
    ).frame  # fmt: skip
    if stored.empty:
        stored = pd.DataFrame({"instrument_id": [], KNOWN_FROM: []})
    stored = stored[pd.to_datetime(stored[KNOWN_FROM]) >= pd.Timestamp(first)]
    frame = stored.sort_values([KNOWN_FROM, "instrument_id"], kind="stable").reset_index(drop=True)
    return _Window(frame, _days(frame[KNOWN_FROM]), need_session=False)


SHARES_ACCEPTED = f"{SHARES}_accepted"  # instruments/shares counted from its acceptance session
STATEMENTS_ACCEPTED = f"{STATEMENTS}_accepted"
STATEMENT_COLUMNS = ["concept", "tag", "period_start", "period_end", "filed", "value", "accn"]
REFERENCE_FACTS = (
    "instrument_id", "security_type", "symbol", "name", "is_leveraged", "is_inverse", "cik",
    "share_class_figi",
)  # fmt: skip


def _reference_facts(reader: StoreReader, session: date) -> pd.DataFrame | None:
    try:
        frame = instruments(reader, session)
    except MissingDataError:
        return None
    if "security_type" not in frame.columns:
        return None
    return frame[[c for c in REFERENCE_FACTS if c in frame.columns]]


def _leveraged_holdings(reader: StoreReader, session: date) -> pd.DataFrame | None:
    """The session's leveraged and inverse funds' latest holdings (``None``: no reference
    snapshot, no such fund, or none of them has holdings stored)."""
    try:
        frame = instruments(reader, session)
    except MissingDataError:
        return None
    geared = pd.Series(False, index=frame.index)
    for flag in ("is_leveraged", "is_inverse"):
        if flag in frame.columns:
            geared |= frame[flag].fillna(False).astype(bool)
    return funds_holdings(reader, frame.loc[geared, "instrument_id"].astype(str).tolist(), session)


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
    "events/fund_nav": _event_snapshots("events/fund_nav"),
    ETF_SHARES: _etf_share_versions,
    "filings/walk": _filing_walks,
    "chains/status": _partition(chain_status),
    "chains/option_quotes": _partition(option_quotes),
    "chains/underlying_quotes": _partition(underlying_quotes),
    "events/dividend": _events_by_date("events/dividend"),
    "events/dividend_declared": _event_snapshots("events/dividend", from_first_session=True),
    "events/split": _events_by_date("events/split"),
    "events/index_change": _events_by_date("events/index_change"),
    "events/filing": _filings,
    INSIDERS: _insider_views,
    "events/short_interest": _short_interest,
    TREASURY: _partition(curve_as_rows),
    SHARES: _share_facts,
    SHARES_ACCEPTED: _share_facts_accepted,
    STATEMENTS: _statement_facts,
    STATEMENTS_ACCEPTED: _statement_facts_accepted,
    ANALYST: _analyst_snapshots,
    "instruments/reference": _partition(_reference_facts),
    HOLDINGS: _partition(_leveraged_holdings),
    "instruments/symbol_ids": _partition(symbol_ids),
    UNIVERSE_TABLE: _partition(_universe),
    COMPANY_TABLE: _partition(company_sectors),
    IBKR_IV30: _ibkr_vols,
    VX_FUTURES: _vx_curves,
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
