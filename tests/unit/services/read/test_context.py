"""The read context of one request: the session resolved once, the caller's catalogue, the
shared result cache, and ``partition``, which reads a session-grain table for exactly the
session and never an older partition (ADR 0036 decision 6)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.explore import store as explore_store
from algotrade.services.read import context
from algotrade.services.read.context import (
    NotFoundError,
    ReadContext,
    ResultCache,
    open_context,
    partition,
)
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.helpers.stored_frames import stamped

D1, D2 = date(2026, 9, 30), date(2026, 10, 1)
EARNINGS = "rollups/instrument/earnings@v1"
USER = UserContext("local")


def write_bar(writer: StoreWriter, day: date) -> None:
    bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
    row = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), **bar}
    write_rows(writer, "bars/1d", day, [row])


@pytest.fixture
def stored() -> tuple[StoreWriter, StoreReader]:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for day in (D1, D2):
        write_bar(writer, day)
    write_rows(writer, EARNINGS, D1, [{"instrument_id": "EQ:AAA", "days_to_earnings": 3}])
    return writer, StoreReader(backend)


def open_for(reader: StoreReader, requested: date | None = None) -> ReadContext:
    return open_context(reader, MemoryConfigStore({}), USER, requested)


def test_open_context_resolves_the_session_once_and_reads_the_catalogue(
    stored: tuple[StoreWriter, StoreReader], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[date | None] = []
    real = context.resolve_session

    def counting(reader: StoreReader, requested: date | None):  # type: ignore[no-untyped-def]
        calls.append(requested)
        return real(reader, requested)

    monkeypatch.setattr(context, "resolve_session", counting)
    ctx = open_for(stored[1])
    assert calls == [None]
    assert (ctx.session.date, ctx.session.is_latest, ctx.user) == (D2, True, USER)
    assert ctx.features.feature("rollup.earnings@v1.days_to_earnings") is not None
    assert isinstance(ctx.cache, ResultCache)


def test_open_context_shares_the_cache_it_is_given(stored: tuple[StoreWriter, StoreReader]) -> None:
    cache = ResultCache()
    ctx = open_context(stored[1], MemoryConfigStore({}), USER, D1, cache)
    assert ctx.cache is cache
    assert ctx.session.date == D1


def publish_bar(backend: MemoryBackend, day: date) -> None:
    """A bar written the way ingestion writes: pending, then committed (a publish)."""
    bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
    row = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), **bar}
    run = f"bars-{day}"
    StoreWriter(backend).write_table("bars/1d", day, run, stamped([row], day, run), pending=True)
    backend.tables.commit_run(run, datetime(2026, 10, 3, tzinfo=UTC))


def test_the_session_is_resolved_once_per_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryBackend()
    publish_bar(backend, D2)
    reader = StoreReader(backend)
    calls: list[date | None] = []
    real = context.resolve_session

    def counting(reader: StoreReader, requested: date | None):  # type: ignore[no-untyped-def]
        calls.append(requested)
        return real(reader, requested)

    monkeypatch.setattr(context, "resolve_session", counting)
    cache = ResultCache()
    first = open_context(reader, MemoryConfigStore({}), USER, None, cache)
    again = open_context(reader, MemoryConfigStore({}), USER, None, cache)
    assert again.session is first.session and calls == [None]  # nothing published since
    open_context(reader, MemoryConfigStore({}), USER, D1, cache)
    assert calls == [None, D1]  # another date is another session
    publish_bar(backend, date(2026, 10, 2))  # a publish: the latest session moves on
    later = open_context(reader, MemoryConfigStore({}), USER, None, cache)
    assert later.session.date == date(2026, 10, 2) and calls == [None, D1, None]


def test_open_context_on_an_empty_store_is_not_found() -> None:
    with pytest.raises(NotFoundError, match="nothing stored"):
        open_for(StoreReader(MemoryBackend()))


def test_partition_reads_exactly_the_session(stored: tuple[StoreWriter, StoreReader]) -> None:
    frame = partition(open_for(stored[1], D1), EARNINGS)
    assert isinstance(frame, pd.DataFrame)
    assert frame["days_to_earnings"].tolist() == [3]


def test_an_older_partition_exists_and_is_ignored(stored: tuple[StoreWriter, StoreReader]) -> None:
    assert partition(open_for(stored[1]), EARNINGS) == Unknown(
        UnknownCode.NO_PARTITION, f"{EARNINGS} has no partition for 2026-10-01"
    )


def test_partition_prunes_columns_and_instruments(stored: tuple[StoreWriter, StoreReader]) -> None:
    writer, reader = stored
    rows = [{"instrument_id": i, "days_to_earnings": n, "next_earnings_date": None}
            for i, n in (("EQ:AAA", 3), ("EQ:BBB", 5))]  # fmt: skip
    write_rows(writer, EARNINGS, D2, rows)
    ctx = open_for(reader, D2)
    frame = partition(ctx, EARNINGS, ["days_to_earnings"], ["EQ:BBB"])
    assert isinstance(frame, pd.DataFrame)
    assert frame["instrument_id"].tolist() == ["EQ:BBB"]
    assert "next_earnings_date" not in frame.columns
    none = partition(ctx, EARNINGS, ["days_to_earnings"], ["EQ:ZZZ"])  # stored, none asked
    assert isinstance(none, pd.DataFrame) and none.empty
    assert partition(open_for(reader, date(2026, 10, 2)), EARNINGS, ["x"]) == Unknown(
        UnknownCode.NO_PARTITION, f"{EARNINGS} has no partition for 2026-10-02"
    )


@pytest.mark.parametrize(
    "table", ["instruments/reference", "events/earnings", "holdings/etf", "instruments/description"]
)
def test_partition_refuses_other_grains(
    stored: tuple[StoreWriter, StoreReader], table: str
) -> None:
    with pytest.raises(ValueError, match="read it by its own rule"):
        partition(open_for(stored[1]), table)


def test_result_cache_is_a_small_lru() -> None:
    cache = ResultCache(size=2)
    assert cache.get("a") is None
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1  # a is now the most recent
    cache.put("c", 3)
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (1, None, 3)


def test_explore_re_exports_the_moved_names() -> None:
    assert explore_store.NotFoundError is NotFoundError
    assert explore_store.ResultCache is ResultCache
