"""The delisted-details task (ADR 0087, PR3b): which Massive-only rows it asks for and in what
order, the marker for a name Massive does not know, increments that are never asked again,
``--limit``, resume, and the run's failure rule. The source is the real adapter on synthetic
answers (the BBBY shape)."""

import itertools
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.data.listings.delisted import read_delisted_details
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.listings.delisted_details import (
    TABLE,
    due_records,
    ingest_delisted_details,
    request_key,
)
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.massive.details import MassiveTickerDetails
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import massive as fx
from tests.helpers.stored_frames import stamped

DAY = date(2026, 11, 3)
NOW = datetime(2026, 11, 3, 22, tzinfo=UTC)
LISTING = "instruments/listing_history"


def row(ticker: str, end: str | None, kind: str | None = "COMMON_STOCK", **more: object) -> dict:
    base = {
        "source": "massive", "ticker": ticker, "exchange": "NYSE", "asset_type": "Stock",
        "start_date": None, "end_date": date.fromisoformat(end) if end else None,
        "security_type": kind, "no_id_reason": "no_start", "scope_reason": None,
        "ts": pd.Timestamp(DAY, tz="UTC"),
    }  # fmt: skip
    return {**base, **more}


def context(*rows: dict) -> TaskContext:
    writer = StoreWriter(MemoryBackend())
    frame = stamped(list(rows), DAY, "h")
    frame["source"] = [r["source"] for r in rows]  # each row's own vendor
    writer.write_table(LISTING, DAY, "h", frame, pending=False)
    ticks = itertools.count()  # each call a second later: runs of one session get their own id
    return task_ctx(writer, clock=lambda: NOW + timedelta(seconds=next(ticks)))


class Massive:
    """The source over answers by ticker (a missing ticker answers 404, ``None`` entry fails
    with a server error); remembers every URL it was asked."""

    def __init__(self, answers: dict[str, bytes | None]) -> None:
        self.answers, self.urls = answers, []

    def __call__(self) -> MassiveTickerDetails:
        def transport(url: str) -> bytes:
            self.urls.append(url)
            ticker = url.rsplit("/", maxsplit=1)[-1].split("?", maxsplit=1)[0]
            if ticker not in self.answers:
                raise HttpError(404)
            answer = self.answers[ticker]
            if answer is None:
                raise HttpError(500)
            return answer

        return MassiveTickerDetails(http_for(transport, RetryPolicy(tries=1)))


def asked(massive: Massive) -> list[str]:
    return [u.split("/")[-1].split("?")[0] for u in massive.urls]


def test_it_asks_stock_types_first_then_no_type_then_the_rest_newest_end_first() -> None:
    listings = pd.DataFrame(
        [
            row("ETFA", "2024-01-05", "ETF"),
            row("OLDS", "2015-03-02"),
            row("NOTY", "2023-07-01", None),
            row("NEWS", "2022-02-02", "ADR"),
            row("NEWR", "2024-06-03"),
        ]
    )
    assert [t for t, _ in due_records(listings, pd.DataFrame())] == [
        "NEWR", "NEWS", "OLDS", "NOTY", "ETFA",
    ]  # fmt: skip


def test_only_the_massive_rows_a_start_can_still_lift_are_due() -> None:
    listings = pd.DataFrame(
        [
            row("OK1", "2020-01-02"),
            row("OK2", "2020-01-02", no_id_reason="perma_ambiguous"),
            row("OK3", "2020-01-02", no_id_reason="no_meta"),
            row("AMB", "2020-01-02", no_id_reason="pair_ambiguous"),
            row("OVL", "2020-01-02", no_id_reason="overlaps_listing"),
            row("DATED", "2020-01-02", start_date=date(2001, 1, 2), no_id_reason=None),
            row("NOEND", None),
            row("TIINGO", "2020-01-02", source="tiingo"),
        ]
    )
    assert {t for t, _ in due_records(listings, pd.DataFrame())} == {"OK1", "OK2", "OK3"}


def test_an_answer_is_stored_with_every_field_and_a_404_as_a_marker() -> None:
    ctx = context(row("BBBY", "2023-05-02"), row("GHOST", "2019-01-02"))
    massive = Massive({"BBBY": fx.ticker_details("BBBY")})
    record = ingest_delisted_details(ctx, massive(), DAY)
    assert record.status is RunStatus.COMPLETE
    stats = record.stats
    assert (stats["asked"], stats["found"], stats["not_found"], stats["failed"]) == (2, 1, 1, 0)
    assert stats["remaining"] == 0 and stats["due"] == 2
    stored = read_delisted_details(ctx.reader).set_index("ticker")
    assert request_key("BBBY", date(2023, 5, 2)) == "BBBY|2023-05-02"
    assert asked(massive) == ["BBBY", "GHOST"]
    assert "date=2023-05-02" in massive.urls[0]  # asked at the record's last day
    bbby = stored.loc["BBBY"]
    assert bool(bbby["found"]) and bbby["list_date"] == date(1992, 6, 4)
    assert (bbby["cik"], bbby["figi"], bbby["asked_date"]) == ("0000886158", "BBG000BB5R87", DAY)
    assert bbby["delisted_date"] == date(2023, 5, 2) and bbby["end_date"] == date(2023, 5, 2)
    ghost = stored.loc["GHOST"]
    assert not bool(ghost["found"]) and pd.isna(ghost["list_date"])  # the marker
    assert set(stored["source"]) == {"massive"} and TABLE == "instruments/delisted_details"


def test_a_name_already_stored_is_never_asked_again_found_or_not() -> None:
    ctx = context(row("BBBY", "2023-05-02"), row("GHOST", "2019-01-02"), row("NEW", "2024-01-02"))
    first = Massive({"BBBY": fx.ticker_details("BBBY")})
    ingest_delisted_details(ctx, first(), DAY, limit=2)
    assert asked(first) == ["NEW", "BBBY"]
    again = Massive({"NEW": fx.ticker_details("NEW"), "BBBY": fx.ticker_details("BBBY")})
    record = ingest_delisted_details(ctx, again(), DAY)
    assert asked(again) == ["GHOST"] and record.stats["asked"] == 1  # only the one never asked
    assert len(read_delisted_details(ctx.reader)) == 3  # the union of both runs
    third = Massive({})
    assert ingest_delisted_details(ctx, third(), DAY).stats["due"] == 0 and third.urls == []


def test_limit_caps_the_requests_and_reports_the_rest() -> None:
    ctx = context(*(row(f"T{i}", f"2020-0{i}-02") for i in range(1, 6)))
    massive = Massive({f"T{i}": fx.ticker_details(f"T{i}") for i in range(1, 6)})
    record = ingest_delisted_details(ctx, massive(), DAY, limit=2)
    assert asked(massive) == ["T5", "T4"] and record.stats["asked"] == 2  # newest first
    assert (record.stats["due"], record.stats["remaining"]) == (5, 3)


def test_a_failed_request_is_an_item_not_a_marker_and_is_asked_again() -> None:
    ctx = context(row("BBBY", "2023-05-02"), row("BOOM", "2022-01-03"))
    massive = Massive({"BBBY": fx.ticker_details("BBBY"), "BOOM": None})
    record = ingest_delisted_details(ctx, massive(), DAY)
    assert record.status is RunStatus.PARTIAL and record.stats["failed"] == 1
    assert record.stats["remaining"] == 1
    assert list(read_delisted_details(ctx.reader)["ticker"]) == ["BBBY"]  # no marker for BOOM
    again = Massive({"BOOM": fx.ticker_details("BOOM")})
    ingest_delisted_details(ctx, again(), DAY)
    assert asked(again) == ["BOOM"]


def test_the_run_fails_only_when_every_request_failed() -> None:
    ctx = context(row("A", "2023-05-02"), row("B", "2022-01-03"))
    record = ingest_delisted_details(ctx, Massive({"A": None, "B": None})(), DAY)
    assert record.status is RunStatus.FAILED and record.stats["failed"] == 2
    assert read_delisted_details(ctx.reader).empty


def test_an_unfinished_run_is_resumed_without_asking_its_names_again() -> None:
    ctx = context(row("A", "2023-05-02"), row("B", "2022-01-03"))
    boom = Massive({"A": fx.ticker_details("A"), "B": None})
    ingest_delisted_details(ctx, boom(), DAY)  # A fetched, B failed: PARTIAL, retryable
    rerun = Massive({"B": fx.ticker_details("B")})
    record = ingest_delisted_details(ctx, rerun(), DAY)
    assert asked(rerun) == ["B"] and record.status is RunStatus.COMPLETE
    assert sorted(read_delisted_details(ctx.reader)["ticker"]) == ["A", "B"]


def test_no_listing_history_fails_the_run() -> None:
    ctx = task_ctx(StoreWriter(MemoryBackend()), clock=lambda: NOW)
    record = ingest_delisted_details(ctx, Massive({})(), DAY)
    assert record.status is RunStatus.FAILED


@pytest.mark.parametrize("limit", [0])
def test_limit_zero_asks_nothing(limit: int) -> None:
    ctx = context(row("A", "2023-05-02"))
    massive = Massive({"A": fx.ticker_details("A")})
    assert ingest_delisted_details(ctx, massive(), DAY, limit).stats["asked"] == 0
    assert massive.urls == []
