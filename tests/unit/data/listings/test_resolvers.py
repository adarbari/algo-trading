"""``listing_resolver``: a ticker resolves to the listing whose dates contain the day, so a
recycled ticker is two ids by date and a delisted issuer keeps its own; a ticker no listing of
the day carries is unknown (never today's holder); no listing history is an error."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.resolvers import listing_resolver
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter

DAY = date(2026, 10, 5)


def reader() -> StoreReader:
    rows = [
        ("EQ:OLD1", "OLD", "2005-01-03", "2012-06-30"),  # the first holder, delisted
        ("EQ:OLD2", "OLD", "2015-02-02", None),  # the ticker, reused
        ("EQ:EXMP", "EXMP", "2010-01-04", None),
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


def test_a_recycled_ticker_is_two_ids_by_the_day() -> None:
    on = listing_resolver(reader())
    assert on(date(2010, 5, 3)).ids["OLD"] == "EQ:OLD1"
    assert on(date(2020, 5, 3)).ids["OLD"] == "EQ:OLD2"
    assert on(date(2020, 5, 3)).ids["EXMP"] == "EQ:EXMP"


def test_a_ticker_no_listing_of_the_day_carries_is_unknown() -> None:
    on = listing_resolver(reader())
    assert "OLD" not in on(date(2013, 6, 3)).ids  # between the two holders
    assert "EXMP" not in on(date(2009, 12, 31)).ids  # not yet listed
    assert on(date(2010, 5, 3)) is on(date(2010, 5, 3))  # one resolver per day, kept


def test_no_listing_history_is_an_error() -> None:
    with pytest.raises(MissingDataError):
        listing_resolver(StoreReader(MemoryBackend()))
