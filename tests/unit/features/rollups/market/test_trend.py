"""``market_trend@v2`` against hand-computed values on stored SPY / QQQ bars and S&P 500 /
Nasdaq Composite levels (``macro/series``).

Bars path: v1's hand-computed values (``expected``, the oracle v1's tests used) on the same
stores, so v2 equals v1 wherever its source is bars; short histories and unlisted tickers are
null (never a shorter window), ids are looked up by ticker. Index path: windows count known
observations (a FRED "." is skipped, not counted), a vintage after the session is never seen,
a stale level is null, one source per prefix and session (never a mix), a backfill equals the
per-session compute across a switch of source, and the result is deterministic."""

import math
import statistics
from collections.abc import Sequence
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.market import trend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import END, series, store, write_bars
from tests.helpers.stored_frames import stamped, write_reference

GROUP = trend.GROUP
F32 = 2e-7  # float32 keeps about 7 significant digits
SPY, QQQ = "EQ:SPYFIGI", "EQ:QQQFIGI"
SPX, COMP = "IDX:SPX", "IDX:COMP"
COLUMNS = trend.TREND


def market_row(reader: StoreReader, session: date = END) -> dict[str, object]:
    frame = compute_one(reader, GROUP, session).frame
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


def assert_trend(row: dict[str, object], prefix: str, closes: np.ndarray) -> None:
    for column, value in expected(closes).items():
        assert row[f"{prefix}_{column}"] == pytest.approx(value, rel=1e-6, abs=1e-7), column


def all_null(row: dict[str, object], prefix: str) -> bool:
    return all(pd.isna(row[f"{prefix}_{c}"]) for c in COLUMNS)


def same(*rows: dict[str, object]) -> None:
    """The rows are equal, nulls included (NaN never equals itself)."""
    for other in rows[1:]:
        pd.testing.assert_series_equal(pd.Series(rows[0]), pd.Series(other))


def obs(iid: str, day: date, vintage: date, value: float | None) -> dict[str, object]:
    return {"instrument_id": iid, "series": iid[4:], "obs_date": day, "vintage_date": vintage,
            "value": value, "vintage_kind": "lagged"}  # fmt: skip


def levels(
    iid: str, values: Sequence[float | None], end: date = END, age: int = 1
) -> list[dict[str, object]]:
    """One observation per session, the newest ``age`` sessions before ``end``, each known
    the next calendar day (``pit = "lag"``, one day): the previous close is the newest known."""
    days = sessions_ending(end, len(values) + age)[: len(values)]
    return [obs(iid, d, d + timedelta(days=1), v) for d, v in zip(days, values, strict=True)]


def write_levels(writer: StoreWriter, rows: list[dict[str, object]], stored: date = END) -> None:
    run = f"macro-{stored}"
    writer.write_table(trend.MACRO, stored, run, stamped(rows, stored, run, source="fred"))


# --- bars: v2 equals v1 wherever its source is bars ---


def test_both_etfs_by_hand_and_the_bars_win_over_a_level() -> None:
    writer, reader = store()
    spy, qqq = series(300, seed=1), series(300, seed=2)
    days = write_bars(writer, {SPY: spy, QQQ: qqq, "EQ:OTHER": series(300, seed=3)})
    write_reference(writer, days[0], {"SPY": SPY, "QQQ": QQQ, "OTHER": "EQ:OTHER"})
    spx = series(300, seed=9, start=4000.0)
    write_levels(writer, levels(SPX, spx))
    row = market_row(reader)
    assert_trend(row, "spx", spy)  # v1's values: the complete bars window wins
    assert_trend(row, "ndx", qqq)
    assert row["spx_source"] == "bars"
    assert row["spx_level"] == pytest.approx(spx[-1], rel=F32)  # the index's previous close
    assert all_null(row, "comp") and pd.isna(row["comp_source"]) and pd.isna(row["comp_level"])


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
    """QQQ keeps v1's per-column windows; SPY with a short history and no index level is null
    (v2 never computes the S&P 500 from a partial bars window: it falls back to the level)."""
    writer, reader = store()
    days = write_bars(
        writer, {SPY: series(100, seed=1), QQQ: series(300, seed=2)}, skip={QQQ: [270]}
    )
    write_reference(writer, days[0], {"SPY": SPY})  # QQQ is not in the reference
    row = market_row(reader)
    assert all_null(row, "spx") and pd.isna(row["spx_source"])
    assert all_null(row, "ndx")

    write_reference(writer, days[-1], {"SPY": SPY, "QQQ": QQQ}, run_id="ref2")
    gapped = market_row(reader)  # a gap 30 sessions back: the windows that span it are null
    assert pd.isna(gapped["ndx_close_vs_sma200"]) and pd.isna(gapped["ndx_ret_252d"])
    assert gapped["ndx_ret_21d"] > -1 and gapped["ndx_realised_vol_20d"] > 0


def test_without_a_reference_or_a_level_every_column_is_null() -> None:
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
    same(*rows)


# --- index levels ---


def test_index_levels_when_the_bars_window_is_short() -> None:
    """SPY has 100 sessions of bars: the S&P 500 comes from its level, every window from the
    level only (never SPY's 21-session return, which the bars could give); COMP likewise."""
    writer, reader = store()
    days = write_bars(writer, {SPY: series(100, seed=1)})
    write_reference(writer, days[0], {"SPY": SPY})
    spx, comp = series(300, seed=4, start=4000.0), series(400, seed=5, start=15000.0)
    write_levels(writer, levels(SPX, spx) + levels(COMP, comp))
    row = market_row(reader)
    assert row["spx_source"] == "index" and row["comp_source"] == "index"
    assert_trend(row, "spx", spx)
    assert_trend(row, "comp", comp)
    assert row["spx_level"] == pytest.approx(spx[-1], rel=F32)
    assert row["comp_level"] == pytest.approx(comp[-1], rel=F32)


def test_a_bars_window_one_session_short_is_not_mixed_with_the_level() -> None:
    writer, reader = store()
    days = write_bars(writer, {SPY: series(trend.WINDOW - 1, seed=1)})
    write_reference(writer, days[0], {"SPY": SPY})
    spx = series(300, seed=4, start=4000.0)
    write_levels(writer, levels(SPX, spx))
    row = market_row(reader)
    assert row["spx_source"] == "index"
    assert_trend(row, "spx", spx)


def test_a_short_index_history_is_null_per_window_and_a_level_needs_no_bars() -> None:
    """60 observations: the 21-observation return and the vol are known, the long windows
    null; with no bars stored at all (before 1993) the row is still written."""
    writer, reader = store()
    comp = series(60, seed=5, start=100.0)
    write_levels(writer, levels(COMP, comp))
    row = market_row(reader)
    assert row["comp_source"] == "index"
    assert row["comp_ret_21d"] == pytest.approx(comp[-1] / comp[-22] - 1, rel=1e-6)
    assert row["comp_realised_vol_20d"] > 0
    assert all(pd.isna(row[f"comp_{c}"]) for c in ("close_vs_sma200", "drawdown_252d", "ret_252d"))
    assert all_null(row, "spx") and all_null(row, "ndx")


def test_a_fred_gap_is_skipped_not_counted() -> None:
    """Null values ("." on a holiday) are no observation: the window is the last 253 values,
    so a gap neither shortens nor nulls it."""
    writer, reader = store()
    comp = series(trend.WINDOW, seed=5, start=15000.0)
    values: list[float | None] = [*comp[:100], None, None, *comp[100:]]
    write_levels(writer, levels(COMP, values))
    row = market_row(reader)
    assert_trend(row, "comp", comp)


def test_no_vintage_after_the_session_is_seen() -> None:
    """The session's own close (known the next day) and a revision published after the session
    are not seen; a revision published before it replaces the first vintage."""
    writer, reader = store()
    comp = series(300, seed=5, start=15000.0)
    rows = levels(COMP, comp)
    last, prev = rows[-1]["obs_date"], rows[-2]["obs_date"]
    assert isinstance(last, date) and isinstance(prev, date)
    rows += [
        obs(COMP, END, END + timedelta(days=1), 1.0),  # the session's own close: tomorrow
        obs(COMP, last, END + timedelta(days=3), 2.0),  # a later revision of the newest
        obs(COMP, prev, END, comp[-2] * 1.01),  # revised by the session
    ]
    write_levels(writer, rows)
    row = market_row(reader)
    seen = comp.copy()
    seen[-2] = comp[-2] * 1.01
    assert_trend(row, "comp", seen)
    assert row["comp_level"] == pytest.approx(comp[-1], rel=F32)


@pytest.mark.parametrize(("age", "known"), [(2, True), (3, False)])
def test_a_stale_level_is_null(age: int, known: bool) -> None:
    writer, reader = store()
    spx = series(300, seed=4, start=4000.0)
    write_levels(writer, levels(SPX, spx, age=age))
    row = market_row(reader)
    if known:
        assert row["spx_source"] == "index" and row["spx_level"] == pytest.approx(spx[-1], F32)
        assert_trend(row, "spx", spx)
    else:
        assert all_null(row, "spx") and pd.isna(row["spx_source"]) and pd.isna(row["spx_level"])


# --- one code path, deterministic ---


def test_backfill_equals_nightly_across_a_switch_of_source() -> None:
    """SPY's window completes 3 sessions before the end: index, then bars."""
    writer, reader = store()
    days = write_bars(writer, {SPY: series(trend.WINDOW + 2, seed=1), QQQ: series(300, seed=2)})
    write_reference(writer, days[0], {"SPY": SPY, "QQQ": QQQ})
    write_levels(
        writer, levels(SPX, series(400, seed=4, start=4000.0))
        + levels(COMP, series(400, seed=5, start=15000.0))
    )  # fmt: skip
    backfill = list(compute_sessions(reader, GROUP, days[-6:]))
    for result in backfill:
        nightly = compute_one(reader, GROUP, result.session).frame
        assert result.frame is not None and nightly is not None
        pd.testing.assert_frame_equal(result.frame, nightly)
    sources = [r.frame["spx_source"].iloc[0] for r in backfill]  # type: ignore[index]
    assert sources == ["index"] * 3 + ["bars"] * 3


def test_deterministic_whatever_the_stored_row_order() -> None:
    rows = []
    for order in (1, -1):
        writer, reader = store()
        days = write_bars(writer, {SPY: series(150, seed=1), QQQ: series(300, seed=2)})
        write_reference(writer, days[0], {"SPY": SPY, "QQQ": QQQ})
        stored = levels(SPX, series(300, seed=4, start=4000.0)) + levels(COMP, series(300, seed=5))
        write_levels(writer, stored[::order])
        rows += [market_row(reader), market_row(reader)]
    same(*rows)


def test_columns_fed_by_an_index_level_are_personal() -> None:
    personal = {f.name for f in GROUP.features if f.licence == "personal"}
    assert personal == {f"{p}_{c}" for p in ("spx", "comp") for c in (*COLUMNS, "level", "source")}
    assert GROUP.key == "market_trend@v2"
    for p in ("spx", "comp"):
        assert f"series:{p.upper()}" in GROUP.feature(f"{p}_ret_21d").inputs
    lagged = [f for f in GROUP.features if f.licence == "personal"]
    assert all("previous session's close (the level is published a day late" in f.description
               for f in lagged)  # fmt: skip
