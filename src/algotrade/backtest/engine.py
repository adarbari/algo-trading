"""The bar-by-bar backtest loop.

Timing model for bar ``t`` (see docs/adr/0002-fill-model.md):

1. Orders decided at the close of ``t-1`` fill at the **open** of ``t`` (with costs),
   limited by available buying power.
2. The portfolio is marked to market at the **close** of ``t``.
3. The strategy sees bars ``0..t`` (via ``MarketView``) and returns target weights.
4. Risk limits are applied and orders are queued for the open of ``t+1``.

Orders decided on the final bar never fill.
"""

from collections.abc import Mapping

import numpy as np

from algotrade.analytics.metrics import compute_metrics
from algotrade.backtest.config import BacktestConfig
from algotrade.backtest.result import BacktestResult
from algotrade.core.errors import ConfigurationError
from algotrade.core.market_view import MarketView
from algotrade.core.series import PriceSeries
from algotrade.core.time import to_utc_datetime
from algotrade.execution.simulated import SimulatedBroker
from algotrade.portfolio.portfolio import Portfolio
from algotrade.risk.limits import apply_limits
from algotrade.risk.sizing import targets_to_orders
from algotrade.strategies.base import Strategy


def _check_aligned(data: Mapping[str, PriceSeries]) -> int:
    if not data:
        raise ConfigurationError("backtest needs at least one symbol")
    first = next(iter(data.values()))
    for s in data.values():
        if not np.array_equal(s.timestamps, first.timestamps):
            raise ConfigurationError("all series must share timestamps; use data.align()")
    return len(first)


def run_backtest(
    data: Mapping[str, PriceSeries], strategy: Strategy, config: BacktestConfig | None = None
) -> BacktestResult:
    config = config or BacktestConfig()
    n = _check_aligned(data)
    if n <= strategy.warmup_bars:
        raise ConfigurationError(f"{n} bars is not enough for warmup of {strategy.warmup_bars}")

    timestamps = next(iter(data.values())).timestamps
    broker = SimulatedBroker(config.costs, config.lot_size)
    portfolio = Portfolio(config.initial_cash)
    equity = np.empty(n)
    exposure = np.empty(n)
    fills = []

    for t in range(n):
        now = to_utc_datetime(timestamps[t])
        opens = {s: float(series.open[t]) for s, series in data.items()}
        closes = {s: float(series.close[t]) for s, series in data.items()}

        leverage_room = max(0.0, config.limits.max_gross_exposure - 1.0)
        buying_power = portfolio.cash + leverage_room * max(0.0, portfolio.equity(opens))
        for fill in broker.execute_pending(opens, now, buying_power):
            portfolio.apply_fill(fill)
            fills.append(fill)

        equity[t] = portfolio.equity(closes)
        exposure[t] = portfolio.gross_exposure(closes)

        if t + 1 < strategy.warmup_bars or t == n - 1:
            continue
        targets = strategy.on_bar(MarketView(data, t))
        if targets is None:
            continue
        limited = apply_limits(targets, config.limits)
        investable = max(0.0, equity[t]) * (1 - config.cash_buffer)
        orders = targets_to_orders(
            limited, portfolio.positions, closes, investable, now, config.lot_size
        )
        broker.submit(orders)

    return BacktestResult(
        strategy=strategy.name,
        params=strategy.params(),
        timestamps=timestamps,
        equity=equity,
        gross_exposure=exposure,
        fills=tuple(fills),
        metrics=compute_metrics(equity, fills, exposure, config.periods_per_year),
    )
