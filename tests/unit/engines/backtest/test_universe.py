from datetime import date

import numpy as np
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.types import Side, TargetWeights
from algotrade.core.views.market_features import MarketFeatures
from algotrade.core.views.market_view import MarketView
from algotrade.core.views.series import PriceSeries, panel
from algotrade.engines.backtest.config import BacktestConfig
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.engine import run_backtest
from algotrade.engines.backtest.universe import DynamicUniverse
from algotrade.engines.overlays.scale import ScaleByLabel
from algotrade.strategies.trading.base import Strategy
from algotrade.strategies.trading.buy_and_hold import BuyAndHold
from tests.helpers.domain_objects import series_from_closes

FREE = BacktestConfig(initial_cash=1_000, costs=CostModel.free(), cash_buffer=0)


class EqualWeight(Strategy):
    """Equal-weights whatever it is shown, every bar; records what it saw."""

    name = "equal_weight"

    def __init__(self, warmup: int = 1) -> None:
        self._warmup = warmup
        self.seen: list[tuple[str, ...]] = []

    @property
    def warmup_bars(self) -> int:
        return self._warmup

    def on_bar(self, view: MarketView) -> TargetWeights | None:
        self.seen.append(view.instruments)
        return dict.fromkeys(view.instruments, 1.0 / len(view.instruments))


def day(i: int) -> date:
    return date(2024, 1, 1 + i)  # business_days from Monday 2024-01-01: bars 0..4 = Jan 1..5


def two(closes_b: list[float] | None = None) -> dict[str, PriceSeries]:
    a = series_from_closes([10.0] * 5, "A")
    b = series_from_closes(closes_b or [20.0] * 5, "B")
    return {"A": a, "B": b}


def test_removed_instrument_is_closed_at_the_effective_open_and_new_one_bought() -> None:
    strategy = EqualWeight()
    schedule = [(day(0), frozenset({"A"})), (day(2), frozenset({"B"}))]
    result = run_backtest(two(), strategy, FREE, schedule=schedule)
    sides = [(f.instrument_id, f.side, f.timestamp.date()) for f in result.fills]
    assert sides == [
        ("A", Side.BUY, day(1)),  # decided at close of bar 0
        ("A", Side.SELL, day(2)),  # removed: closed at the open of the effective bar
        ("B", Side.BUY, day(3)),  # first seen at the close of the effective bar
    ]
    assert strategy.seen == [("A",), ("A",), ("B",), ("B",)]


def test_strategy_never_sees_an_instrument_without_its_warmup_window() -> None:
    a = series_from_closes([10.0] * 6, "A")
    b = series_from_closes([20.0] * 4, "B")
    data = panel(
        {
            "A": a,
            "B": PriceSeries(
                "B",
                a.timestamps[2:].copy(),
                *(getattr(b, f) for f in ("open", "high", "low", "close", "volume")),
            ),
        }
    )
    strategy = EqualWeight(warmup=2)
    run_backtest(data, strategy, FREE, schedule=[(day(0), frozenset({"A", "B"}))])
    assert strategy.seen == [("A",), ("A",), ("A", "B"), ("A", "B")]  # B listed on bar 2


def test_orders_wait_for_a_bar_and_marks_carry_the_last_close() -> None:
    closes = [20.0, 20.0, np.nan, 22.0, 22.0]
    b = series_from_closes([20.0] * 5, "B")
    gappy = PriceSeries(
        "B", b.timestamps, np.array(closes), b.high, b.low, np.array(closes), b.volume
    )
    data = {"A": series_from_closes([10.0] * 5, "A"), "B": gappy}
    strategy = EqualWeight()
    schedule = [(day(0), frozenset({"B"})), (day(2), frozenset({"A"}))]
    result = run_backtest(data, strategy, FREE, schedule=schedule)
    sells = [f for f in result.fills if f.instrument_id == "B" and f.side is Side.SELL]
    assert [f.timestamp.date() for f in sells] == [day(3)]  # no bar on day 2: waited
    assert sells[0].price == 22.0
    assert np.isfinite(result.equity).all()
    assert result.equity[2] == pytest.approx(1_000)  # B marked at its last close (20)


def test_static_and_single_set_schedules_agree() -> None:
    data = two([20.0, 21.0, 19.0, 23.0, 24.0])
    plain = run_backtest(data, EqualWeight(), FREE)
    scheduled = run_backtest(data, EqualWeight(), FREE, schedule=[(day(0), frozenset(data))])
    np.testing.assert_allclose(plain.equity, scheduled.equity)
    assert plain.fills == scheduled.fills


def test_a_set_after_the_last_bar_never_applies_and_empty_schedules_fail() -> None:
    data = two()
    universe = DynamicUniverse(data, [(day(0), frozenset({"A"})), (day(30), frozenset())], 1)
    assert universe.members(4) == frozenset({"A"})
    with pytest.raises(ConfigurationError):
        DynamicUniverse(data, [], 1)


def test_a_held_instrument_that_left_the_set_is_not_bought_back_by_an_overlay() -> None:
    """ADR 0049: a hold strategy (``None``) resized by a regime change after A left the set
    trades only the set in force; A's exit is never replaced by a buy."""
    data = two()
    label = "market.regime@v1.label"
    labels = ["CALM", "CALM", "STRESS", "STRESS", "CALM"]
    market = MarketFeatures(data["A"].timestamps, {label: labels})
    overlay = ScaleByLabel(label, {"CALM": 1.0, "STRESS": 0.5})
    schedule = [(day(0), frozenset({"A", "B"})), (day(2), frozenset({"B"}))]
    result = run_backtest(
        data, BuyAndHold(), FREE, schedule=schedule, overlays=(overlay,), market=market
    )
    fills = [(f.instrument_id, f.side, f.timestamp.date()) for f in result.fills]
    assert fills == [
        ("A", Side.BUY, day(1)),
        ("B", Side.BUY, day(1)),
        ("A", Side.SELL, day(2)),  # left the set: closed at the effective open
        ("B", Side.SELL, day(3)),  # the storm at bar 2 halves B only
    ]


def test_an_instrument_that_re_enters_is_not_bought_back_from_old_targets() -> None:
    """A leaves {A, B} and comes back while the hold strategy still holds its first targets;
    a storm while A is out resizes B only, and A's return buys nothing (the strategy decides
    nothing new)."""
    data = {"A": series_from_closes([10.0] * 7, "A"), "B": series_from_closes([20.0] * 7, "B")}
    label = "market.regime@v1.label"
    labels = ["CALM", "CALM", "CALM", "STRESS", "CALM", "CALM", "CALM"]
    market = MarketFeatures(data["A"].timestamps, {label: labels})
    overlay = ScaleByLabel(label, {"CALM": 1.0, "STRESS": 0.5})
    bars = [d.item() for d in data["A"].timestamps.astype("datetime64[D]")]
    schedule = [
        (bars[0], frozenset({"A", "B"})),
        (bars[2], frozenset({"B"})),
        (bars[4], frozenset({"A", "B"})),
    ]
    result = run_backtest(
        data, BuyAndHold(), FREE, schedule=schedule, overlays=(overlay,), market=market
    )
    fills = [(f.instrument_id, f.side, f.timestamp.date()) for f in result.fills]
    assert fills == [
        ("A", Side.BUY, bars[1]),
        ("B", Side.BUY, bars[1]),
        ("A", Side.SELL, bars[2]),  # left the set
        ("B", Side.SELL, bars[4]),  # the storm at bar 3 halves B
        ("B", Side.BUY, bars[5]),  # calm again at bar 4: B back to its weight; A stays out
    ]
