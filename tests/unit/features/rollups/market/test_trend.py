"""``market_trend@v1`` against hand-computed values on stored SPY / QQQ series: short
histories and unlisted tickers are null (never a shorter window), ids are looked up by ticker
(a permutation of ids changes nothing), and a backfill equals the per-session compute."""

import math
import statistics

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.market import trend
from tests.helpers.rollup_store import END, series, store, write_bars
from tests.helpers.stored_frames import write_reference

GROUP = trend.GROUP
F32 = 2e-7  # float32 keeps about 7 significant digits
SPY, QQQ = "EQ:SPYFIGI", "EQ:QQQFIGI"


def market_row(reader: object, session: object = END) -> dict[str, object]:
    frame = compute_one(reader, GROUP, session).frame  # type: ignore[arg-type]
    assert frame is not None and list(frame["instrument_id"]) == ["MKT:US"]
    return frame.iloc[0].to_dict()


def expected(c: np.ndarray) -> dict[str, float]:
    returns = [math.log(c[i] / c[i - 1]) for i in range(len(c) - 20, len(c))]
    return {
        "close_vs_sma200": c[-1] / c[-200:].mean() - 1,
        "sma50_vs_sma200": c[-50:].mean() / c[-200:].mean() - 1,
        "drawdown_252d": c[-1] / c[-252:].max() - 1,
        "realised_vol_20d": statistics.stdev(returns) * math.sqrt(252),
        "ret_21d": c[-1] / c[-22] - 1,
        "ret_252d": c[-1] / c[-253] - 1,
    }


def test_both_indexes_by_hand() -> None:
    writer, reader = store()
    spy, qqq = series(300, seed=1), series(300, seed=2)
    days = write_bars(writer, {SPY: spy, QQQ: qqq, "EQ:OTHER": series(300, seed=3)})
    write_reference(writer, days[0], {"SPY": SPY, "QQQ": QQQ, "OTHER": "EQ:OTHER"})
    row = market_row(reader)
    for prefix, closes in (("spx", spy), ("ndx", qqq)):
        for column, value in expected(closes).items():
            assert row[f"{prefix}_{column}"] == pytest.approx(value, rel=1e-6, abs=1e-7), column


def test_drawdown_is_zero_at_a_new_high_and_negative_below_it() -> None:
    writer, reader = store()
    rising = np.linspace(100, 200, 260)
    falling = np.r_[np.linspace(100, 200, 200), np.linspace(200, 150, 60)]
    days = write_bars(writer, {SPY: rising, QQQ: falling})
    write_reference(writer, days[0], {"SPY": SPY, "QQQ": QQQ})
    row = market_row(reader)
    assert row["spx_drawdown_252d"] == 0.0
    assert row["ndx_drawdown_252d"] == pytest.approx(150 / 200 - 1, rel=F32)
    assert row["spx_sma50_vs_sma200"] > 0 > row["ndx_close_vs_sma200"]


def test_short_history_gap_and_unlisted_ticker_are_null() -> None:
    writer, reader = store()
    days = write_bars(
        writer, {SPY: series(100, seed=1), QQQ: series(300, seed=2)}, skip={QQQ: [270]}
    )
    write_reference(writer, days[0], {"SPY": SPY})  # QQQ is not in the reference
    row = market_row(reader)
    short = ("close_vs_sma200", "sma50_vs_sma200", "drawdown_252d", "ret_252d")
    assert all(pd.isna(row[f"spx_{c}"]) for c in short)
    assert row["spx_ret_21d"] > -1 and row["spx_realised_vol_20d"] > 0
    assert all(pd.isna(row[c]) for c in trend.COLUMNS if c.startswith("ndx_"))

    write_reference(writer, days[-1], {"SPY": SPY, "QQQ": QQQ}, run_id="ref2")
    gapped = market_row(reader)  # a gap 30 sessions back: the windows that span it are null
    assert pd.isna(gapped["ndx_close_vs_sma200"]) and pd.isna(gapped["ndx_ret_252d"])
    assert gapped["ndx_ret_21d"] > -1 and gapped["ndx_realised_vol_20d"] > 0


def test_without_a_reference_every_column_is_null() -> None:
    """The bars are read for the ids SPY and QQQ resolve to (``Input.symbols``): none, so the
    session has input (bars are stored) but every column is unknown."""
    writer, reader = store()
    write_bars(writer, {SPY: series(300)})
    row = market_row(reader)
    assert all(pd.isna(row[c]) for c in trend.COLUMNS)


def test_a_permutation_of_ids_changes_nothing() -> None:
    rows = []
    for spy_id, qqq_id in ((SPY, QQQ), ("EQ:ZZZ", "EQ:AAA")):
        writer, reader = store()
        days = write_bars(writer, {spy_id: series(300, seed=1), qqq_id: series(300, seed=2)})
        write_reference(writer, days[0], {"SPY": spy_id, "QQQ": qqq_id})
        rows.append(market_row(reader))
    assert rows[0] == rows[1]


def test_backfill_equals_nightly() -> None:
    writer, reader = store()
    days = write_bars(writer, {SPY: series(300, seed=1), QQQ: series(300, seed=2)})
    write_reference(writer, days[0], {"SPY": SPY, "QQQ": QQQ})
    backfill = list(compute_sessions(reader, GROUP, days[-5:]))
    for result in backfill:
        nightly = compute_one(reader, GROUP, result.session).frame
        assert result.frame is not None and nightly is not None
        pd.testing.assert_frame_equal(result.frame, nightly)
    assert backfill[0].frame["spx_ret_21d"].iloc[0] != backfill[-1].frame["spx_ret_21d"].iloc[0]  # type: ignore[index]
