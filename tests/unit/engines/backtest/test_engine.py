import numpy as np
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.types import TargetWeights
from algotrade.core.time.clock import business_days, to_utc_datetime
from algotrade.core.views.market_features import MarketFeatures
from algotrade.core.views.market_view import MarketView
from algotrade.core.views.series import PriceSeries
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.engine import run_backtest
from algotrade.engines.backtest.result import BacktestResult
from algotrade.engines.overlays.scale import ScaleByLabel
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


# ----------------------------------------------------------------------------- overlays (ADR 0049)

LABEL = "market.regime@v1.label"
REGIME = ScaleByLabel(LABEL, {"CALM": 1.0, "CAUTION": 0.75, "STRESS": 0.5, "CRISIS": 0.25})


def _regime(labels: list[str | None], data: dict[str, PriceSeries]) -> MarketFeatures:
    return MarketFeatures(next(iter(data.values())).timestamps, {LABEL: labels})


def _fills(result: BacktestResult) -> list[tuple[int, str, float]]:
    bars = [to_utc_datetime(ts) for ts in result.timestamps]
    return [(bars.index(f.timestamp), f.side.value, f.quantity) for f in result.fills]


def test_weights_halve_in_stress_and_fill_at_the_next_open() -> None:
    """Session t's label sizes the order decided at t's close, filled at t+1's open."""
    data = {"TEST": series_from_closes([10] * 6)}
    market = _regime(["CALM", "CALM", "STRESS", "STRESS", "CALM", "CALM"], data)
    result = run_backtest(data, Recorder(), FREE, overlays=(REGIME,), market=market)
    assert _fills(result) == [(1, "buy", 100), (3, "sell", 50), (5, "buy", 50)]
    assert result.overlay_reasons == {"regime=STRESS: x0.5": 2}
    plain = run_backtest(data, Recorder(), FREE)
    assert _fills(plain) == [(1, "buy", 100)] and plain.overlay_reasons == {}


def test_a_hold_strategy_is_resized_when_the_regime_changes() -> None:
    """``None`` (no change) re-applies the overlay to the last targets; equal weights send
    nothing, a new regime rebalances."""
    data = {"TEST": series_from_closes([10] * 6)}
    market = _regime(["CALM", "CALM", "STRESS", "STRESS", None, "CALM"], data)
    result = run_backtest(data, BuyAndHold(), FREE, overlays=(REGIME,), market=market)
    assert _fills(result) == [(1, "buy", 100), (3, "sell", 50), (5, "sell", 50)]
    assert result.overlay_reasons == {"regime unknown": 1, "regime=STRESS: x0.5": 2}


def test_the_strategy_sees_market_features_through_its_view() -> None:
    class Reader(Recorder):
        def on_bar(self, view: MarketView) -> TargetWeights | None:
            self.seen.append(view.market_feature(LABEL) == "STRESS")
            return None

    data = {"TEST": series_from_closes([10] * 4)}
    strategy = Reader()
    run_backtest(data, strategy, FREE, market=_regime(["CALM", "STRESS", "CALM", "CALM"], data))
    assert strategy.seen == [False, True, False]


def test_overlays_need_market_features_on_the_same_timeline() -> None:
    data = {"TEST": series_from_closes([10] * 4)}
    with pytest.raises(ConfigurationError, match="market features"):
        run_backtest(data, Recorder(), FREE, overlays=(REGIME,))
    other = MarketFeatures(business_days("2021-01-04", 4), {LABEL: [None] * 4})
    with pytest.raises(ConfigurationError, match="timestamps"):
        run_backtest(data, Recorder(), FREE, overlays=(REGIME,), market=other)
