"""Events are read by EVENT date, from any partition (``algotrade.data.events``)."""

from datetime import date, timedelta

import pandas as pd

from algotrade.data import StoreReader
from algotrade.data.events import read_events
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.writers import StoreWriter
from tests.storage_helpers import T0, stamped

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
