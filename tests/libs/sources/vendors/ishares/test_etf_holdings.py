"""iShares ETF holdings against recorded CSVs and product screener (no network)."""

from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest, HoldingsSource
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.ishares.etf_holdings import (
    IsharesHoldings,
    no_file,
    parse_csv,
    parse_screener,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources" / "ishares"
SCREENER = (FIXTURES / "product-screener.json").read_bytes()


def csv(fund: str) -> bytes:
    return (FIXTURES / f"{fund}_latest-holdings.csv").read_bytes()


def source(urls: list[str] | None = None) -> IsharesHoldings:
    def transport(url: str) -> bytes:
        if urls is not None:
            urls.append(url)
        if "product-screener" in url:
            return SCREENER
        return csv(_fund_of(url))

    return IsharesHoldings(http_for(transport, RetryPolicy(tries=1)))


def _fund_of(url: str) -> str:
    for fund, slug in (("IVV", "core-sp-500"), ("IWM", "russell-2000"), ("AGG", "bond-market")):
        if slug in url:
            return fund
    raise AssertionError(url)


def test_the_screener_maps_tickers_to_fund_pages() -> None:
    funds = parse_screener(SCREENER)
    assert sorted(funds) == ["AGG", "EFA", "IVV", "IWM", "SLV"]
    assert funds["IVV"][1] == "/us/products/239726/ishares-core-sp-500-etf"


def test_an_equity_fund_parses_the_table_and_the_as_of_date() -> None:
    as_of, lines = parse_csv(csv("IVV"))
    assert as_of == date(2026, 10, 1) and lines[0]["Ticker"] == "NVDA"
    normalized = source().normalize(FetchRequest("IVV"), csv("IVV"))
    assert normalized is not None and normalized.session_date == date(2026, 10, 1)
    holdings = normalized.parsed["holdings"]
    top = holdings.iloc[0]
    assert (top["holding_symbol"], top["weight"], top["asset_class"]) == ("NVDA", 0.0844, "Equity")
    assert bool(top["us_listed"]) and top["shares"] == 322517198.0
    futures = holdings[holdings["asset_class"] == "Futures"].iloc[0]
    assert not futures["us_listed"]  # a future's code is never linked to an instrument


def test_share_classes_use_the_universe_style_and_blank_tickers_stay_name_only() -> None:
    holdings = source().normalize(FetchRequest("IWM"), csv("IWM")).parsed["holdings"]  # type: ignore[union-attr]
    assert "MOG.A" in set(holdings["holding_symbol"])  # printed "MOG A"
    unlisted = holdings[holdings["holding_name"] == "RENT THE RUNWAY INC"].iloc[0]
    assert pd.isna(unlisted["holding_symbol"])
    cash = holdings[holdings["holding_name"] == "USD CASH"].iloc[0]
    assert cash["weight"] == pytest.approx(-0.001) and not cash["us_listed"]


def test_a_foreign_line_is_not_a_us_listing_even_when_its_ticker_clashes() -> None:
    holdings = source().normalize(FetchRequest("EFA"), csv("EFA")).parsed["holdings"]  # type: ignore[union-attr]
    roche = holdings[holdings["holding_name"] == "ROCHE PS PAR AG"].iloc[0]
    assert roche["holding_symbol"] == "ROP" and not roche["us_listed"]  # Roper's ticker in the U.S.


def test_a_bond_fund_has_cusips_and_no_tickers() -> None:
    holdings = source().normalize(FetchRequest("AGG"), csv("AGG")).parsed["holdings"]  # type: ignore[union-attr]
    assert holdings["holding_symbol"].isna().all() and not holdings["us_listed"].any()
    assert holdings["identifier"].iloc[0] == "066922519"
    assert holdings["shares"].iloc[0] == pytest.approx(4460909058.0)


def test_text_without_a_table_is_nothing() -> None:
    assert source().normalize(FetchRequest("IVV"), b"<html>no csv here</html>") is None


def test_fetch_goes_through_the_screener_to_the_fund_page() -> None:
    urls: list[str] = []
    src = source(urls)
    assert isinstance(src, HoldingsSource)
    funds = src.normalize(
        FetchRequest(src.directory_key), src.fetch(FetchRequest("directory")) or b""
    )
    assert funds is not None and len(funds.parsed["funds"]) == 5
    assert src.fetch(FetchRequest("ivv")) == csv("IVV")
    assert urls[-1] == (
        "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/latest-holdings.csv"
    )
    assert src.fetch(FetchRequest("QQQ")) is None  # not an iShares fund: no request
    assert len(urls) == 2


def test_http_400_means_no_file() -> None:
    assert no_file(HttpError(400)) and not no_file(HttpError(403)) and not no_file(HttpError(500))
