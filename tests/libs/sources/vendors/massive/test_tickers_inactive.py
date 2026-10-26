"""Massive's inactive (delisted) ticker list on a RECORDED slice of the 2026-10-24 pull: the
parse, the ``next_url`` paging and the request URLs (ADR 0086)."""

import json
from datetime import date

import pandas as pd

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.vendors.massive.tickers import (
    DELISTED_COLUMNS,
    DELISTED_TABLE,
    INACTIVE,
    MassiveTickers,
    parse_inactive,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import massive as fx

SLICE = REPO_ROOT / "tests/fixtures/sources/massive/inactive_tickers_slice.json"
RECORDS = json.loads(SLICE.read_text())["results"]


def row(frame: pd.DataFrame, ticker: str) -> pd.Series:
    return frame.set_index("ticker").loc[ticker]


def test_the_recorded_slice_parses_to_identity_columns_with_nulls_kept() -> None:
    frame, notes = parse_inactive(RECORDS)
    assert list(frame.columns) == DELISTED_COLUMNS
    assert len(frame) == len(RECORDS) == 60 and notes == {"dropped_duplicate": 0}
    twtr = row(frame, "TWTR")
    assert (twtr["vendor_type"], twtr["security_type"]) == ("CS", "COMMON_STOCK")
    assert (twtr["figi"], twtr["cik"], twtr["exchange"]) == ("BBG000H6HNW3", "0001418091", "XNYS")
    assert twtr["share_class_figi"] == "BBG001T35PT7" and twtr["end_date"] == date(2022, 10, 31)
    # A name Massive types and identifies only in part: nulls stay null, never "".
    old = row(frame, "AAB.WS")
    assert old[["vendor_type", "security_type", "cik", "figi"]].isna().all()
    assert old["exchange"] == "XASE"
    assert pd.isna(row(frame, "AAII")["exchange"]) and pd.notna(row(frame, "AAII")["figi"])
    assert pd.isna(row(frame, "AADI")["end_date"])  # Massive gives some rows no delisting date
    assert row(frame, "WFM")["cik"] == "0000865436" and pd.isna(row(frame, "WFM")["figi"])
    # Types: ours where the vendor's code is mapped, none for a code we do not map (INDEX).
    kinds = frame.set_index("vendor_type")["security_type"].to_dict()
    assert kinds["ETF"] == "ETF" and kinds["WARRANT"] == "WARRANT" and kinds["UNIT"] == "UNIT"
    assert pd.isna(kinds["INDEX"]) and kinds["ADRC"] == "ADR" and kinds["FUND"] == "CEF"


def test_tickers_use_the_act_symbol_space_of_the_active_list() -> None:
    frame, _ = parse_inactive(RECORDS)
    tickers = set(frame["ticker"])
    assert {"AA$", "AAIC$B", "DDW"} <= tickers  # KIMpL -> KIM$L; a lowercase "w" is upper-cased
    assert "AAp" not in tickers and "AAICpB" not in tickers


def test_a_repeated_ticker_and_day_is_dropped_and_counted_a_reused_ticker_is_kept() -> None:
    first = {"ticker": "ABC", "type": "CS", "delisted_utc": "2010-05-03T04:00:00Z", "name": "A"}
    reused = {"ticker": "ABC", "type": "CS", "delisted_utc": "2021-08-02T04:00:00Z", "name": "B"}
    frame, notes = parse_inactive([first, dict(first, name="again"), reused, {"name": "no ticker"}])
    assert notes == {"dropped_duplicate": 1}
    assert list(frame["name"]) == ["A", "B"]  # the first record wins; both lives of ABC stay
    assert list(frame["end_date"]) == [date(2010, 5, 3), date(2021, 8, 2)]


def test_the_inactive_list_pages_through_next_url_and_active_keeps_its_own_url() -> None:
    urls: list[str] = []
    second = "https://api.massive.com/v3/reference/tickers?cursor=abc"

    def transport(url: str) -> bytes:
        urls.append(url)
        if url == second:
            return fx.page(RECORDS[30:])
        return fx.page(RECORDS[:30], next_url=second)

    source = MassiveTickers(http_for(transport))
    request = FetchRequest(INACTIVE, session_date=date(2026, 10, 24))
    payload = source.fetch(request)
    assert payload is not None and len(urls) == 2 and urls[1] == second
    assert "active=false" in urls[0] and "market=stocks" in urls[0] and "limit=1000" in urls[0]
    assert "apiKey" not in urls[0] + urls[1]  # the key travels in the Authorization header
    normalized = source.normalize(request, payload)
    assert normalized is not None and not normalized.tables
    assert len(normalized.parsed[DELISTED_TABLE]) == 60  # both pages
    urls.clear()
    source.fetch(FetchRequest("active"))
    assert "active=true" in urls[0]


def test_an_empty_inactive_list_normalizes_to_nothing() -> None:
    source = MassiveTickers(http_for(lambda url: fx.page([])))
    request = FetchRequest(INACTIVE)
    assert source.normalize(request, source.fetch(request) or b"") is None
