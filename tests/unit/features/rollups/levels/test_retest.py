"""``retest@v1`` by hand: the breakout rule (a close above the highest high of the 20 sessions
before), the latest one among the last 60 sessions (the boundary), every retest_state with its
precedence (the breakout session itself is never a retest, the tolerance edge counts, a null
ATR is NO_ATR except where FAILED or NONE needs none), the failed-breakout count (the first
session of a run counts once, a close below the level on the 20th session after counts and on
the 21st does not, a pending breakout counts only if already failed, gaps and short history are
null) and point in time."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_in_memory, compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.levels import retest as rt
from algotrade.features.rollups.price import momentum
from tests.helpers.rollup_store import END, series, store, write_bars, write_rows

N = 300  # sessions written; the last, index 299, is END (292 are read)
Bar = tuple[float, float, float]  # high, low, close
BASE: Bar = (101.0, 99.0, 100.0)
SPIKE: Bar = (103.0, 100.0, 102.5)  # a breakout of the base: close above the prior high 101
UP: Bar = (104.0, 103.0, 103.0)  # after a breakout at level 101: above level + tol, no new one
ATR = 2.0  # so the retest tolerance is 1.0: a low up to 102 retests the level 101


def path(*regimes: tuple[int, Bar], edits: dict[int, Bar] | None = None) -> list[Bar]:
    bars: list[Bar] = [BASE] * N
    for start, bar in regimes:
        bars[start:] = [bar] * (N - start)
    for i, bar in (edits or {}).items():
        bars[i] = bar
    return bars


def setup(
    data: dict[str, list[Bar]],
    atr: dict[str, float | None] | None = None,
    skip: dict[str, list[int]] | None = None,
) -> tuple[list[date], StoreReader]:
    writer, reader = store()
    days = write_bars(
        writer,
        {i: [b[2] for b in bars] for i, bars in data.items()},
        opens={i: [b[2] for b in bars] for i, bars in data.items()},  # open = close: always inside
        highs={i: [b[0] for b in bars] for i, bars in data.items()},
        lows={i: [b[1] for b in bars] for i, bars in data.items()},
        skip=skip,
    )
    write_rows(
        writer,
        "rollups/instrument/momentum@v1",
        END,
        [{"instrument_id": i, "atr_14": (atr or {}).get(i, ATR)} for i in data],
    )
    return days, reader


def rows(reader: StoreReader) -> dict[str, dict[str, object]]:
    frame = compute_one(reader, rt.GROUP, END).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def states(
    data: dict[str, list[Bar]], atr: dict[str, float | None] | None = None
) -> dict[str, str]:
    _, reader = setup(data, atr)
    return {i: str(r["retest_state"]) for i, r in rows(reader).items()}


def test_breakout_rule_by_hand() -> None:
    high = np.array([[101.0] * 21 + [103.0]]).T
    close = np.array([[100.0] * 20 + [101.0, 101.5]]).T  # at the prior high, then above it
    is_break, level = rt.breakouts(high, close)
    assert is_break[:, 0].tolist() == [False] * 21 + [True]  # a close AT the level is no breakout
    assert level[20, 0] == 101.0 and level[21, 0] == 101.0  # the 20 sessions before, itself out
    assert np.isnan(level[:20]).all()  # fewer than 20 sessions before
    gap = high.copy()
    gap[5] = np.nan  # a missing bar among the 20 voids the level
    assert not rt.breakouts(gap, close)[0][:21].any() and not rt.breakouts(gap, close)[0][21]


def test_every_retest_state_by_hand() -> None:
    b = 290  # a breakout at level 101, nine sessions ago; tolerance 1.0: a low up to 102 retests
    regime = [(b, SPIKE), (b + 1, UP)]
    out = states(
        {
            "EQ:FRESH": path(*regime),  # lows 103: never near the level
            "EQ:RETEST": path(*regime, edits={299: (104.0, 102.0, 103.0)}),  # low == level + tol
            "EQ:NEAR": path(*regime, edits={299: (104.0, 102.1, 103.0)}),  # just outside
            "EQ:BELOW": path(*regime, edits={299: (104.0, 100.0, 101.0)}),  # dips under, closes at
            "EQ:HELD": path(*regime, edits={295: (104.0, 101.5, 103.0)}),  # an earlier retest
            "EQ:FAILED": path(*regime, edits={295: (104.0, 100.0, 100.5)}),  # a close below 101
            "EQ:BOTH": path(
                *regime, edits={295: (104.0, 100.0, 100.5), 299: (104.0, 101.5, 103.0)}
            ),
            "EQ:NONE": path(),
            "EQ:TODAY": path((299, (104.0, 100.0, 103.0))),  # the breakout is today, low in tol
        }
    )
    assert out == {
        "EQ:FRESH": "FRESH",
        "EQ:RETEST": "RETESTING",
        "EQ:NEAR": "FRESH",
        "EQ:BELOW": "RETESTING",  # low under the level, close at it: a retest, not a failure
        "EQ:HELD": "HELD",
        "EQ:FAILED": "FAILED",
        "EQ:BOTH": "FAILED",  # a failure wins over today's retest
        "EQ:NONE": "NONE",
        "EQ:TODAY": "FRESH",  # the breakout session is not its own retest
    }


def test_the_latest_breakout_and_its_columns() -> None:
    days, reader = setup(
        {
            # breakouts at 270 (level 101) and 285 (close 105.5 > the prior high 104)
            "EQ:TWO": path(
                (270, SPIKE), (271, UP), (285, (106.0, 104.5, 105.5)), (286, (106.0, 105.0, 105.5))
            ),
            "EQ:ONE": path((299, (104.0, 103.0, 103.5))),
        }
    )
    out = rows(reader)
    two = out["EQ:TWO"]
    assert two["breakout_date"] == days[285] and two["sessions_since_breakout"] == 14
    assert two["breakout_level"] == 104.0  # the highest high of the 20 sessions before 285
    assert (
        out["EQ:ONE"]["sessions_since_breakout"] == 0 and out["EQ:ONE"]["breakout_level"] == 101.0
    )


def test_the_search_window_is_the_last_sixty_sessions() -> None:
    days, reader = setup(
        {"EQ:IN": path((240, SPIKE), (241, UP)), "EQ:OUT": path((239, SPIKE), (240, UP))}
    )
    out = rows(reader)
    assert (
        out["EQ:IN"]["sessions_since_breakout"] == 59 and out["EQ:IN"]["breakout_date"] == days[240]
    )
    assert out["EQ:OUT"]["retest_state"] == "NONE" and out["EQ:OUT"]["breakout_date"] is None
    assert pd.isna(out["EQ:OUT"]["breakout_level"])
    assert pd.isna(out["EQ:OUT"]["sessions_since_breakout"])


def test_no_atr_is_unknown_except_where_none_or_failed_need_none() -> None:
    regime = [(290, SPIKE), (291, UP)]
    out = states(
        {
            "EQ:FRESH": path(*regime),
            "EQ:FAILED": path(*regime, edits={295: (104.0, 100.0, 100.5)}),
            "EQ:NONE": path(),
        },
        atr={"EQ:FRESH": None, "EQ:FAILED": None, "EQ:NONE": None},
    )
    assert out == {"EQ:FRESH": "NO_ATR", "EQ:FAILED": "FAILED", "EQ:NONE": "NONE"}


def failed(
    data: dict[str, list[Bar]], skip: dict[str, list[int]] | None = None
) -> dict[str, float]:
    _, reader = setup(data, skip=skip)
    return {i: r["failed_breakouts_252d"] for i, r in rows(reader).items()}


def test_failed_breakouts_by_hand() -> None:
    held = [(150, SPIKE), (151, UP)]  # stays above its level to today: held, never counted
    runs = path(
        edits={100: (102.5, 100.0, 102.0), 101: (103.5, 101.0, 103.0), 102: (104.5, 102.0, 104.0)}
    )
    out = failed(
        {
            "EQ:TWO": path(edits={60: SPIKE, 100: SPIKE}),  # both revert at once: two failures
            "EQ:OLD": path(edits={47: SPIKE, 80: SPIKE}),  # 47 is outside the last 252 sessions
            "EQ:HELD": path(*held),
            "EQ:RUN": runs,  # three consecutive breakout sessions: one failed breakout
            "EQ:F20": path(
                (150, SPIKE), (151, (103.0, 101.5, 102.0)), (170, BASE)
            ),  # 20th session after
            "EQ:F21": path((150, SPIKE), (151, (103.0, 101.5, 102.0)), (171, BASE)),  # 21st: held
            "EQ:PENDING": path((285, SPIKE), (286, UP)),  # 14 sessions old, not failed: not counted
            "EQ:PENDFAIL": path((285, SPIKE), (286, UP), edits={290: (104.0, 100.0, 100.5)}),
            "EQ:NONE": path(),
        }
    )
    assert out == {
        "EQ:TWO": 2, "EQ:OLD": 1, "EQ:HELD": 0, "EQ:RUN": 1, "EQ:F20": 1, "EQ:F21": 0,
        "EQ:PENDING": 0, "EQ:PENDFAIL": 1, "EQ:NONE": 0,
    }  # fmt: skip


def test_failed_breakouts_are_null_on_a_gap_or_a_short_history() -> None:
    spiked = path(edits={60: SPIKE})
    out = failed({"EQ:OK": spiked, "EQ:GAP": spiked}, skip={"EQ:GAP": [120]})
    assert out["EQ:OK"] == 1 and pd.isna(out["EQ:GAP"])
    short = failed({"EQ:LONG": spiked, "EQ:NEW": spiked[-100:]})  # 100 bars: shorter than 292
    assert pd.isna(short["EQ:NEW"]) and short["EQ:LONG"] == 1


def test_params_are_validated() -> None:
    for bad in (
        {"search_sessions": 0},
        {"search_sessions": 273},
        {"retest_atr": 0.0},
        {"fail_sessions": 0},
    ):
        with pytest.raises(ValueError):
            rt.RetestParams(**bad)  # type: ignore[arg-type]
    wide = rt.RetestParams(retest_atr=2.0)  # tolerance 4: a low of 102.5 is a retest of 101
    _, reader = setup({"EQ:A": path((290, SPIKE), (291, (103.0, 102.5, 102.8)))})
    frame = compute_one(reader, rt.GROUP, END, wide).frame
    assert frame is not None and frame["retest_state"].tolist() == ["RETESTING"]
    assert rows(reader)["EQ:A"]["retest_state"] == "FRESH"  # the default tolerance 1.0: not near


def test_point_in_time_and_a_chain_from_stored_momentum() -> None:
    full = {"EQ:A": series(300, seed=41), "EQ:B": series(300, seed=42, start=40.0)}
    writer, reader = store()
    days = write_bars(writer, full)
    picks = [days[i] for i in (120, 200, 299)]
    chain = compute_in_memory(reader, [momentum.GROUP, rt.GROUP], picks)[rt.GROUP.key]
    for result in chain:
        k = days.index(result.session)
        small_writer, small = store()
        write_bars(small_writer, {i: c[: k + 1] for i, c in full.items()}, end=result.session)
        alone = compute_in_memory(small, [momentum.GROUP, rt.GROUP], [result.session])
        pd.testing.assert_frame_equal(alone[rt.GROUP.key][0].frame, result.frame)
    states_seen = {s for r in chain if r.frame is not None for s in r.frame["retest_state"]}
    assert states_seen <= set(rt.STATES) and len(states_seen) >= 2


def test_registered_with_the_declared_lookback() -> None:
    assert GROUPS["retest@v1"].table == "rollups/instrument/retest@v1"
    assert rt.GROUP.inputs[0].sessions_back(rt.GROUP.params) == rt.LOOKBACK == 291
    assert rt.GROUP.inputs[1].sessions_back(rt.GROUP.params) == 0
