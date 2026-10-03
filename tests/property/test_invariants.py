"""Property-based tests for invariants that must hold for *every* strategy and input."""

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from algotrade.core.market_view import MarketView
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.engine import run_backtest
from algotrade.strategies.trading.registry import STRATEGIES, create_strategy
from tests.factories import series_from_closes

prices = st.lists(st.floats(min_value=1.0, max_value=1_000.0), min_size=130, max_size=200)


@pytest.mark.parametrize("name", sorted(STRATEGIES))
@given(closes=prices, data=st.data())
def test_no_lookahead(name: str, closes: list[float], data: st.DataObject) -> None:
    """Decisions up to bar t must not change when bars after t are rewritten."""
    cut = data.draw(st.integers(min_value=110, max_value=len(closes) - 2))
    future = data.draw(st.lists(st.floats(1.0, 1_000.0), min_size=len(closes) - cut - 1,
                                max_size=len(closes) - cut - 1))  # fmt: skip
    original = {"TEST": series_from_closes(closes)}
    altered = {"TEST": series_from_closes(closes[: cut + 1] + future)}

    def decisions(series: dict) -> list:  # type: ignore[type-arg]
        strategy = create_strategy(name)
        start = strategy.warmup_bars - 1
        return [strategy.on_bar(MarketView(series, t)) for t in range(start, cut + 1)]

    assert decisions(original) == decisions(altered)


@pytest.mark.parametrize("name", sorted(STRATEGIES))
@given(closes=prices)
def test_accounting_identity(name: str, closes: list[float]) -> None:
    """With no costs, final equity == initial cash + sum of P&L on every fill."""
    config = BacktestConfig(costs=CostModel.free())
    result = run_backtest({"TEST": series_from_closes(closes)}, create_strategy(name), config)
    position = sum(f.signed_quantity for f in result.fills)
    cash = config.initial_cash - sum(f.signed_quantity * f.price for f in result.fills)
    assert result.equity[-1] == pytest.approx(cash + position * closes[-1], rel=1e-9)
    assert np.all(np.isfinite(result.equity))


@pytest.mark.parametrize("name", sorted(STRATEGIES))
@given(closes=prices)
def test_long_only_never_shorts_or_borrows(name: str, closes: list[float]) -> None:
    """Default limits forbid shorts and leverage, even across violent overnight gaps."""
    result = run_backtest({"TEST": series_from_closes(closes)}, create_strategy(name))
    position = np.cumsum([f.signed_quantity for f in result.fills])
    assert np.all(position >= -1e-9)
    assert np.all(result.equity > 0)
