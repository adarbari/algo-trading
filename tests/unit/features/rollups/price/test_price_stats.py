"""``price_stats@v2`` against hand-computed values on small stored series (32-bit floats:
``F32`` relative tolerance), including split adjustment as of each session, missing history
and gaps (null, never zero)."""

import math
import statistics
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.price import price_stats as ps
from tests.helpers.rollup_store import END, series, store, write_bars, write_split

P = ps.PriceStatsParams()
GROUP = ps.GROUP
F32 = 2e-7  # float32 keeps about 7 significant digits


def row(frame: pd.DataFrame | None, iid: str) -> dict[str, object]:
    assert frame is not None
    return frame.set_index("instrument_id").loc[iid].to_dict()


def test_full_history_by_hand() -> None:
    writer, reader = store()
    c = series(260)
    volume = np.linspace(1000, 2000, 260)
    write_bars(writer, {"EQ:A": c}, volume={"EQ:A": volume})
    out = row(compute_one(reader, GROUP, END).frame, "EQ:A")
    assert out["close"] == pytest.approx(c[-1])
    for n in (20, 50, 200):
        assert out[f"sma_{n}"] == pytest.approx(c[-n:].mean(), rel=F32)
    assert out["ret_20d"] == pytest.approx(c[-1] / c[-21] - 1)
    assert out["ret_60d"] == pytest.approx(c[-1] / c[-61] - 1)
    opens = np.r_[c[0], c[:-1]]
    highs, lows = np.maximum(opens, c) * 1.01, np.minimum(opens, c) * 0.99
    assert out["high_52w"] == pytest.approx(highs[-252:].max())
    assert out["low_52w"] == pytest.approx(lows[-252:].min())
    for n in (20, 30):
        returns = [math.log(c[i] / c[i - 1]) for i in range(len(c) - n, len(c))]
        assert out[f"hv{n}"] == pytest.approx(statistics.stdev(returns) * math.sqrt(252))
    assert out["hv20_yz"] > 0
    assert out["adv_usd_20d"] == pytest.approx(float(np.mean(c[-20:] * volume[-20:])))
    assert out["history_days"] == 252


def test_missing_history_and_gaps_are_null_not_zero() -> None:
    writer, reader = store()
    write_bars(
        writer,
        {"EQ:NEW": series(30, seed=2), "EQ:GAP": series(260, seed=3)},
        skip={"EQ:GAP": [250]},  # no bar 10 sessions before the end
    )
    frame = compute_one(reader, GROUP, END).frame
    new, gap = row(frame, "EQ:NEW"), row(frame, "EQ:GAP")
    assert new["history_days"] == 30 and new["sma_20"] > 0 and new["hv20"] > 0
    for column in ("sma_50", "sma_200", "ret_60d", "hv30", "high_52w", "low_52w"):
        assert pd.isna(new[column]), column
    assert pd.isna(gap["sma_20"]) and pd.isna(gap["hv20"]) and pd.isna(gap["ret_20d"])
    assert gap["history_days"] == 251 and gap["high_52w"] > 0  # 251 >= min_year_sessions


def test_only_instruments_with_a_bar_on_the_session() -> None:
    writer, reader = store()
    write_bars(writer, {"EQ:A": series(40), "EQ:B": series(40, seed=5)}, skip={"EQ:B": [39]})
    frame = compute_one(reader, GROUP, END).frame
    assert frame is not None and list(frame["instrument_id"]) == ["EQ:A"]


def test_split_adjusted_as_of_each_session() -> None:
    """EQ:S trades the same as EQ:P until a 2-for-1 split 5 sessions before the end; after it
    its raw price halves and volume doubles. As of the end, levels are half of EQ:P's and
    ratios equal; as of a session before the split, EQ:S equals EQ:P (no later split leaks)."""
    writer, reader = store()
    c = series(260, seed=7)
    raw = c.copy()
    raw[-5:] /= 2
    volume = np.full(260, 1000.0)
    split_volume = volume.copy()
    split_volume[-5:] *= 2
    opens = np.r_[c[0], c[:-1]]
    split_opens = opens.copy()
    split_opens[-5:] /= 2  # the ex-date opens post-split
    days = write_bars(
        writer,
        {"EQ:P": c, "EQ:S": raw},
        volume={"EQ:P": volume, "EQ:S": split_volume},
        opens={"EQ:P": opens, "EQ:S": split_opens},
    )
    write_split(writer, "EQ:S", days[-5], 2.0, stored=END)
    results = list(compute_sessions(reader, GROUP, days[-8:]))
    before, after = results[0].frame, results[-1].frame
    assert row(before, "EQ:S") == row(before, "EQ:P")
    plain, split = row(after, "EQ:P"), row(after, "EQ:S")
    for column in ("close", "sma_20", "sma_200", "high_52w", "low_52w"):
        assert split[column] == pytest.approx(plain[column] / 2, rel=F32), column
    for column in ("ret_20d", "ret_60d", "hv20", "hv30", "hv20_yz"):
        assert split[column] == pytest.approx(plain[column], rel=F32), column
    assert split["adv_usd_20d"] == pytest.approx(plain["adv_usd_20d"], rel=F32)


def test_params_shorten_the_year_and_validate() -> None:
    writer, reader = store()
    write_bars(writer, {"EQ:A": series(60)})
    short = replace(P, year_sessions=50, min_year_sessions=50)
    out = row(compute_one(reader, GROUP, END, short).frame, "EQ:A")
    assert out["history_days"] == 50 and out["high_52w"] > 0
    assert ps.lookback(short) == 199  # sma_200 is still the longest window
    with pytest.raises(ValueError, match="year_sessions"):
        ps.PriceStatsParams(year_sessions=1)
    with pytest.raises(ValueError, match="min_year_sessions"):
        ps.PriceStatsParams(min_year_sessions=300)
    with pytest.raises(ValueError, match="periods_per_year"):
        ps.PriceStatsParams(periods_per_year=0)


def test_no_bars_for_the_session_is_no_input() -> None:
    _, reader = store()
    result = compute_one(reader, GROUP, END)
    assert result.frame is None and result.no_input == f"no bars/1d for {END}"


def test_columns_are_typed_as_declared() -> None:
    writer, reader = store()
    write_bars(writer, {"EQ:A": series(30)})
    frame = compute_one(reader, GROUP, END).frame
    assert frame is not None
    assert list(frame.columns) == ["instrument_id", *ps.COLUMNS]
    assert str(frame["history_days"].dtype) == "int64[pyarrow]"
    assert frame["sma_50"].dtype == np.float32  # v2 stores 32-bit floats
