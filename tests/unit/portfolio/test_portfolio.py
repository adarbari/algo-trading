import pytest

from algotrade.core.types import Side
from algotrade.portfolio.portfolio import Portfolio
from tests.factories import fill


def test_buy_then_sell_round_trip() -> None:
    p = Portfolio(1_000)
    p.apply_fill(fill(qty=5, price=100, commission=1))
    assert p.cash == 499
    assert p.positions == {"TEST": 5}
    assert p.equity({"TEST": 110}) == 1049
    p.apply_fill(fill(side=Side.SELL, qty=5, price=110, commission=1))
    assert p.positions == {}
    assert p.cash == 1048
    assert p.total_commission == 2


def test_gross_exposure() -> None:
    p = Portfolio(1_000)
    p.apply_fill(fill(qty=5, price=100))
    assert p.gross_exposure({"TEST": 100}) == pytest.approx(0.5)


def test_exposure_infinite_when_equity_wiped_out() -> None:
    p = Portfolio(100)
    p.apply_fill(fill(qty=1, price=100))
    assert p.gross_exposure({"TEST": 0.0}) == float("inf")


def test_positions_are_read_only() -> None:
    p = Portfolio(100)
    with pytest.raises(TypeError):
        p.positions["X"] = 1  # type: ignore[index]


def test_rejects_non_positive_cash() -> None:
    with pytest.raises(ValueError, match="positive"):
        Portfolio(0)
