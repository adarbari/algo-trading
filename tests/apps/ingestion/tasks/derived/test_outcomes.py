"""The ``outcomes`` task on a store of bars, a universe and a reference snapshot: a backfill
writes exactly the rows the nightly runs write (one run per window end), each window into its
start session's partition with the benchmark's excess; a delisted name is DELISTED; a window
before the stored history is not computed; a window not yet closed is refused; horizons come
from the open edge documents; the acceptance check passes on the run's own rows and fails on a
name that has neither a row nor a reason."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.time.calendar import close_time, next_session, sessions_ending
from algotrade.data.prices import FLAGS_TABLE, raw_bars
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.outcome_paths import NO_END_BAR
from algotrade_ingestion.tasks.derived.outcomes import (
    DEFAULT_HORIZON,
    RECHECK,
    TABLE,
    check_outcomes,
    compute_outcomes,
    horizons_and_benchmarks,
)
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import (
    END,
    SPY,
    series,
    store,
    write_bars,
    write_rows,
    write_split,
)
from tests.helpers.stored_frames import stamped, universe_rows

N = 70  # sessions of bars: room for the 60-session horizon
IDS = {"A": "EQ:A", "B": "EQ:B", "D": "EQ:D", "SPY": SPY}


def _reference(delisted: date | None) -> list[dict[str, object]]:
    return [
        {"instrument_id": iid, "symbol": symbol, "asset_class": "EQ",
         "security_type": "COMMON_STOCK", "multiplier": 1.0, "status": "ACTIVE",
         "delisted_on": delisted if symbol == "D" else None}
        for symbol, iid in IDS.items()
    ]  # fmt: skip


def _store(a: list[float] | None = None) -> tuple[StoreWriter, StoreReader, list[date]]:
    writer, reader = store()
    closes = {"EQ:A": a or series(N), "EQ:B": series(N, seed=2), SPY: series(N, seed=3),
              "EQ:D": series(N - 3, seed=4)}  # fmt: skip
    # D's bars start three sessions in and stop four before END (skip: indexes from day 0)
    days = write_bars(writer, closes, skip={"EQ:D": [N - 3, N - 2, N - 1]})
    write_rows(writer, "instruments/reference", days[0], _reference(days[-2]))
    rows = universe_rows(["A", "B", "D"]) + universe_rows(["SPY"], instrument_id=SPY)
    write_rows(writer, "universe", days[0], rows)
    return writer, reader, days


def _outcomes(reader: StoreReader) -> pd.DataFrame:
    parts = [reader.table(TABLE, d) for d in reader.dates(TABLE)]
    frame = pd.concat([p for p in parts if p is not None], ignore_index=True)
    keys = ["session_date", "horizon_sessions", "benchmark", "instrument_id"]
    return frame.drop(columns=["run_id", "knowledge_ts"]).sort_values(keys).reset_index(drop=True)


def test_horizons_come_from_the_open_edge_documents() -> None:
    horizons, benchmarks = horizons_and_benchmarks()
    assert DEFAULT_HORIZON in horizons and {6, 60} <= set(horizons)
    assert 1 not in horizons  # leveraged_etf_rebalancing is rejected
    assert benchmarks == ["SPY"]


def test_horizons_include_study_horizon() -> None:
    horizons, benchmarks = horizons_and_benchmarks()
    assert 504 in horizons  # the winners study's (config/site/studies/winners.toml), backfill-only
    assert "SPY" in benchmarks


def test_backfill_rows_equal_nightly_rows() -> None:
    nightly_writer, nightly_reader, days = _store()
    for day in days[-3:]:
        record = compute_outcomes(task_ctx(nightly_writer), day)
        assert record.status == RunStatus.COMPLETE, record.stats
    backfill_writer, backfill_reader, _ = _store()
    first = days[-3 - RECHECK]  # each night also recomputes the RECHECK window ends before it
    compute_outcomes(task_ctx(backfill_writer), days[-1], first, days[-1])
    pd.testing.assert_frame_equal(_outcomes(nightly_reader), _outcomes(backfill_reader))
    assert len(backfill_reader.runs("outcomes")) == 3 + RECHECK  # one run per window end


def test_rows_land_in_the_start_partition_with_the_excess_over_spy() -> None:
    writer, reader, days = _store()
    compute_outcomes(task_ctx(writer), END)
    start = sessions_ending(END, DEFAULT_HORIZON + 1)[0]
    part = reader.table(TABLE, start)
    assert part is not None
    a = part[(part["instrument_id"] == "EQ:A") & (part["horizon_sessions"] == DEFAULT_HORIZON)]
    closes = dict(zip(days, series(N), strict=True))
    spy = dict(zip(days, series(N, seed=3), strict=True))
    expected = closes[END] / closes[start] - 1
    assert a["fwd_return"].iloc[0] == pytest.approx(expected)
    assert a["fwd_excess_return"].iloc[0] == pytest.approx(expected - (spy[END] / spy[start] - 1))
    assert pd.Timestamp(a["ts"].iloc[0]) == pd.Timestamp(close_time(start))
    assert a["window_end"].iloc[0] == END and a["benchmark"].iloc[0] == "SPY"


def test_a_delisted_name_is_measured_to_its_last_bar() -> None:
    writer, reader, _days = _store()
    record = compute_outcomes(task_ctx(writer), END)
    start = sessions_ending(END, 7)[0]
    part = reader.table(TABLE, start)
    assert part is not None
    d = part[(part["instrument_id"] == "EQ:D") & (part["horizon_sessions"] == 6)]
    assert d["outcome_status"].iloc[0] == "DELISTED"
    assert record.stats["h6"]["reasons"] == 0


def test_a_delisting_the_reference_notices_later_turns_a_reason_into_a_row() -> None:
    writer, reader, days = _store()  # D's last bar is days[-4]
    write_rows(writer, "instruments/reference", days[0], _reference(None))  # not noticed yet
    record = compute_outcomes(task_ctx(writer), days[-3])
    assert record.stats["h6"]["examples"] == {"EQ:D": NO_END_BAR}
    start = sessions_ending(days[-3], 7)[0]
    assert "EQ:D" not in set(_partition(reader, start, days[-3])["instrument_id"])
    # the weekly build notices on days[-1]; that night rechecks the window ending days[-3]
    write_rows(writer, "instruments/reference", days[-1], _reference(days[-1]))
    compute_outcomes(task_ctx(writer), days[-1])
    d = _partition(reader, start, days[-3])
    assert d.loc[d["instrument_id"] == "EQ:D", "outcome_status"].tolist() == ["DELISTED"]
    assert [c.status for c in check_outcomes(reader, days[-3], task_ctx(writer).settings)] == [
        "PASS"
    ]


def test_a_two_for_one_split_inside_a_window_is_not_a_fifty_percent_return() -> None:
    """ED6: a delisted-name id (``EQ:TIINGO:``) has Tiingo's split row; the raw bars halve on the
    ex-date and the outcome reads them split-adjusted (flat), not -50%."""
    writer, reader, days = _store()
    tid = "EQ:TIINGO:US0001"
    start = sessions_ending(END, 7)[0]
    ex_date = days[days.index(start) + 3]
    raw = [100.0 if d < ex_date else 50.0 for d in days]  # a 2-for-1 on ex_date, price flat
    write_bars(writer, {tid: raw})
    rows = universe_rows(["A", "B", "D"]) + universe_rows(["SPY"], instrument_id=SPY)
    write_rows(writer, "universe", days[0], rows + universe_rows(["T"], instrument_id=tid))
    write_split(writer, tid, ex_date, 2.0, END)
    compute_outcomes(task_ctx(writer), END)
    part = _partition(reader, start, END)
    row = part[part["instrument_id"] == tid]
    assert row["fwd_return"].iloc[0] == pytest.approx(0.0)  # not -0.5


def _partition(reader: StoreReader, start: date, end: date) -> pd.DataFrame:
    part = reader.table(TABLE, start)
    assert part is not None
    window_end = pd.to_datetime(part["window_end"]).dt.date
    return part[(window_end == end) & (part["horizon_sessions"] == 6)]


def test_windows_before_the_stored_history_are_not_computed() -> None:
    writer, _reader, days = _store()
    record = compute_outcomes(task_ctx(writer), days[30])
    assert record.items["h60"] == "BEFORE_HISTORY"
    assert record.items["h20"].startswith("OK")


def test_a_window_that_has_not_closed_is_refused() -> None:
    writer, _, _ = _store()
    early = datetime(2026, 10, 2, 15, tzinfo=UTC)  # before END's close
    with pytest.raises(ValueError, match="has not closed"):
        compute_outcomes(task_ctx(writer, clock=lambda: early), END)
    with pytest.raises(ValueError, match="has not closed"):
        compute_outcomes(task_ctx(writer), next_session(END))


def test_acceptance_passes_on_the_run_and_fails_on_an_unaccounted_name() -> None:
    writer, reader, days = _store()
    compute_outcomes(task_ctx(writer), END)
    settings = task_ctx(writer).settings
    assert [c.status for c in check_outcomes(reader, END, settings)] == ["PASS"]
    rows = universe_rows(["A", "B", "D", "C"]) + universe_rows(["SPY"], instrument_id=SPY)
    write_rows(writer, "universe", days[0], rows)  # C: in the universe now, no row
    write_bars(writer, {"EQ:C": series(N, seed=9)})
    [check] = check_outcomes(reader, END, settings)
    assert check.status == "FAIL" and "names without a row or a reason" in check.detail


def test_acceptance_fails_without_a_run() -> None:
    _, reader, _ = _store()
    [check] = check_outcomes(reader, END, task_ctx(StoreWriter(reader._backend)).settings)
    assert check.status == "FAIL"


def test_a_reference_delisting_noticed_after_the_recheck_span_is_not_counted() -> None:
    writer, _reader, days = _store()
    noticed = days[-1]
    for _ in range(RECHECK):
        noticed = next_session(noticed)  # the notice is RECHECK sessions after END: too late for -3
    write_rows(writer, "instruments/reference", days[0], _reference(next_session(noticed)))
    record = compute_outcomes(task_ctx(writer), days[-3])
    assert record.stats["h6"]["examples"] == {"EQ:D": NO_END_BAR}


def _flag(writer: StoreWriter, reader: StoreReader, iid: str, day: date) -> None:
    """Flag ``iid``'s bar on ``day`` as ``bar-quality`` would (ADR 0061)."""
    stored = raw_bars(reader, "1d", day, day, [iid])
    row = [{"instrument_id": iid, "ts": stored["ts"].iloc[0], "reason": "UNEXPLAINED_JUMP",
            "detail": "d", "status": "FLAGGED"}]  # fmt: skip
    writer.write_table(FLAGS_TABLE, END, f"flag-{iid}", stamped(row, END, f"flag-{iid}"))


def test_a_flagged_bar_in_the_window_is_an_unmeasured_row_with_a_reason() -> None:
    writer, reader, days = _store()
    start = sessions_ending(END, 7)[0]
    _flag(writer, reader, "EQ:B", days[days.index(start) + 2])  # mid-window
    _flag(writer, reader, "EQ:A", start)  # the entry bar itself: still eligible, never dropped
    record = compute_outcomes(task_ctx(writer), END)
    part = _partition(reader, start, END).set_index("instrument_id")
    for iid in ("EQ:A", "EQ:B"):
        assert part.loc[iid, "outcome_status"] == "UNMEASURED"
        assert part.loc[iid, "outcome_reason"] == "BAD_BAR" and pd.isna(part.loc[iid, "fwd_return"])
    assert part.loc["EQ:D", "outcome_status"] == "DELISTED" and part.loc["EQ:D", "fwd_return"] < 1
    assert record.stats["h6"]["rows"] == 4  # A, B, D and SPY: every eligible name has a row
    settings = task_ctx(writer).settings
    assert [c.status for c in check_outcomes(reader, END, settings)] == ["PASS"]


def test_outcome_rows_bounded() -> None:
    """An outlandish COMPLETE short-horizon return that no flag explains FAILs the acceptance."""
    jump = [100.0] * (N - 3) + [5000.0] * 3  # +4900% inside the 6-session window, no flag
    writer, reader, _ = _store(jump)
    compute_outcomes(task_ctx(writer), END)
    settings = task_ctx(writer).settings
    [check] = check_outcomes(reader, END, settings)
    assert check.status == "FAIL" and "EQ:A" in check.detail and "bar-quality" in check.detail
    _flag(writer, reader, "EQ:A", END)  # flagged: the row becomes UNMEASURED, nothing to explain
    compute_outcomes(task_ctx(writer), END)
    assert [c.status for c in check_outcomes(reader, END, settings)] == ["PASS"]


def test_a_real_squeeze_warns_and_never_fails_the_acceptance() -> None:
    """A +1,600% run in a few sessions with no jump beyond the detector's bound (a GME-style
    squeeze) is a WARN naming the name: the row stays COMPLETE."""
    squeeze = [100.0] * (N - 4) + [200.0, 400.0, 800.0, 1700.0]
    writer, reader, _ = _store(squeeze)
    compute_outcomes(task_ctx(writer), END)
    [check] = check_outcomes(reader, END, task_ctx(writer).settings)
    assert check.status == "WARN" and "EQ:A" in check.detail and "no suspect bar" in check.detail
    part = _partition(reader, sessions_ending(END, 7)[0], END).set_index("instrument_id")
    assert part.loc["EQ:A", "outcome_status"] == "COMPLETE"
