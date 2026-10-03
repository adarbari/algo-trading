from datetime import date

import pytest

from algotrade_ingestion.sources.framework.base import FetchRequest
from algotrade_ingestion.sources.framework.http import RetryPolicy
from algotrade_ingestion.sources.vendors.nasdaq.symbol_directory import (
    NasdaqTraderSource,
    parse_listings,
    parse_option_underlyings,
)
from algotrade_ingestion.sources.vendors.ssga.spy_holdings import SpyHoldingsSource, parse_holdings
from algotrade_ingestion.tasks.reference.classify import security_type
from tests import universe_fixture as fx
from tests.ingest_helpers import http_for


def test_parse_listings_both_files() -> None:
    n = parse_listings(
        "nasdaqlisted",
        fx.nasdaq([("AAPL", "Apple Inc. - Common Stock", "N", "N"), ("ZTST", "Test Co", "N", "Y")]),
    )
    assert list(n["symbol"]) == ["AAPL", "ZTST"]
    assert list(n["exchange"]) == ["NASDAQ", "NASDAQ"]
    assert list(n["is_test_issue"]) == [False, True]
    o = parse_listings(
        "otherlisted",
        fx.other(
            [
                ("BRK.B", "Berkshire Common Stock", "N", "N"),
                ("SPY", "SPDR S&P 500 ETF Trust", "P", "Y"),
                ("ODD", "Odd venue", "M", "N"),
            ]
        ),
    )
    assert list(o["exchange"]) == ["NYSE", "NYSE_ARCA", "M"]
    assert list(o["is_etf"]) == [False, True, False]


def test_option_underlyings_are_distinct() -> None:
    assert list(parse_option_underlyings(fx.options(["SPY", "AAPL", "SPY"]))["symbol"]) == [
        "AAPL",
        "SPY",
    ]


def test_parse_spy_holdings_skips_cash_and_disclaimers() -> None:
    holdings, as_of, skipped = parse_holdings(fx.spy(["NVDA", "BRK.B"]))
    assert list(holdings["symbol"]) == ["NVDA", "BRK.B"]
    assert as_of == date(2026, 10, 1)
    assert skipped == 1


def test_sources_fetch_and_normalize() -> None:
    payloads = {"nasdaqlisted": fx.nasdaq([("AAPL", "Apple", "N", "N")])}
    urls: list[str] = []

    def transport(url: str) -> bytes:
        urls.append(url)
        return payloads["nasdaqlisted"] if "nasdaqlisted" in url else fx.spy(["AAPL"])

    nasdaq = NasdaqTraderSource(http_for(transport, RetryPolicy(tries=1)))
    request = FetchRequest("nasdaqlisted")
    normalized = nasdaq.normalize(request, nasdaq.fetch(request) or b"")
    assert normalized is not None and list(normalized.parsed["nasdaqlisted"]["symbol"]) == ["AAPL"]
    with pytest.raises(ValueError, match="unknown Nasdaq Trader file"):
        nasdaq.fetch(FetchRequest("nope"))
    assert nasdaq.normalize(FetchRequest("options"), fx.options([])) is None
    spy = SpyHoldingsSource(http_for(transport))
    result = spy.normalize(FetchRequest("SPY"), spy.fetch(FetchRequest("SPY")) or b"")
    assert result is not None and result.session_date == date(2026, 10, 1)
    assert spy.normalize(FetchRequest("SPY"), fx.spy([])) is None
    assert "nasdaqtrader.com" in urls[0]


@pytest.mark.parametrize(
    ("name", "symbol", "is_etf", "expected"),
    [
        ("Apple Inc. - Common Stock", "AAPL", False, "COMMON_STOCK"),
        ("AllianceBernstein Holding L.P.  Units", "AB", False, "COMMON_STOCK"),
        ("Energy Transfer LP Common Units", "ET", False, "COMMON_STOCK"),
        ("ATA Creativity Global - American Depositary Shares", "AACG", False, "ADR"),
        (
            "Arbor Realty Trust 6.375% Series D Cumulative Redeemable Preferred Stock",
            "ABR$D",
            False,
            "PREFERRED",
        ),
        (
            "Bank X Depositary Shares, each representing a 1/1000th interest in a Preferred share",
            "BX$A",
            False,
            "PREFERRED",
        ),
        ("Ares Acquisition Corporation III Redeemable warrants", "AAC.W", False, "WARRANT"),
        (
            "Ares Acquisition Corp Units, each consisting of one share and one warrant",
            "AAC.U",
            False,
            "UNIT",
        ),
        ("Some SPAC Rights", "SPC.R", False, "RIGHT"),
        ("Abacus 9.875% Fixed Rate Senior Notes due 2028", "ABXL", False, "NOTE"),
        ("iPath Bloomberg Commodity ETN", "DJP", True, "ETN"),
        ("AdvisorShares Dorsey Wright ADR ETF", "AADR", True, "ETF"),
        ("Unnamed security", "XYZ$B", False, "PREFERRED"),
        ("Plain name", "XYZ.WS", False, "WARRANT"),
    ],
)
def test_security_type(name: str, symbol: str, is_etf: bool, expected: str) -> None:
    assert security_type(name, symbol, is_etf) == expected
