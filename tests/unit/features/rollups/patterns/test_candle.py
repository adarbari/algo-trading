"""``candle@v1``: body and wick shares, the body against the 20-session average, each bar
relation and each named candle by hand, the precedence between them, the no-range and
previous-bar nulls, and point in time (a session's row on bars up to it equals the
backfilled row)."""

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.patterns import candle as cd
from algotrade.features.rollups.price.price_stats import Panel
from tests.helpers.rollup_store import END, store, write_bars
from tests.unit.features.rollups.price.test_momentum import rows

P = cd.CandleParams()


def bars(*ohlc: tuple[float, float, float, float], base: float = 100.0, n: int = 21) -> Panel:
    """``n`` sessions of one instrument: the earlier ones are 2-point bodies (open 99, close
    101: the 20-session average body is 2) around ``base``; the last ``len(ohlc)`` are given."""
    quiet = [(base - 1, base + 2, base - 2, base + 1)] * (n - len(ohlc))
    o, h, low, c = (
        np.array([b[i] for b in (*quiet, *ohlc)], dtype=float)[:, None] for i in range(4)
    )
    return Panel(np.array(["EQ:A"]), o, h, low, c, np.ones_like(o))


def candle_of(*ohlc: tuple[float, float, float, float]) -> str | None:
    return cd.named_candle(bars(*ohlc), P)[0]


def test_shares_by_hand() -> None:
    out = cd.shape(bars((100.0, 110.0, 90.0, 105.0)))  # range 20, body 5, upper 5, lower 10
    assert out["body_share"][0] == pytest.approx(0.25)
    assert out["upper_wick_share"][0] == pytest.approx(0.25)
    assert out["lower_wick_share"][0] == pytest.approx(0.5)
    down = cd.shape(bars((105.0, 110.0, 90.0, 100.0)))  # the same bar, falling
    assert down["upper_wick_share"][0] == pytest.approx(0.25)
    assert down["lower_wick_share"][0] == pytest.approx(0.5)


def test_no_range_bar_has_null_shares_and_candle_but_a_relation() -> None:
    px = bars((100.0, 100.0, 100.0, 100.0))
    assert all(np.isnan(v[0]) for v in cd.shape(px).values())
    assert cd.named_candle(px, P)[0] is None
    assert cd.relation(px.high[-1], px.low[-1], px.high[-2], px.low[-2])[0] == "INSIDE"


@pytest.mark.parametrize(
    ("bar", "expected"),
    [
        ((100.0, 101.0, 99.5, 100.5), "INSIDE"),  # previous 98..102
        ((100.0, 103.0, 97.0, 101.0), "OUTSIDE"),
        ((105.0, 108.0, 103.0, 107.0), "UP_GAP"),
        ((92.0, 95.0, 90.0, 93.0), "DOWN_GAP"),
        ((101.0, 104.0, 99.0, 103.0), "OVERLAP"),  # higher high, low inside
        ((100.0, 102.0, 98.0, 101.0), "INSIDE"),  # equal extremes count as inside
        ((100.0, 103.0, 98.0, 101.0), "OVERLAP"),  # higher high, equal low
        ((103.0, 106.0, 102.0, 104.0), "OVERLAP"),  # a low equal to the previous high is no gap
    ],
)
def test_bar_relation_each_label(bar: tuple[float, float, float, float], expected: str) -> None:
    px = bars(bar)
    assert cd.relation(px.high[-1], px.low[-1], px.high[-2], px.low[-2])[0] == expected


def test_previous_bar_relation_is_the_relation_one_session_back() -> None:
    px = bars((100.0, 101.0, 99.5, 100.5), (100.0, 104.0, 99.0, 103.0))  # inside, then up
    out = cd.relation(px.high[-2], px.low[-2], px.high[-3], px.low[-3])
    assert out[0] == "INSIDE"


def test_each_named_candle() -> None:
    assert candle_of((100.0, 101.2, 95.0, 101.0)) == "HAMMER"  # lower wick 5.0 vs body 1.0
    assert candle_of((101.0, 106.2, 100.0, 100.0)) == "SHOOTING_STAR"  # upper wick 5.2
    assert candle_of((100.0, 105.0, 95.0, 100.5)) == "DOJI"  # body 0.05 of the range
    assert candle_of((100.0, 103.0, 98.0, 101.0)) == "NONE"
    # previous bar down (101 -> 99, body 2), today up from 98.5 to 102.5: body 4, 2 x the average
    assert candle_of((101.0, 101.5, 99.0, 99.0), (98.5, 103.0, 98.0, 102.5)) == "BULLISH_ENGULFING"
    assert candle_of((99.0, 101.0, 98.5, 101.0), (101.5, 102.0, 97.0, 97.5)) == "BEARISH_ENGULFING"


def test_hammer_needs_a_small_other_wick_and_a_body_above_doji() -> None:
    # lower wick 4, body 1: an upper wick of 1.5 (0.23 of the range) passes, 2.5 (0.33) fails
    assert candle_of((100.0, 102.5, 96.0, 101.0)) == "HAMMER"
    assert candle_of((100.0, 103.5, 96.0, 101.0)) == "NONE"
    # a hammer shape whose body is a doji share of the range reads DOJI
    assert candle_of((100.0, 100.4, 90.0, 100.2)) == "DOJI"


def test_engulfing_needs_the_average_body_and_covering_the_previous_body() -> None:
    prev = (101.0, 101.5, 99.0, 99.0)
    assert candle_of(prev, (98.5, 100.0, 98.0, 99.8)) == "NONE"  # the close stays under 101
    # covers the previous body (open 98.9 <= 99, close 101.1 >= 101): body 2.2 >= 0.5 x 2
    assert candle_of(prev, (98.9, 101.5, 98.5, 101.1)) == "BULLISH_ENGULFING"
    # covers the previous body but the average body is 10: 2.2 < 5, not engulfing
    big = bars(prev, (98.9, 101.5, 98.5, 101.1))
    big.open[:-2] = big.close[:-2] - 10.0
    assert cd.named_candle(big, P)[0] != "BULLISH_ENGULFING"


def test_precedence_engulfing_beats_hammer_and_hammer_beats_doji() -> None:
    prev = (101.0, 101.5, 99.0, 99.0)
    # an up body 98.9 -> 101.1 with a long lower wick: also a hammer shape, engulfing wins
    assert candle_of(prev, (98.9, 101.2, 90.0, 101.1)) == "BULLISH_ENGULFING"
    # no engulfing (previous bar up): the same shape is a HAMMER
    assert candle_of((99.0, 101.5, 98.5, 101.0), (98.9, 101.2, 90.0, 101.1)) == "HAMMER"


def test_previous_bar_missing_is_null() -> None:
    px = bars((100.0, 103.0, 98.0, 101.0))
    for m in (px.open, px.high, px.low, px.close):
        m[-2] = np.nan
    assert cd.named_candle(px, P)[0] is None
    assert cd.relation(px.high[-1], px.low[-1], px.high[-2], px.low[-2])[0] is None
    assert not np.isnan(cd.shape(px)["body_share"][0])  # the shares need only the session


def test_body_vs_average_by_hand_and_nulls() -> None:
    px = bars((100.0, 106.0, 99.0, 104.0))  # body 4 over 20 bodies of 2
    assert cd.body_vs_average(px)[0] == pytest.approx(2.0)
    gap = bars((100.0, 106.0, 99.0, 104.0))
    gap.open[-10] = gap.close[-10] = np.nan
    assert np.isnan(cd.body_vs_average(gap)[0])
    flat = bars((100.0, 106.0, 99.0, 104.0))
    flat.open[:-1] = flat.close[:-1]  # every earlier body zero
    assert np.isnan(cd.body_vs_average(flat)[0])
    # the session's own body is not in the average: 20 earlier sessions only
    older = bars((100.0, 106.0, 99.0, 104.0), n=22)
    older.open[0], older.close[0] = 0.0, 50.0  # the 21st session back: outside the window
    assert cd.body_vs_average(older)[0] == pytest.approx(2.0)


def test_compute_end_to_end_and_short_history() -> None:
    writer, reader = store()
    n = 40
    close = np.full(n, 100.0)
    open_ = np.full(n, 99.0)  # a 1-point body every session
    high, low = np.full(n, 102.0), np.full(n, 98.0)
    open_[-1], high[-1], low[-1], close[-1] = 100.0, 101.5, 97.0, 101.0  # a hammer, body 1
    write_bars(
        writer,
        {"EQ:A": close, "EQ:NEW": close[-2:]},
        opens={"EQ:A": open_, "EQ:NEW": open_[-2:]},
        highs={"EQ:A": high, "EQ:NEW": high[-2:]},
        lows={"EQ:A": low, "EQ:NEW": low[-2:]},
    )
    out = rows(compute_one(reader, cd.GROUP, END).frame)
    a = out["EQ:A"]
    assert a["candle"] == "HAMMER" and a["bar_relation"] == "OVERLAP"
    assert a["prev_bar_relation"] == "INSIDE"  # equal extremes the session before
    assert a["body_vs_avg_20d"] == pytest.approx(1.0)
    new = out["EQ:NEW"]  # two bars: the relation exists, the average and the prior relation do not
    assert new["bar_relation"] == "OVERLAP" and pd.isna(new["body_vs_avg_20d"])
    assert pd.isna(new["prev_bar_relation"]) and new["candle"] == "HAMMER"


def test_point_in_time_a_session_never_sees_later_bars() -> None:
    rng = np.random.default_rng(5)
    n = 60
    close = 100 + np.cumsum(rng.normal(0, 1.5, n))
    open_ = close + rng.normal(0, 1.0, n)
    high = np.maximum(open_, close) + rng.uniform(0.1, 1.5, n)
    low = np.minimum(open_, close) - rng.uniform(0.1, 1.5, n)
    writer, reader = store()
    days = write_bars(
        writer, {"EQ:A": close}, opens={"EQ:A": open_}, highs={"EQ:A": high}, lows={"EQ:A": low}
    )
    picks = [days[i] for i in (30, 45, 59)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, cd.GROUP, picks)}
    for k, day in zip((30, 45, 59), picks, strict=True):
        w2, r2 = store()
        write_bars(
            w2, {"EQ:A": close[: k + 1]}, end=day, opens={"EQ:A": open_[: k + 1]},
            highs={"EQ:A": high[: k + 1]}, lows={"EQ:A": low[: k + 1]},
        )  # fmt: skip
        alone = compute_one(r2, cd.GROUP, day).frame
        pd.testing.assert_frame_equal(
            backfilled[day].reset_index(drop=True), alone.reset_index(drop=True)
        )


def test_params_are_validated() -> None:
    for bad in (
        {"doji_body": 0.0}, {"doji_body": 1.0}, {"small_body": 1.5}, {"hammer_wick": 0.0},
        {"engulf_min_body": -1.0},
    ):  # fmt: skip
        with pytest.raises(ValueError):
            cd.CandleParams(**bad)
