"""``Sp500Membership`` on the RECORDED fja05680 slice."""

from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.vendors.sp500_history.membership import (
    COLUMNS,
    TABLE,
    URL,
    Sp500Membership,
    parse_membership,
)
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import published as payloads


def test_the_one_file_is_fetched_as_received() -> None:
    urls: list[str] = []
    raw = payloads.membership_csv()
    source = Sp500Membership(http_for(lambda url: urls.append(url) or raw))
    assert source.fetch(FetchRequest("membership")) == raw
    assert urls == [URL]


def test_intervals_keep_every_stay_and_an_open_end_is_none() -> None:
    rows, dropped = parse_membership(payloads.membership_csv())
    assert (
        list(rows.columns) == COLUMNS and len(rows) == 77 and set(rows["index_name"]) == {"SP500"}
    )
    assert dropped == {"no_ticker": 0, "no_start_date": 0}
    h = rows[rows["ticker"] == "H"]
    assert list(zip(h["start_date"], h["end_date"], strict=True)) == [
        (date(1996, 1, 2), date(2001, 6, 29)),
        (date(2006, 8, 1), date(2007, 4, 10)),
    ]
    assert rows.set_index("ticker").loc["AAPL", "end_date"] is None


def test_rows_without_a_ticker_or_a_start_are_dropped_and_counted() -> None:
    raw = b"ticker,start_date,end_date\nAAA,1999-01-04,\n,2000-01-03,\nBBB,,2005-01-03\nBBB,,\n"
    rows, dropped = parse_membership(raw)
    assert list(rows["ticker"]) == ["AAA"] and dropped == {"no_ticker": 1, "no_start_date": 2}


def test_normalize_exposes_the_frame_as_parsed() -> None:
    source = Sp500Membership(http_for(lambda url: b""))
    normalized = source.normalize(
        FetchRequest("x", session_date=date(2026, 10, 8)), payloads.membership_csv()
    )
    assert normalized is not None and normalized.tables == {}
    assert len(normalized.parsed[TABLE]) == 77


def test_a_file_without_the_documented_header_is_an_error() -> None:
    with pytest.raises(ValueError, match="lacks columns"):
        parse_membership(b"symbol,from\nAAA,1999-01-04\n")


def test_a_share_class_dot_becomes_the_hyphen_tiingo_uses() -> None:
    raw = b"ticker,start_date,end_date\nBRK.B,2010-02-16,\nBF.B,1996-01-02,\n"
    rows, _ = parse_membership(raw)
    assert list(rows["ticker"]) == ["BF-B", "BRK-B"]
