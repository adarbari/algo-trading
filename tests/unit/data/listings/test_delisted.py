"""``read_delisted_tickers``: the latest snapshot, whatever the session, and which (ADR 0086)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.delisted import TABLE, read_delisted_tickers
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped


def rows(day: date, tickers: list[str]) -> list[dict[str, object]]:
    return [
        {"ticker": t, "ts": pd.Timestamp(day, tz="UTC"), "name": f"{t} Inc",
         "security_type": "COMMON_STOCK", "end_date": date(2020, 1, 2)}
        for t in tickers
    ]  # fmt: skip


def test_it_reads_the_latest_snapshot_and_names_it() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for day, tickers in ((date(2026, 10, 10), ["OLD"]), (date(2026, 10, 24), ["AAA", "BBB"])):
        writer.write_table(
            TABLE, day, f"r-{day}", stamped(rows(day, tickers), day, f"r-{day}", source="massive")
        )
    frame, snapshot = read_delisted_tickers(StoreReader(backend))
    assert snapshot == date(2026, 10, 24)
    assert sorted(frame["ticker"]) == ["AAA", "BBB"]
    assert {"end_date", "security_type"} <= set(frame.columns)


def test_no_snapshot_is_an_error_naming_the_task() -> None:
    with pytest.raises(MissingDataError, match="delisted-tickers"):
        read_delisted_tickers(StoreReader(MemoryBackend()))
