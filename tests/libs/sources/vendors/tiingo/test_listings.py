"""``TiingoSupportedTickers`` on the RECORDED supported-tickers slice."""

from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.vendors.tiingo.listings import (
    COLUMNS,
    TABLE,
    URL,
    TiingoSupportedTickers,
    parse_listings,
)
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import tiingo as payloads


def test_the_one_file_is_fetched_as_received() -> None:
    urls: list[str] = []
    zipped = payloads.supported_tickers_zip()
    source = TiingoSupportedTickers(http_for(lambda url: urls.append(url) or zipped))
    assert source.fetch(FetchRequest("supported_tickers")) == zipped
    assert urls == [URL]


def test_rows_are_filtered_mapped_and_a_recycled_ticker_keeps_every_listing() -> None:
    listings, dropped = parse_listings(payloads.supported_tickers_zip())
    assert list(listings.columns) == COLUMNS
    assert len(listings) == 217
    by_listing = listings.set_index(["ticker", "start_date"])
    aac = listings[listings["ticker"] == "AAC"]
    assert list(zip(aac["start_date"], aac["end_date"], strict=True)) == [
        (date(2014, 10, 2), date(2021, 4, 19)),  # the vendor's own dates overlap here
        (date(2021, 3, 25), date(2023, 11, 6)),
        (date(2026, 8, 27), None),
    ]
    aaap = listings[listings["ticker"] == "AAAP"]
    assert list(aaap["asset_type"]) == ["Stock", "ETF"]
    assert by_listing.loc[("TWTR", date(2013, 11, 7)), "end_date"] == date(2022, 10, 28)
    assert by_listing.loc[("AAPL", date(1980, 12, 12)), "end_date"] is None  # live: open
    assert set(listings["exchange"]) == {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}
    assert (listings["exchange"] == "AMEX").sum() == 9  # AMEX and NYSE MKT rows
    assert (listings["exchange"] == "ARCA").sum() == 7  # NYSE ARCA rows
    assert set(listings["perma_ticker"]) == {""} and set(listings["price_currency"]) == {"USD"}
    assert not listings["ticker"].str.contains("[/ (]", regex=True).any()
    assert dropped == {
        "not_usd": 8, "other_exchange": 11, "other_asset_type": 0, "no_start_date": 0,
        "no_ticker": 0, "odd_ticker": 6,
    }  # fmt: skip


def test_a_ticker_listed_twice_on_one_day_keeps_the_row_still_open() -> None:
    raw = (
        b"ticker,exchange,assetType,priceCurrency,startDate,endDate\n"
        b"ACHX,BATS,Stock,USD,2026-06-30,2026-06-30\n"
        b"ACHX,BATS,ETF,USD,2026-06-30,2026-10-08\n"
    )
    listings, _ = parse_listings(raw)
    assert list(listings["asset_type"]) == ["ETF"] and listings["end_date"].isna().all()


def test_a_bare_csv_parses_too_and_normalize_exposes_the_frame_as_parsed() -> None:
    source = TiingoSupportedTickers(http_for(lambda url: b""))
    normalized = source.normalize(
        FetchRequest("x", session_date=date(2026, 10, 8)), payloads.supported_tickers_csv()
    )
    assert normalized is not None and normalized.tables == {}
    assert len(normalized.parsed[TABLE]) == 217 and normalized.notes["dropped_not_usd"] == 8
    assert normalized.notes["dropped_odd_ticker"] == 6


def test_a_file_without_the_documented_header_is_an_error() -> None:
    with pytest.raises(ValueError, match="lacks columns"):
        parse_listings(b"symbol,name\nAAA,Triple A\n")


def test_a_live_name_stays_in_the_universe_and_a_delisted_one_leaves_it() -> None:
    from algotrade.data.listings.universe import listed_asof  # noqa: PLC0415

    listings, _ = parse_listings(payloads.supported_tickers_zip())
    by_ticker = {t: listings[listings["ticker"] == t] for t in ("AAPL", "TWTR")}
    ids = pd.concat([x.assign(instrument_id=f"EQ:TIINGO:{t}") for t, x in by_ticker.items()])
    after = listed_asof(ids, date(2026, 12, 1), {"AAPL"})  # past the pull's last day
    assert list(after.instruments["ticker"]) == ["AAPL"]
    during = listed_asof(ids, date(2018, 6, 1), {"TWTR"})  # TWTR is NYSE: a member
    assert list(during.instruments["ticker"]) == ["AAPL", "TWTR"]


def test_the_open_end_is_the_latest_day_of_the_kept_rows_not_of_a_foreign_listing() -> None:
    raw = (
        b"ticker,exchange,assetType,priceCurrency,startDate,endDate\n"
        b"AAA,NYSE,Stock,USD,2000-01-03,2026-10-08\n"
        b"BBB,NYSE,Stock,USD,2000-01-03,2026-10-07\n"
        b"600000,SHG,Stock,CNY,2000-01-03,2026-10-09\n"
    )
    listings, _ = parse_listings(raw)
    by = listings.set_index("ticker")["end_date"]
    assert by["AAA"] is None and by["BBB"] == date(2026, 10, 7)
