"""Massive ticker overview against recorded responses (KO: a stock with a description; SPY: an
ETF, which the free tier answers with identity fields only)."""

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.massive.overview import (
    MassiveOverview,
    massive_ticker,
    parse_overview,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources" / "massive"
KO = (FIXTURES / "overview_KO.json").read_bytes()
SPY = (FIXTURES / "overview_SPY.json").read_bytes()


def test_a_stock_has_a_description_website_and_head_count() -> None:
    row = parse_overview(KO, "KO").iloc[0]
    assert row["symbol"] == "KO"
    assert row["description"].startswith("Founded in 1886, Atlanta-headquartered Coca-Cola")
    assert row["homepage_url"] == "https://www.coca-colacompany.com"
    assert row["total_employees"] == 65900


def test_an_etf_gets_a_row_without_text() -> None:
    """Massive's free tier has no description for ETFs; the row is the marker the task stores."""
    row = parse_overview(SPY, "SPY").iloc[0]
    assert row["symbol"] == "SPY"
    assert row["description"] is None and row["homepage_url"] is None
    assert row["total_employees"] is None


def test_fetch_asks_for_the_massive_ticker_and_normalises() -> None:
    urls: list[str] = []

    def transport(url: str) -> bytes:
        urls.append(url)
        return KO

    source = MassiveOverview(http_for(transport, RetryPolicy(tries=1)))
    request = FetchRequest("KO")
    payload = source.fetch(request)
    assert urls == ["https://api.massive.com/v3/reference/tickers/KO"]
    normalized = source.normalize(request, payload or b"")
    assert normalized is not None and normalized.parsed["overview"].iloc[0]["symbol"] == "KO"


def test_an_unknown_ticker_is_nothing_there() -> None:
    def transport(url: str) -> bytes:
        raise HttpError(404)

    source = MassiveOverview(http_for(transport, RetryPolicy(tries=1)))
    assert source.fetch(FetchRequest("ZZZZ")) is None


@pytest.mark.parametrize(
    ("symbol", "ticker"), [("KIM$L", "KIMpL"), ("BRK.B", "BRK.B"), ("AAPL", "AAPL")]
)
def test_preferred_symbols_map_back_to_massive_tickers(symbol: str, ticker: str) -> None:
    assert massive_ticker(symbol) == ticker


def test_a_response_without_results_still_gives_a_marker_row() -> None:
    row = parse_overview(b'{"status": "OK"}', "NEW").iloc[0]
    assert row["symbol"] == "NEW" and row["description"] is None
