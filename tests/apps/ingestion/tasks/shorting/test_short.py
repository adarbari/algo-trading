"""The ``short-interest`` and ``short-volume`` tasks over hand-built FINRA payloads: one
partition per date, ids resolved (unknown tickers dropped), ``known_from`` by the schedule,
resumable (a stored date is skipped, ``force`` refetches), an unpublished date ``NO_DATA``, a
failed date PARTIAL, and the nightly window defaults."""

from datetime import date

import pytest

from algotrade.data import StoreReader
from algotrade.data.events import ALL_TIME, read_events
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.registry import run_task
from algotrade_ingestion.tasks.shorting import short_interest, short_volume
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.finra.short_interest import FinraShortInterest
from algotrade_sources.vendors.finra.short_volume import FinraShortVolume
from tests.helpers.finra import payloads
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.stored_frames import write_reference

IDS = {"AAA": "EQ:AAA", "BBB": "EQ:BBB"}  # OTCX is not in the universe
SESSION = date(2026, 10, 16)


def _writer() -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    write_reference(writer, date(2026, 10, 2), IDS)
    return writer


def _interest(asked: list[str], missing: set[str] = frozenset(), broken: set[str] = frozenset()):
    def transport(url: str) -> bytes:
        day = url.split("equal.settlementDate=")[1]
        asked.append(day)
        if day in broken:
            raise HttpError(500)
        return b"[]" if day in missing else payloads.short_interest(day)

    return FinraShortInterest(http_for(transport, RetryPolicy(tries=1)))


def _volume(asked: list[str], missing: set[str] = frozenset()):
    def transport(url: str) -> bytes:
        day = url.split("equal.tradeReportDate=")[1]
        asked.append(day)
        return b"[]" if day in missing else payloads.short_volume(day)

    return FinraShortVolume(http_for(transport, RetryPolicy(tries=1)))


def test_settlement_dates_are_the_15th_and_the_last_session() -> None:
    assert short_interest.settlement_dates(date(2026, 8, 1), date(2026, 10, 31)) == [
        date(2026, 8, 14),  # the 15th is a Saturday
        date(2026, 8, 31),
        date(2026, 9, 15),
        date(2026, 9, 30),
        date(2026, 10, 15),
        date(2026, 10, 30),  # the 31st is a Saturday
    ]
    assert short_interest.settlement_dates(date(2026, 9, 16), date(2026, 9, 29)) == []


def test_short_interest_partitions_by_settlement_date_with_known_from() -> None:
    writer, asked = _writer(), []
    ctx = task_ctx(writer, sources={short_interest.SOURCE: _interest(asked)})
    record = run_task("short-interest", ctx, {"session": SESSION, "start": date(2026, 9, 1)})
    assert record.status is RunStatus.COMPLETE
    assert asked == ["2026-09-15", "2026-09-30", "2026-10-15"]
    reader = StoreReader(writer._backend)
    assert reader.dates("events/short_interest") == [
        date(2026, 9, 15),
        date(2026, 9, 30),
        date(2026, 10, 15),
    ]
    assert record.items["2026-09-30"] == "OK: 2 rows"  # OTCX is not in the universe
    assert record.stats["unresolved"] == 3
    rows = read_events(reader, "events/short_interest", *ALL_TIME).frame
    last = rows[rows["ts"] == rows["ts"].max()]
    assert sorted(last["instrument_id"]) == ["EQ:AAA", "EQ:BBB"]
    assert last["published"].iloc[0] == date(2026, 10, 26)
    assert last["known_from"].iloc[0] == date(2026, 10, 27)
    # a read as of the publication date does not see it; the session after does
    as_of = read_events(reader, "events/short_interest", *ALL_TIME, through=date(2026, 10, 26))
    assert date(2026, 10, 15) not in set(as_of.frame["ts"].dt.date)
    later = read_events(reader, "events/short_interest", *ALL_TIME, through=date(2026, 10, 27))
    assert date(2026, 10, 15) in set(later.frame["ts"].dt.date)


def test_a_stored_date_is_not_refetched_unless_forced() -> None:
    writer, asked = _writer(), []
    ctx = task_ctx(writer, sources={short_interest.SOURCE: _interest(asked)})
    params = {"session": SESSION, "start": date(2026, 9, 1), "end": date(2026, 9, 30)}
    short_interest.run(ctx, params)
    assert len(asked) == 2
    again = short_interest.run(ctx, params)
    assert len(asked) == 2 and again.stats["already_stored"] == 2  # first-seen values stay
    short_interest.run(ctx, {**params, "force": True})
    assert len(asked) == 4


def test_an_unpublished_date_is_no_data_and_a_failed_one_partial() -> None:
    asked: list[str] = []
    ctx = task_ctx(
        _writer(),
        sources={
            short_interest.SOURCE: _interest(asked, missing={"2026-10-15"}, broken={"2026-09-30"})
        },
    )
    record = short_interest.run(ctx, {"session": SESSION, "start": date(2026, 9, 1)})
    assert record.items["2026-10-15"] == "NO_DATA"
    assert record.items["2026-09-30"].startswith("FETCH_ERROR")
    assert record.status is RunStatus.PARTIAL
    assert record.items["2026-09-15"].startswith("OK")


def test_short_interest_window_defaults_to_the_lookback() -> None:
    asked: list[str] = []
    ctx = task_ctx(_writer(), sources={short_interest.SOURCE: _interest(asked)})
    record = short_interest.run(ctx, {"session": SESSION})  # 45 calendar days back
    assert record.stats["window"] == ["2026-09-15", "2026-10-15"]


def test_short_volume_partitions_by_trade_date_over_the_sessions() -> None:
    writer, asked = _writer(), []
    ctx = task_ctx(writer, sources={short_volume.SOURCE: _volume(asked, missing={"2026-10-14"})})
    record = run_task(
        "short-volume", ctx, {"session": SESSION, "start": date(2026, 10, 12), "end": SESSION}
    )
    assert asked == ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"]
    assert record.items["2026-10-14"] == "NO_DATA"
    assert record.status is RunStatus.COMPLETE
    reader = StoreReader(writer._backend)
    assert reader.dates("events/short_volume")[-1] == date(2026, 10, 16)
    stored = reader.table("events/short_volume", date(2026, 10, 16))
    assert stored is not None
    assert sorted(stored["instrument_id"]) == ["EQ:AAA", "EQ:BBB"]
    assert set(stored["known_from"]) == {date(2026, 10, 19)}
    assert stored[stored["instrument_id"] == "EQ:AAA"]["short_volume"].iloc[0] == 500
    assert set(stored["source"]) == {"finra_short_volume"}


def test_short_volume_window_defaults_to_the_lookback() -> None:
    ctx = task_ctx(_writer(), sources={short_volume.SOURCE: _volume([])})
    record = short_volume.run(ctx, {"session": SESSION})  # 10 calendar days
    assert record.stats["window"] == ["2026-10-07", "2026-10-16"]


@pytest.mark.parametrize("module", [short_interest, short_volume])
def test_a_session_is_required(module) -> None:
    with pytest.raises(ValueError, match="session"):
        module.run(task_ctx(_writer()), {})
