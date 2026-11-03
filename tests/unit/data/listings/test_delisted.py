"""``read_delisted_tickers``: the latest snapshot, whatever the session, and which (ADR 0087)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.delisted import (
    DETAILS_TABLE,
    TABLE,
    read_delisted_details,
    read_delisted_tickers,
)
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


def answer(ticker: str, found: bool, asked: date, **more: object) -> dict[str, object]:
    return {
        "ticker": ticker, "end_date": date(2023, 5, 2), "asked_date": asked, "found": found,
        "ts": pd.Timestamp(asked, tz="UTC"), **more,
    }  # fmt: skip


def test_details_are_the_union_of_the_increments_the_latest_answer_per_key() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    first, second = date(2026, 11, 2), date(2026, 11, 3)
    one = [answer("AAA", False, first), answer("BBB", True, first, list_date=date(1990, 1, 2))]
    two = [answer("AAA", True, second, list_date=date(2001, 3, 4)), answer("CCC", False, second)]
    for day, rows in ((first, one), (second, two)):
        at = datetime(day.year, day.month, day.day, 22, tzinfo=UTC)
        frame = stamped(rows, day, f"r-{day}", knowledge=at, source="massive")
        writer.write_table(DETAILS_TABLE, day, f"r-{day}", frame)
    frame = read_delisted_details(StoreReader(backend))
    assert list(frame["ticker"]) == ["AAA", "BBB", "CCC"]
    by = frame.set_index("ticker")
    assert bool(by.loc["AAA", "found"]) and by.loc["AAA", "list_date"] == date(2001, 3, 4)
    assert not bool(by.loc["CCC", "found"])


def test_no_details_is_an_empty_frame_never_an_error() -> None:
    frame = read_delisted_details(StoreReader(MemoryBackend()))
    assert frame.empty and {"ticker", "end_date", "found"} <= set(frame.columns)
