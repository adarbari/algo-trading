"""Which instruments a backtest may trade on each bar: fixed, or changing on a schedule.

``StaticUniverse`` is the default: every series is tradable on every bar (series aligned by
``core.views.series.align``); the engine behaves exactly as before rebalancing existed.

``DynamicUniverse`` serves ``[backtest] rebalance_selection``. Series are on one timeline
(``core.views.series.panel``: NaN where an instrument has no bar) and a schedule says from
which bar each selected set applies. Rules (docs/configuration.md "Rebalancing selections"):

- **Eligible** on bar ``t``: in the set in force at ``t`` AND with a bar on each of the last
  ``max(1, warmup_bars)`` bars, so a strategy's warm-up window never holds a gap. Only eligible
  instruments are in the ``MarketView`` the strategy sees.
- **Removed** from the set at bar ``E``: open orders for it are cancelled and the position is
  closed by a market order filled at the open of ``E`` (ADR 0002's next-open rule: the set was
  decided on an earlier session's data). New members can be bought from the close of ``E``.
- **No bar** on a fill session: the order waits for the instrument's next bar, unless a newer
  order for the same instrument replaces it.
- **Marks**: the last close (before the first close: the first open) values positions and
  sizes orders on bars an instrument lacks.
"""

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from datetime import date, datetime

import numpy as np

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.types import Fill, Order, Side
from algotrade.core.views.series import FloatArray, PriceSeries
from algotrade.engines.backtest.simulated import SimulatedBroker

type Schedule = Sequence[tuple[date, frozenset[str]]]  # (effective date, set); first: bar 0


class StaticUniverse:
    """Every series, every bar (the engine's behaviour without rebalancing)."""

    def __init__(self, data: Mapping[str, PriceSeries]) -> None:
        self._data = data

    def view(self, t: int) -> Mapping[str, PriceSeries]:
        return self._data

    def opens(self, t: int) -> dict[str, float]:
        return {s: float(series.open[t]) for s, series in self._data.items()}

    def closes(self, t: int) -> dict[str, float]:
        return {s: float(series.close[t]) for s, series in self._data.items()}

    def rebalance(
        self, t: int, positions: Mapping[str, float], broker: SimulatedBroker, now: datetime
    ) -> None:
        return None

    def execute(
        self, t: int, broker: SimulatedBroker, now: datetime, buying_power: float
    ) -> list[Fill]:
        return broker.execute_pending(self.opens(t), now, buying_power)

    def submit(self, broker: SimulatedBroker, orders: Sequence[Order]) -> None:
        broker.submit(orders)


def _filled(values: FloatArray) -> FloatArray:
    """Forward-fill NaN (leading NaN stay NaN)."""
    idx = np.where(np.isfinite(values), np.arange(len(values)), 0)
    np.maximum.accumulate(idx, out=idx)
    out = values[idx]
    out[~np.isfinite(values[idx])] = np.nan
    return out


def _runs(finite: np.ndarray) -> np.ndarray:
    """Consecutive bars with data ending at each bar (0 where the bar is missing)."""
    idx = np.arange(len(finite))
    last_gap = np.maximum.accumulate(np.where(finite, -1, idx))
    return idx - last_gap


class DynamicUniverse:
    """Tradable set per bar from a schedule (see the module docstring)."""

    def __init__(self, data: Mapping[str, PriceSeries], schedule: Schedule, warmup: int) -> None:
        if not schedule:
            raise ConfigurationError("a rebalance schedule needs at least one selected set")
        self._data = data
        self._warmup = max(1, warmup)
        timestamps = next(iter(data.values())).timestamps
        days = timestamps.astype("datetime64[D]")
        self._sets: dict[int, frozenset[str]] = {0: schedule[0][1]}
        for effective, members in schedule[1:]:
            t = int(np.searchsorted(days, np.datetime64(effective, "D"), side="left"))
            if t < len(days):
                self._sets[t] = members
        self._starts = sorted(self._sets)
        self._runs = {s: _runs(np.isfinite(series.close)) for s, series in data.items()}
        self._marks = {}
        for s, series in data.items():
            marks = _filled(np.asarray(series.close, dtype=float))
            first_open = _filled(np.asarray(series.open, dtype=float))
            self._marks[s] = np.where(np.isfinite(marks), marks, first_open)

    def members(self, t: int) -> frozenset[str]:
        """The selected set in force on bar ``t``."""
        return self._sets[self._starts[bisect_right(self._starts, t) - 1]]

    def view(self, t: int) -> Mapping[str, PriceSeries]:
        return {
            s: self._data[s]
            for s in sorted(self.members(t))
            if s in self._data and self._runs[s][t] >= self._warmup
        }

    def _marks_at(self, t: int) -> dict[str, float]:
        return {s: float(m[t]) for s, m in self._marks.items() if np.isfinite(m[t])}

    def opens(self, t: int) -> dict[str, float]:
        """Opens to value the account at the open (the previous mark where there is no bar)."""
        prices = self._marks_at(t - 1) if t else {}
        for s, series in self._data.items():
            if np.isfinite(series.open[t]):
                prices[s] = float(series.open[t])
        return prices

    def closes(self, t: int) -> dict[str, float]:
        return self._marks_at(t)

    def rebalance(
        self, t: int, positions: Mapping[str, float], broker: SimulatedBroker, now: datetime
    ) -> None:
        """At a set change: cancel orders outside the new set, close positions that left it."""
        members = self._sets.get(t) if t else None
        if members is None:
            return
        keep = [o for o in broker.pending if o.instrument_id in members]
        exits = [
            Order(i, Side.SELL if q > 0 else Side.BUY, abs(q), now)
            for i, q in sorted(positions.items())
            if i not in members
        ]
        broker.cancel_all()
        broker.submit([*keep, *exits])

    def execute(
        self, t: int, broker: SimulatedBroker, now: datetime, buying_power: float
    ) -> list[Fill]:
        """Fill orders for instruments with a bar at ``t``; the others wait."""
        opens = {s: float(x.open[t]) for s, x in self._data.items() if np.isfinite(x.open[t])}
        waiting = [o for o in broker.pending if o.instrument_id not in opens]
        ready = [o for o in broker.pending if o.instrument_id in opens]
        broker.cancel_all()
        broker.submit(ready)
        fills = broker.execute_pending(opens, now, buying_power)
        broker.submit(waiting)
        return fills

    def submit(self, broker: SimulatedBroker, orders: Sequence[Order]) -> None:
        """New orders replace waiting ones for the same instrument."""
        replaced = {o.instrument_id for o in orders}
        waiting = [o for o in broker.pending if o.instrument_id not in replaced]
        broker.cancel_all()
        broker.submit([*waiting, *orders])
