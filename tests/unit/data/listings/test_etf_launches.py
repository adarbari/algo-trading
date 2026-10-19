"""``etf_launches``: the launch date of each specialised ETF from the listing history's first
listing, only thematic and sector funds, only from the fund's own start date, and nothing
without a category (UNKNOWN stays out)."""

from datetime import date

import pandas as pd

from algotrade.data.listings.etf_launches import LAUNCH_SOURCE, etf_launches, launched_by
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter

DAY = date(2026, 10, 5)
NOW = pd.Timestamp(DAY, tz="UTC")


def reader(with_category: bool = True) -> StoreReader:
    ref = pd.DataFrame(
        {
            "instrument_id": ["EQ:ARKK", "EQ:XLK", "EQ:SPY", "EQ:NEW", "EQ:UNK", "EQ:ICLN"],
            "symbol": ["ARKK", "XLK", "SPY", "NEW", "UNK", "ICLN"],
            "etf_category": ["thematic", "sector", "broad", "thematic", None, "thematic"],
            "etf_theme": ["technology", "technology", None, "health", None, "clean_energy"],
            "asset_class": "EQUITY", "security_type": "ETF", "multiplier": 1.0,
            "status": "ACTIVE", "knowledge_ts": NOW, "session_date": DAY,
            "source": "t", "run_id": "r",
        }
    )  # fmt: skip
    if not with_category:
        ref = ref.drop(columns=["etf_category", "etf_theme"])
    listings = pd.DataFrame(
        [
            ("EQ:ARKK", "ARKK", "2014-10-31", None),
            ("EQ:XLK", "XLK", "1998-12-22", None),
            ("EQ:XLK", "XLK", "2005-01-03", None),  # a later row of the same fund: the first wins
            ("EQ:SPY", "SPY", "1993-01-29", None),
            ("EQ:ICLN", "ICLN", "2008-06-25", "2012-01-01"),  # closed since: still a launch
            (None, "NOID", "2020-01-02", None),  # no trusted id
        ],
        columns=["instrument_id", "ticker", "start_date", "end_date"],
    )
    listings = listings.assign(
        start_date=pd.to_datetime(listings["start_date"]).dt.date,
        end_date=pd.to_datetime(listings["end_date"]).dt.date.where(
            listings["end_date"].notna(), None
        ),
        exchange="NYSE", asset_type="ETF", price_currency="USD", perma_ticker="",
        ts=NOW, knowledge_ts=NOW, session_date=DAY, source="tiingo", run_id="r",
    )  # fmt: skip
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    writer.write_table("instruments/reference", DAY, "r", ref)
    writer.write_table("instruments/listing_history", DAY, "r", listings)
    return StoreReader(backend)


def test_only_specialised_funds_with_a_listing_get_a_launch_date() -> None:
    out = etf_launches(reader()).set_index("instrument_id")
    assert set(out.index) == {"EQ:ARKK", "EQ:XLK", "EQ:ICLN"}  # SPY broad, NEW no listing, UNK none
    assert out.at["EQ:XLK", "event_date"] == date(1998, 12, 22)  # the earliest listing
    assert out.at["EQ:XLK", "etf_category"] == "sector"
    assert out.at["EQ:ICLN", "event_date"] == date(2008, 6, 25)  # delisted funds count
    assert list(etf_launches(reader())["event_date"]) == sorted(out["event_date"])
    assert LAUNCH_SOURCE == "tiingo_listing"


def test_a_snapshot_without_the_category_columns_has_no_launches() -> None:
    assert etf_launches(reader(with_category=False)).empty


def test_a_launch_after_the_session_is_not_known() -> None:
    out = launched_by(etf_launches(reader()), date(2010, 1, 4))
    assert set(out["instrument_id"]) == {"EQ:XLK", "EQ:ICLN"}
