"""The index-membership task on the recorded fja05680 slice: a snapshot per session, a broken
pull writes nothing."""

from datetime import UTC, date, datetime

from algotrade.data.listings.membership import index_members
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.listings.index_membership import ingest_index_membership
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sp500_history.membership import Sp500Membership
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import published as payloads

DAY = date(2026, 10, 8)
CLOCK = lambda: datetime(2026, 10, 8, 22, tzinfo=UTC)  # noqa: E731
SLICE = (5, 40)  # the 77-row slice holds fewer than the ~500 open intervals of the full file


def source(payload: bytes | None = None) -> Sp500Membership:
    def transport(url: str) -> bytes:
        if payload is None:
            raise HttpError(404)
        return payload

    return Sp500Membership(http_for(transport, RetryPolicy(tries=1)))


def test_task_writes_the_intervals_as_a_snapshot_and_they_read_back() -> None:
    ctx = task_ctx(StoreWriter(MemoryBackend()), clock=CLOCK)
    record = ingest_index_membership(ctx, source(payloads.membership_csv()), DAY, SLICE)
    assert record.status is RunStatus.COMPLETE
    assert record.stats["intervals"] == 77 and record.stats["first_start"] == "1996-01-02"
    stored = ctx.reader.table("instruments/index_membership", DAY)
    assert stored is not None and set(stored["source"]) == {"sp500_history"}
    got = index_members(ctx.reader, date(2019, 1, 2))
    assert got.snapshot == DAY and {"AAPL", "TWTR", "FB"} <= got.tickers
    assert "META" not in got.tickers and record.stats["members_on_session"] == 32


def test_a_pull_that_lists_far_too_few_members_is_a_failure_and_writes_nothing() -> None:
    ctx = task_ctx(StoreWriter(MemoryBackend()), clock=CLOCK)
    record = ingest_index_membership(ctx, source(payloads.membership_csv()), DAY)  # 450..550
    assert record.status is RunStatus.FAILED and "expected 450..550" in str(
        record.stats["failed_because"]
    )
    assert ctx.reader.dates("instruments/index_membership") == []


def test_no_file_fails_the_run_without_writing() -> None:
    ctx = task_ctx(StoreWriter(MemoryBackend()), clock=CLOCK)
    record = ingest_index_membership(ctx, source(None), DAY, SLICE)
    assert record.status is RunStatus.FAILED
    assert ctx.reader.dates("instruments/index_membership") == []
