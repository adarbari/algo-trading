"""``core.bars.ohlcv_problems``: the one OHLCV sanity check."""

from algotrade.core.bars import ohlcv_problems


def test_sane_bars_have_no_problems() -> None:
    assert ohlcv_problems([10.0], [11.0], [9.0], [10.5], [100.0]) == []


def test_each_problem_is_named() -> None:
    assert ohlcv_problems([10.0], [11.0], [9.0], [float("nan")], [1.0]) == [
        "bars contain NaN prices or volume"
    ]
    problems = ohlcv_problems([10.0, -1.0], [9.0, 1.0], [11.0, -2.0], [10.0, 1.0], [-1.0, 0.0])
    assert problems == [
        "non-positive prices",
        "negative volume",
        "high below open/close",
        "low above open/close",
    ]
