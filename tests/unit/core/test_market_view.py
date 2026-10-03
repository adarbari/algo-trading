import numpy as np
import pytest

from algotrade.core.market_view import MarketView
from tests.factories import series_from_closes


@pytest.fixture
def view() -> MarketView:
    return MarketView({"TEST": series_from_closes([1, 2, 3, 4, 5])}, cursor=2)


def test_history_stops_at_cursor(view: MarketView) -> None:
    np.testing.assert_array_equal(view.history("TEST"), [1, 2, 3])


def test_history_lookback(view: MarketView) -> None:
    np.testing.assert_array_equal(view.history("TEST", lookback=2), [2, 3])
    np.testing.assert_array_equal(view.history("TEST", lookback=10), [1, 2, 3])


def test_latest_and_index(view: MarketView) -> None:
    assert view.latest("TEST") == 3
    assert view.bar_index == 2
    assert view.instruments == ("TEST",)
    assert view.symbols == view.instruments  # deprecated alias
    assert view.now.tzinfo is not None


def test_history_is_read_only(view: MarketView) -> None:
    with pytest.raises(ValueError, match="read-only"):
        view.history("TEST")[0] = 99


def test_invalid_lookback(view: MarketView) -> None:
    with pytest.raises(ValueError, match="positive"):
        view.history("TEST", lookback=0)


def test_cursor_out_of_range() -> None:
    with pytest.raises(IndexError):
        MarketView({"TEST": series_from_closes([1, 2])}, cursor=2)


def test_misaligned_series_rejected() -> None:
    with pytest.raises(ValueError, match="aligned"):
        MarketView({"A": series_from_closes([1, 2]), "B": series_from_closes([1, 2, 3])}, 0)
