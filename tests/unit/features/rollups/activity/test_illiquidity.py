"""``illiquidity@v1`` on hand-built bars: Amihud is the mean absolute return per million dollars
over 63 sessions; a gap, a short history or a session with no volume gives null."""

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one
from algotrade.features.rollups.activity import illiquidity as an
from tests.helpers.rollup_store import END, store, write_bars

N = an.AMIHUD_WINDOW + 1
DAYS = sessions_ending(END, N)


def flat(value: float = 100.0) -> np.ndarray:
    return np.full(N, value)


def build(
    closes: Mapping[str, np.ndarray],
    volume: Mapping[str, Sequence[float]] | None = None,
    skip: Mapping[str, list[int]] | None = None,
) -> StoreReader:
    writer, reader = store()
    write_bars(writer, closes, end=END, volume=volume, skip=skip)
    return reader


def result(reader: StoreReader) -> dict[str, dict[str, object]]:
    frame = compute_one(reader, an.GROUP, END, None).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def test_amihud_is_the_mean_absolute_return_per_million_dollars() -> None:
    close = flat()
    close[1::2] = 101.0  # alternates 100, 101: |return| about 1% every day
    volume = [10_000.0] * N  # about $1M a day
    thin = [100.0] * N  # about $10k a day: a hundred times more per dollar
    out = result(
        build({"EQ:L": close, "EQ:T": close.copy()}, volume={"EQ:L": volume, "EQ:T": thin})
    )
    daily = np.abs(close[1:] / close[:-1] - 1.0)
    expect = float(np.mean(daily / (close[1:] * 10_000.0 / 1e6)))
    assert float(out["EQ:L"]["amihud_63d"]) == pytest.approx(expect)  # type: ignore[arg-type]
    assert float(out["EQ:T"]["amihud_63d"]) == pytest.approx(expect * 100)  # type: ignore[arg-type]


def test_a_gap_a_short_history_or_a_session_without_volume_is_null() -> None:
    zero = [1000.0] * N
    zero[30] = 0.0
    out = result(
        build(
            {"EQ:G": flat(), "EQ:S": flat()[-30:], "EQ:Z": flat(), "EQ:OK": flat()},
            volume={"EQ:Z": zero},
            skip={"EQ:G": [N - 5]},
        )
    )
    for iid in ("EQ:G", "EQ:S"):
        assert pd.isna(out[iid]["amihud_63d"]), iid
    assert pd.isna(out["EQ:Z"]["amihud_63d"])
    assert not pd.isna(out["EQ:OK"]["amihud_63d"])
