"""``volume@v1``: every column by hand on a 21-session series (a flat close, a high == low bar);
gaps and short history are null for exactly the windows they touch (never a shorter window or
zero); zero volume is null without warnings; split-adjusted as of each session (a 2:1 split is
no volume spike); point in time (a session's row computed on bars up to it equals the
backfilled row, and later bars never change it)."""

import math
import warnings
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.price import volume as vo
from tests.helpers.rollup_store import END, series, store, write_bars, write_split

F32 = 2e-7
WINDOW_COLUMNS = (
    "adv_shares_20d",
    "volume_ratio_5d_20d",
    "volume_z_20d",
    "up_volume_share_20d",
    "cmf_20d",
)


def rows(frame: pd.DataFrame | None) -> dict[str, dict[str, float]]:
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def hand_series() -> tuple[list[float], list[float], list[float], list[float]]:
    """21 sessions (0..20). Volume alternates 900 (even) / 1100 (odd), 1500 on the session.
    Odd sessions close up 1 at the high (mfm +1), even ones down 1 at the low (mfm -1), except
    session 2 (unchanged close) and session 20 (up 2, high == low: mfm 0)."""
    close, high, low, volume = [100.0], [101.0], [99.0], [900.0]
    for i in range(1, 21):
        step = 2.0 if i == 20 else 0.0 if i == 2 else 1.0 if i % 2 else -1.0
        c = close[-1] + step
        close.append(c)
        high.append(c if i % 2 or i == 20 else c + 2)
        low.append(c - 2 if i % 2 else c)
        volume.append(1500.0 if i == 20 else 1100.0 if i % 2 else 900.0)
    return close, high, low, volume


def test_every_column_by_hand() -> None:
    writer, reader = store()
    close, high, low, volume = hand_series()
    write_bars(
        writer,
        {"EQ:A": close},
        opens={"EQ:A": close},  # open = close: every bar inside its high-low range
        volume={"EQ:A": volume},
        highs={"EQ:A": high},
        lows={"EQ:A": low},
    )
    out = rows(compute_one(reader, vo.GROUP, END).frame)["EQ:A"]
    assert close[-1] == 104.0  # 100 + 10 up - 8 down + 2
    assert out["session_volume"] == 1500.0
    assert out["dollar_volume"] == pytest.approx(104.0 * 1500, rel=F32)
    total = 19_100 + 1500  # sessions 1..20
    assert out["adv_shares_20d"] == pytest.approx(total / 20, rel=F32)  # 1030
    last5 = (900 + 1100 + 900 + 1100 + 1500) / 5  # sessions 16..20
    assert out["volume_ratio_5d_20d"] == pytest.approx(last5 / (total / 20), rel=F32)
    # base: sessions 0..19, ten of 900 and ten of 1100: mean 1000, stdev 100 x sqrt(20 / 19)
    assert out["volume_z_20d"] == pytest.approx(500 / (100 * math.sqrt(20 / 19)), rel=F32)
    # up sessions: the ten odd ones (1100) and the session (1500); session 2 is neither
    assert out["up_volume_share_20d"] == pytest.approx((11_000 + 1500) / total, rel=F32)
    # mfm x volume: +1100 x 10 (odd), -900 x 9 (even 2..18), 0 x 1500 (high == low)
    assert out["cmf_20d"] == pytest.approx((11_000 - 8100) / total, rel=F32)


def test_gaps_and_short_history_are_null_for_the_windows_they_touch() -> None:
    writer, reader = store()
    write_bars(
        writer,
        {
            "EQ:GAP": series(30, seed=2),
            "EQ:BEFORE": series(30, seed=3),
            "EQ:N20": series(20, seed=4),
            "EQ:N19": series(19, seed=5),
        },
        skip={"EQ:GAP": [25], "EQ:BEFORE": [9]},  # 5 / 21 sessions before the end
        volume={i: list(np.arange(1000.0, 1030.0)) for i in ("EQ:GAP", "EQ:BEFORE")},
    )
    out = rows(compute_one(reader, vo.GROUP, END).frame)
    assert all(np.isnan(out["EQ:GAP"][c]) for c in WINDOW_COLUMNS)
    assert out["EQ:GAP"]["session_volume"] == 1029.0 and out["EQ:GAP"]["dollar_volume"] > 0
    for iid in ("EQ:BEFORE", "EQ:N20"):  # the last 20 sessions have bars, the 21st not
        known = ("adv_shares_20d", "volume_ratio_5d_20d", "cmf_20d")
        assert all(not np.isnan(out[iid][c]) for c in known), iid
        assert np.isnan(out[iid]["volume_z_20d"]) and np.isnan(out[iid]["up_volume_share_20d"])
    assert all(np.isnan(out["EQ:N19"][c]) for c in WINDOW_COLUMNS)
    assert out["EQ:N19"]["session_volume"] == 1000.0


def test_zero_or_constant_volume_is_null_not_zero_or_inf() -> None:
    writer, reader = store()
    write_bars(
        writer,
        {"EQ:IDLE": series(25, seed=6), "EQ:FLAT": series(25, seed=7)},
        volume={"EQ:IDLE": [0.0] * 25, "EQ:FLAT": [1000.0] * 24 + [3000.0]},
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = rows(compute_one(reader, vo.GROUP, END).frame)
    idle = out["EQ:IDLE"]
    assert idle["session_volume"] == 0.0 and idle["adv_shares_20d"] == 0.0  # known: no trades
    assert all(np.isnan(idle[c]) for c in WINDOW_COLUMNS[1:])
    flat = out["EQ:FLAT"]
    assert np.isnan(flat["volume_z_20d"])  # zero stdev before the session: no z-score
    assert flat["volume_ratio_5d_20d"] == pytest.approx(1400 / 1100, rel=F32)


def test_split_adjusted_as_of_each_session() -> None:
    writer, reader = store()
    c = series(60, seed=8)
    raw = c.copy()
    raw[-5:] /= 2  # 2-for-1 split 5 sessions before the end
    volume = 1000.0 + 300.0 * np.sin(np.arange(60.0))
    raw_volume = volume.copy()
    raw_volume[-5:] *= 2
    days = write_bars(  # open = close: no bar straddles the split
        writer,
        {"EQ:P": c, "EQ:S": raw},
        volume={"EQ:P": volume, "EQ:S": raw_volume},
        opens={"EQ:P": c, "EQ:S": raw},
    )
    write_split(writer, "EQ:S", days[-5], 2.0, stored=END)
    shares = ("session_volume", "adv_shares_20d")
    for result in compute_sessions(reader, vo.GROUP, days[-8:]):
        out = rows(result.frame)
        for column in vo.COLUMNS:
            after = result.session >= days[-5]  # before the ex-date: unadjusted
            scale = 2.0 if column in shares and after else 1.0
            assert out["EQ:S"][column] == pytest.approx(out["EQ:P"][column] * scale, rel=1e-5)


def truncated(full: dict[str, np.ndarray], days: list[date], k: int) -> StoreReader:
    """A store holding only the bars up to ``days[k]``."""
    writer, reader = store()
    offsets = {i: len(days) - len(c) for i, c in full.items()}  # a shorter series starts later
    kept = {i: c[: k + 1 - offsets[i]] for i, c in full.items() if k >= offsets[i]}
    vols = {i: 1000.0 + 10.0 * np.arange(len(c)) % 7 for i, c in kept.items()}
    write_bars(writer, kept, end=days[k], volume=vols)
    return reader


def test_point_in_time_a_session_never_sees_later_bars() -> None:
    full = {"EQ:A": series(80, seed=11), "EQ:B": series(50, seed=12, start=50.0)}
    writer, reader = store()
    vols = {i: 1000.0 + 10.0 * np.arange(len(c)) % 7 for i, c in full.items()}
    days = write_bars(writer, full, volume=vols)
    picks = [days[i] for i in (40, 55, 70, 79)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, vo.GROUP, picks)}
    for day in picks:
        alone = compute_one(truncated(full, days, days.index(day)), vo.GROUP, day).frame
        pd.testing.assert_frame_equal(alone, backfilled[day])


def test_columns_are_float32_and_registered_with_the_declared_lookback() -> None:
    writer, reader = store()
    write_bars(writer, {"EQ:A": series(25)})
    frame = compute_one(reader, vo.GROUP, END).frame
    assert frame is not None
    assert {c: str(frame[c].dtype) for c in vo.COLUMNS} == dict.fromkeys(vo.COLUMNS, "float32")
    assert GROUPS["volume@v1"].table == "rollups/instrument/volume@v1"
    assert vo.GROUP.inputs[0].sessions_back(None) == vo.LOOKBACK
    assert len(sessions_ending(END, vo.LOOKBACK + 1)) == 21
