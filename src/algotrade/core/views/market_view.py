"""The only window a strategy has onto market data.

``MarketView`` is the structural guard against look-ahead bias: it is constructed with a
cursor and every accessor slices data up to and including that cursor. Strategies never
receive the underlying ``PriceSeries``, so they cannot read the future by accident.
Market-wide features (``MarketFeatures``, ADR 0049), when the run loads them, are sliced at the
same cursor (``market_feature``).
"""

from collections.abc import Mapping
from datetime import datetime

from algotrade.core.model.errors import MissingDataError
from algotrade.core.time.clock import to_utc_datetime
from algotrade.core.views.feature_view import FeatureValue
from algotrade.core.views.market_features import HINT, MARKET_FEATURES, MarketFeatures
from algotrade.core.views.series import FloatArray, PriceSeries


class MarketView:
    __slots__ = ("_cursor", "_market", "_series")

    def __init__(
        self,
        series: Mapping[str, PriceSeries],
        cursor: int,
        market: MarketFeatures | None = None,
    ) -> None:
        lengths = {len(s) for s in series.values()}
        if len(lengths) > 1:
            raise ValueError("All series in a MarketView must be aligned to the same length")
        n = lengths.pop() if lengths else 0
        if not 0 <= cursor < n:
            raise IndexError(f"cursor {cursor} out of range for {n} bars")
        if market is not None and len(market) != n:
            raise ValueError(f"market features cover {len(market)} bars, the series {n}")
        self._series = series
        self._cursor = cursor
        self._market = market

    @property
    def instruments(self) -> tuple[str, ...]:
        """Instrument ids available in this view."""
        return tuple(self._series)

    @property
    def symbols(self) -> tuple[str, ...]:
        """Deprecated alias of ``instruments`` (kept through phase 1)."""
        return self.instruments

    @property
    def bar_index(self) -> int:
        """Number of bars before the current one (0 on the first bar)."""
        return self._cursor

    @property
    def now(self) -> datetime:
        first = next(iter(self._series.values()))
        return to_utc_datetime(first.timestamps[self._cursor])

    def history(
        self, instrument: str, field: str = "close", lookback: int | None = None
    ) -> FloatArray:
        """Values of ``field`` up to and including the current bar (read-only view).

        ``lookback`` limits the result to the most recent N bars; fewer are returned if
        not enough history exists yet.
        """
        arr = self._series[instrument].field(field)[: self._cursor + 1]
        if lookback is not None:
            if lookback <= 0:
                raise ValueError("lookback must be positive")
            arr = arr[-lookback:]
        return arr

    def latest(self, instrument: str, field: str = "close") -> float:
        return float(self._series[instrument].field(field)[self._cursor])

    def market_feature(self, name: str) -> FeatureValue:
        """The market feature ``name`` (``market.<group>@v<N>.<column>``) for the current
        session; ``None`` when that session has no value. ``MissingDataError`` when the run
        loaded no such feature (ADR 0008)."""
        if self._market is None:
            raise MissingDataError(MARKET_FEATURES, f"{name}: this run loads none", HINT)
        return self._market.value(name, self._cursor)
