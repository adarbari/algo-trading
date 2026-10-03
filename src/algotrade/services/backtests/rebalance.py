"""Use case step: re-evaluate a backtest's selection on its rebalance sessions (point in time).

Each evaluation is ``services.selection.select`` on that session (the reference snapshot and
rollups for the session, read ``as_of`` the launch), so a later session's data never reaches
an earlier selection. A set evaluated on session ``D`` trades from the bar ``lag`` bars after
``D``'s bar (``[backtest] selection_lag_sessions``, default 1); the set evaluated on ``start``
trades from the first bar, exactly as without rebalancing. Prices are loaded once, for the
union of every instrument ever selected, and put on one timeline (``panel``).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np

from algotrade.config.site.settings import BacktestSettings
from algotrade.config.strategy.schema import Selection
from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.calendar import sessions_between
from algotrade.core.views.series import panel
from algotrade.data import StoreReader
from algotrade.data.prices import PriceData, load_price_data
from algotrade.engines.backtest.universe import Schedule
from algotrade.engines.selection.evaluate import SelectionResult
from algotrade.engines.selection.schedule import Rebalance, diff, rebalance_sessions
from algotrade.services.selection import select

ROLLUPS_HINT = "algotrade-ingest rollups --from <first rebalance session> --to <end>"


def evaluate_sessions(
    reader: StoreReader,
    selection: Selection,
    start: date,
    end: date,
    frequency: str,
    as_of: datetime,
) -> list[tuple[date, SelectionResult]]:
    """The selection on ``start`` and on every rebalance session up to ``end``.

    A rebalance session whose rollups are missing is an error (ADR 0008): evaluating it would
    select nothing and close every position."""
    out = []
    for session in rebalance_sessions(start, sessions_between(start, end), frequency):
        result = select(reader, selection, session, as_of=as_of)
        if session != start and result.missing_tables:
            table = result.missing_tables[0]
            raise MissingDataError(table, f"no rows for rebalance session {session}", ROLLUPS_HINT)
        out.append((session, result))
    return out


def rebalances(
    evaluations: Sequence[tuple[date, SelectionResult]], days: np.ndarray, lag: int
) -> list[Rebalance]:
    """Audit rows: when each set takes effect on the bar timeline ``days`` (datetime64[D])."""
    out: list[Rebalance] = []
    previous: frozenset[str] = frozenset()
    for k, (session, result) in enumerate(evaluations):
        if k == 0:
            effective: date | None = days[0].item() if len(days) else None
        else:
            bar = int(np.searchsorted(days, np.datetime64(session, "D"), side="right")) - 1 + lag
            effective = days[bar].item() if bar < len(days) else None
        added, removed = diff(previous, result)
        out.append(Rebalance(session, effective, result, added, removed, result.pre_snapshot))
        previous = frozenset(result.instruments)
    return out


@dataclass(frozen=True)
class RebalancedData:
    prices: PriceData  # every instrument ever selected, on one timeline (NaN: no bar)
    rebalances: tuple[Rebalance, ...]

    @property
    def schedule(self) -> Schedule:
        return [(r.effective, r.members) for r in self.rebalances if r.effective is not None]


def load_rebalanced(
    reader: StoreReader,
    selection: Selection,
    start: date,
    end: date,
    settings: BacktestSettings,
    as_of: datetime,
) -> RebalancedData:
    """Evaluate every rebalance session, then load prices once for the union selected."""
    evaluations = evaluate_sessions(
        reader, selection, start, end, settings.rebalance_selection, as_of
    )
    union = sorted({i for _, r in evaluations for i in r.instruments})
    data = load_price_data(
        reader,
        union,
        start,
        end,
        as_of=as_of,
        adjustment=settings.price_adjustment,
        aligned=False,
    )
    series = panel(data.series)
    days = next(iter(series.values())).timestamps.astype("datetime64[D]")
    prices = PriceData(series, data.terms, data.versions, data.reference)
    lag = settings.selection_lag_sessions
    return RebalancedData(prices, tuple(rebalances(evaluations, days, lag)))
