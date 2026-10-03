from datetime import date

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.services.explore.store import (
    NotFoundError,
    latest_session,
    paginate,
    partition_for,
    record,
    store_info,
    store_over,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference

D1, D2 = date(2026, 9, 30), date(2026, 10, 1)


def test_paginate_clamps_page_and_size() -> None:
    rows = list(range(5))
    assert paginate(rows, 2, 2).items == [2, 3]
    page = paginate(rows, 0, 0)
    assert (page.items, page.page, page.size, page.total) == ([0], 1, 1, 5)
    assert paginate(rows, 1, 10_000).size == 1000
    assert paginate(rows, 9, 2).items == []


def test_record_is_json_safe_without_stamps() -> None:
    row = {"instrument_id": "X", "v": float("nan"), "ts": pd.Timestamp("2026-10-01", tz="UTC"),
           "session_date": D1, "run_id": "r", "n": 3}  # fmt: skip
    assert record(row, ["instrument_id"]) == {"v": None, "ts": "2026-10-01T00:00:00+00:00", "n": 3}


def test_empty_store_has_no_session_and_reports_its_kind() -> None:
    store = store_over(MemoryBackend(), MemoryConfigStore({}), UserContext("local"))
    info = store_info(store)
    assert (info.storage, info.latest_session, info.tables) == ("memory", None, [])
    with pytest.raises(NotFoundError, match="nothing stored"):
        partition_for(store.reader, "bars/1d", None)


def test_session_is_the_partition_on_or_before_and_never_a_later_one() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    write_reference(writer, D2, {"AAA": "EQ:AAA"})
    store = store_over(backend, MemoryConfigStore({}), UserContext("local"), "file://x")
    assert latest_session(store.reader) == D2  # no bars: the reference snapshot
    assert partition_for(store.reader, "instruments/reference", date(2026, 10, 5)) == D2
    with pytest.raises(NotFoundError, match="on or before 2026-09-30"):
        partition_for(store.reader, "instruments/reference", D1)
    assert store.kind == "file"
    rows = [{"instrument_id": "EQ:AAA", "ts": pd.Timestamp(D1, tz="UTC"), "open": 1.0,
             "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]  # fmt: skip
    writer.write_table("bars/1d", D1, "b", stamped(rows, D1, "b"))
    assert latest_session(store.reader) == D1
