"""The only window a strategy has onto market data.

``MarketView`` is the structural guard against look-ahead bias: it is constructed with a
cursor and every accessor slices data up to and including that cursor. Strategies never
receive the underlying ``PriceSeries``, so they cannot read the future by accident.
"""

from collections.abc import Mapping
from datetime import datetime

from algotrade.core.series import FloatArray, PriceSeries
from algotrade.core.time import to_utc_datetime


class MarketView:
    __slots__ = ("_cursor", "_series")

    def __init__(self, series: Mapping[str, PriceSeries], cursor: int) -> None:
        lengths = {len(s) for s in series.values()}
        if len(lengths) > 1:
            raise ValueError("All series in a MarketView must be aligned to the same length")
        n = lengths.pop() if lengths else 0
        if not 0 <= cursor < n:
            raise IndexError(f"cursor {cursor} out of range for {n} bars")
        self._series = series
        self._cursor = cursor

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(self._series)

    @property
    def bar_index(self) -> int:
        """Number of bars before the current one (0 on the first bar)."""
        return self._cursor

    @property
    def now(self) -> datetime:
        first = next(iter(self._series.values()))
        return to_utc_datetime(first.timestamps[self._cursor])

    def history(self, symbol: str, field: str = "close", lookback: int | None = None) -> FloatArray:
        """Values of ``field`` up to and including the current bar (read-only view).

        ``lookback`` limits the result to the most recent N bars; fewer are returned if
        not enough history exists yet.
        """
        arr = self._series[symbol].field(field)[: self._cursor + 1]
        if lookback is not None:
            if lookback <= 0:
                raise ValueError("lookback must be positive")
            arr = arr[-lookback:]
        return arr

    def latest(self, symbol: str, field: str = "close") -> float:
        return float(self._series[symbol].field(field)[self._cursor])
