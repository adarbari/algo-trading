"""``pivot_strength@v1`` by hand: touches counted with the ATR tolerance (the edge counts, the
close must stay on the near side, consecutive touching bars and a missing bar), the ages, the
pivot structure from the last two swing highs and lows (HH_HL, LH_LL, MIXED, equal pairs,
fewer than two), null ATR and null levels; point in time over the real chain."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_in_memory, compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.levels import pivot_strength as ps
from algotrade.features.rollups.levels import swing_levels
from algotrade.features.rollups.price import momentum
from tests.helpers.rollup_store import END, series, store, write_bars, write_rows

N = 40  # sessions written; the last, index 39, is END
LEVELS = "rollups/instrument/swing_levels@v1"
MOMENTUM = "rollups/instrument/momentum@v1"
ATR = 2.0  # so the touch tolerance is 1.0


def bars(
    highs: dict[int, float] | None = None,
    lows: dict[int, float] | None = None,
    closes: dict[int, float] | None = None,
) -> dict[str, list[float]]:
    """Flat bars (high 101, low 99, close 100) with the given sessions changed."""
    out = {"high": [101.0] * N, "low": [99.0] * N, "close": [100.0] * N}
    for column, edits in (("high", highs), ("low", lows), ("close", closes)):
        for i, value in (edits or {}).items():
            out[column][i] = value
    return out


def setup(
    data: dict[str, dict[str, list[float]]],
    levels: dict[str, dict[str, object]],
    atr: dict[str, float | None] | None = None,
    skip: dict[str, list[int]] | None = None,
) -> tuple[list[date], StoreReader]:
    """Bars, and the stored swing_levels / momentum rows of the session. ``levels`` by
    instrument: swing_high, swing_high_idx, swing_low, swing_low_idx (an index into the days)."""
    writer, reader = store()
    days = write_bars(
        writer,
        {i: d["close"] for i, d in data.items()},
        opens={i: d["close"] for i, d in data.items()},
        highs={i: d["high"] for i, d in data.items()},
        lows={i: d["low"] for i, d in data.items()},
        skip=skip,
    )
    rows = []
    for iid, lv in levels.items():
        high, low = lv.get("swing_high"), lv.get("swing_low")
        rows.append(
            {
                "instrument_id": iid,
                "swing_high": high,
                "swing_high_date": days[lv["swing_high_idx"]] if high is not None else None,  # type: ignore[index]
                "swing_low": low,
                "swing_low_date": days[lv["swing_low_idx"]] if low is not None else None,  # type: ignore[index]
            }
        )
    write_rows(writer, LEVELS, END, rows)
    write_rows(
        writer,
        MOMENTUM,
        END,
        [{"instrument_id": i, "atr_14": (atr or {}).get(i, ATR)} for i in data],
    )
    return days, reader


def rows(reader: StoreReader) -> dict[str, dict[str, object]]:
    frame = compute_one(reader, ps.GROUP, END).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def test_resistance_touches_by_hand() -> None:
    # the level is the 110 pivot at 20; the tolerance is 0.5 x 2.0 = 1.0
    highs = {
        20: 110.0,  # the pivot bar touches
        21: 109.5,  # next to it: the same touch
        25: 109.0,  # exactly 1.0 below: the edge counts, a second touch
        28: 108.9,  # 1.1 below: too far
        30: 110.8,  # above the level but within 1.0: a third touch
        33: 111.2,  # 1.2 above: too far
        35: 110.8,  # within, but the close is above the level: no touch ...
        36: 110.0,  # ... and a touching bar after a non-touching one is a new touch (fourth)
    }
    closes = {35: 110.5, 36: 110.0}  # a close AT the level still touches
    data = {"EQ:A": bars(highs=highs, closes=closes)}
    _, reader = setup(data, {"EQ:A": {"swing_high": 110.0, "swing_high_idx": 20}})
    out = rows(reader)["EQ:A"]
    assert out["resistance_touches"] == 4
    assert out["resistance_age"] == N - 1 - 20  # 19 sessions
    assert pd.isna(out["support_touches"]) and pd.isna(out["support_age"])  # no support level


def test_support_touches_mirror_with_lows() -> None:
    lows = {
        20: 90.0,  # the pivot bar
        22: 91.0,  # 1.0 above: the edge counts
        24: 88.9,  # 1.1 below: too far
        26: 89.0,  # 1.0 below: counts
        30: 89.0,  # near, but the close is below the level: no touch
    }
    data = {"EQ:A": bars(lows=lows, closes={30: 89.5})}
    _, reader = setup(data, {"EQ:A": {"swing_low": 90.0, "swing_low_idx": 20}})
    out = rows(reader)["EQ:A"]
    assert out["support_touches"] == 3 and out["support_age"] == 19
    assert pd.isna(out["resistance_touches"])


def test_a_missing_bar_splits_a_run_and_the_pivot_bar_always_touches() -> None:
    highs = {10: 110.0, 11: 110.0, 12: 110.0}
    data = {"EQ:RUN": bars(highs=highs), "EQ:HOLE": bars(highs=highs)}
    levels = {i: {"swing_high": 110.0, "swing_high_idx": 10} for i in data}
    _, reader = setup(data, levels, skip={"EQ:HOLE": [11]})
    out = rows(reader)
    assert out["EQ:RUN"]["resistance_touches"] == 1  # three consecutive bars: one touch
    assert out["EQ:HOLE"]["resistance_touches"] == 2  # a missing bar ends the run
    # a zero ATR gives a zero tolerance: only the level itself touches, the pivot bar still does
    _, flat = setup(
        {"EQ:Z": bars(highs={10: 110.0, 15: 110.5})}, {"EQ:Z": levels["EQ:RUN"]}, {"EQ:Z": 0.0}
    )
    assert rows(flat)["EQ:Z"]["resistance_touches"] == 1


def test_the_stored_float32_level_never_costs_the_pivot_bar_its_touch() -> None:
    high = 110.123456789  # not a float32: the stored level is rounded
    data = {"EQ:A": bars(highs={10: high}, closes={10: high})}  # the close at the high
    _, reader = setup(data, {"EQ:A": {"swing_high": float(np.float32(high)), "swing_high_idx": 10}})
    assert rows(reader)["EQ:A"]["resistance_touches"] == 1


def test_no_atr_nulls_the_touches_but_not_the_ages_or_the_structure() -> None:
    data = {"EQ:A": bars(highs={20: 110.0}, lows={20: 90.0})}
    levels = {
        "EQ:A": {"swing_high": 110.0, "swing_high_idx": 20, "swing_low": 90.0, "swing_low_idx": 20}
    }
    _, reader = setup(data, levels, atr={"EQ:A": None})
    out = rows(reader)["EQ:A"]
    assert pd.isna(out["resistance_touches"]) and pd.isna(out["support_touches"])
    assert out["resistance_age"] == 19 and out["support_age"] == 19


def peaks(highs: dict[int, float], lows: dict[int, float]) -> dict[str, list[float]]:
    return bars(highs=highs, lows=lows)


def test_pivot_structure_by_hand() -> None:
    up_h, down_h = {10: 105.0, 25: 108.0}, {10: 108.0, 25: 105.0}
    up_l, down_l = {15: 95.0, 30: 96.0}, {15: 96.0, 30: 95.0}
    data = {
        "EQ:UP": peaks(up_h, up_l),  # both step up
        "EQ:DOWN": peaks(down_h, down_l),  # both step down
        "EQ:MIX": peaks(up_h, down_l),  # higher highs, lower lows
        "EQ:FLAT": peaks({10: 105.0, 25: 105.0}, up_l),  # an equal pair is neither
        "EQ:ONEHIGH": peaks({10: 105.0}, up_l),  # one swing high: unknown
        "EQ:ONELOW": peaks(up_h, {15: 95.0}),
        "EQ:NONE": bars(),
    }
    levels = {i: {"swing_high": 120.0, "swing_high_idx": 10} for i in data}
    _, reader = setup(data, levels)
    out = {i: r["pivot_structure"] for i, r in rows(reader).items()}
    assert out == {
        "EQ:UP": "HH_HL",
        "EQ:DOWN": "LH_LL",
        "EQ:MIX": "MIXED",
        "EQ:FLAT": "MIXED",
        "EQ:ONEHIGH": None,
        "EQ:ONELOW": None,
        "EQ:NONE": None,
    }


def test_the_structure_uses_the_last_two_pivots_not_only_those_beyond_the_close() -> None:
    # three swing highs 110, 105, 108 (the last two step up) and lows 95, 96, 97 (all up)
    data = {"EQ:A": peaks({8: 110.0, 18: 105.0, 28: 108.0}, {13: 95.0, 23: 96.0, 33: 97.0})}
    _, reader = setup(data, {"EQ:A": {"swing_high": 110.0, "swing_high_idx": 8}})
    assert rows(reader)["EQ:A"]["pivot_structure"] == "HH_HL"  # 110 -> 105 is ignored: not last two


def test_only_instruments_with_a_swing_levels_row_get_one() -> None:
    data = {"EQ:A": bars(), "EQ:B": bars(highs={10: 110.0})}
    _, reader = setup(data, {"EQ:B": {"swing_high": 110.0, "swing_high_idx": 10}})
    assert list(rows(reader)) == ["EQ:B"]


def test_params_are_validated() -> None:
    with pytest.raises(ValueError):
        ps.PivotStrengthParams(touch_atr=0.0)
    wide = ps.PivotStrengthParams(touch_atr=2.0)  # tolerance 4: 106 touches the level 110
    data = {"EQ:A": bars(highs={10: 110.0, 20: 106.0})}
    _, reader = setup(data, {"EQ:A": {"swing_high": 110.0, "swing_high_idx": 10}})
    frame = compute_one(reader, ps.GROUP, END, wide).frame
    assert frame is not None and frame["resistance_touches"].tolist() == [2]
    assert rows(reader)["EQ:A"]["resistance_touches"] == 1


def test_point_in_time_over_the_chain_and_the_declared_ranges() -> None:
    full = {"EQ:A": series(300, seed=51), "EQ:B": series(300, seed=52, start=40.0)}
    writer, reader = store()
    days = write_bars(writer, full)
    picks = [days[i] for i in (60, 150, 260, 299)]
    chain = [momentum.GROUP, swing_levels.GROUP, ps.GROUP]
    results = compute_in_memory(reader, chain, picks)[ps.GROUP.key]
    seen = 0
    for result in results:
        k = days.index(result.session)
        small_writer, small = store()
        write_bars(small_writer, {i: c[: k + 1] for i, c in full.items()}, end=result.session)
        alone = compute_in_memory(small, chain, [result.session])[ps.GROUP.key][0].frame
        pd.testing.assert_frame_equal(alone, result.frame)
        frame = result.frame
        assert frame is not None
        for side in ("resistance", "support"):
            touches, age = frame[f"{side}_touches"].dropna(), frame[f"{side}_age"].dropna()
            assert (touches >= 1).all() and (touches <= ps.WINDOW).all()
            assert (age >= ps.PIVOT_WIDTH).all() and (age <= ps.FIRST_PIVOT).all()
            seen += len(touches)
        assert set(frame["pivot_structure"].dropna()) <= set(ps.STRUCTURES)
    assert seen > 0


def test_registered_with_the_declared_lookbacks() -> None:
    assert GROUPS["pivot_strength@v1"].table == "rollups/instrument/pivot_strength@v1"
    assert [i.sessions_back(None) for i in ps.GROUP.inputs] == [ps.WINDOW - 1, 0, 0]
