"""``listing_tickers``: a listing's ticker on a session from the listing history, only from its
own start date, never a later one and never through the vendor's end date."""

from datetime import date

import pandas as pd

from algotrade.data.listings.tickers import listing_tickers
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter

DAY = date(2026, 10, 5)


def reader() -> StoreReader:
    rows = [
        ("EQ:TIINGO:OLD", "ABC", "2005-01-03", "2010-12-31"),  # delisted
        ("EQ:TIINGO:MOVED", "XYZ", "2005-01-03", None),
        ("EQ:TIINGO:MOVED", "XYZ2", "2015-06-01", None),  # the same id, renamed
        (None, "NOID", "2001-01-02", None),  # no trusted id
    ]
    now = pd.Timestamp(DAY, tz="UTC")
    frame = pd.DataFrame(rows, columns=["instrument_id", "ticker", "start_date", "end_date"])
    frame = frame.assign(
        start_date=pd.to_datetime(frame["start_date"]).dt.date,
        end_date=pd.to_datetime(frame["end_date"]).dt.date.where(frame["end_date"].notna(), None),
        exchange="NYSE", asset_type="Stock", price_currency="USD", perma_ticker="",
        ts=now, knowledge_ts=now, session_date=DAY, source="tiingo", run_id="r",
    )  # fmt: skip
    backend = MemoryBackend()
    StoreWriter(backend).write_table("instruments/listing_history", DAY, "r", frame)
    return StoreReader(backend)


def test_a_delisted_name_has_its_ticker_for_every_session_it_was_listed() -> None:
    found = listing_tickers(reader())
    assert found.snapshot == DAY
    assert found.on("EQ:TIINGO:OLD", date(2009, 3, 2)) == "ABC"
    assert found.on("EQ:TIINGO:OLD", date(2012, 1, 3)) == "ABC"  # after its end: still its name


def test_a_ticker_is_never_one_the_listing_took_after_the_session() -> None:
    found = listing_tickers(reader())
    assert found.on("EQ:TIINGO:MOVED", date(2014, 1, 2)) == "XYZ"
    assert found.on("EQ:TIINGO:MOVED", date(2016, 1, 4)) == "XYZ2"
    assert found.on("EQ:TIINGO:OLD", date(2004, 12, 31)) is None  # not yet listed


def test_a_listing_without_a_trusted_id_or_an_unknown_id_has_none() -> None:
    found = listing_tickers(reader())
    assert found.on("EQ:TIINGO:NONE", date(2012, 1, 3)) is None
    assert "NOID" not in {t for v in found.by_id.values() for _, t in v}
