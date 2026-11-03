"""Massive ticker details against a synthetic answer in the shape probed 2026-11-01 (BBBY on
2023-05-02: the old Bed Bath & Beyond, listed 1992-06-04), ADR 0087 PR3b."""

from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.massive.details import (
    MassiveTickerDetails,
    details_key,
    parse_details,
    split_key,
)
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import massive as fx

BBBY = fx.ticker_details("BBBY")


def test_every_field_of_the_answer_is_kept_with_dates_as_dates() -> None:
    row = parse_details(BBBY, "BBBY").iloc[0]
    assert row["ticker"] == "BBBY" and row["name"] == "Bed Bath & Beyond Inc."
    assert row["list_date"] == date(1992, 6, 4) and row["delisted_date"] == date(2023, 5, 2)
    assert (row["cik"], row["figi"], row["share_class_figi"]) == (
        "0000886158", "BBG000BB5R87", "BBG001S5SRZ9",
    )  # fmt: skip
    assert (row["vendor_type"], row["exchange"], row["active"]) == ("CS", "XNAS", False)
    assert (row["market"], row["locale"], row["currency_name"]) == ("stocks", "us", "usd")
    assert row["last_updated_utc"] == "2023-05-03T00:00:00Z"  # as received, never parsed
    assert (row["sic_code"], row["total_employees"]) == ("5700", 14000)
    assert row["description"] == "Bed Bath & Beyond sells home goods."  # whitespace collapsed


def test_a_sparse_answer_leaves_gaps_none() -> None:
    row = parse_details(fx.ticker_details("OLD", list_date=None, cik=None), "OLD").iloc[0]
    assert row["list_date"] is None and row["cik"] is None and row["ticker"] == "OLD"
    assert parse_details(b'{"status": "OK"}', "NEW").iloc[0]["ticker"] == "NEW"


def test_fetch_asks_for_the_ticker_as_of_the_day_and_normalises() -> None:
    urls: list[str] = []

    def transport(url: str) -> bytes:
        urls.append(url)
        return BBBY

    source = MassiveTickerDetails(http_for(transport, RetryPolicy(tries=1)))
    request = FetchRequest(details_key("KIM$L", date(2023, 5, 2)))
    payload = source.fetch(request)
    assert urls == ["https://api.massive.com/v3/reference/tickers/KIMpL?date=2023-05-02"]
    normalized = source.normalize(request, payload or b"")
    assert normalized is not None and normalized.parsed["details"].iloc[0]["ticker"] == "BBBY"


def test_a_ticker_massive_does_not_know_that_day_is_nothing_there() -> None:
    def transport(url: str) -> bytes:
        raise HttpError(404)

    source = MassiveTickerDetails(http_for(transport, RetryPolicy(tries=1)))
    assert source.fetch(FetchRequest(details_key("ZZZZ", date(2020, 1, 2)))) is None


def test_a_key_is_ticker_and_day() -> None:
    assert split_key("BRK.B|2020-01-02") == ("BRK.B", "2020-01-02")
    for bad in ("BBBY", "BBBY|soon"):
        with pytest.raises(ValueError):
            split_key(bad)
