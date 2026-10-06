from datetime import UTC, date, datetime

import pytest

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.market.earnings import (
    backfill_earnings,
    ingest_earnings,
    report_days,
)
from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.nasdaq.earnings import NasdaqEarningsSource, parse_calendar
from tests.helpers.ingest_fakes import CountingLimiter, http_for, task_ctx
from tests.helpers.payloads.nasdaq_earnings import calendar
from tests.helpers.stored_frames import write_reference

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


def test_source_waits_on_the_shared_limiter() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()
    transport = lambda url: urls.append(url) or calendar([("A", "x")])  # noqa: E731
    source = NasdaqEarningsSource(http_for(transport, RetryPolicy(tries=1), limiter))
    payload = source.fetch(FetchRequest("2026-10-05"))
    assert urls == ["https://api.nasdaq.com/api/calendar/earnings?date=2026-10-05"]
    assert limiter.waits == 1
    normalized = source.normalize(FetchRequest("2026-10-05"), payload or b"")
    assert normalized is not None and normalized.session_date == date(2026, 10, 5)


def test_report_days_are_exchange_sessions() -> None:
    assert report_days(DAY, 4) == [date(2026, 10, 2), date(2026, 10, 5)]
    assert report_days(date(2026, 11, 25), 3) == [date(2026, 11, 25), date(2026, 11, 27)]


def test_job_writes_snapshot_and_reports_failed_dates() -> None:
    def transport(url: str) -> bytes:
        if url.endswith("2026-10-06"):
            raise HttpError(500)
        if url.endswith("2026-10-05"):
            return calendar([("AAPL", "time-after-hours"), ("MSFT", "time-pre-market")])
        return calendar([])

    backend = MemoryBackend()
    write_reference(StoreWriter(backend), DAY, {"AAPL": "EQ:BBG000B9XRY4"})
    source = NasdaqEarningsSource(http_for(transport, RetryPolicy(tries=1)))
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
    source = NasdaqEarningsSource(http_for(lambda url: calendar([]), RetryPolicy(tries=1)))
    backend = MemoryBackend()
    record = ingest_earnings(
        task_ctx(StoreWriter(backend), StoreReader(backend), CLOCK), source, DAY, days=2
    )
    assert (record.status, record.stats["rows"]) == (RunStatus.COMPLETE, 0)


def test_each_row_is_known_from_the_earlier_of_the_session_and_its_report_date() -> None:
    def transport(url: str) -> bytes:
        return calendar([("AAPL", "time-after-hours")], reported=url.endswith("2026-09-30"))

    backend = MemoryBackend()
    source = NasdaqEarningsSource(http_for(transport, RetryPolicy(tries=1)))
    ctx = task_ctx(StoreWriter(backend), StoreReader(backend), CLOCK)
    ingest_earnings(ctx, source, DAY, date(2026, 9, 30), days=6)
    events = StoreReader(backend).table("events/earnings", DAY)
    assert events is not None
    known = dict(zip(events["earnings_date"], events["known_from"], strict=True))
    assert known == {
        date(2026, 9, 30): date(2026, 9, 30),  # last week's result: knowable on its date
        date(2026, 10, 1): date(2026, 10, 1),
        date(2026, 10, 2): DAY,
        date(2026, 10, 5): DAY,  # a forward row: known on the session that stored it
    }


def test_backfill_is_known_from_each_report_date_and_resumes() -> None:
    asked: list[str] = []
    broken = {"2026-09-29"}

    def transport(url: str) -> bytes:
        day = url.rsplit("=", 1)[1]
        asked.append(day)
        if day in broken:
            raise HttpError(500)
        return calendar([("AAPL", "time-pre-market")], reported=True)

    backend = MemoryBackend()
    writer = StoreWriter(backend)
    write_reference(writer, DAY, {"AAPL": "EQ:BBG000B9XRY4"})
    source = NasdaqEarningsSource(http_for(transport, RetryPolicy(tries=1)))
    ctx = task_ctx(writer, StoreReader(backend), CLOCK)
    first = backfill_earnings(ctx, source, DAY, date(2026, 9, 28), date(2026, 10, 1))
    assert first.status is RunStatus.PARTIAL and first.stats["fetched"] == 4
    assert first.stats["dates_failed"][0].startswith("2026-09-29")
    broken.clear()
    asked.clear()
    resumed = backfill_earnings(ctx, source, DAY, date(2026, 9, 28), date(2026, 10, 1))
    assert (resumed.run_id, resumed.status, asked) == (
        first.run_id,
        RunStatus.COMPLETE,
        ["2026-09-29"],
    )
    events = StoreReader(backend).table("events/earnings", DAY)  # the run session's partition
    assert events is not None
    assert list(events["known_from"]) == list(events["earnings_date"])  # each its report date
    assert len(events) == 4 and set(events["instrument_id"]) == {"EQ:BBG000B9XRY4"}
    assert resumed.stats["pre_snapshot_rows"] == 1  # before the 10-02 reference snapshot
    later = backfill_earnings(ctx, source, date(2026, 10, 5), date(2026, 9, 28), date(2026, 10, 2))
    assert len(asked) == 6 and later.stats["already_done"] == 0  # a new session: the window
    assert later.stats["pre_snapshot_rows"] == 4  # 10-02 resolves through its own snapshot
    with pytest.raises(ValueError, match="after"):
        backfill_earnings(ctx, source, DAY, date(2026, 10, 1), date(2026, 9, 1))


def test_a_failed_day_carries_the_previous_forecasts_forward() -> None:
    """A failed fetch never cancels knowledge (ADR 0050): the previous snapshot's rows for the
    day are stored again with ``carried_from``, and ``earnings@v1`` keeps the date."""
    from algotrade.features.framework.runner import compute_one  # noqa: PLC0415
    from algotrade.features.rollups.corporate.earnings import GROUP  # noqa: PLC0415

    report, failing = date(2026, 10, 6), {"on": False}

    def transport(url: str) -> bytes:
        if url.endswith(report.isoformat()):
            if failing["on"]:
                raise HttpError(500)
            return calendar([("AAPL", "time-after-hours")])
        return calendar([("MSFT", "time-pre-market")])

    backend = MemoryBackend()
    writer = StoreWriter(backend)
    write_reference(writer, date(2026, 10, 1), {"AAPL": "EQ:BBG000B9XRY4"})
    source = NasdaqEarningsSource(http_for(transport, RetryPolicy(tries=1)))
    ctx = task_ctx(writer, StoreReader(backend), CLOCK)
    ingest_earnings(ctx, source, date(2026, 10, 1), days=8)
    failing["on"] = True
    second = ingest_earnings(ctx, source, DAY, days=8)
    assert second.status is RunStatus.PARTIAL
    assert (second.stats["carried_rows"], second.stats["carried_days"]) == (1, ["2026-10-06"])
    stored = StoreReader(backend).table("events/earnings", DAY)
    assert stored is not None
    aapl = stored[stored["instrument_id"] == "EQ:BBG000B9XRY4"].iloc[0]
    assert (aapl["carried_from"], aapl["known_from"]) == (date(2026, 10, 1), date(2026, 10, 1))
    assert stored[stored["instrument_id"] != "EQ:BBG000B9XRY4"]["carried_from"].isna().all()
    third = ingest_earnings(ctx, source, date(2026, 10, 5), days=8)  # fails again
    again = StoreReader(backend).table("events/earnings", date(2026, 10, 5))
    assert third.stats["carried_rows"] == 1 and again is not None
    carried = again[again["instrument_id"] == "EQ:BBG000B9XRY4"].iloc[0]
    assert carried["carried_from"] == date(2026, 10, 1)  # the session that fetched it
    frame = compute_one(StoreReader(backend), GROUP, date(2026, 10, 5)).frame
    assert frame is not None
    row = frame.set_index("instrument_id").loc["EQ:BBG000B9XRY4"]
    assert row["next_earnings_date"] == report  # the failed day cancelled nothing


def test_a_ticker_that_no_longer_resolves_keeps_its_previous_row() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    write_reference(writer, date(2026, 10, 1), {"AAPL": "EQ:BBG000B9XRY4"})
    source = NasdaqEarningsSource(
        http_for(lambda url: calendar([("AAPL", "time-after-hours")]), RetryPolicy(tries=1))
    )
    ctx = task_ctx(writer, StoreReader(backend), CLOCK)
    ingest_earnings(ctx, source, date(2026, 10, 1), days=2)
    write_reference(writer, DAY, {"OTHER": "EQ:BBG000OTHER0"}, run_id="ref2")  # AAPL gone
    record = ingest_earnings(ctx, source, DAY, start=date(2026, 10, 1), days=2)
    stored = StoreReader(backend).table("events/earnings", DAY)
    assert stored is not None and record.stats["carried_rows"] == 2  # 10-01 and 10-02
    old = stored[stored["instrument_id"] == "EQ:BBG000B9XRY4"]
    assert list(old["carried_from"]) == [date(2026, 10, 1)] * 2
    assert "EQ:AAPL" in set(stored["instrument_id"])  # today's unresolved row is kept too


def test_a_failed_backfill_day_carries_the_previous_forecasts_until_retried() -> None:
    broken = {"on": False}

    def transport(url: str) -> bytes:
        if url.endswith("2026-09-29") and broken["on"]:
            raise HttpError(500)
        return calendar([("AAPL", "time-pre-market")])

    backend = MemoryBackend()
    writer = StoreWriter(backend)
    source = NasdaqEarningsSource(http_for(transport, RetryPolicy(tries=1)))
    ctx = task_ctx(writer, StoreReader(backend), CLOCK)
    ingest_earnings(ctx, source, date(2026, 9, 28), days=3)  # the calendar knew 09-29
    broken["on"] = True
    first = backfill_earnings(ctx, source, DAY, date(2026, 9, 29), date(2026, 9, 30))
    assert first.stats["carried_rows"] == 1
    stored = StoreReader(backend).table("events/earnings", DAY)
    assert stored is not None and list(stored["carried_from"].dropna()) == [date(2026, 9, 28)]
    broken["on"] = False
    backfill_earnings(ctx, source, DAY, date(2026, 9, 29), date(2026, 9, 30))  # the resume
    stored = StoreReader(backend).table("events/earnings", DAY)
    assert stored is not None and len(stored) == 2  # 09-29 fetched, replacing the carried row
    assert "carried_from" not in stored.columns or stored["carried_from"].isna().all()
