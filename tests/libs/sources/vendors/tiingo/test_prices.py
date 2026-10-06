from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.tiingo.prices import (
    DEFAULT_START,
    TiingoDailyPrices,
    parse_key,
    parse_prices,
    vendor_ticker,
)
from tests.helpers.ingest_fakes import CountingLimiter, http_for
from tests.helpers.payloads import tiingo as payloads


def test_the_request_asks_for_the_window_and_waits_on_the_shared_limiter() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()
    transport = lambda url: urls.append(url) or payloads.sample()  # noqa: E731
    source = TiingoDailyPrices(http_for(transport, RetryPolicy(tries=1), limiter))
    assert source.fetch(FetchRequest("AAPL:2018-01-01:2026-10-05")) == payloads.sample()
    assert urls == [
        "https://api.tiingo.com/tiingo/daily/AAPL/prices"
        "?startDate=2018-01-01&endDate=2026-10-05&format=json"
    ]
    assert limiter.waits == 1
    source.fetch(FetchRequest("BRK.B"))  # a bare ticker: from 2018, no end
    assert urls[1].endswith("/BRK-B/prices?startDate=2018-01-01&format=json")


def test_an_unknown_ticker_answers_none_not_an_error() -> None:
    def transport(url: str) -> bytes:
        raise HttpError(404)

    source = TiingoDailyPrices(http_for(transport, RetryPolicy(tries=1)))
    assert source.fetch(FetchRequest("NOPE:2018-01-01:2026-10-05")) is None


def test_key_and_ticker_spelling() -> None:
    assert parse_key("MSFT") == ("MSFT", DEFAULT_START, None)
    assert parse_key("MSFT:2019-02-03:") == ("MSFT", date(2019, 2, 3), None)
    assert parse_key("MSFT:2019-02-03:2020-01-02") == ("MSFT", date(2019, 2, 3), date(2020, 1, 2))
    assert vendor_ticker(" brk.b ") == "BRK-B"


def test_normalize_stores_the_unadjusted_columns_and_keeps_the_actions() -> None:
    source = TiingoDailyPrices(http_for(lambda url: b""))
    request = FetchRequest("AAPL:2020-08-27:2020-11-06", "EQ:BBG000B9XRY4")
    normalized = source.normalize(request, payloads.sample())
    assert normalized is not None and normalized.session_date is None
    bars = normalized.tables["bars/1d"]
    assert list(bars.columns) == [
        "ts", "open", "high", "low", "close", "volume", "symbol", "instrument_id",
    ]  # fmt: skip
    assert set(bars["symbol"]) == {"AAPL"} and set(bars["instrument_id"]) == {"EQ:BBG000B9XRY4"}
    assert list(bars["ts"].dt.date)[:3] == [date(2020, 8, 27), date(2020, 8, 28), date(2020, 8, 31)]
    assert str(bars["ts"].dt.tz) == "UTC" and (bars["ts"].dt.hour == 0).all()
    split_day = bars[bars["ts"].dt.date == date(2020, 8, 31)].iloc[0]
    assert (split_day["close"], split_day["volume"]) == (129.0, 4_000_000.0)  # not adjClose
    actions = normalized.parsed["actions"]
    assert [(t.date(), f, d) for t, f, d in actions.itertuples(index=False)] == [
        (date(2020, 8, 31), 4.0, 0.0),
        (date(2020, 11, 6), 1.0, 0.205),
    ]
    assert normalized.notes == {"invalid_rows": 0}


def test_without_an_instrument_id_the_rows_carry_only_the_symbol() -> None:
    source = TiingoDailyPrices(http_for(lambda url: b""))
    normalized = source.normalize(FetchRequest("aapl"), payloads.sample())
    assert normalized is not None
    bars = normalized.tables["bars/1d"]
    assert "instrument_id" not in bars.columns and set(bars["symbol"]) == {"AAPL"}


def test_invalid_rows_are_dropped_and_counted() -> None:
    payload = payloads.prices(
        [
            ("2020-01-02", 10, 11, 9, 10.5, 100),
            ("2020-01-03", 10, 9, 9, 10.5, 100),  # high below the close
            ("2020-01-06", 0, 11, 9, 10.5, 100),  # a zero price
            ("2020-01-07", 10, 11, 9, 10.5, 100),
        ]
    )
    bars, actions, invalid = parse_prices(payload)
    assert [t.date() for t in bars["ts"]] == [date(2020, 1, 2), date(2020, 1, 7)]
    assert invalid == 2 and actions.empty


def test_an_empty_list_is_an_empty_history_and_anything_else_is_an_error() -> None:
    bars, actions, invalid = parse_prices(b"[]")
    assert bars.empty and actions.empty and invalid == 0
    assert list(bars.columns) == ["ts", "open", "high", "low", "close", "volume"]
    with pytest.raises(ValueError, match="JSON list"):
        parse_prices(b'{"detail": "Error: Ticker not found"}')


def test_plain_date_strings_parse_too() -> None:
    payload = b'[{"date": "2020-01-02", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 3}]'
    bars, _, _ = parse_prices(payload)
    assert bars["ts"].iloc[0] == pd.Timestamp("2020-01-02", tz="UTC")
