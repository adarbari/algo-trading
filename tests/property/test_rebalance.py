"""Rebalancing never looks ahead: a selection evaluated on session D trades from D + lag, so
rewriting data (bars or selections) after a bar leaves every earlier trade unchanged."""

from datetime import date

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.core.views.series import PriceSeries
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.engine import run_backtest
from algotrade.engines.selection.evaluate import SelectionResult
from algotrade.services.backtests.rebalance import rebalances
from algotrade.strategies.trading.registry import create_strategy
from tests.factories import series_from_closes

IDS = ("A", "B", "C")
N = 40
CONFIG = BacktestConfig(initial_cash=10_000, costs=CostModel.free(), cash_buffer=0)
closes = st.lists(st.floats(1.0, 100.0), min_size=N, max_size=N)
sets = st.lists(st.frozensets(st.sampled_from(IDS)), min_size=4, max_size=4)


def _result(members: frozenset[str]) -> SelectionResult:
    return SelectionResult("s", len(IDS), tuple(sorted(members)), 0, 0, ())


def _run(prices: dict[str, list[float]], chosen: list[frozenset[str]], lag: int) -> tuple:  # type: ignore[type-arg]
    data: dict[str, PriceSeries] = {i: series_from_closes(prices[i], i) for i in IDS}
    days = data["A"].timestamps.astype("datetime64[D]")
    evaluated = [days[k * 10].item() for k in range(len(chosen))]  # every 10 bars
    history = rebalances(list(zip(evaluated, map(_result, chosen), strict=True)), days, lag)
    schedule = [(r.effective, r.members) for r in history if r.effective is not None]
    strategy = create_strategy("sma_crossover", fast=2, slow=4)
    return run_backtest(data, strategy, CONFIG, schedule=schedule), history


@settings(max_examples=60, deadline=None)
@given(
    a=closes, b=closes, c=closes, chosen=sets, other=sets, data=st.data(),
    lag=st.integers(1, 3),
)  # fmt: skip
def test_future_bars_and_selections_never_change_past_trades(
    a: list[float],
    b: list[float],
    c: list[float],
    chosen: list[frozenset[str]],
    other: list[frozenset[str]],
    data: st.DataObject,
    lag: int,
) -> None:
    cut = data.draw(st.integers(5, N - 2))
    future = {i: data.draw(closes) for i in IDS}
    prices = {"A": a, "B": b, "C": c}
    altered = {i: prices[i][: cut + 1] + future[i][cut + 1 :] for i in IDS}
    # Selections evaluated at or after the cut may change: they only see data from then on.
    rewritten = [s if k * 10 < cut else other[k] for k, s in enumerate(chosen)]
    base, history = _run(prices, chosen, lag)
    changed, _ = _run(altered, rewritten, lag)
    for r in history[1:]:
        assert r.effective is None or r.effective > r.evaluated  # lag >= 1: never the same bar
    np.testing.assert_array_equal(base.equity[: cut + 1], changed.equity[: cut + 1])
    stamp = base.timestamps[cut].astype("datetime64[D]").item()

    def until_cut(result: object) -> list:  # type: ignore[type-arg]
        return [f for f in result.fills if f.timestamp.date() <= stamp]  # type: ignore[attr-defined]

    assert until_cut(base) == until_cut(changed)
    assert isinstance(stamp, date)
