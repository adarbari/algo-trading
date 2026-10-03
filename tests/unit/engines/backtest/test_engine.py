import numpy as np
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.types import TargetWeights
from algotrade.core.views.market_view import MarketView
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.engine import run_backtest
from algotrade.strategies.trading.base import Strategy
from algotrade.strategies.trading.buy_and_hold import BuyAndHold
from tests.helpers.domain_objects import series_from_closes

FREE = BacktestConfig(initial_cash=1_000, costs=CostModel.free(), cash_buffer=0)


class Recorder(Strategy):
    """Records the bar indices it was called on and always targets 100%."""

    name = "recorder"

    def __init__(self, warmup: int = 1) -> None:
        self._warmup = warmup
        self.seen: list[int] = []

    @property
    def warmup_bars(self) -> int:
        return self._warmup

    def on_bar(self, view: MarketView) -> TargetWeights | None:
        self.seen.append(view.bar_index)
        return {"TEST": 1.0}


def test_orders_fill_at_next_open_not_decision_close() -> None:
    data = {"TEST": series_from_closes([10, 10, 10], opens=[10, 20, 20])}
    result = run_backtest(data, BuyAndHold(), FREE)
    assert result.fills[0].price == 20  # decided at close of bar 0 (10), filled at open of bar 1
    assert result.fills[0].quantity == 50


def test_equity_tracks_price_with_no_costs() -> None:
    data = {"TEST": series_from_closes([10, 10, 12, 15])}
    result = run_backtest(data, BuyAndHold(), FREE)
    np.testing.assert_allclose(result.equity, [1_000, 1_000, 1_200, 1_500])
    assert result.metrics.total_return == pytest.approx(0.5)


def test_costs_reduce_returns() -> None:
    data = {"TEST": series_from_closes([10, 10, 12, 15])}
    costly = BacktestConfig(initial_cash=1_000, costs=CostModel(commission_bps=50, slippage_bps=50))
    assert run_backtest(data, BuyAndHold(), costly).metrics.total_return < 0.5


def test_warmup_and_last_bar_respected() -> None:
    strategy = Recorder(warmup=3)
    run_backtest({"TEST": series_from_closes([1, 2, 3, 4, 5, 6])}, strategy, FREE)
    assert strategy.seen == [2, 3, 4]  # first call once 3 bars exist; never on final bar


def test_rejects_unaligned_and_empty_data() -> None:
    with pytest.raises(ConfigurationError, match="at least one"):
        run_backtest({}, BuyAndHold())
    a = series_from_closes([1, 2, 3], "A")
    b = series_from_closes([1, 2, 3, 4], "B")
    with pytest.raises(ConfigurationError, match="share timestamps"):
        run_backtest({"A": a, "B": b}, BuyAndHold())


def test_rejects_too_little_data() -> None:
    with pytest.raises(ConfigurationError, match="warmup"):
        run_backtest({"TEST": series_from_closes([1, 2])}, Recorder(warmup=5))


@pytest.mark.parametrize("kwargs", [{"initial_cash": 0}, {"cash_buffer": 1.0}])
def test_config_validation(kwargs: dict[str, float]) -> None:
    with pytest.raises(ConfigurationError):
        BacktestConfig(**kwargs)  # type: ignore[arg-type]


def test_instruments_supply_multipliers() -> None:
    from algotrade.core.model.instruments import AssetClass, Instrument  # noqa: PLC0415

    data = {"TEST": series_from_closes([2, 2, 3, 4])}
    option = {"TEST": Instrument("TEST", "TEST", AssetClass.OPTION, multiplier=100)}
    result = run_backtest(data, BuyAndHold(), FREE, instruments=option)
    assert result.fills[0].quantity == 5  # 1000 / (2 x 100)
    np.testing.assert_allclose(result.equity, [1_000, 1_000, 1_500, 2_000])
