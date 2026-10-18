"""The ``vx-futures`` task (EB D3): one partition per trade date, known from the next session after
it, only new rows after the first fetch, done expiries not asked again, resumable, the expiry rule
against the dates verified on Cboe's CDN 2026-10-17, and its WARN-only check."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest

from algotrade.data import StoreReader
from algotrade.data.volatility import vx_futures
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.registry import run_task
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance.quality import VX_TASK
from algotrade_ingestion.tasks.market.volatility.vx_futures import (
    STOP_AFTER_FAILED,
    expiry_dates,
    ingest_vx_futures,
    monthly_expiries,
    monthly_expiry,
    nightly_window,
)
from algotrade_ingestion.tasks.market.volatility.vx_futures import TABLE as VX_TABLE
from algotrade_ingestion.tasks.market.volatility.vx_futures import TASK as VX_TASK_NAME
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.cboe.vx_futures import CboeVxFutures
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import cboe as files

VX_DENIED = HttpError(403, body=b"<Error><Code>AccessDenied</Code></Error>")
VX_SESSION = date(2013, 5, 23)
VX_WINDOW = (date(2013, 5, 22), date(2013, 5, 29))  # Wednesdays 05-22 and 05-29
VX_FETCHED = datetime(2013, 5, 23, 23, tzinfo=UTC)


def _vx_source(
    served: dict[str, bytes], urls: list[str], error: Callable[[str], bool] = lambda u: False
) -> CboeVxFutures:
    def transport(url: str) -> bytes:
        urls.append(url)
        if error(url):
            raise HttpError(500)
        name = url.rsplit("VX_", 1)[1].removesuffix(".csv")
        if name not in served:
            raise VX_DENIED
        return served[name]

    policy = RetryPolicy(tries=1, not_found=lambda e: e.status == 403 and b"AccessDenied" in e.body)
    return CboeVxFutures(http_for(transport, policy))


def _vx_ctx(backend: MemoryBackend, clock: datetime = VX_FETCHED) -> TaskContext:
    return task_ctx(StoreWriter(backend), clock=lambda: clock)


def test_backfill_writes_a_partition_per_trade_date_known_from_the_fetch() -> None:
    backend, urls = MemoryBackend(), []
    served = {
        "2013-05-22": files.vx_file("F (Jan 2014)"),
        "2013-05-29": files.vx_file("G (Feb 2014)"),
    }
    record = ingest_vx_futures(_vx_ctx(backend), _vx_source(served, urls), VX_SESSION, *VX_WINDOW)
    assert record.status is RunStatus.COMPLETE
    assert urls == [
        "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_2013-05-22.csv",
        "https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_2013-05-29.csv",
    ]
    assert record.items == {
        "2013-05-22": "OK: 4 rows through 2013-05-22",
        "2013-05-29": "OK: 4 rows through 2013-05-22",
    }
    reader = StoreReader(backend)
    assert reader.dates(VX_TABLE) == [date(2013, 5, d) for d in (15, 20, 21, 22)]
    day = reader.table(VX_TABLE, date(2013, 5, 22))
    assert day is not None and sorted(day["instrument_id"]) == [
        "FUT:VX-20130522",
        "FUT:VX-20130529",
    ]
    assert set(day["source"]) == {"cboe_vx"}
    assert set(day["knowledge_ts"]) == {VX_FETCHED}  # the write instant
    assert set(day["known_from"]) == {date(2013, 5, 23)}  # known from the NEXT session
    assert record.stats["rows"] == 8 and record.stats["latest"] == "2013-05-22"
    assert record.stats["listed"] == 2 and record.stats["sessions_written"] == 4


def test_a_session_reads_only_rows_known_by_it_even_for_a_backfill() -> None:
    backend = MemoryBackend()
    served = {
        "2013-05-22": files.vx_file("F (Jan 2014)"),
        "2013-05-29": files.vx_file("G (Feb 2014)"),
    }
    # a backfill run years later: the rows are still known from the session after their trade date
    late = datetime(2026, 10, 17, 12, tzinfo=UTC)
    ingest_vx_futures(
        _vx_ctx(backend, late), _vx_source(served, []), date(2026, 10, 16), *VX_WINDOW
    )
    reader = StoreReader(backend)
    curve = vx_futures(reader, date(2013, 5, 22), date(2013, 5, 22))
    assert curve["expiry"].tolist() == [date(2013, 5, 22), date(2013, 5, 29)]
    assert curve["settle"].tolist() == [15.75, 15.75]
    # on the trade date itself the settle is not known yet; the next session has it
    on_day = vx_futures(reader, date(2013, 5, 22), date(2013, 5, 22), session=date(2013, 5, 22))
    assert on_day.empty
    nxt = vx_futures(reader, date(2013, 5, 22), date(2013, 5, 22), session=date(2013, 5, 23))
    assert len(nxt) == 2
    # a backtest as_of before the write sees nothing; the table is not hidden from a 2013 session
    assert vx_futures(reader, date(2013, 5, 15), date(2013, 5, 22), as_of=late - timedelta(1)).empty
    assert vx_futures(StoreReader(MemoryBackend()), date(2013, 5, 1), date(2013, 5, 31)).empty


def test_a_forced_restatement_is_known_from_the_session_after_the_fetch() -> None:
    backend = MemoryBackend()
    served = {"2013-05-22": files.vx_file("F (Jan 2014)")}
    ingest_vx_futures(
        _vx_ctx(backend), _vx_source(served, []), VX_SESSION, VX_WINDOW[0], VX_WINDOW[0]
    )
    revised = tuple(
        (d, o, h, lo, c, 16.0 if d == "2013-05-22" else st, ch, v, e, oi)
        for d, o, h, lo, c, st, ch, v, e, oi in files.ROWS
    )
    fetch = datetime(2013, 6, 10, 23, tzinfo=UTC)  # a Monday evening
    record = ingest_vx_futures(
        _vx_ctx(backend, fetch),
        _vx_source({"2013-05-22": files.vx_file("F (Jan 2014)", revised)}, []),
        date(2013, 6, 10),
        VX_WINDOW[0],
        VX_WINDOW[0],
        force=True,
    )
    assert record.items["2013-05-22"] == "OK: 1 rows through 2013-05-22"  # only the changed row
    reader = StoreReader(backend)
    one = (date(2013, 5, 22), date(2013, 5, 22))
    assert vx_futures(reader, *one, session=date(2013, 5, 23))["settle"].tolist() == [15.75]
    assert vx_futures(reader, *one, session=date(2013, 6, 10))["settle"].tolist() == [15.75]
    assert vx_futures(reader, *one, session=date(2013, 6, 11))["settle"].tolist() == [16.0]
    assert vx_futures(reader, *one)["settle"].tolist() == [16.0]


def test_a_never_listed_expiry_is_no_data_and_not_asked_again_once_past() -> None:
    backend, urls = MemoryBackend(), []
    served = {"2013-05-22": files.vx_file("F (Jan 2014)")}
    first = ingest_vx_futures(_vx_ctx(backend), _vx_source(served, urls), VX_SESSION, *VX_WINDOW)
    assert first.items["2013-05-29"] == "NO_DATA" and first.status is RunStatus.COMPLETE
    later = date(2013, 6, 3)  # after both expiries
    asked: list[str] = []
    # 05-22 holds its last row (fetched after it expired); 05-29 was probed BEFORE its expiry, so
    # it may have been listed since: asked once more, then it is known never to have existed.
    ingest_vx_futures(_vx_ctx(backend), _vx_source(served, asked), later, *VX_WINDOW)
    assert [u[-14:] for u in asked] == ["2013-05-29.csv"]
    asked.clear()
    again = ingest_vx_futures(_vx_ctx(backend), _vx_source(served, asked), later, *VX_WINDOW)
    assert asked == [] and set(again.items.values()) == {"NOT_DUE"}
    redo = ingest_vx_futures(
        _vx_ctx(backend), _vx_source(served, asked), later, *VX_WINDOW, force=True
    )
    assert (
        len(asked) == 2 and redo.items["2013-05-22"] == "OK: 0 rows through 2013-05-22"
    )  # unchanged: not rewritten


def test_an_expiry_not_yet_past_is_asked_again_and_only_new_rows_are_written() -> None:
    backend = MemoryBackend()
    short = files.ROWS[:3]
    ingest_vx_futures(
        _vx_ctx(backend),
        _vx_source({"2013-05-22": files.vx_file("F (Jan 2014)", short)}, []),
        date(2013, 5, 21),
        date(2013, 5, 22),
        date(2013, 5, 22),
    )
    stored = StoreReader(backend).dates(VX_TABLE)
    assert stored[-1] == date(2013, 5, 21)
    night = datetime(2013, 5, 23, 23, tzinfo=UTC)
    second = ingest_vx_futures(
        _vx_ctx(backend, night),
        _vx_source({"2013-05-22": files.vx_file("F (Jan 2014)")}, []),
        date(2013, 5, 22),  # the session is not after the expiry: the file is asked for again
        date(2013, 5, 22),
        date(2013, 5, 22),
    )
    assert second.items == {"2013-05-22": "OK: 1 rows through 2013-05-22"}
    rows = StoreReader(backend).table(VX_TABLE, date(2013, 5, 22))
    assert rows is not None and set(rows["knowledge_ts"]) == {night}
    old = StoreReader(backend).table(VX_TABLE, date(2013, 5, 21))
    assert old is not None and set(old["knowledge_ts"]) == {VX_FETCHED}  # never restated


def test_a_forced_restatement_may_change_a_count_between_na_and_a_value() -> None:
    backend = MemoryBackend()
    day = date(2013, 5, 22)
    na = b"\n".join([files.VX_HEADER.encode(), b"2013-05-22,F (Jan 2014),1,1,1,1,15.0,0,5,0,"])
    full = na + b"7\n"
    ingest_vx_futures(
        _vx_ctx(backend), _vx_source({"2013-05-22": na + b"\n"}, []), VX_SESSION, day, day
    )
    fetch = datetime(2013, 6, 10, 23, tzinfo=UTC)
    for payload, changed in ((full, True), (na + b"\n", True)):
        record = ingest_vx_futures(
            _vx_ctx(backend, fetch),
            _vx_source({"2013-05-22": payload}, []),
            date(2013, 6, 10),
            day,
            day,
            force=True,
        )
        assert record.status is RunStatus.COMPLETE and changed
        assert record.items["2013-05-22"] == "OK: 1 rows through 2013-05-22"
        fetch += timedelta(days=1)


def test_fetch_errors_make_the_run_partial_and_stop_after_a_streak() -> None:
    urls: list[str] = []
    record = ingest_vx_futures(
        _vx_ctx(MemoryBackend()),
        _vx_source({}, urls, error=lambda u: True),
        VX_SESSION,
        date(2013, 1, 1),
        date(2013, 12, 31),
    )
    assert record.status is RunStatus.PARTIAL
    assert len(urls) == STOP_AFTER_FAILED and record.stats["listed"] == 0
    assert any("in a row" in reason for reason in record.stats["partial"])


def test_a_resumed_run_keeps_its_finished_items_and_refetches_the_failed() -> None:
    backend, urls = MemoryBackend(), []
    served = {
        "2013-05-22": files.vx_file("F (Jan 2014)"),
        "2013-05-29": files.vx_file("G (Feb 2014)"),
    }
    first = ingest_vx_futures(
        _vx_ctx(backend),
        _vx_source(served, urls, error=lambda u: "05-29" in u),
        VX_SESSION,
        *VX_WINDOW,
    )
    assert first.status is RunStatus.PARTIAL and first.items["2013-05-29"].startswith("FETCH_ERROR")
    urls.clear()
    second = ingest_vx_futures(_vx_ctx(backend), _vx_source(served, urls), VX_SESSION, *VX_WINDOW)
    assert [u[-14:] for u in urls] == ["2013-05-29.csv"]
    assert second.items["2013-05-29"].startswith("OK: 4 rows")
    assert StoreReader(backend).dates(VX_TABLE) == [date(2013, 5, d) for d in (15, 20, 21, 22)]


def test_the_window_is_checked_and_the_nightly_window_looks_back_and_ahead() -> None:
    with pytest.raises(ValueError, match="empty window"):
        ingest_vx_futures(
            _vx_ctx(MemoryBackend()),
            _vx_source({}, []),
            VX_SESSION,
            date(2013, 6, 1),
            date(2013, 5, 1),
        )
    start, end = nightly_window(date(2026, 10, 16))
    assert start == date(2026, 10, 9) and end > date(2027, 7, 1)


def test_the_cli_task_runs_the_nightly_window_from_the_session() -> None:
    backend, urls = MemoryBackend(), []
    ctx = task_ctx(StoreWriter(backend), sources={"cboe_vx": _vx_source({}, urls)})
    record = run_task("vx-futures", ctx, {"session": date(2026, 10, 16)})
    assert record.job == VX_TASK_NAME and record.status is RunStatus.COMPLETE
    assert any("VX_2026-11-18.csv" in u for u in urls)  # the November monthly is in the window
    assert any("VX_2026-10-21.csv" in u for u in urls)  # a weekly inside the weekly horizon
    assert not any("VX_2026-12-30.csv" in u for u in urls)  # a far weekly is not listed yet
    assert not any("VX_2027-10" in u for u in urls)  # beyond the monthly horizon


@pytest.mark.parametrize(
    ("year", "month", "expiry"),
    [
        (2013, 1, date(2013, 1, 16)),  # 30 days before Friday 2013-02-15
        (2025, 1, date(2025, 1, 22)),
        (2026, 11, date(2026, 11, 18)),
        (2014, 3, date(2014, 3, 18)),  # Good Friday 2014-04-18: 30 days before the Thursday
        (2024, 6, date(2024, 6, 18)),  # the Wednesday, Juneteenth, is a holiday: the Tuesday
        (2013, 12, date(2013, 12, 18)),  # the next month is January of the next year
    ],
)
def test_monthly_expiry_follows_the_settlement_rule(year: int, month: int, expiry: date) -> None:
    assert monthly_expiry(year, month) == expiry
    assert monthly_expiry(year, month).weekday() in (1, 2)  # a Tuesday only around a holiday


def test_expiries_are_the_monthlies_plus_the_wednesdays_on_sessions() -> None:
    days = expiry_dates(date(2013, 1, 1), date(2013, 2, 28))
    assert days[:3] == [date(2013, 1, 2), date(2013, 1, 9), date(2013, 1, 16)]
    assert date(2013, 2, 13) in days and len(days) == 9
    assert expiry_dates(date(2024, 6, 12), date(2024, 6, 26)) == [
        date(2024, 6, 12),
        date(2024, 6, 18),  # Juneteenth (Wednesday): the session before, once, not twice
        date(2024, 6, 26),
    ]


def test_weeklies_stop_at_the_horizon_but_monthlies_do_not() -> None:
    days = expiry_dates(date(2026, 10, 14), date(2027, 1, 31), weeklies_until=date(2026, 10, 28))
    assert days[:3] == [date(2026, 10, 14), date(2026, 10, 21), date(2026, 10, 28)]
    assert days[3:] == [date(2026, 11, 18), date(2026, 12, 16), date(2027, 1, 20)]
    assert monthly_expiries(date(2026, 11, 1), date(2026, 11, 30)) == [date(2026, 11, 18)]


def test_the_range_since_2013_has_one_expiry_per_wednesday() -> None:
    days = expiry_dates(date(2013, 1, 1), date(2026, 11, 30))
    assert len(days) == len(set(days)) == 731 and days[0] == date(2013, 1, 2)


def test_the_quality_check_reads_the_run_records_this_task_writes() -> None:
    assert VX_TASK == VX_TASK_NAME
