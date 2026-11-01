"""The listing-history task on the RECORDED supported-tickers slice and Massive's delisted names:
one merged snapshot per session; ids from the previous snapshot, ``symbol_history``, a permaTicker
or a unique FIGI, never ``EQ:<symbol>`` (ADR 0018 amendment, ADR 0087)."""

from datetime import UTC, date, datetime

import pandas as pd

from algotrade.config.site.settings import SourcesSettings
from algotrade.data.listings.universe import listed_asof, listing_frame, universe_asof
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.listings.delisted_tickers import ingest_delisted_tickers
from algotrade_ingestion.tasks.listings.index_membership import ingest_index_membership
from algotrade_ingestion.tasks.listings.listing_history import (
    ingest_listing_history,
)
from algotrade_ingestion.tasks.reference.instrument_ids import assign_listing_ids
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.massive.tickers import MassiveTickers
from algotrade_sources.vendors.sp500_history.membership import Sp500Membership
from algotrade_sources.vendors.tiingo.listings import TiingoSupportedTickers
from algotrade_sources.vendors.tiingo.meta import TiingoListingMeta
from tests.helpers.ingest_fakes import http_for, task_ctx
from tests.helpers.payloads import massive as mfx
from tests.helpers.payloads import published as sp500
from tests.helpers.payloads import tiingo as payloads
from tests.helpers.stored_frames import stamped

DAY = date(2026, 10, 5)
CLOCK = lambda: datetime(2026, 10, 5, 22, tzinfo=UTC)  # noqa: E731
TABLE = "instruments/listing_history"
SETTINGS = SourcesSettings(min_delisted_tickers=1)
TWTR = mfx.inactive_record(
    "TWTR", "2022-10-31", "XNYS", "CS", cik="0001418091", composite_figi="BBG000H6HNW3"
)  # Tiingo's TWTR row ended 2022-10-28: three days apart, one listing
GONE = mfx.inactive_record("GONE", "2015-03-02", "XNAS", "WARRANT", composite_figi="BBG000GONE0")


def source(payload: bytes | None = None) -> TiingoSupportedTickers:
    def transport(url: str) -> bytes:
        if payload is None:
            raise HttpError(404)
        return payload

    return TiingoSupportedTickers(http_for(transport, RetryPolicy(tries=1)))


def context(*records: dict[str, object], history: bool = True) -> TaskContext:
    """A store with Massive's delisted names (the real task, a recorded-shape page) and, when
    asked, the two ``symbol_history`` rows the slice's AAPL and AAC (2026) match."""
    writer = StoreWriter(MemoryBackend())
    ctx = task_ctx(writer, clock=CLOCK, settings=SETTINGS)
    if records:
        page = mfx.page(list(records))
        massive = MassiveTickers(http_for(lambda url: page, RetryPolicy(tries=1)))
        assert ingest_delisted_tickers(ctx, massive, DAY).status is RunStatus.COMPLETE
    if history:
        now = pd.Timestamp(DAY, tz="UTC")
        rows = [
            {"instrument_id": "EQ:BBG000AAPL", "ts": now, "figi": "BBG000AAPL",
             "symbol": "AAPL", "valid_from": date(1999, 1, 4), "valid_to": None},
            {"instrument_id": "EQ:BBG000AAC", "ts": now, "figi": "BBG000AAC",
             "symbol": "AAC", "valid_from": date(2026, 8, 1), "valid_to": None},
        ]  # fmt: skip
        writer.write_table(
            "instruments/symbol_history", DAY, "h", stamped(rows, DAY, "h"), pending=False
        )
    return ctx


def stored(ctx: TaskContext, day: date = DAY) -> pd.DataFrame:
    frame = ctx.reader.table(TABLE, day)
    assert frame is not None
    return frame


def by_key(frame: pd.DataFrame) -> dict[tuple[str, date | None], pd.Series]:
    return {(r["ticker"], r["start_date"]): r for _, r in frame.iterrows()}


def test_task_writes_one_merged_snapshot_with_each_rows_own_source() -> None:
    ctx = context(TWTR, GONE)
    record = ingest_listing_history(ctx, source(payloads.supported_tickers_zip()), DAY)
    assert record.status is RunStatus.COMPLETE
    rows = stored(ctx)
    # Every Tiingo row (244 of the file) and every Massive record (TWTR paired, GONE alone).
    assert record.stats["listings"] == len(rows) == 245
    assert record.stats["out_of_scope"] == 27 and record.stats["paired"] == 1
    assert record.stats["massive_only"] == 1 and record.stats["delisted_snapshot"] == "2026-10-05"
    assert (
        record.stats["out_of_scope_odd_ticker"] == 6 and record.stats["out_of_scope_not_usd"] == 8
    )
    assert record.stats["out_of_scope_duplicate_start"] == 2
    assert dict(rows["source"].value_counts()) == {"tiingo": 244, "massive": 1}
    assert set(rows["run_id"]) == {record.run_id}
    gone = rows[rows["ticker"] == "GONE"].iloc[0]  # alone, with its own attributes, undated
    assert (gone["source"], gone["security_type"], gone["exchange"]) == (
        "massive",
        "WARRANT",
        "NASDAQ",
    )
    assert pd.isna(gone["start_date"]) and pd.isna(gone["instrument_id"])
    assert gone["no_id_reason"] == "no_start" and gone["figi"] == "BBG000GONE0"  # no id from a figi
    twtr = rows[(rows["ticker"] == "TWTR") & (rows["source"] == "tiingo")].iloc[0]
    assert (twtr["security_type"], twtr["cik"], twtr["vendor_exchange"]) == (
        "COMMON_STOCK",
        "0001418091",
        "XNYS",
    )
    assert twtr["vendor_end_date"] == date(2022, 10, 31) and twtr["end_date"] == date(2022, 10, 28)


def test_ids_come_from_symbol_history_or_a_unique_figi_never_from_the_symbol() -> None:
    ctx = context(TWTR, GONE)
    record = ingest_listing_history(ctx, source(payloads.supported_tickers_zip()), DAY)
    rows = stored(ctx)
    ids = {k: r["instrument_id"] for k, r in by_key(rows[rows["source"] == "tiingo"]).items()}
    assert ids[("AAPL", date(1980, 12, 12))] == "EQ:BBG000AAPL"
    # The recycled ticker: only the listing overlapping the FIGI's row gets its id.
    assert ids[("AAC", date(2026, 8, 27))] == "EQ:BBG000AAC"
    assert pd.isna(ids[("AAC", date(2014, 10, 2))]) and pd.isna(ids[("AAC", date(2021, 3, 25))])
    twtr = rows[(rows["ticker"] == "TWTR") & (rows["source"] == "tiingo")].iloc[0]
    assert (twtr["instrument_id"], twtr["id_source"]) == ("EQ:BBG000H6HNW3", "figi")
    assert not any(str(i).startswith(("EQ:AAC", "EQ:TWTR")) for i in rows["instrument_id"].dropna())
    aapl = rows[rows["ticker"] == "AAPL"].iloc[0]
    assert aapl["id_source"] == "symbol_history"
    assert (record.stats["with_id"], record.stats["ids_by_figi"]) == (3, 1)
    assert record.stats["no_id_out_of_scope"] == 27 and record.stats["no_id_no_start"] == 1
    # Out of scope: stored, with a reason, no id and no meta request.
    out = rows[rows["scope_reason"].notna()]
    assert len(out) == 27 and out["instrument_id"].isna().all()
    assert set(out["no_id_reason"]) == {"out_of_scope"}
    members = ingest_index_membership(
        ctx, Sp500Membership(http_for(lambda url: sp500.membership_csv())), DAY, (5, 40)
    )
    assert members.status is RunStatus.COMPLETE
    got = universe_asof(ctx.reader, date(2018, 6, 1))
    assert got.snapshot == DAY and got.membership_snapshot == DAY
    assert list(got.instruments["ticker"]) == ["AAPL"]  # the only listing with an id alive then
    assert got.without_id > 50  # the rest wait for a trusted id (the meta pull)
    assert got.null_type == 1  # AAPL: a Stock whose type no Massive record gave


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


def test_meta_fills_perma_tickers_only_for_unique_matches_and_asks_only_in_scope_rows() -> None:
    ctx = context(TWTR, GONE)
    urls: list[str] = []
    meta = TiingoListingMeta(http_for(lambda url: urls.append(url) or payloads.meta_payload()))
    record = ingest_listing_history(ctx, source(payloads.supported_tickers_zip()), DAY, meta)
    assert record.status is RunStatus.COMPLETE
    asked = {t for url in urls for t in url.split("tickers=")[1].split(",")}
    assert "aapl" not in asked and "twtr" in asked  # AAPL already has its id
    assert not asked & {"bc/pa", "159725"}  # an out-of-scope row is never asked
    assert record.stats["meta_batches"] == len(urls) >= 1
    rows = stored(ctx)
    ids = {k: r["instrument_id"] for k, r in by_key(rows[rows["source"] == "tiingo"]).items()}
    assert ids[("TWTR", date(2013, 11, 7))] == "EQ:TIINGO:US000000012345"  # the perma comes first
    twtr = rows[(rows["ticker"] == "TWTR") & (rows["source"] == "tiingo")].iloc[0]
    assert twtr["id_source"] == "perma" and twtr["perma_ticker"] == "US000000012345"
    assert pd.notna(twtr["is_adr"]) and not twtr["is_adr"]  # Tiingo's own free field, kept
    assert twtr["data_provider_perma_ticker"] == "US000000012345"
    assert pd.isna(ids[("AAC", date(2014, 10, 2))])  # two delisted listings, two inactive rows
    assert pd.isna(ids[("AAC", date(2021, 3, 25))])
    assert ids[("AAC", date(2026, 8, 27))] == "EQ:BBG000AAC"  # symbol_history first
    reasons = {k: r["no_id_reason"] for k, r in by_key(rows[rows["source"] == "tiingo"]).items()}
    assert reasons[("AAC", date(2014, 10, 2))] == "perma_ambiguous"
    assert record.stats["perma_ambiguous"] >= 2 and record.stats["perma_matched"] >= 1
    assert record.stats["with_id"] > 3


def test_meta_answering_nothing_fails_the_run() -> None:
    ctx = context(TWTR, history=False)

    def refuse(url: str) -> bytes:
        raise HttpError(404)

    meta = TiingoListingMeta(http_for(refuse, RetryPolicy(tries=1)))
    record = ingest_listing_history(ctx, source(payloads.supported_tickers_zip()), DAY, meta)
    assert record.status is RunStatus.FAILED
    assert ctx.reader.dates(TABLE) == []


def test_no_file_fails_the_run_without_writing() -> None:
    ctx = context(TWTR)
    record = ingest_listing_history(ctx, source(None), DAY)
    assert record.status is RunStatus.FAILED
    assert ctx.reader.dates(TABLE) == []


def test_with_no_delisted_snapshot_the_run_fails_closed_and_writes_nothing() -> None:
    ctx = context()  # no instruments/delisted_tickers stored
    record = ingest_listing_history(ctx, source(payloads.supported_tickers_zip()), DAY)
    assert record.status is RunStatus.FAILED
    assert "delisted" in str(record.stats["failed_because"])
    assert ctx.reader.dates(TABLE) == []  # the universe never silently loses the delisted names


# ---------------------------------------------------- BBBY: a Massive-only record with a successor

FILE = (
    b"ticker,exchange,assetType,priceCurrency,startDate,endDate\n"
    b"ZLIVE,NYSE,Stock,USD,2000-01-03,2026-10-02\n"
    b"BBBYQ,PINK,Stock,USD,1992-06-04,2023-09-29\n"
)
BBBY = mfx.inactive_record(
    "BBBY", "2023-05-02", "XNAS", "CS", cik="0000886158", composite_figi="BBG000CSY9H9"
)


def bbby_meta(answer: bytes) -> TiingoListingMeta:
    """Tiingo's meta, answering ``answer`` to the BBBY record's own request and nothing else."""

    def transport(url: str) -> bytes:
        return answer if "tickers=bbby,bbbyq" in url else payloads.meta_rows()

    return TiingoListingMeta(http_for(transport, RetryPolicy(tries=1)))


def test_bbby_with_the_recorded_meta_stays_undated_and_gets_no_id_even_with_a_figi() -> None:
    ctx = context(BBBY, history=False)
    meta = bbby_meta(payloads.meta_bbby_payload())  # the 2026-11-01 answer: two permaTickers
    record = ingest_listing_history(ctx, source(FILE), DAY, meta)
    assert record.status is RunStatus.COMPLETE
    bbby = stored(ctx).set_index("ticker").loc["BBBY"]
    assert (bbby["source"], bbby["figi"]) == ("massive", "BBG000CSY9H9")
    assert pd.isna(bbby["start_date"]) and pd.isna(bbby["instrument_id"])
    assert bbby["no_id_reason"] == "perma_ambiguous"
    assert (
        record.stats["meta_record_requests"] == 1 and record.stats["massive_perma_ambiguous"] == 1
    )
    frame, _ = listing_frame(ctx.reader)
    out = listed_asof(frame, date(2023, 4, 3), set())
    assert out.undated == 1 and "BBBY" not in set(
        out.instruments["ticker"]
    )  # counted, not returned


def test_bbby_takes_its_successors_start_and_a_perma_id_when_meta_names_one_company() -> None:
    ctx = context(BBBY, history=False)
    one = payloads.meta_rows(
        ("US000000000258", "bbby", None, True), ("US000000000258", "bbbyq", "Bed Bath", True)
    )  # built by hand in the recorded shape: what the recorded answer would be for one company
    record = ingest_listing_history(ctx, source(FILE), DAY, bbby_meta(one))
    assert record.status is RunStatus.COMPLETE
    rows = stored(ctx)
    bbby = rows[(rows["ticker"] == "BBBY") & (rows["source"] == "massive")].iloc[0]
    assert bbby["start_date"] == date(1992, 6, 4) and bbby["end_date"] == date(2023, 5, 2)
    assert (bbby["instrument_id"], bbby["id_source"]) == ("EQ:TIINGO:US000000000258", "perma")
    frame, _ = listing_frame(ctx.reader)
    out = listed_asof(frame, date(2023, 4, 3), set())  # NASDAQ, dated, with an id: in
    assert list(out.instruments["ticker"]) == ["BBBY"] and out.undated == 0
    assert out.instruments["security_type"].iloc[0] == "COMMON_STOCK" and out.null_type == 0
    # The OTC successor itself is stored and never read.
    otc = rows[rows["ticker"] == "BBBYQ"].iloc[0]
    assert otc["scope_reason"] == "other_exchange" and otc["exchange"] == "PINK"
    assert pd.isna(otc["instrument_id"])


# ----------------------------------------------------------------- an id once given is kept


def test_a_later_snapshot_keeps_every_id_it_carried_even_when_the_rules_now_differ() -> None:
    ctx = context(TWTR, history=False)
    meta = TiingoListingMeta(http_for(lambda url: payloads.meta_payload()))
    first = ingest_listing_history(ctx, source(payloads.supported_tickers_zip()), DAY, meta)
    rows = stored(ctx)
    twtr = rows[(rows["ticker"] == "TWTR") & (rows["source"] == "tiingo")].iloc[0]
    assert twtr["instrument_id"] == "EQ:TIINGO:US000000012345"
    # A symbol_history row for TWTR appears (the rule would now give EQ:BBG000TWTR): the id stays.
    later = date(2026, 10, 12)
    history = [{"instrument_id": "EQ:BBG000TWTR", "ts": pd.Timestamp(later, tz="UTC"),
                "figi": "BBG000TWTR", "symbol": "TWTR", "valid_from": date(2013, 11, 7),
                "valid_to": date(2022, 10, 28)}]  # fmt: skip
    ctx.writer.write_table(
        "instruments/symbol_history", later, "h", stamped(history, later, "h"), pending=False
    )
    second = ingest_listing_history(ctx, source(payloads.supported_tickers_zip()), later, meta)
    assert (first.status, second.status) == (RunStatus.COMPLETE, RunStatus.COMPLETE)
    again = stored(ctx, later)
    twtr = again[(again["ticker"] == "TWTR") & (again["source"] == "tiingo")].iloc[0]
    assert (twtr["instrument_id"], twtr["id_source"]) == ("EQ:TIINGO:US000000012345", "perma")
    assert second.stats["ids_carried"] == first.stats["with_id"] and second.stats["ids_held"] >= 1
