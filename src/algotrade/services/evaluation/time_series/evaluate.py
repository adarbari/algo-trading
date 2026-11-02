"""One time-series edge's evaluation (ADR 0073): for each named instrument, the raw return of
every period of its calendar window and of the out-of-window stretches beside it, measured as in
``measures.py``, with the seeded random window sets and the timing Sharpe ratio.

The periods come from the calendar alone (``periods.py``) for the sessions ``start..end``; each
period's value is read at its own entry session S through ``harness.py`` as of ``as_of`` (the
one-session rule holds: no partition is read for another session than its S). A symbol the
reference snapshot does not know, a period with no closed or measurable outcome: counted under
its reason in ``lost``, never filled (an instrument with none has an empty ``all`` row and no
frozen one, so the verdict says there is nothing to judge)."""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime

import pandas as pd

from algotrade.config.edges.document import MAIN, Edge
from algotrade.config.edges.named import named_symbols
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.windows import window_length, window_name
from algotrade.data import StoreReader
from algotrade.services.evaluation.cross_section.measures import SliceMeasure
from algotrade.services.evaluation.cross_section.random_picks import DEFAULT_DRAWS
from algotrade.services.evaluation.cross_section.reads.entry import read_entries
from algotrade.services.evaluation.evidence.shapes import series_trades
from algotrade.services.evaluation.time_series import harness
from algotrade.services.evaluation.time_series.measures import (
    Obs,
    measures,
    timing_sharpes,
    with_pairs,
)
from algotrade.services.evaluation.time_series.periods import Period, periods
from algotrade.services.evaluation.time_series.random_windows import random_windows
from algotrade.services.evaluation.time_series.triggers import STALE, trigger_periods


@dataclass(frozen=True)
class InstrumentResult:
    """One named instrument's evaluation."""

    symbol: str
    horizon: int  # the window's length in sessions
    measures: tuple[SliceMeasure, ...]  # ``all`` first
    randoms: tuple[SliceMeasure, ...]  # out-of-sample draws; empty without a split
    in_window: tuple[tuple[date, float], ...]  # (entry session, raw return) of the windows
    paired: tuple[tuple[date, float], ...]  # (entry session, window minus the next stretch)
    timing: dict[str, float | int | None] = field(default_factory=dict)
    lost: dict[str, int] = field(default_factory=dict)  # reason -> periods without a value
    # the windows as trade-contract rows (ADR 0088, 2.5a); no measure reads them yet
    trades: pd.DataFrame | None = field(default=None, compare=False)
    edge_variant: str = MAIN  # a named sleeve's ``[[variants]]`` or grid point id (sleeve.py)
    identity: str = ""  # what the trial hash is of: edge, window or schedule, symbol (+ position)


@dataclass(frozen=True)
class TimeSeriesRun:
    window: str
    horizon: int
    scheduled: int  # the windows the calendar places in the range
    unclosed: int  # of those, windows with a value for no instrument
    results: tuple[InstrumentResult, ...]


def evaluate_time_series(
    reader: StoreReader,
    edge: Edge,
    start: date,
    end: date,
    as_of: datetime,
    label: Callable[[date], str],
    split: date | None,
    exploratory: bool,
    draws: int = DEFAULT_DRAWS,
    gate: Callable[[date], str] | None = None,
    domains: Mapping[str, Sequence[str]] | None = None,
) -> TimeSeriesRun:
    """``edge`` (``base = "out_of_window"``) over the periods of ``start..end``. ``label``: the
    site's regime label at a session (the regime slices); ``split``: the run's split date;
    ``gate``: the setup gate's state (open / closed / unknown) at a decision session, ``None`` for
    an ungated edge. A gated edge's result is its open periods; the closed and unknown ones are
    kept as the ``gate`` slices (ADR 0088). With an entry condition each period of an instrument
    starts at its own S (``_entries``; ``domains``: the catalogue's string domains), windows and
    base stretches alike; a period it never entered is lost under its reason."""
    trigger = edge.market_trigger
    name = trigger or window_name(edge.schedule)
    if name is None or not isinstance(edge.universe, Selection):
        raise ConfigurationError(f"edge {edge.id}: not a time-series edge")
    horizon = edge.outcome.horizon_sessions[0] if trigger else window_length(name)
    symbols = named_symbols(edge.universe)
    placed = trigger_periods(reader, trigger, start, end, horizon, as_of) if trigger else None
    ps = placed.periods if placed else periods(name, start, end)
    ids, unknown = harness.resolve_symbols(reader, symbols, end, as_of)
    starts = _entries(reader, edge, list(ids.values()), ps, domains)
    wanted = {p.entry for p in ps} | {s for s in starts.values() if isinstance(s, date)}
    read = harness.read_returns(reader, list(ids.values()), sorted(wanted), horizon, as_of)
    bills = harness.bill_returns(reader, [p.decision for p in ps], horizon, as_of)
    results = [
        _instrument(s, ids.get(s), ps, read, bills, label, edge, split, exploratory, draws,
                    horizon, unknown.get(s), gate, starts)
        for s in symbols
    ]  # fmt: skip
    if placed and placed.dropped:  # base stretches left out for a stale trigger reading
        results = [replace(r, lost={**r.lost, STALE: placed.dropped}) for r in results]
    windows = [p for p in ps if p.inside]
    measured = {e for r in results for e, _ in r.in_window}
    return TimeSeriesRun(
        name, horizon, len(windows), sum(p.entry not in measured for p in windows), tuple(results)
    )


def _instrument(
    symbol: str,
    instrument: str | None,
    ps: list[Period],
    read: harness.Returns,
    bills: dict[date, float],
    label: Callable[[date], str],
    edge: Edge,
    split: date | None,
    exploratory: bool,
    draws: int,
    horizon: int,
    unknown: str | None,
    gate: Callable[[date], str] | None = None,
    starts: Mapping[tuple[str, date], date | str] | None = None,
) -> InstrumentResult:
    lost: Counter[str] = Counter()
    obs: list[Obs] = []
    for period_ in ps:
        start = (starts or {}).get((instrument or "", period_.first), period_.entry)
        p = replace(period_, entry=start) if isinstance(start, date) else period_
        if instrument is None:
            lost[unknown or harness.UNKNOWN_SYMBOL] += 1
        elif isinstance(start, str):  # an entry condition never entered: its reason
            lost[start] += 1
        elif (instrument, p.entry) in read.values:
            state = "" if gate is None else gate(p.decision)
            obs.append(Obs(p, read.values[instrument, p.entry], label(p.decision), state))
        else:
            lost[read.reasons.get((instrument, p.entry), harness.NO_OUTCOME)] += 1
    obs = with_pairs(obs, horizon)
    every = obs
    if gate is not None:  # the edge's own series: the open periods (the slices hold the rest)
        obs = [o for o in obs if o.gate == "open"]
    window = edge.market_trigger or window_name(edge.schedule)
    entries = {o.period.entry for o in obs if o.period.inside}
    kept = (
        read.rows[
            (read.rows["instrument_id"] == instrument)
            & pd.to_datetime(read.rows["session_date"]).dt.date.isin(entries)
        ]
        if instrument is not None and read.rows is not None
        else None
    )
    oos = [o for o in obs if split is not None and o.period.decision >= split]
    return InstrumentResult(
        identity=f"{edge.id}|{window}|{symbol}",
        symbol=symbol,
        horizon=horizon,
        measures=measures(every, horizon, split, exploratory),
        randoms=random_windows(oos, f"{edge.id}|{window}|{symbol}|{horizon}", draws)
        if split is not None
        else (),
        in_window=tuple((o.period.entry, o.value) for o in obs if o.period.inside),
        paired=tuple((o.period.entry, o.paired) for o in obs if o.paired is not None),
        timing=timing_sharpes(obs, bills),
        lost=dict(lost),
        trades=None if kept is None else series_trades(edge, kept),
    )


def _entries(
    reader: StoreReader,
    edge: Edge,
    ids: Sequence[str],
    ps: Sequence[Period],
    domains: Mapping[str, Sequence[str]] | None,
) -> dict[tuple[str, date], date | str]:
    """With an entry condition, each (instrument, period's first session) -> its own S (the first
    close t of the wait from the period's D whose rule holds, S = t + 1 as the period's own S is
    D + 1), or the reason it never entered (``NOT_TRIGGERED``, ``ENTRY_UNKNOWN``, or the market
    table of a gap); empty without one."""
    spec = edge.outcome.entry
    if spec is None:
        return {}
    if spec.within_sessions > 1:  # a shifted window would run into the stretch beside it
        raise ConfigurationError(
            f"edge {edge.id} outcome.entry: a time-series edge takes within_sessions = 1"
        )
    out: dict[tuple[str, date], date | str] = {}
    for p in ps:
        found = read_entries(reader, spec, 1, ids, p.decision, domains)
        for i in ids:
            out[i, p.first] = found.gap or found.at.get(i) or found.reasons[i]
    return out
