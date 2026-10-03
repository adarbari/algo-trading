import numpy as np
import pytest

from algotrade.analytics.metrics import compute_metrics, max_drawdown
from algotrade.analytics.report import markdown_table
from tests.factories import fill


def test_max_drawdown() -> None:
    assert max_drawdown(np.array([100, 120, 90, 130])) == pytest.approx(0.25)
    assert max_drawdown(np.array([1, 2, 3])) == 0


def test_metrics_on_constant_growth() -> None:
    equity = 100 * 1.001 ** np.arange(253)
    m = compute_metrics(equity, [fill()], np.ones(253))
    assert m.total_return == pytest.approx(1.001**252 - 1)
    assert m.cagr == pytest.approx(m.total_return)
    assert m.max_drawdown == 0
    assert m.sortino == 0  # no down days
    assert m.num_trades == 1
    assert m.exposure == 1


def test_metrics_on_wipeout() -> None:
    m = compute_metrics(np.array([100.0, 50.0, 0.0]), [], np.zeros(3))
    assert m.cagr == -1
    assert m.exposure == 0


def test_metrics_need_two_points() -> None:
    with pytest.raises(ValueError, match="two"):
        compute_metrics(np.array([1.0]), [], np.zeros(1))


def test_markdown_table_formats() -> None:
    table = markdown_table(
        [{"strategy": "s", "total_return": 0.1234, "num_trades": 3.0, "sharpe": 1.234}],
        ["strategy", "total_return", "num_trades", "sharpe"],
    )
    assert "| s | 12.34% | 3 | 1.23 |" in table
