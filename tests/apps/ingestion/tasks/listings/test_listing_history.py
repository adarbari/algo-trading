"""The listing-history task on the RECORDED supported-tickers slice: one snapshot per session,
ids only from symbol_history or a permaTicker, never ``EQ:<symbol>`` (ADR 0018 amendment)."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data.listings.universe import universe_asof
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.listings.index_membership import ingest_index_membership
from algotrade_ingestion.tasks.listings.listing_history import (
    ingest_listing_history,
)
from algotrade_ingestion.tasks.reference.instrument_ids import assign_listing_ids
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sp500_history.membership import Sp500Membership
from algotrade_sources.vendors.tiingo.listings import TiingoSupportedTickers
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import published as sp500
from tests.helpers.payloads import tiingo as payloads
from tests.helpers.stored_frames import stamped

DAY = date(2026, 10, 5)
CLOCK = lambda: datetime(2026, 10, 5, 22, tzinfo=UTC)  # noqa: E731


def source(payload: bytes | None = None) -> TiingoSupportedTickers:
    def transport(url: str) -> bytes:
        if payload is None:
            raise HttpError(404)
        return payload

    return TiingoSupportedTickers(http_for(transport, RetryPolicy(tries=1)))


def test_task_writes_a_snapshot_and_ids_come_only_from_symbol_history() -> None:
    writer = StoreWriter(MemoryBackend())
    history = [
        {"instrument_id": "EQ:BBG000AAPL", "ts": pd.Timestamp(DAY, tz="UTC"),
         "figi": "BBG000AAPL", "symbol": "AAPL", "valid_from": date(1999, 1, 4), "valid_to": None},
        {"instrument_id": "EQ:BBG000AAC", "ts": pd.Timestamp(DAY, tz="UTC"),
         "figi": "BBG000AAC", "symbol": "AAC", "valid_from": date(2026, 8, 1), "valid_to": None},
    ]  # fmt: skip
    writer.write_table(
        "instruments/symbol_history", DAY, "h", stamped(history, DAY, "h"), pending=False
    )
    ctx = task_ctx(writer, clock=CLOCK)
    record = ingest_listing_history(ctx, source(payloads.supported_tickers_zip()), DAY)
    assert record.status is RunStatus.COMPLETE
    assert (record.stats["listings"], record.stats["with_id"]) == (217, 2)
    assert record.stats["dropped_odd_ticker"] == 6 and record.stats["dropped_not_usd"] == 8
    stored = ctx.reader.table("instruments/listing_history", DAY)
    assert stored is not None and len(stored) == 217
    keys = zip(stored["ticker"], stored["start_date"], strict=True)
    ids = dict(zip(keys, stored["instrument_id"], strict=True))
    assert ids[("AAPL", date(1980, 12, 12))] == "EQ:BBG000AAPL"
    # The recycled ticker: only the listing overlapping the FIGI's row gets its id.
    assert ids[("AAC", date(2026, 8, 27))] == "EQ:BBG000AAC"
    assert pd.isna(ids[("AAC", date(2014, 10, 2))]) and pd.isna(ids[("AAC", date(2021, 3, 25))])
    assert not any(
        str(i).startswith(("EQ:AAC", "EQ:TWTR")) for i in stored["instrument_id"].dropna()
    )
    members = ingest_index_membership(
        ctx, Sp500Membership(http_for(lambda url: sp500.membership_csv())), DAY, (5, 40)
    )
    assert members.status is RunStatus.COMPLETE
    got = universe_asof(ctx.reader, date(2018, 6, 1))
    assert got.snapshot == DAY and got.membership_snapshot == DAY
    assert list(got.instruments["ticker"]) == ["AAPL"]  # the only listing with an id alive then
    assert got.without_id > 50  # the rest wait for a trusted id (the meta pull)


def test_a_perma_ticker_gives_the_namespaced_id_when_symbol_history_has_none() -> None:
    listings = pd.DataFrame(
        {
            "ticker": ["OLD"],
            "start_date": [date(2005, 1, 3)],
            "end_date": [date(2009, 1, 2)],
            "perma_ticker": ["US000000042"],
        }
    )
    assert list(assign_listing_ids(listings, None)["instrument_id"]) == ["EQ:TIINGO:US000000042"]
    assert assign_listing_ids(listings.assign(perma_ticker=""), None)["instrument_id"].isna().all()


def test_no_file_fails_the_run_without_writing() -> None:
    writer = StoreWriter(MemoryBackend())
    ctx = task_ctx(writer, clock=CLOCK)
    record = ingest_listing_history(ctx, source(None), DAY)
    assert record.status is RunStatus.FAILED
    assert ctx.reader.dates("instruments/listing_history") == []
