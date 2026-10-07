"""``gaps@v1`` by hand: up and down gaps, the fill rule (a later low at or below the previous
high, a later high at or above the previous low; the edge counts), the nearest unfilled zone
wholly below or above the close, a close inside a zone, today's gap and today's fill, the
opening gap and its null without a previous bar; point in time."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.levels import gaps as gp
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import END, series, store, write_bars

N = 30  # sessions written; the last, index 29, is END
Bar = tuple[float, float, float, float]  # open, high, low, close
BASE: Bar = (100.0, 101.0, 99.0, 100.0)
UP: Bar = (105.0, 106.0, 104.0, 105.0)  # after an up gap: lows stay above 103
DOWN: Bar = (95.0, 96.0, 94.0, 95.0)  # after a down gap: highs stay below 97
F32 = 2e-7


def path(*regimes: tuple[int, Bar], edits: dict[int, Bar] | None = None) -> list[Bar]:
    """Bars by session: each regime holds from its first index until the next one."""
    bars: list[Bar] = [BASE] * N
    for start, bar in regimes:
        bars[start:] = [bar] * (N - start)
    for i, bar in (edits or {}).items():
        bars[i] = bar
    return bars


def write(
    data: dict[str, list[Bar]], skip: dict[str, list[int]] | None = None
) -> tuple[list[date], StoreReader]:
    writer, reader = store()
    days = write_bars(
        writer,
        {i: [b[3] for b in bars] for i, bars in data.items()},
        opens={i: [b[0] for b in bars] for i, bars in data.items()},
        highs={i: [b[1] for b in bars] for i, bars in data.items()},
        lows={i: [b[2] for b in bars] for i, bars in data.items()},
        skip=skip,
    )
    return days, reader


def rows(reader: StoreReader) -> dict[str, dict[str, object]]:
    frame = compute_one(reader, gp.GROUP, END).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def test_unfilled_up_gap_is_support_below_with_its_upper_edge() -> None:
    gapped = path((10, (104.0, 106.0, 103.0, 105.0)), (11, UP))  # low 103 > previous high 101
    days, reader = write({"EQ:A": gapped})
    out = rows(reader)["EQ:A"]
    assert out["gap_below"] == 103.0 and out["gap_below_date"] == days[10]  # zone [101, 103]
    assert np.isnan(out["gap_above"]) and out["gap_above_date"] is None


def test_an_up_gap_is_filled_by_a_later_low_at_or_below_the_previous_high() -> None:
    gapped = [(10, (104.0, 106.0, 103.0, 105.0)), (11, UP)]
    _, reader = write(
        {
            "EQ:EDGE": path(*gapped, edits={20: (103.0, 106.0, 101.0, 105.0)}),  # low == 101
            "EQ:NEAR": path(*gapped, edits={20: (103.0, 106.0, 101.5, 105.0)}),  # stops short
            "EQ:TODAY": path(*gapped, edits={29: (103.0, 106.0, 101.0, 105.0)}),  # today fills it
        }
    )
    out = rows(reader)
    assert np.isnan(out["EQ:EDGE"]["gap_below"])  # the edge counts as filled
    assert out["EQ:NEAR"]["gap_below"] == 103.0
    assert np.isnan(out["EQ:TODAY"]["gap_below"])  # through today, the session included


def test_unfilled_down_gap_is_resistance_above_with_its_lower_edge() -> None:
    gapped = path((10, (96.0, 97.0, 94.0, 95.0)), (11, DOWN))  # high 97 < previous low 99
    days, reader = write({"EQ:A": gapped})
    out = rows(reader)["EQ:A"]
    assert out["gap_above"] == 97.0 and out["gap_above_date"] == days[10]  # zone [97, 99]
    assert np.isnan(out["gap_below"]) and out["gap_below_date"] is None


def test_a_down_gap_is_filled_by_a_later_high_at_or_above_the_previous_low() -> None:
    gapped = [(10, (96.0, 97.0, 94.0, 95.0)), (11, DOWN)]
    _, reader = write(
        {
            "EQ:EDGE": path(*gapped, edits={20: (96.0, 99.0, 94.0, 95.0)}),  # high == 99
            "EQ:NEAR": path(*gapped, edits={20: (96.0, 98.5, 94.0, 95.0)}),
        }
    )
    out = rows(reader)
    assert np.isnan(out["EQ:EDGE"]["gap_above"])
    assert out["EQ:NEAR"]["gap_above"] == 97.0


def test_the_nearest_zone_wins_and_the_older_ones_stay_unfilled() -> None:
    days, reader = write(
        {
            # up gaps at 8 (zone [101, 103]) and 15 (zone [106, 108]): the nearer one is 108
            "EQ:UP": path(
                (8, (104.0, 106.0, 103.0, 105.0)),
                (9, UP),
                (15, (109.0, 110.0, 108.0, 109.0)),
                (16, (109.0, 110.0, 108.0, 109.0)),
            ),
            # down gaps at 8 (zone [97, 99]) and 15 (zone [92, 94]): the nearer edge is 92
            "EQ:DOWN": path(
                (8, (96.0, 97.0, 94.0, 95.0)),
                (9, DOWN),
                (15, (91.0, 92.0, 90.0, 91.0)),
                (16, (91.0, 92.0, 90.0, 91.0)),
            ),
        }
    )
    out = rows(reader)
    assert out["EQ:UP"]["gap_below"] == 108.0 and out["EQ:UP"]["gap_below_date"] == days[15]
    assert out["EQ:DOWN"]["gap_above"] == 92.0 and out["EQ:DOWN"]["gap_above_date"] == days[15]


def test_a_close_inside_the_zone_is_neither_above_nor_below() -> None:
    # up gap zone [101, 103]; price falls back to a close of 102 without reaching 101
    fall, stay = (103.0, 105.0, 101.5, 102.0), (102.0, 103.0, 101.5, 102.0)
    _, reader = write(
        {"EQ:IN": path((10, (104.0, 106.0, 103.0, 105.0)), (11, UP), (25, fall), (26, stay))}
    )
    out = rows(reader)["EQ:IN"]
    assert np.isnan(out["gap_below"]) and np.isnan(out["gap_above"])


def test_a_gap_today_and_the_opening_gap() -> None:
    days, reader = write(
        {"EQ:T": path(edits={29: (103.5, 105.0, 103.0, 104.0)})}
    )  # low 103 > high 101
    out = rows(reader)["EQ:T"]
    assert out["gap_below"] == 103.0 and out["gap_below_date"] == days[29]
    assert out["gap_open_pct"] == pytest.approx(103.5 / 100.0 - 1, rel=F32)  # 0.035
    # and a down open: 98 / 100 - 1
    _, reader = write({"EQ:D": path(edits={29: (98.0, 98.5, 97.0, 98.0)})})
    assert rows(reader)["EQ:D"]["gap_open_pct"] == pytest.approx(-0.02, rel=F32)


def test_no_previous_bar_means_no_opening_gap() -> None:
    _, reader = write(
        {"EQ:MISS": path(), "EQ:NEW": path()[29:], "EQ:OK": path()},
        skip={"EQ:MISS": [28]},  # no bar on the session before today
    )
    out = rows(reader)
    assert np.isnan(out["EQ:MISS"]["gap_open_pct"]) and np.isnan(out["EQ:NEW"]["gap_open_pct"])
    assert out["EQ:OK"]["gap_open_pct"] == 0.0
    assert np.isnan(out["EQ:NEW"]["gap_above"]) and out["EQ:NEW"]["gap_below_date"] is None


def test_a_missing_bar_hides_the_gap_it_would_form_but_never_fills_one() -> None:
    gapped = path((10, (104.0, 106.0, 103.0, 105.0)), (11, UP))
    _, reader = write(
        {"EQ:HOLE": gapped, "EQ:NOPREV": gapped}, skip={"EQ:HOLE": [20], "EQ:NOPREV": [9]}
    )
    out = rows(reader)
    assert out["EQ:HOLE"]["gap_below"] == 103.0  # a missing bar later is not a fill
    assert np.isnan(out["EQ:NOPREV"]["gap_below"])  # the gap session's previous bar is missing


def test_a_gap_is_found_from_the_second_bar_of_the_window_on() -> None:
    n = gp.LOOKBACK + 60
    writer, reader = store()
    first = n - 1 - gp.LOOKBACK  # the oldest bar read
    bars = [BASE] * n
    bars[first] = (110.0, 111.0, 108.0, 110.0)  # a gap against a previous bar that is not read
    bars[first + 1 :] = [(110.0, 111.0, 108.0, 110.0)] * (n - first - 1)
    write_bars(
        writer,
        {"EQ:A": [b[3] for b in bars]},
        opens={"EQ:A": [b[0] for b in bars]},
        highs={"EQ:A": [b[1] for b in bars]},
        lows={"EQ:A": [b[2] for b in bars]},
    )
    out = compute_one(reader, gp.GROUP, END).frame
    assert out is not None and np.isnan(out["gap_below"]).all()  # its previous bar is unread


def jumpy(n: int, seed: int, start: float = 100.0) -> dict[str, np.ndarray]:
    """Bars that open away from the previous close (about 1%) with narrow ranges: gaps."""
    close = series(n, seed=seed, start=start)
    opened = close * (1 + np.random.default_rng(seed + 100).normal(0, 0.01, n))
    return {
        "close": close,
        "open": opened,
        "high": np.maximum(opened, close) * 1.002,
        "low": np.minimum(opened, close) * 0.998,
    }


def write_jumpy(
    writer: StoreWriter, full: dict[str, dict[str, np.ndarray]], k: int, end: date | None = None
) -> list[date]:
    cut = {i: {c: v[: k + 1] for c, v in d.items()} for i, d in full.items()}
    return write_bars(
        writer,
        {i: d["close"] for i, d in cut.items()},
        opens={i: d["open"] for i, d in cut.items()},
        highs={i: d["high"] for i, d in cut.items()},
        lows={i: d["low"] for i, d in cut.items()},
        **({"end": end} if end else {}),
    )


def test_point_in_time_and_the_gap_sides_bracket_the_close() -> None:
    full = {"EQ:A": jumpy(300, seed=31), "EQ:B": jumpy(300, seed=32, start=40.0)}
    writer, reader = store()
    days = write_jumpy(writer, full, 299)
    picks = [days[i] for i in (60, 150, 299)]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, gp.GROUP, picks)}
    for day in picks:
        k = days.index(day)
        small_writer, small = store()
        write_jumpy(small_writer, full, k, end=day)
        pd.testing.assert_frame_equal(compute_one(small, gp.GROUP, day).frame, backfilled[day])
        frame = backfilled[day]
        assert frame is not None
        close = {i: d["close"][k] for i, d in full.items()}
        for _, row in frame.iterrows():
            assert np.isnan(row["gap_above"]) or row["gap_above"] > close[row["instrument_id"]]
            assert np.isnan(row["gap_below"]) or row["gap_below"] < close[row["instrument_id"]]
    found = [f for f in backfilled.values() if f is not None]
    assert sum(f["gap_above"].notna().sum() + f["gap_below"].notna().sum() for f in found) > 0


def test_registered_with_the_declared_lookback() -> None:
    assert GROUPS["gaps@v1"].table == "rollups/instrument/gaps@v1"
    assert gp.GROUP.inputs[0].sessions_back(None) == gp.LOOKBACK == 252
