"""The ``short-interest`` and ``short-volume`` tasks over hand-built FINRA payloads: one
partition per date, ids resolved (unknown tickers dropped), ``known_from`` by the schedule,
resumable (a stored date is skipped, ``force`` refetches), an unpublished date ``NO_DATA``, a
failed date PARTIAL, and the nightly window defaults."""

import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.data.events import ALL_TIME, read_events
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.registry import run_task
from algotrade_ingestion.tasks.shorting import short_interest, short_volume
from algotrade_ingestion.tasks.shorting.daily import row_known_from
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


def _clock() -> datetime:
    return datetime(2026, 11, 20, 22, tzinfo=UTC)  # a Friday evening in New York


FETCH_FLOOR = date(2026, 11, 23)  # the session after that fetch


def _interest_known(writer: StoreWriter, settlement: date) -> dict[str, date]:
    frame = StoreReader(writer._backend).table("events/short_interest", settlement)
    assert frame is not None
    return dict(zip(frame["instrument_id"], frame["known_from"], strict=True))


def _fetch_interest(
    writer: StoreWriter, settlement: date, later: bool = False, **params: object
) -> None:
    def clock() -> datetime:
        return _clock() + timedelta(seconds=2 if later else 0)  # a later run id wins the merge

    ctx = task_ctx(writer, clock=clock, sources={short_interest.SOURCE: _interest([])})
    short_interest.run(
        ctx,
        {"session": date(2026, 11, 20), "start": settlement, "end": settlement, **params},
    )


def test_a_backfilled_report_is_known_from_its_publication_not_the_fetch() -> None:
    """The bug of 2026-10-19: a backfill stamped every past report known_from the session after
    the fetch, so rollups short_interest@v1 was empty for every session before it. A report
    FINRA does not flag as revised is known from the schedule's date; a flagged one (OTCX, not
    in the universe, so BBB is made flagged below) only from the session after the fetch."""
    writer = _writer()
    _fetch_interest(writer, date(2026, 9, 30))
    known = _interest_known(writer, date(2026, 9, 30))
    assert set(known.values()) == {date(2026, 10, 12)}  # the schedule's date, not the fetch's
    ctx = task_ctx(writer, clock=_clock, sources={short_volume.SOURCE: _volume([])})
    short_volume.run(
        ctx, {"session": date(2026, 11, 20), "start": date(2026, 10, 16), "end": date(2026, 10, 16)}
    )
    volume = StoreReader(writer._backend).table("events/short_volume", date(2026, 10, 16))
    assert volume is not None and set(volume["known_from"]) == {date(2026, 10, 19)}


def _row(**values: object) -> pd.DataFrame:
    base = {
        "instrument_id": "EQ:AAA",
        "ts": pd.Timestamp("2026-09-30", tz="UTC"),
        "short_position": 5,
    }
    return pd.DataFrame([{**base, **values}])


SCHED = date(2026, 10, 12)


def _stored(known_from: date, **values: object) -> pd.DataFrame:
    return _row(known_from=known_from, published=date(2026, 10, 9), **values)


@pytest.mark.parametrize(
    ("row", "stored", "expected"),
    [
        (_row(revision_flag=None), None, SCHED),  # never stored, unflagged
        (_row(revision_flag=" "), None, SCHED),  # a blank flag is no flag
        (_row(revision_flag="R"), None, FETCH_FLOOR),  # flagged: when restated is unknown
        (_row(), _stored(FETCH_FLOOR), SCHED),  # stored identical unflagged: restamped earlier
        (_row(), _stored(date(2026, 10, 8)), date(2026, 10, 8)),  # never later than stored
        (_row(revision_flag="R"), _stored(FETCH_FLOOR, revision_flag="R"), FETCH_FLOOR),
        (_row(short_position=6), _stored(date(2026, 10, 12)), FETCH_FLOOR),  # restated value
    ],
)
def test_row_known_from_rule(
    row: pd.DataFrame, stored: pd.DataFrame | None, expected: date
) -> None:
    assert row_known_from(row, SCHED, FETCH_FLOOR, stored).iloc[0] == expected


def test_a_forced_refetch_restamps_rows_stamped_by_the_old_rule() -> None:
    """The live-store repair: partitions stamped with the fetch session by the old rule move to
    the schedule's date when forced again and their values are unchanged."""
    writer = _writer()
    _fetch_interest(writer, date(2026, 9, 30))
    frame = StoreReader(writer._backend).table("events/short_interest", date(2026, 9, 30))
    assert frame is not None
    old = frame.assign(known_from=FETCH_FLOOR)
    writer.write_table(
        "events/short_interest",
        date(2026, 9, 30),
        "short-interest-2026-11-20-20261120T220001Z",
        old,
        restates=True,
    )
    assert set(_interest_known(writer, date(2026, 9, 30)).values()) == {FETCH_FLOOR}
    _fetch_interest(writer, date(2026, 9, 30), later=True, force=True)
    assert set(_interest_known(writer, date(2026, 9, 30)).values()) == {date(2026, 10, 12)}


def test_backfilled_dates_resolve_against_their_own_reference() -> None:
    """The reference snapshot of the date, not today's: a name listed only later is not resolved
    for an earlier date."""
    writer = StoreWriter(MemoryBackend())
    write_reference(writer, date(2026, 10, 2), {"AAA": "EQ:AAA"})
    write_reference(writer, date(2026, 10, 14), IDS, "ref2")
    ctx = task_ctx(writer, sources={short_volume.SOURCE: _volume([])})
    short_volume.run(ctx, {"session": SESSION, "start": date(2026, 10, 9), "end": SESSION})
    reader = StoreReader(writer._backend)
    early = reader.table("events/short_volume", date(2026, 10, 9))
    late = reader.table("events/short_volume", date(2026, 10, 15))
    assert early is not None and late is not None
    assert sorted(early["instrument_id"]) == ["EQ:AAA"]
    assert sorted(late["instrument_id"]) == ["EQ:AAA", "EQ:BBB"]


def test_a_ticker_whose_case_differs_from_the_reference_is_dropped_and_counted() -> None:
    """FINRA lists ``TpC`` beside ``TPC`` (2026-10-16: 4 rows, 2 ids); the resolver reads both as
    one id and the table key held one row: the first run failed ``duplicate rows for the table
    key`` on 250 of 251 days. The lowercase series is a different security: dropped, counted."""

    def row(symbol: str, facility: str, short: int, total: int) -> dict:
        return {
            "tradeReportDate": "2026-10-16",
            "securitiesInformationProcessorSymbolIdentifier": symbol,
            "shortParQuantity": short,
            "shortExemptParQuantity": 0,
            "totalParQuantity": total,
            "reportingFacilityCode": facility,
        }

    rows = [row("AAA", "NQTRF", 400, 1000), row("AAa", "ADF", 30, 90), row("BBB", "ADF", 10, 40)]
    source = FinraShortVolume(http_for(lambda url: json.dumps(rows).encode(), RetryPolicy(tries=1)))
    writer = _writer()
    ctx = task_ctx(writer, sources={short_volume.SOURCE: source})
    record = run_task("short-volume", ctx, {"session": SESSION, "start": SESSION, "end": SESSION})
    assert record.status is RunStatus.COMPLETE and record.items["2026-10-16"] == "OK: 2 rows"
    assert record.stats["unresolved"] == 1
    stored = StoreReader(writer._backend).table("events/short_volume", SESSION)
    assert stored is not None and sorted(stored["instrument_id"]) == ["EQ:AAA", "EQ:BBB"]
    aaa = stored[stored["instrument_id"] == "EQ:AAA"].iloc[0]
    assert (aaa["short_volume"], aaa["total_volume"], aaa["facilities"]) == (400, 1000, 1)
