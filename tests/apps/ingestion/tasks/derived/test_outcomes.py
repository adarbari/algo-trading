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
from tests.helpers.rollup_store import END, SPY, series, store, write_bars, write_rows
from tests.helpers.stored_frames import universe_rows

N = 70  # sessions of bars: room for the 60-session horizon
IDS = {"A": "EQ:A", "B": "EQ:B", "D": "EQ:D", "SPY": SPY}


def _reference(delisted: date | None) -> list[dict[str, object]]:
    return [
        {"instrument_id": iid, "symbol": symbol, "asset_class": "EQ",
         "security_type": "COMMON_STOCK", "multiplier": 1.0, "status": "ACTIVE",
         "delisted_on": delisted if symbol == "D" else None}
        for symbol, iid in IDS.items()
    ]  # fmt: skip


def _store() -> tuple[StoreWriter, StoreReader, list[date]]:
    writer, reader = store()
    closes = {"EQ:A": series(N), "EQ:B": series(N, seed=2), SPY: series(N, seed=3),
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
