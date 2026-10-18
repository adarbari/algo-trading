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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from algotrade.config.edges.document import Edge
from algotrade.config.edges.named import named_symbols
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.windows import window_length, window_name
from algotrade.data import StoreReader
from algotrade.services.evaluation.cross_section.measures import SliceMeasure
from algotrade.services.evaluation.cross_section.random_picks import DEFAULT_DRAWS
from algotrade.services.evaluation.time_series import harness
from algotrade.services.evaluation.time_series.measures import (
    Obs,
    measures,
    timing_sharpes,
    with_pairs,
)
from algotrade.services.evaluation.time_series.periods import Period, periods
from algotrade.services.evaluation.time_series.random_windows import random_windows
from algotrade.services.evaluation.time_series.triggers import trigger_periods


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
) -> TimeSeriesRun:
    """``edge`` (``base = "out_of_window"``) over the periods of ``start..end``. ``label``: the
    site's regime label at a session (the regime slices); ``split``: the run's split date."""
    trigger = edge.market_trigger
    name = trigger or window_name(edge.schedule)
    if name is None or not isinstance(edge.universe, Selection):
        raise ConfigurationError(f"edge {edge.id}: not a time-series edge")
    horizon = edge.outcome.horizon_sessions[0] if trigger else window_length(name)
    symbols = named_symbols(edge.universe)
    ps = (
        trigger_periods(reader, trigger, start, end, horizon, as_of)
        if trigger
        else periods(name, start, end)
    )
    ids, unknown = harness.resolve_symbols(reader, symbols, end, as_of)
    read = harness.read_returns(reader, list(ids.values()), [p.entry for p in ps], horizon, as_of)
    bills = harness.bill_returns(reader, [p.decision for p in ps], horizon, as_of)
    results = [
        _instrument(s, ids.get(s), ps, read, bills, label, edge, split, exploratory, draws,
                    horizon, unknown.get(s))
        for s in symbols
    ]  # fmt: skip
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
) -> InstrumentResult:
    lost: Counter[str] = Counter()
    obs: list[Obs] = []
    for p in ps:
        if instrument is None:
            lost[unknown or harness.UNKNOWN_SYMBOL] += 1
        elif (instrument, p.entry) in read.values:
            obs.append(Obs(p, read.values[instrument, p.entry], label(p.decision)))
        else:
            lost[read.reasons.get((instrument, p.entry), harness.NO_OUTCOME)] += 1
    obs = with_pairs(obs, horizon)
    window = edge.market_trigger or window_name(edge.schedule)
    oos = [o for o in obs if split is not None and o.period.decision >= split]
    return InstrumentResult(
        symbol=symbol,
        horizon=horizon,
        measures=measures(obs, horizon, split, exploratory),
        randoms=random_windows(oos, f"{edge.id}|{window}|{symbol}|{horizon}", draws)
        if split is not None
        else (),
        in_window=tuple((o.period.entry, o.value) for o in obs if o.period.inside),
        paired=tuple((o.period.entry, o.paired) for o in obs if o.paired is not None),
        timing=timing_sharpes(obs, bills),
        lost=dict(lost),
    )
