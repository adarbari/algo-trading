import pytest

from algotrade.core.errors import ConfigurationError
from algotrade.core.types import Side
from algotrade.engines.backtest.limits import RiskLimits, apply_limits
from algotrade.engines.backtest.sizing import targets_to_orders
from tests.factories import T0


def test_limits_clip_position_and_gross() -> None:
    out = apply_limits({"A": 0.8, "B": 0.8}, RiskLimits(max_position_weight=0.6))
    assert out == pytest.approx({"A": 0.5, "B": 0.5})


def test_limits_drop_shorts_unless_allowed() -> None:
    assert apply_limits({"A": -0.5}, RiskLimits()) == {"A": 0.0}
    allowed = RiskLimits(allow_short=True, max_gross_exposure=2.0)
    assert apply_limits({"A": -0.5}, allowed) == {"A": -0.5}


def test_limits_validate() -> None:
    with pytest.raises(ConfigurationError):
        RiskLimits(max_position_weight=2.0, max_gross_exposure=1.0)


def test_sizing_buys_whole_shares() -> None:
    orders = targets_to_orders({"A": 0.5}, {}, {"A": 30.0}, 1000.0, T0)
    assert len(orders) == 1
    assert orders[0].side is Side.BUY
    assert orders[0].quantity == 16  # 500 / 30 = 16.67, rounded down


def test_sizing_closes_positions_not_in_targets_and_sells_first() -> None:
    orders = targets_to_orders({"B": 1.0}, {"A": 10.0}, {"A": 10.0, "B": 10.0}, 100.0, T0)
    assert [(o.instrument_id, o.side) for o in orders] == [("A", Side.SELL), ("B", Side.BUY)]


def test_sizing_skips_tiny_changes_and_supports_lots() -> None:
    assert targets_to_orders({"A": 0.5}, {"A": 50.0}, {"A": 1.0}, 100.0, T0) == []
    orders = targets_to_orders({"A": 1.0}, {}, {"A": 1.0}, 250.0, T0, lot_size=100)
    assert orders[0].quantity == 200


def test_sizing_respects_contract_multiplier() -> None:
    # 10% of 100k into an option at $5 with multiplier 100 -> 10k / 500 per contract = 20
    orders = targets_to_orders({"OPT:X": 0.1}, {}, {"OPT:X": 5.0}, 100_000.0, T0,
                               multipliers={"OPT:X": 100.0})  # fmt: skip
    assert orders[0].quantity == 20
