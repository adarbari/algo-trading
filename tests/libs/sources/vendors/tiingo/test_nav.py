"""The Tiingo NAV adapters: the NMFQS listing on the RECORDED slice, a NAV series on a payload
built from the documentation."""

from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.vendors.tiingo.nav import (
    NAV_TICKER_COLUMNS,
    TABLE,
    TiingoFundNav,
    TiingoNavTickers,
    parse_nav,
    parse_nav_tickers,
)
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import tiingo as payloads


def test_the_listing_keeps_only_nmfqs_rows_one_per_ticker() -> None:
    nav = parse_nav_tickers(payloads.nav_tickers_zip())
    assert list(nav.columns) == NAV_TICKER_COLUMNS
    tickers = set(nav["ticker"])
    assert {"XPHKX", "XGDLX", "XJPSX", "XCATX", "AZNH"} <= tickers
    assert not tickers & {"AAPL", "SPY", "PHK"}  # NYSE / NASDAQ rows are the listing task's
    assert len(nav) == len(tickers) == 21
    rows = nav.set_index("ticker")
    assert rows.loc["XPHKX", "first_nav"] == date(2004, 3, 22)
    assert rows.loc["XPHKX", "last_nav"] == date(2026, 10, 7)
    assert rows.loc["XJPSX", "last_nav"] == date(2024, 10, 8)  # ended: no NAV since
    assert rows.loc["AZNH", "last_nav"] == date(2026, 1, 30)  # the NMFQS row, not NYSE ARCA's
    assert rows.loc["AZNH", "asset_type"] == "ETF"


def test_a_file_without_the_columns_is_refused() -> None:
    with pytest.raises(ValueError, match="lacks columns"):
        parse_nav_tickers(b"ticker,exchange\nXPHKX,NMFQS\n")


def test_the_listing_source_fetches_the_one_file_and_parses_it() -> None:
    urls: list[str] = []
    zipped = payloads.nav_tickers_zip()
    source = TiingoNavTickers(http_for(lambda url: urls.append(url) or zipped))
    request = FetchRequest("nav_tickers", session_date=date(2026, 10, 8))
    payload = source.fetch(request)
    assert payload == zipped and urls[0].endswith("supported_tickers.zip")
    normalized = source.normalize(request, payload)
    assert normalized is not None and len(normalized.parsed["nav_tickers"]) == 21


def test_the_nav_is_the_unadjusted_close_and_bad_rows_are_dropped_and_counted() -> None:
    body = payloads.nav_prices(
        [("2026-10-01", 20.5), ("2026-10-02", None), ("2026-10-05", 0.0), ("2026-10-06", 20.7)]
    )
    nav, invalid = parse_nav(body)
    assert list(nav["nav"]) == [20.5, 20.7]  # adjClose (half) is never read
    assert list(nav["ts"].dt.date) == [date(2026, 10, 1), date(2026, 10, 6)]
    assert invalid == 2
    assert parse_nav(b"[]")[1] == 0
    with pytest.raises(ValueError, match="JSON list"):
        parse_nav(b'{"detail": "Not found."}')


def test_the_series_request_is_the_prices_endpoint_with_its_window_and_keys_the_rows() -> None:
    urls: list[str] = []
    body = payloads.nav_prices([("2026-10-01", 20.5)])
    source = TiingoFundNav(http_for(lambda url: urls.append(url) or body))
    request = FetchRequest("XPHKX:2004-01-01:2026-10-16", "EQ:BBG000PHK")
    payload = source.fetch(request)
    assert urls == [
        "https://api.tiingo.com/tiingo/daily/XPHKX/prices?startDate=2004-01-01"
        "&endDate=2026-10-16&format=json"
    ]
    assert payload is not None
    normalized = source.normalize(request, payload)
    assert normalized is not None
    frame = normalized.tables[TABLE]
    assert list(frame["instrument_id"]) == ["EQ:BBG000PHK"]
    assert list(frame["nav_symbol"]) == ["XPHKX"] and list(frame["series"]) == ["nav"]
