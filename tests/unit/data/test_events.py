"""Events are read by EVENT date, from any partition, among the rows known as of a session
(``known_from``, else the stored session: ADR 0050) (``algotrade.data.events``)."""

from datetime import date, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.events import read_events
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped

SPLIT_DAY, BACKFILLED_ON = date(2015, 6, 1), date(2026, 10, 2)


def split(day: date, ratio: float, iid: str = "EQ:A") -> dict[str, object]:
    return {"instrument_id": iid, "ts": pd.Timestamp(day, tz="UTC"), "ratio": ratio}


def test_finds_events_stored_in_a_later_partition() -> None:
    """Regression: a 2015 split backfilled into date=2026-10-02 was invisible to a backtest
    ending in 2016, because events were filtered by partition date."""
    backend = MemoryBackend()
    rows = [split(SPLIT_DAY, 2.0), split(date(2020, 1, 2), 4.0)]
    StoreWriter(backend).write_table(
        "events/split", BACKFILLED_ON, "ca", stamped(rows, BACKFILLED_ON, "ca")
    )
    events = read_events(StoreReader(backend), "events/split", date(2015, 1, 1), date(2016, 1, 1))
    assert list(events.frame["ratio"]) == [2.0]  # the 2020 split is outside the window
    assert events.runs == ["ca"]
    none = read_events(StoreReader(backend), "events/split", date(2010, 1, 1), date(2011, 1, 1))
    assert none.frame.empty and none.runs == []


def test_keeps_the_latest_knowledge_per_event_and_filters_instruments() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    later = T0 + timedelta(days=1)
    first = [split(SPLIT_DAY, 3.0), split(SPLIT_DAY, 5.0, "EQ:B")]
    writer.write_table("events/split", SPLIT_DAY, "r1", stamped(first, SPLIT_DAY, "r1"))
    fixed = [split(SPLIT_DAY, 2.0)]  # a correction, stored years later
    writer.write_table(
        "events/split", BACKFILLED_ON, "r2", stamped(fixed, BACKFILLED_ON, "r2", later)
    )
    reader = StoreReader(backend)
    events = read_events(reader, "events/split", SPLIT_DAY, SPLIT_DAY, ["EQ:A"])
    assert list(events.frame["ratio"]) == [2.0] and events.runs == ["r2"]
    pinned = read_events(reader, "events/split", SPLIT_DAY, SPLIT_DAY, ["EQ:A"], as_of=T0)
    assert list(pinned.frame["ratio"]) == [3.0]  # as stored at T0 (the version pin)
    both = read_events(reader, "events/split", SPLIT_DAY, SPLIT_DAY)
    assert list(both.frame["instrument_id"]) == ["EQ:A", "EQ:B"]
    assert read_events(reader, "events/dividend", SPLIT_DAY, SPLIT_DAY).frame.empty


def test_several_kinds_of_change_on_one_day_are_distinct_events() -> None:
    backend = MemoryBackend()
    ts = pd.Timestamp(SPLIT_DAY, tz="UTC")
    rows = [
        {"instrument_id": "EQ:META", "ts": ts, "change": "added"},
        {"instrument_id": "EQ:META", "ts": ts, "change": "ticker_changed"},
    ]
    StoreWriter(backend).write_table(
        "events/reference_change", SPLIT_DAY, "r1", stamped(rows, SPLIT_DAY, "r1")
    )
    events = read_events(StoreReader(backend), "events/reference_change", SPLIT_DAY, SPLIT_DAY)
    assert sorted(events.frame["change"]) == ["added", "ticker_changed"]


def test_without_known_from_a_row_is_known_from_the_session_that_stored_it() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    first = stamped([split(SPLIT_DAY, 3.0)], SPLIT_DAY, "r1")
    writer.write_table("events/split", SPLIT_DAY, "r1", first)
    fixed = stamped([split(SPLIT_DAY, 2.0)], BACKFILLED_ON, "r2", T0 + timedelta(days=1))
    writer.write_table("events/split", BACKFILLED_ON, "r2", fixed)
    args = (StoreReader(backend), "events/split", SPLIT_DAY, SPLIT_DAY)
    assert list(read_events(*args, through=SPLIT_DAY).frame["ratio"]) == [3.0]
    assert list(read_events(*args, through=BACKFILLED_ON).frame["ratio"]) == [2.0]
    assert list(read_events(*args).frame["ratio"]) == [2.0]
    assert read_events(*args, through=date(2015, 5, 31)).frame.empty


def test_a_row_known_before_its_partition_is_visible_to_earlier_sessions() -> None:
    """A 2015 split backfilled into date=2026-10-02 with ``known_from`` = its date is known to a
    2015 session; one stored without ``known_from`` (or with a null) is not."""
    backend = MemoryBackend()
    known = {**split(SPLIT_DAY, 2.0), "known_from": SPLIT_DAY}
    rows = [
        known,
        split(SPLIT_DAY, 3.0, "EQ:B"),
        {**split(SPLIT_DAY, 4.0, "EQ:C"), "known_from": None},
    ]
    StoreWriter(backend).write_table(
        "events/split", BACKFILLED_ON, "ca", stamped(rows, BACKFILLED_ON, "ca")
    )
    args = (StoreReader(backend), "events/split", SPLIT_DAY, SPLIT_DAY)
    assert list(read_events(*args, through=SPLIT_DAY).frame["instrument_id"]) == ["EQ:A"]
    assert read_events(*args, through=SPLIT_DAY - timedelta(days=1)).frame.empty
    every = ["EQ:A", "EQ:B", "EQ:C"]
    assert list(read_events(*args, through=BACKFILLED_ON).frame["instrument_id"]) == every
    assert list(read_events(*args).frame["instrument_id"]) == every  # None: unchanged


def test_events_by_event_date_passes_through_on() -> None:
    from algotrade.data.events import events_by_event_date  # noqa: PLC0415

    backend = MemoryBackend()
    rows = [split(SPLIT_DAY, 2.0), {**split(SPLIT_DAY, 3.0, "EQ:B"), "known_from": SPLIT_DAY}]
    StoreWriter(backend).write_table(
        "events/split", BACKFILLED_ON, "ca", stamped(rows, BACKFILLED_ON, "ca")
    )
    args = (StoreReader(backend), "events/split", SPLIT_DAY, SPLIT_DAY)
    assert list(events_by_event_date(*args, through=SPLIT_DAY)["instrument_id"]) == ["EQ:B"]
    assert len(events_by_event_date(*args)) == 2


def test_stored_events_keep_each_snapshot_up_to_a_date() -> None:
    from algotrade.data.events import stored_events  # noqa: PLC0415

    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    assert stored_events(reader, "events/earnings", BACKFILLED_ON).empty
    for day in (date(2026, 9, 1), date(2026, 10, 1), date(2026, 10, 2)):
        row = {
            "instrument_id": "EQ:A",
            "ts": pd.Timestamp(2026, 11, 2, tz="UTC"),
            "known_from": day,
        }
        writer.write_table("events/earnings", day, f"r{day}", stamped([row], day, f"r{day}"))
    frame = stored_events(reader, "events/earnings", date(2026, 10, 1))
    assert list(frame["session_date"]) == [date(2026, 9, 1), date(2026, 10, 1)]  # not merged
    assert list(frame["known_from"]) == [date(2026, 9, 1), date(2026, 10, 1)]


def test_stored_events_include_later_partitions_known_by_the_date() -> None:
    """A backfill on 2026-10-02 of a 2019 report (``known_from`` = its report date) is in the
    calendar as of 2019-05-01, sorted by when it was known; the forward row it stored is not."""
    from algotrade.data.events import stored_events  # noqa: PLC0415

    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    nightly = {
        "instrument_id": "EQ:A",
        "ts": pd.Timestamp(2019, 4, 1, tz="UTC"),
        "known_from": date(2019, 3, 1),
    }
    writer.write_table(
        "events/earnings", date(2019, 3, 1), "n", stamped([nightly], date(2019, 3, 1), "n")
    )
    report = date(2019, 5, 1)
    rows = [
        {"instrument_id": "EQ:A", "ts": pd.Timestamp(report, tz="UTC"), "known_from": report},
        {
            "instrument_id": "EQ:A",
            "ts": pd.Timestamp(2026, 11, 2, tz="UTC"),
            "known_from": BACKFILLED_ON,
        },
    ]
    writer.write_table("events/earnings", BACKFILLED_ON, "b", stamped(rows, BACKFILLED_ON, "b"))
    frame = stored_events(reader, "events/earnings", report)
    assert list(frame["known_from"]) == [date(2019, 3, 1), report]
    assert list(frame["session_date"]) == [date(2019, 3, 1), BACKFILLED_ON]
    assert len(stored_events(reader, "events/earnings", BACKFILLED_ON)) == 3


def test_a_nightly_window_run_does_not_hide_the_backfilled_dividends() -> None:
    """Regression (real store, 2026-10-02): the 26-month corporate-actions backfill and that
    night's -7..+30-day window run share ``date=2026-10-02``; reads picked the window run
    only, so AAPL showed no trailing dividends. Event runs now merge."""
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    session = date(2026, 10, 2)

    def dividend(iid: str, day: date) -> dict[str, object]:
        return {"instrument_id": iid, "ts": pd.Timestamp(day, tz="UTC"), "cash_amount": 0.26}

    paid = [date(2025, 11, 10), date(2026, 2, 9), date(2026, 5, 11), date(2026, 8, 10)]
    backfill = [dividend("EQ:AAPL", d) for d in paid] + [dividend("EQ:KO", d) for d in paid]
    writer.write_table("events/dividend", session, "ca1", stamped(backfill, session, "ca1"))
    window = [dividend("EQ:XOM", date(2026, 10, 9))]  # tonight's run: nothing for AAPL / KO
    late = T0 + timedelta(hours=5)
    writer.write_table("events/dividend", session, "ca2", stamped(window, session, "ca2", late))
    trailing = read_events(reader, "events/dividend", date(2025, 10, 2), session)
    counts = trailing.frame.groupby("instrument_id").size().to_dict()
    assert counts == {"EQ:AAPL": 4, "EQ:KO": 4}
    assert trailing.runs == ["ca1"]
    ahead = read_events(reader, "events/dividend", session, date(2026, 11, 1))
    assert list(ahead.frame["instrument_id"]) == ["EQ:XOM"]
