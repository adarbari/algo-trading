from datetime import UTC, date, datetime

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.writers import StoreWriter
from algotrade_ingestion.sources.base import FetchRequest
from algotrade_ingestion.sources.http import HttpError, RetryPolicy
from algotrade_ingestion.sources.nasdaq_earnings import NasdaqEarningsSource, parse_calendar
from algotrade_ingestion.tasks.earnings import ingest_earnings, weekdays
from tests.earnings_fixture import calendar
from tests.ingest_helpers import task_ctx
from tests.storage_helpers import write_reference

DAY = date(2026, 10, 2)  # a Friday
CLOCK = lambda: datetime(2026, 10, 2, 22, tzinfo=UTC)  # noqa: E731


def test_parse_forecast_and_reported_rows() -> None:
    upcoming = parse_calendar(
        DAY,
        calendar(
            [("AAPL", "time-after-hours"), ("MSFT", "time-pre-market"), ("ODD", "time-unexpected")]
        ),
    )
    assert list(upcoming["time"]) == ["after_hours", "pre_market", "unknown"]
    assert list(upcoming["symbol"]) == ["AAPL", "MSFT", "ODD"]  # the job resolves ids
    assert upcoming["eps_forecast"].tolist() == [1.2, 1.2, 1.2]
    assert not upcoming["reported"].any()
    past = parse_calendar(DAY, calendar([("LOSS", "time-pre-market")], reported=True))
    assert (past.at[0, "eps_reported"], past.at[0, "surprise_pct"], past.at[0, "reported"]) == (
        -0.3,
        -12.5,
        True,
    )
    assert parse_calendar(DAY, calendar([])).empty
    assert parse_calendar(DAY, calendar([("", "time-pre-market")])).empty


def test_source_paces_requests() -> None:
    pauses: list[float] = []
    urls: list[str] = []
    source = NasdaqEarningsSource(
        lambda url: urls.append(url) or calendar([("A", "x")]),
        pauses.append,
        RetryPolicy(tries=1),
        pause_s=0.25,
    )
    payload = source.fetch(FetchRequest("2026-10-05"))
    assert urls == ["https://api.nasdaq.com/api/calendar/earnings?date=2026-10-05"]
    assert pauses == [0.25]
    normalized = source.normalize(FetchRequest("2026-10-05"), payload or b"")
    assert normalized is not None and normalized.session_date == date(2026, 10, 5)


def test_weekdays_window() -> None:
    assert weekdays(DAY, 4) == [date(2026, 10, 2), date(2026, 10, 5)]


def test_job_writes_snapshot_and_reports_failed_dates() -> None:
    def transport(url: str) -> bytes:
        if url.endswith("2026-10-06"):
            raise HttpError(500)
        if url.endswith("2026-10-05"):
            return calendar([("AAPL", "time-after-hours"), ("MSFT", "time-pre-market")])
        return calendar([])

    backend = MemoryBackend()
    write_reference(StoreWriter(backend), DAY, {"AAPL": "EQ:BBG000B9XRY4"})
    source = NasdaqEarningsSource(transport, lambda s: None, RetryPolicy(tries=1))
    reader = StoreReader(backend)
    record = ingest_earnings(task_ctx(StoreWriter(backend), reader, CLOCK), source, DAY, days=5)
    assert record.status is RunStatus.PARTIAL
    assert record.stats["dates_failed"][0].startswith("2026-10-06")
    assert (record.stats["rows"], record.stats["companies"]) == (2, 2)
    events = StoreReader(backend).table("events/earnings", DAY)  # the run's session partition
    assert events is not None
    assert set(events["earnings_date"]) == {date(2026, 10, 5)}
    assert set(events["instrument_id"]) == {"EQ:BBG000B9XRY4", "EQ:MSFT"}  # MSFT: no reference
    assert record.stats["unresolved"] == 1
    assert backend.raw.get("nasdaq_earnings", "earnings_calendar", DAY, record.run_id, "2026-10-05")


def test_quiet_window_is_complete_with_no_rows() -> None:
    source = NasdaqEarningsSource(lambda url: calendar([]), lambda s: None, RetryPolicy(tries=1))
    backend = MemoryBackend()
    record = ingest_earnings(
        task_ctx(StoreWriter(backend), StoreReader(backend), CLOCK), source, DAY, days=2
    )
    assert (record.status, record.stats["rows"]) == (RunStatus.COMPLETE, 0)
