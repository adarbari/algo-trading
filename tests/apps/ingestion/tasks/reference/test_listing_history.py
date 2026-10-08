"""The listing-history task on the SYNTHETIC supported-tickers file: one snapshot per session,
ids only from symbol_history or a permaTicker, never ``EQ:<symbol>`` (ADR 0018 amendment)."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.data.listings.universe import universe_asof
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.reference.instrument_ids import assign_listing_ids
from algotrade_ingestion.tasks.reference.listing_history import (
    ingest_listing_history,
)
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.tiingo.listings import TiingoSupportedTickers
from tests.helpers.ingest_fakes import http_for, task_ctx
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
        {"instrument_id": "EQ:BBG000AAA", "ts": pd.Timestamp(DAY, tz="UTC"), "figi": "BBG000AAA",
         "symbol": "AAA", "valid_from": date(1999, 1, 4), "valid_to": None},
        {"instrument_id": "EQ:BBG000RCY", "ts": pd.Timestamp(DAY, tz="UTC"), "figi": "BBG000RCY",
         "symbol": "RCY", "valid_from": date(2011, 1, 3), "valid_to": None},
    ]  # fmt: skip
    writer.write_table(
        "instruments/symbol_history", DAY, "h", stamped(history, DAY, "h"), pending=False
    )
    ctx = task_ctx(writer, clock=CLOCK)
    record = ingest_listing_history(ctx, source(payloads.supported_tickers_zip()), DAY)
    assert record.status is RunStatus.COMPLETE
    assert (record.stats["listings"], record.stats["with_id"]) == (6, 2)
    stored = ctx.reader.table("instruments/listing_history", DAY)
    assert stored is not None and len(stored) == 6
    keys = zip(stored["ticker"], stored["start_date"], strict=True)
    ids = dict(zip(keys, stored["instrument_id"], strict=True))
    assert ids[("AAA", date(2000, 1, 3))] == "EQ:BBG000AAA"
    # The recycled ticker: only the listing overlapping the FIGI's row gets its id.
    assert ids[("RCY", date(2011, 3, 1))] == "EQ:BBG000RCY"
    assert pd.isna(ids[("RCY", date(2005, 1, 3))])
    assert not any(str(i).startswith("EQ:RCY") for i in stored["instrument_id"].dropna())
    members = {"EQ:BBG000AAA", "EQ:BBG000RCY"}
    got = universe_asof(ctx.reader, date(2012, 6, 1), members)
    assert got.snapshot == DAY and set(got.instruments["ticker"]) == {"AAA", "RCY"}


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
