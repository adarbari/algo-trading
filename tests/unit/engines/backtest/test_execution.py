import pytest

from algotrade.core.model.types import Order, Side
from algotrade.engines.backtest.costs import CostModel
from algotrade.engines.backtest.simulated import SimulatedBroker
from tests.helpers.domain_objects import T0


def test_slippage_is_adverse() -> None:
    costs = CostModel(slippage_bps=10)
    assert costs.fill_price(Side.BUY, 100) == pytest.approx(100.1)
    assert costs.fill_price(Side.SELL, 100) == pytest.approx(99.9)


def test_commission_floor() -> None:
    costs = CostModel(commission_bps=1, min_commission=5)
    assert costs.commission(1_000) == 5
    assert costs.commission(1_000_000) == pytest.approx(100)
    assert CostModel.free().commission(1e9) == 0


def test_broker_fills_pending_at_given_open() -> None:
    broker = SimulatedBroker(CostModel.free())
    broker.submit([Order("A", Side.BUY, 5, T0)])
    assert len(broker.pending) == 1
    fills = broker.execute_pending({"A": 42.0}, T0)
    assert [(f.instrument_id, f.quantity, f.price) for f in fills] == [("A", 5, 42.0)]
    assert broker.pending == ()


def test_broker_cancel_all() -> None:
    broker = SimulatedBroker()
    broker.submit([Order("A", Side.BUY, 5, T0)])
    broker.cancel_all()
    assert broker.execute_pending({"A": 1.0}, T0) == []


def test_buys_are_capped_by_buying_power() -> None:
    broker = SimulatedBroker(CostModel.free())
    broker.submit([Order("A", Side.BUY, 100, T0)])
    (f,) = broker.execute_pending({"A": 10.0}, T0, buying_power=255.0)
    assert f.quantity == 25


def test_sells_fund_buys_and_unaffordable_buys_are_dropped() -> None:
    broker = SimulatedBroker(CostModel(commission_bps=0, min_commission=1, slippage_bps=0))
    broker.submit([Order("B", Side.BUY, 10, T0), Order("A", Side.SELL, 5, T0)])
    fills = broker.execute_pending({"A": 10.0, "B": 10.0}, T0, buying_power=0.0)
    assert [(x.instrument_id, x.quantity) for x in fills] == [("A", 5), ("B", 4)]  # 50 - 1 fee = 49
    broker.submit([Order("B", Side.BUY, 10, T0)])
    assert broker.execute_pending({"B": 10.0}, T0, buying_power=5.0) == []


def test_multiplier_drives_cost_buying_power_and_commission() -> None:
    broker = SimulatedBroker(
        CostModel(commission_bps=10, slippage_bps=0), multipliers={"OPT:X": 100}
    )
    broker.submit([Order("OPT:X", Side.BUY, 10, T0)])
    (f,) = broker.execute_pending({"OPT:X": 2.0}, T0, buying_power=1_000.0)
    assert f.quantity == 4  # 4 x 2.00 x 100 = 800 (+0.80 fee); 5 contracts would be 1000.10
    assert f.multiplier == 100
    assert f.notional == 800
    assert f.commission == pytest.approx(0.8)
