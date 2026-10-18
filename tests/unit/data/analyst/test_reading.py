"""``data.analyst.reading``: the latest stored version of each snapshot row, nulls equal in the
keys, and what a session may see: ``session_date`` on or before it AND published before the next
session's open (a late re-run never reaches back into the sessions before it)."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.analyst import reading
from algotrade.data.analyst.reading import (
    COVERAGE,
    ESTIMATES,
    KINDS,
    TABLE,
    TARGET,
    latest_versions,
    snapshot_window,
    stored_snapshots,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

WED, THU, FRI, SAT, MON = (date(2026, 10, d) for d in (14, 15, 16, 17, 19))
NIGHT_WED = datetime(2026, 10, 14, 22, 5, tzinfo=UTC)  # 18:05 in New York: after the close
FRI_MORNING = datetime(2026, 10, 16, 14, 0, tzinfo=UTC)  # 10:00 in New York: after the open
MON_PRE_OPEN = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)  # 08:00 in New York: before the open
MON_AFTER_OPEN = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)


def snapshot(iid: str = "EQ:A", kind: str = ESTIMATES, period: str = "2026-12-31", **more: object):
    row = {"instrument_id": iid, "kind": kind, "period": period, "ts": pd.Timestamp(NIGHT_WED)}
    return {**row, **more}


def put(
    writer: StoreWriter,
    day: date,
    run_id: str,
    rows: list[dict],
    knowledge: datetime,
    source: str = "fmp",
) -> None:
    writer.write_table(TABLE, day, run_id, stamped(rows, day, run_id, knowledge, source))


def test_an_empty_store_has_no_snapshots_and_no_window() -> None:
    reader = StoreReader(MemoryBackend())
    assert stored_snapshots(reader, None, KINDS).empty
    assert snapshot_window(reader, KINDS, WED).at(WED, 5) is None


def test_the_kind_constants_of_the_feature_groups_are_the_readers() -> None:
    """The groups cannot import ``data``: they spell the kinds themselves, and must agree."""
    from algotrade.features.rollups.consensus import analyst_status  # noqa: PLC0415

    assert (analyst_status.ESTIMATES, analyst_status.TARGET, analyst_status.COVERAGE) == (
        reading.ESTIMATES,
        reading.TARGET,
        reading.COVERAGE,
    )
    assert analyst_status.SNAPSHOTS == reading.TABLE


def test_a_rerun_of_a_night_replaces_that_nights_row_and_other_nights_stay() -> None:
    writer = StoreWriter(MemoryBackend())
    put(writer, WED, "r1", [snapshot(eps_avg=1.0)], NIGHT_WED)
    put(writer, WED, "r2", [snapshot(eps_avg=2.0)], datetime(2026, 10, 14, 23, 30, tzinfo=UTC))
    put(writer, THU, "r3", [snapshot(eps_avg=3.0)], datetime(2026, 10, 15, 22, 5, tzinfo=UTC))
    got = stored_snapshots(StoreReader(writer._backend), None, KINDS)
    assert list(got["session_date"]) == [WED, THU]  # date objects, in key order
    assert list(got["eps_avg"]) == [2.0, 3.0]


def version(run_id: str, known: str, fetched: str, v: int, period: object = "2026-12-31") -> dict:
    """One stored version of a row, as a reader frame holds it."""
    return {
        "instrument_id": "EQ:A",
        "source": "fmp",
        "kind": ESTIMATES,
        "period": period,
        "session_date": WED,
        "knowledge_ts": pd.Timestamp(f"2026-10-14T{known}Z"),
        "ts": pd.Timestamp(f"2026-10-14T{fetched}Z"),
        "run_id": run_id,
        "v": v,
    }


def test_the_latest_version_wins_by_knowledge_then_fetch_then_run_id() -> None:
    rows = [
        version("a", "22:00", "21:00", 1),
        version("a", "22:00", "21:30", 2),
        version("b", "22:00", "21:30", 3),
        version("z", "21:00", "23:00", 0),
    ]
    for order in (rows, rows[::-1]):
        got = latest_versions(pd.DataFrame(order))
        assert list(got["v"]) == [3]  # knowledge first, then the fetch instant, then the run id


def test_a_null_in_a_key_column_equals_another_null() -> None:
    """Fails if a null ``period`` compared unequal to itself: the row would be kept twice."""
    frame = pd.DataFrame(
        [
            version("a", "22:00", "21:00", 1, period=None),
            version("b", "23:00", "21:00", 2, period=float("nan")),
        ]
    )
    assert list(latest_versions(frame)["v"]) == [2]


def test_a_session_sees_only_rows_of_its_own_session_or_earlier() -> None:
    writer = StoreWriter(MemoryBackend())
    put(writer, WED, "r1", [snapshot(eps_avg=1.0)], NIGHT_WED)
    put(writer, THU, "r2", [snapshot(eps_avg=2.0)], datetime(2026, 10, 15, 22, 5, tzinfo=UTC))
    reader = StoreReader(writer._backend)
    assert list(stored_snapshots(reader, None, KINDS, through=WED)["eps_avg"]) == [1.0]
    assert list(stored_snapshots(reader, None, KINDS, through=THU)["eps_avg"]) == [1.0, 2.0]
    window = snapshot_window(reader, KINDS, WED)
    assert list(window.at(WED, 5)["eps_avg"]) == [1.0]
    assert list(window.at(THU, 5)["eps_avg"]) == [1.0, 2.0]


def test_a_late_rerun_is_invisible_before_the_open_that_follows_its_publication() -> None:
    """The lookahead rule. Fails if the ``visible_from`` filter were removed: Wednesday's
    session would read the value a Friday-morning re-run published, two days later."""
    writer = StoreWriter(MemoryBackend())
    put(writer, WED, "r1", [snapshot(eps_avg=1.0)], NIGHT_WED)
    put(writer, WED, "r2", [snapshot(eps_avg=9.0)], FRI_MORNING)  # the same night, re-run late
    reader = StoreReader(writer._backend)
    for session in (WED, THU):
        assert stored_snapshots(reader, None, KINDS, through=session).empty, session
    assert snapshot_window(reader, KINDS, WED).at(THU, 5) is None
    assert list(stored_snapshots(reader, None, KINDS, through=FRI)["eps_avg"]) == [9.0]
    assert list(snapshot_window(reader, KINDS, WED).at(FRI, 5)["eps_avg"]) == [9.0]
    # read as of before the re-run (ADR 0007), the earlier version is the one every session sees
    before = datetime(2026, 10, 15, tzinfo=UTC)
    assert list(stored_snapshots(reader, before, KINDS, through=WED)["eps_avg"]) == [1.0]


def test_the_open_of_the_next_session_is_the_line() -> None:
    """A run published over the weekend or before Monday's open belongs to Friday's session; one
    published after Monday's open does not."""
    writer = StoreWriter(MemoryBackend())
    friday_night = datetime(2026, 10, 16, 23, 0, tzinfo=UTC)
    put(writer, FRI, "r1", [snapshot("EQ:A", eps_avg=1.0)], friday_night)
    put(writer, FRI, "r2", [snapshot("EQ:B", eps_avg=2.0)], datetime(2026, 10, 17, 15, tzinfo=UTC))
    put(writer, FRI, "r3", [snapshot("EQ:C", eps_avg=3.0)], MON_PRE_OPEN)
    put(writer, FRI, "r4", [snapshot("EQ:D", eps_avg=4.0)], MON_AFTER_OPEN)
    got = stored_snapshots(StoreReader(writer._backend), None, KINDS, through=FRI)
    assert list(got["instrument_id"]) == ["EQ:A", "EQ:B", "EQ:C"]
    both = stored_snapshots(StoreReader(writer._backend), None, KINDS, through=MON)
    assert list(both["instrument_id"]) == ["EQ:A", "EQ:B", "EQ:C", "EQ:D"]
    assert list(both["visible_from"]) == [FRI, FRI, FRI, MON]


def test_kinds_instruments_and_the_first_session_narrow_the_read() -> None:
    writer = StoreWriter(MemoryBackend())
    rows = [
        snapshot("EQ:A", ESTIMATES, eps_avg=1.0),
        snapshot("EQ:B", TARGET, "current", target_consensus=50.0),
        snapshot("EQ:A", COVERAGE, "current", status="OK"),
    ]
    put(writer, WED, "r1", rows, NIGHT_WED)
    put(
        writer,
        THU,
        "r2",
        [snapshot("EQ:A", ESTIMATES, eps_avg=2.0)],
        datetime(2026, 10, 15, 22, tzinfo=UTC),
    )
    reader = StoreReader(writer._backend)
    assert set(stored_snapshots(reader, None, (TARGET,))["instrument_id"]) == {"EQ:B"}
    assert set(stored_snapshots(reader, None, KINDS, ["EQ:B"])["kind"]) == {TARGET}
    assert list(stored_snapshots(reader, None, (ESTIMATES,), since=THU)["session_date"]) == [THU]
    marker = stored_snapshots(reader, None, (COVERAGE,))
    assert list(marker["status"]) == ["OK"]


def test_rows_stored_before_the_markers_read_with_an_empty_status() -> None:
    writer = StoreWriter(MemoryBackend())
    put(writer, WED, "r1", [snapshot(eps_avg=1.0)], NIGHT_WED)  # no status column in the rows
    got = stored_snapshots(StoreReader(writer._backend), None, KINDS)
    assert list(got["status"].isna()) == [True]
