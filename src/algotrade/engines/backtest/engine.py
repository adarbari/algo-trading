"""The bar-by-bar backtest loop.

Timing model for bar ``t`` (see docs/adr/0002-fill-model.md):

1. Orders decided at the close of ``t-1`` fill at the **open** of ``t`` (with costs),
   limited by available buying power.
2. The portfolio is marked to market at the **close** of ``t``.
3. The strategy sees bars ``0..t`` (via ``MarketView``) and returns target weights.
4. Run overlays (``engines.overlays``, ADR 0049) adjust them from session ``t``'s market
   features (``MarketFeatures.at(t)``), then risk limits are applied and orders are queued
   for the open of ``t+1``.

Orders decided on the final bar never fill. With overlays, a bar where the strategy returns
``None`` ("no change") re-applies them to its latest targets and rebalances only when the
result differs (a regime change resizes held positions); the run counts, per reason, the bars
an overlay changed the weights (``BacktestResult.overlay_reasons``).

With a ``schedule`` (``[backtest] rebalance_selection``) the tradable set changes over time;
``engines.backtest.universe`` holds those rules. Without one, every series trades every bar.
"""

from collections import Counter
from collections.abc import Mapping, Sequence

import numpy as np

from algotrade.analytics.metrics import compute_metrics
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.instruments import Instrument, multipliers
from algotrade.core.model.types import TargetWeights
from algotrade.core.time.clock import to_utc_datetime
from algotrade.core.views.feature_view import FeatureValue
from algotrade.core.views.market_features import MarketFeatures
from algotrade.core.views.market_view import MarketView
from algotrade.core.views.series import PriceSeries
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.limits import apply_limits
from algotrade.engines.backtest.portfolio import Portfolio
from algotrade.engines.backtest.result import BacktestResult
from algotrade.engines.backtest.simulated import SimulatedBroker
from algotrade.engines.backtest.sizing import targets_to_orders
from algotrade.engines.backtest.universe import DynamicUniverse, Schedule, StaticUniverse
from algotrade.engines.overlays.overlay import Overlay
from algotrade.strategies.trading.base import Strategy


def _check_aligned(data: Mapping[str, PriceSeries]) -> int:
    if not data:
        raise ConfigurationError("backtest needs at least one instrument")
    first = next(iter(data.values()))
    for s in data.values():
        if not np.array_equal(s.timestamps, first.timestamps):
            raise ConfigurationError("all series must share timestamps; use data.align()")
    return len(first)


def _check_market(
    timestamps: np.ndarray, overlays: Sequence[Overlay], market: MarketFeatures | None
) -> None:
    if overlays and market is None:
        raise ConfigurationError("overlays need the run's market features (market=...)")
    if market is not None and not np.array_equal(market.timestamps, timestamps):
        raise ConfigurationError("market features must share the bars' timestamps")


def overlaid(
    weights: TargetWeights,
    overlays: Sequence[Overlay],
    market: Mapping[str, FeatureValue],
) -> tuple[dict[str, float], tuple[str, ...]]:
    """``weights`` through every overlay in order -> (the result, every reason given)."""
    out: dict[str, float] = dict(weights)
    reasons: list[str] = []
    for overlay in overlays:
        step = overlay.apply(out, market)
        out = dict(step.weights)
        reasons.extend(step.reasons)
    return out, tuple(reasons)


class _Overlays:
    """The overlays of one run and what they last did (see the module docstring)."""

    def __init__(self, overlays: Sequence[Overlay], market: MarketFeatures | None) -> None:
        self.overlays, self.market = tuple(overlays), market
        self.reasons: Counter[str] = Counter()
        self._decided: TargetWeights | None = None  # the strategy's latest targets
        self._sent: dict[str, float] | None = None  # the latest overlaid weights sent on

    def step(
        self, targets: TargetWeights | None, t: int, view: Mapping[str, object]
    ) -> TargetWeights | None:
        """The weights to trade towards at bar ``t`` (``None``: no change). Only instruments
        in ``view`` (the tradable set at ``t``) are kept, for good: one that left a rebalanced
        set is never bought back from the strategy's older targets, even when it re-enters."""
        if not self.overlays or self.market is None:
            return targets
        self._decided = self._decided if targets is None else targets
        if self._decided is None:
            return None
        # Written back: an instrument that left the set stays out of the held targets, so it is
        # never bought back when it re-enters (only the strategy's new targets can buy it).
        self._decided = {i: w for i, w in self._decided.items() if i in view}
        weights, why = overlaid(self._decided, self.overlays, self.market.at(t))
        self.reasons.update(why)
        sent = {i: w for i, w in (self._sent or {}).items() if i in view}
        if targets is None and weights == sent:
            return None
        self._sent = weights
        return weights


def run_backtest(
    data: Mapping[str, PriceSeries],
    strategy: Strategy,
    config: BacktestConfig | None = None,
    instruments: Mapping[str, Instrument] | None = None,
    schedule: Schedule | None = None,
    overlays: Sequence[Overlay] = (),
    market: MarketFeatures | None = None,
) -> BacktestResult:
    """Run ``strategy`` over aligned ``data`` keyed by instrument id.

    ``instruments`` supplies contract terms (multipliers); instruments not listed are
    treated as multiplier-1 equities. ``schedule``: (effective date, selected set) pairs, the
    first in force from bar 0; ``data`` then shares one timeline with NaN for missing bars
    (``core.views.series.panel``). ``overlays`` adjust the strategy's weights from ``market``
    (the run's market features on the same timeline; strategies see it too, through
    ``MarketView.market_feature``).
    """
    config = config or BacktestConfig()
    contract_multipliers = multipliers((instruments or {}).values())
    n = _check_aligned(data)
    if n <= strategy.warmup_bars:
        raise ConfigurationError(f"{n} bars is not enough for warmup of {strategy.warmup_bars}")

    timestamps = next(iter(data.values())).timestamps
    _check_market(timestamps, overlays, market)
    universe: StaticUniverse | DynamicUniverse = (
        StaticUniverse(data)
        if schedule is None
        else DynamicUniverse(data, schedule, strategy.warmup_bars)
    )
    broker = SimulatedBroker(config.costs, config.lot_size, contract_multipliers)
    portfolio = Portfolio(config.initial_cash)
    equity = np.empty(n)
    exposure = np.empty(n)
    fills = []
    overlay = _Overlays(overlays, market)

    for t in range(n):
        now = to_utc_datetime(timestamps[t])
        opens = universe.opens(t)
        closes = universe.closes(t)
        universe.rebalance(t, portfolio.positions, broker, now)

        leverage_room = max(0.0, config.limits.max_gross_exposure - 1.0)
        buying_power = portfolio.cash + leverage_room * max(0.0, portfolio.equity(opens))
        for fill in universe.execute(t, broker, now, buying_power):
            portfolio.apply_fill(fill)
            fills.append(fill)

        equity[t] = portfolio.equity(closes)
        exposure[t] = portfolio.gross_exposure(closes)

        if t + 1 < strategy.warmup_bars or t == n - 1:
            continue
        view = universe.view(t)
        if not view:
            continue
        targets = overlay.step(strategy.on_bar(MarketView(view, t, market)), t, view)
        if targets is None:
            continue
        limited = apply_limits(targets, config.limits)
        investable = max(0.0, equity[t]) * (1 - config.cash_buffer)
        orders = targets_to_orders(
            limited,
            portfolio.positions,
            closes,
            investable,
            now,
            config.lot_size,
            contract_multipliers,
        )
        universe.submit(broker, orders)

    return BacktestResult(
        strategy=strategy.name,
        params=strategy.params(),
        timestamps=timestamps,
        equity=equity,
        gross_exposure=exposure,
        fills=tuple(fills),
        metrics=compute_metrics(equity, fills, exposure, config.periods_per_year),
        overlay_reasons=dict(sorted(overlay.reasons.items())),
    )
