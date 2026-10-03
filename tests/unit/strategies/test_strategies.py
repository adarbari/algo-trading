import pytest

from algotrade.core.errors import ConfigurationError
from algotrade.core.market_view import MarketView
from algotrade.strategies.trading.buy_and_hold import BuyAndHold
from algotrade.strategies.trading.registry import STRATEGIES, create_strategy
from algotrade.strategies.trading.sma_crossover import SmaCrossover
from algotrade.strategies.trading.zscore_mean_reversion import ZScoreMeanReversion
from tests.factories import series_from_closes


def views(closes: list[float]) -> list[MarketView]:
    data = {"TEST": series_from_closes(closes)}
    return [MarketView(data, t) for t in range(len(closes))]


def test_buy_and_hold_invests_once() -> None:
    s = BuyAndHold()
    vs = views([1, 2, 3])
    assert s.on_bar(vs[0]) == {"TEST": 1.0}
    assert s.on_bar(vs[1]) is None


def test_sma_crossover_enters_on_uptrend_and_exits_on_downtrend() -> None:
    s = SmaCrossover(fast=2, slow=4)
    closes = [10, 10, 10, 10, 12, 14, 16, 12, 8, 6]
    decisions = [s.on_bar(v) for v in views(closes)[s.warmup_bars - 1 :]]
    assert decisions.index({}) > decisions.index({"TEST": 1.0})
    assert s.params() == {"fast": 2, "slow": 4}


def test_sma_rejects_bad_windows() -> None:
    with pytest.raises(ConfigurationError):
        SmaCrossover(fast=10, slow=5)


def test_zscore_buys_dip_and_exits_on_reversion() -> None:
    s = ZScoreMeanReversion(lookback=5, entry_z=1.0, exit_z=0.0)
    closes = [10, 10.1, 9.9, 10, 10, 8, 9, 10.5, 11]
    decisions = [s.on_bar(v) for v in views(closes)[s.warmup_bars - 1 :]]
    assert decisions[1] == {"TEST": 1.0}  # bought the dip at 8
    assert {} in decisions[2:]  # exited after reverting


def test_zscore_flat_prices_do_nothing() -> None:
    s = ZScoreMeanReversion(lookback=3)
    assert all(s.on_bar(v) is None for v in views([5, 5, 5, 5])[2:])


@pytest.mark.parametrize("kwargs", [{"lookback": 1}, {"entry_z": 1.0, "exit_z": 1.0}])
def test_zscore_rejects_bad_params(kwargs: dict[str, float]) -> None:
    with pytest.raises(ConfigurationError):
        ZScoreMeanReversion(**kwargs)  # type: ignore[arg-type]


def test_registry() -> None:
    assert set(STRATEGIES) == {"buy_and_hold", "sma_crossover", "zscore_mean_reversion"}
    assert isinstance(create_strategy("sma_crossover", fast=5, slow=10), SmaCrossover)
    with pytest.raises(ConfigurationError, match="Unknown"):
        create_strategy("nope")
    with pytest.raises(ConfigurationError, match="Bad parameters"):
        create_strategy("sma_crossover", nonsense=1)
