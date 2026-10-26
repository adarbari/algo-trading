"""The delisted-tickers task on the RECORDED Massive inactive slice: one snapshot per session,
stamps, an idempotent rerun, and the ``[quality] min_delisted_tickers`` floor (ADR 0086)."""

import json
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.data.listings.delisted import read_delisted_tickers
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.schemas import spec_for
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.listings.delisted_tickers import (
    TABLE,
    ingest_delisted_tickers,
)
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.massive.tickers import MassiveTickers
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import massive as fx

DAY = date(2026, 10, 24)
CLOCK = lambda: datetime(2026, 10, 24, 22, tzinfo=UTC)  # noqa: E731
RECORDS = json.loads(
    (REPO_ROOT / "tests/fixtures/sources/massive/inactive_tickers_slice.json").read_text()
)["results"]
LOW = SourcesSettings(min_delisted_tickers=5)


def source(records: list[dict[str, object]] | None = None) -> MassiveTickers:
    def transport(url: str) -> bytes:
        if records is None:
            raise HttpError(404)
        return fx.page(records)

    return MassiveTickers(http_for(transport, RetryPolicy(tries=1)))


def test_the_task_writes_a_stamped_snapshot_with_its_stats() -> None:
    ctx = task_ctx(StoreWriter(MemoryBackend()), clock=CLOCK, settings=LOW)
    record = ingest_delisted_tickers(ctx, source(RECORDS), DAY)
    assert record.status is RunStatus.COMPLETE
    stored = ctx.reader.table(TABLE, DAY)
    assert stored is not None and len(stored) == 60
    assert set(stored["source"]) == {"massive"} and set(stored["run_id"]) == {record.run_id}
    assert set(stored["session_date"]) == {DAY}
    assert set(pd.to_datetime(stored["knowledge_ts"])) == {pd.Timestamp(CLOCK())}  # write time
    assert set(pd.to_datetime(stored["ts"])) == {pd.Timestamp(DAY, tz="UTC")}
    assert "instrument_id" not in stored.columns  # no id until the listing-history merge
    twtr = stored[stored["ticker"] == "TWTR"].iloc[0]
    assert (twtr["end_date"], twtr["security_type"]) == (date(2022, 10, 31), "COMMON_STOCK")
    stats = record.stats
    assert stats["rows"] == 60 and stats["dropped_duplicate"] == 0
    assert (stats["with_cik"], stats["with_figi"], stats["without_end_date"]) == (54, 25, 3)
    assert stats["by_security_type"]["NULL"] == 10  # 6 untyped + 4 INDEX (unmapped): counted
    assert sum(stats["by_security_type"].values()) == 60
    assert stats["by_year"]["2022"] >= 1 and sum(stats["by_year"].values()) == 57
    assert spec_for(TABLE).key == ("source", "ticker", "end_date")


def test_a_rerun_for_the_session_replaces_the_snapshot_not_doubles_it() -> None:
    ctx = task_ctx(StoreWriter(MemoryBackend()), clock=CLOCK, settings=LOW)
    first = ingest_delisted_tickers(ctx, source(RECORDS), DAY)
    second = ingest_delisted_tickers(ctx, source(RECORDS[:40]), DAY)
    assert (first.status, second.status) == (RunStatus.COMPLETE, RunStatus.COMPLETE)
    frame, snapshot = read_delisted_tickers(ctx.reader)
    assert snapshot == DAY and len(frame) == 40  # the latest run of the session wins
    assert set(frame["run_id"]) == {second.run_id}
    again = ingest_delisted_tickers(ctx, source(RECORDS[:40]), DAY)
    assert len(read_delisted_tickers(ctx.reader)[0]) == 40 and again.stats["rows"] == 40


def test_a_pull_under_the_floor_fails_and_writes_nothing_and_the_setting_drives_it() -> None:
    ctx = task_ctx(StoreWriter(MemoryBackend()), clock=CLOCK)  # the site floor: 10,000
    record = ingest_delisted_tickers(ctx, source(RECORDS), DAY)
    assert record.status is RunStatus.FAILED
    assert "60 delisted tickers, expected at least 10000" in str(record.stats)
    assert ctx.reader.table(TABLE, DAY) is None
    for floor, status in ((60, RunStatus.COMPLETE), (61, RunStatus.FAILED)):
        ctx = task_ctx(
            StoreWriter(MemoryBackend()),
            clock=CLOCK,
            settings=SourcesSettings(min_delisted_tickers=floor),
        )
        assert ingest_delisted_tickers(ctx, source(RECORDS), DAY).status is status


def test_no_response_or_an_empty_list_fails_the_run() -> None:
    ctx = task_ctx(StoreWriter(MemoryBackend()), clock=CLOCK, settings=LOW)
    assert ingest_delisted_tickers(ctx, source(None), DAY).status is RunStatus.FAILED
    assert ingest_delisted_tickers(ctx, source([]), DAY).status is RunStatus.FAILED
    assert ctx.reader.table(TABLE, DAY) is None


def test_a_reused_ticker_keeps_both_lives_and_a_repeat_is_dropped_and_counted() -> None:
    records = [
        {"ticker": "ABC", "type": "CS", "delisted_utc": "2010-05-03T04:00:00Z"},
        {"ticker": "ABC", "type": "CS", "delisted_utc": "2010-05-03T04:00:00Z"},
        {"ticker": "ABC", "type": "CS", "delisted_utc": "2021-08-02T04:00:00Z"},
        {"ticker": "XYZ", "type": "ETF"},  # no delisting date: kept, end_date null
    ]
    ctx = task_ctx(
        StoreWriter(MemoryBackend()), clock=CLOCK, settings=SourcesSettings(min_delisted_tickers=3)
    )
    record = ingest_delisted_tickers(ctx, source(records), DAY)
    assert record.status is RunStatus.COMPLETE
    assert (record.stats["rows"], record.stats["dropped_duplicate"]) == (3, 1)
    frame, _ = read_delisted_tickers(ctx.reader)
    assert sorted(frame["ticker"]) == ["ABC", "ABC", "XYZ"]
    assert frame[frame["ticker"] == "XYZ"]["end_date"].isna().all()
