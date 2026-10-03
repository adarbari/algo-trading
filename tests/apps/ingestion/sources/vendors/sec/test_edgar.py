"""SEC EDGAR adapter: parsing recorded-shape payloads, SIC sectors, pacing and errors."""

import pytest

from algotrade_ingestion.sources.framework.base import FetchRequest
from algotrade_ingestion.sources.framework.http import HttpError, RetryPolicy
from algotrade_ingestion.sources.vendors.sec.edgar import (
    SUBMISSIONS_URL,
    TICKERS_URL,
    SecSubmissions,
    SecTickerMap,
    act_symbol,
    pad_cik,
    parse_submissions,
    parse_tickers,
    user_agent,
)
from algotrade_ingestion.sources.vendors.sec.sic import sic_division, sic_sector
from tests.helpers.ingest_fakes import CountingLimiter, http_for
from tests.helpers.payloads.sec import submissions, tickers


def test_pad_cik_and_symbols() -> None:
    assert pad_cik(320193) == pad_cik("0000320193") == pad_cik(320193.0) == "0000320193"
    assert [pad_cik(v) for v in (None, float("nan"), "", "abc", 0)] == [None] * 5
    assert [act_symbol(t) for t in ("brk-b", "ABR-PD", "AAPL")] == ["BRK.B", "ABR$D", "AAPL"]
    assert user_agent("ops@example.org") == "algotrade-ingestion/0.1 ops@example.org"


def test_parse_ticker_map() -> None:
    frame = parse_tickers(
        tickers(
            [
                (320193, "Apple Inc.", "AAPL", "Nasdaq"),
                (1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"),
                (1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"),  # duplicate
                (0, "Broken", "BAD", "NYSE"),
                (1234, "No ticker", "", "OTC"),
            ]
        )
    )
    assert frame.to_dict("records") == [
        {"cik": "0000320193", "sec_name": "Apple Inc.", "symbol": "AAPL", "sec_exchange": "Nasdaq"},
        {
            "cik": "0001067983",
            "sec_name": "BERKSHIRE HATHAWAY INC",
            "symbol": "BRK.B",
            "sec_exchange": "NYSE",
        },
    ]
    assert parse_tickers(b'{"fields": [], "data": []}').empty


def test_parse_submissions() -> None:
    row = parse_submissions(
        submissions(320193, "Apple Inc.", former=("APPLE COMPUTER INC", "APPLE COMPUTER INC"))
    ).iloc[0]
    assert row["cik"] == "0000320193"
    assert (row["sic"], row["sector"], row["industry"]) == (
        "3571",
        "Technology",
        "Electronic Computers",
    )
    assert row["sic_division"] == "Manufacturing"
    assert (row["state_of_incorporation"], row["fiscal_year_end"]) == ("CA", "0926")
    assert row["website"] is None  # SEC leaves it blank for most filers
    assert row["former_names"] == "APPLE COMPUTER INC"
    assert (row["exchanges"], row["tickers"]) == ("Nasdaq", "AAPL")
    fund = parse_submissions(
        submissions(884394, "SPDR S&P 500  ETF TRUST", sic="", sic_description="", website="x.com")
    ).iloc[0]
    assert (fund["sic"], fund["sector"], fund["website"]) == (None, None, "x.com")
    assert fund["name"] == "SPDR S&P 500 ETF TRUST"
    with pytest.raises(ValueError, match="no CIK"):
        parse_submissions(b'{"name": "x"}')


@pytest.mark.parametrize(
    ("sic", "sector", "division"),
    [
        ("2834", "Health Care", "Manufacturing"),
        ("6022", "Financials", "Finance, Insurance and Real Estate"),
        ("6798", "Real Estate", "Finance, Insurance and Real Estate"),
        ("1311", "Energy", "Mining"),
        ("4911", "Utilities", "Transportation, Communications and Utilities"),
        ("4953", "Industrials", "Transportation, Communications and Utilities"),
        ("7372", "Technology", "Services"),
        ("5812", "Consumer Discretionary", "Retail Trade"),
        ("3560", "Industrials", "Manufacturing"),
        ("0100", "Consumer Staples", "Agriculture, Forestry and Fishing"),
        ("9995", None, None),
        (None, None, None),
    ],
)
def test_sic_sectors(sic: str | None, sector: str | None, division: str | None) -> None:
    assert (sic_sector(sic), sic_division(sic)) == (sector, division)


def test_sources_pace_and_build_urls() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()

    def transport(url: str) -> bytes:
        urls.append(url)
        return tickers([(1, "A", "A", "NYSE")]) if url == TICKERS_URL else submissions(1, "A")

    ticker_map = SecTickerMap(http_for(transport, limiter=limiter))
    subs = SecSubmissions(http_for(transport, limiter=limiter))
    payload = ticker_map.fetch(FetchRequest("tickers"))
    assert payload is not None
    normalized = ticker_map.normalize(FetchRequest("tickers"), payload)
    assert normalized is not None and len(normalized.parsed["tickers"]) == 1
    assert subs.fetch(FetchRequest("1")) is not None
    assert urls == [TICKERS_URL, SUBMISSIONS_URL.format(cik="0000000001")]
    assert limiter.waits == 2  # both sources wait on the one shared limiter
    assert ticker_map.normalize(FetchRequest("tickers"), tickers([])) is None
    with pytest.raises(ValueError, match="not a CIK"):
        subs.fetch(FetchRequest("AAPL"))


def test_not_found_is_none_and_forbidden_is_an_error() -> None:
    def transport(url: str) -> bytes:
        raise HttpError(404 if url.endswith("CIK0000000404.json") else 403)

    subs = SecSubmissions(http_for(transport, RetryPolicy(tries=1)))
    assert subs.fetch(FetchRequest("404")) is None
    with pytest.raises(RuntimeError, match="giving up"):
        subs.fetch(FetchRequest("403"))
    default = SecSubmissions(http_for(lambda url: b"{}"))  # default policy and limiter
    assert default.fetch(FetchRequest("1")) == b"{}"
