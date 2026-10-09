"""The read context of one request: the session resolved once, the caller's catalogue, the
shared result cache, and ``partition``, which reads a session-grain table for exactly the
session and never an older partition (ADR 0036 decision 6)."""

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read import context
from algotrade.services.read.context import (
    NotFoundError,
    ReadContext,
    ResultCache,
    at_session,
    open_context,
    open_read_stores,
    partition,
    partition_on,
    partition_range,
    previous_session,
    snapshot_on,
    stored_dates,
    weigh,
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
    found = partition(open_for(stored[1]), EARNINGS)
    assert isinstance(found, Unknown) and found.code is UnknownCode.NO_PARTITION
    assert found.cause.text == f"{EARNINGS} has no partition for 2026-10-01"


def test_inventory_reads_name_their_dates(stored: tuple[StoreWriter, StoreReader]) -> None:
    """The ops loaders' inventory: every stored date, a partition on a date they name, the
    snapshot a date sees (ADR 0007's rule), not the session's fact reads."""
    ctx = open_for(stored[1])
    assert stored_dates(ctx, EARNINGS) == (D1,)
    found = partition_on(ctx, EARNINGS, D1)
    assert found is not None and found["days_to_earnings"].tolist() == [3]
    assert partition_on(ctx, EARNINGS, D2) is None
    snap = snapshot_on(ctx, "bars/1d", date(2026, 10, 5))
    assert snap is not None and snap.snapshot_date == D2
    assert snapshot_on(ctx, "instruments/reference", D2) is None


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
    found = partition(open_for(reader, date(2026, 10, 2)), EARNINGS, ["x"])
    assert isinstance(found, Unknown) and found.code is UnknownCode.NO_PARTITION
    assert found.cause.text == f"{EARNINGS} has no partition for 2026-10-02"


@pytest.mark.parametrize(
    "table", ["instruments/reference", "events/earnings", "holdings/etf", "instruments/description"]
)
def test_partition_refuses_other_grains(
    stored: tuple[StoreWriter, StoreReader], table: str
) -> None:
    with pytest.raises(ValueError, match="read it by its own rule"):
        partition(open_for(stored[1]), table)


def test_partition_range_reads_a_window_ending_at_the_session(
    stored: tuple[StoreWriter, StoreReader],
) -> None:
    ctx = open_for(stored[1], D2)
    found = partition_range(ctx, EARNINGS, D1, D2)
    assert found is not None and found["days_to_earnings"].tolist() == [3]
    assert partition_range(ctx, EARNINGS, D2, D2) is None  # nothing stored in the window
    with pytest.raises(ValueError, match="after the request's session"):
        partition_range(open_for(stored[1], D1), EARNINGS, D1, D2)
    with pytest.raises(ValueError, match="only session-grain tables"):
        partition_range(ctx, "holdings/etf", D1, D2)


def test_the_previous_session_of_a_table_is_named_explicitly(
    stored: tuple[StoreWriter, StoreReader],
) -> None:
    reader = stored[1]
    latest = open_for(reader)
    assert previous_session(latest, "bars/1d") == D1
    assert previous_session(latest, EARNINGS) == D1
    assert previous_session(open_for(reader, D1), "bars/1d") is None
    with pytest.raises(ValueError, match="only session-grain tables"):
        previous_session(latest, "instruments/reference")
    earlier = at_session(latest, D1)
    assert (earlier.session.date, earlier.user, earlier.cache) == (D1, latest.user, latest.cache)
    assert earlier.loaders is None
    frame = partition(earlier, EARNINGS)
    assert isinstance(frame, pd.DataFrame) and frame["days_to_earnings"].tolist() == [3]


def test_result_cache_is_a_small_lru() -> None:
    cache = ResultCache(size=2)
    assert cache.get("a") is None
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1  # a is now the most recent
    cache.put("c", 3)
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (1, None, 3)


def test_result_cache_holds_32_entries_by_default() -> None:
    cache = ResultCache()
    for i in range(33):
        cache.put(i, i)
    assert cache.get(0) is None and cache.get(1) == 1 and cache.get(32) == 32


def test_result_cache_is_bounded_by_the_bytes_of_its_frames() -> None:
    frame = pd.DataFrame({"x": range(1000)})  # 8 000 bytes and its index
    held = weigh(frame)
    assert held >= 8000 and weigh((frame, {"k": frame})) == 2 * held and weigh("text") == 0
    cache = ResultCache(size=32, max_bytes=2 * held + 1)
    for key in "abc":
        cache.put(key, frame)
    # the oldest went to keep the frames under the bound; the newest always stays
    assert (cache.get("a"), cache.get("b") is frame, cache.get("c") is frame) == (None, True, True)
    cache.put("d", pd.DataFrame({"x": range(10 * 1000)}))  # alone over the bound
    assert cache.get("d") is not None and cache.get("b") is None and cache.get("c") is None
    cache.put("d", 1)  # replaced by a small value: its weight is released
    cache.put("e", frame)
    cache.put("f", frame)
    assert cache.get("d") == 1 and cache.get("e") is frame and cache.get("f") is frame


def test_the_weight_of_a_pandas_3_string_frame_is_close_to_its_real_memory() -> None:
    # the string dtype is counted from its Arrow buffers; pricing every cell again held about
    # a quarter of the bound (a rule_screen partition weighed 3.8x its size)
    table = pa.table(
        {
            "run_id": [f"screen-run-{i % 50}" for i in range(20_000)],
            "decision": ["QUALIFIED"] * 20_000,
            "score": [float(i) for i in range(20_000)],
        }
    )
    frame = table.to_pandas()
    real = int(frame.memory_usage(deep=True).sum())
    assert real <= weigh(frame) <= 1.5 * real
    objects = pd.DataFrame({"s": pd.Series([f"v{i}" for i in range(1000)], dtype=object)})
    assert weigh(objects) >= int(objects.memory_usage(deep=True).sum()) // 2  # priced per cell


def test_a_request_memo_is_its_own_and_shared_by_its_sessions(
    stored: tuple[StoreWriter, StoreReader],
) -> None:
    ctx = open_for(stored[1])
    assert ctx.memo == {} and at_session(ctx, D1).memo is ctx.memo
    assert open_for(stored[1]).memo is not ctx.memo


def test_open_read_stores_opens_the_store_and_the_configs(tmp_path: Path) -> None:
    reader, configs = open_read_stores("memory://", tmp_path)
    assert reader.table_names() == []
    assert configs.names("local", "screeners") == []
