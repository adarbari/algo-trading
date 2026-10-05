"""The ProShares adapter against a recorded sample of ``psdlyhld.csv`` (real rows of ACQQ, IQMM,
SVXY, UVXY, VIXY and six lines of TQQQ, as of 2026-10-02)."""

from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import RetryPolicy
from algotrade_sources.vendors.proshares.etf_holdings import (
    FILE_URL,
    ProsharesHoldings,
    asset_class,
    parse_file,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FILE = (REPO_ROOT / "tests/fixtures/sources/proshares/psdlyhld_sample.csv").read_bytes()


def source(payload: bytes = FILE, urls: list[str] | None = None) -> ProsharesHoldings:
    def transport(url: str) -> bytes:
        if urls is not None:
            urls.append(url)
        return payload

    return ProsharesHoldings(http_for(transport, RetryPolicy(tries=1)))


def holdings(ticker: str) -> object:
    adapter = source()
    adapter.fetch(FetchRequest("directory"))
    payload = adapter.fetch(FetchRequest(ticker))
    assert payload is not None
    normalized = adapter.normalize(FetchRequest(ticker), payload)
    assert normalized is not None
    return normalized


def test_the_file_is_one_request_and_lists_every_fund() -> None:
    urls: list[str] = []
    adapter = source(urls=urls)
    payload = adapter.fetch(FetchRequest("directory"))
    assert payload == FILE and urls == [FILE_URL]
    directory = adapter.normalize(FetchRequest("directory"), payload or b"")
    assert directory is not None
    funds = directory.parsed["funds"].set_index("symbol")["name"]
    assert list(funds.index) == ["ACQQ", "IQMM", "SVXY", "TQQQ", "UVXY", "VIXY"]
    assert funds["UVXY"].startswith("ProShares")


def test_a_fund_is_answered_from_the_file_already_read() -> None:
    urls: list[str] = []
    adapter = source(urls=urls)
    uvxy = adapter.fetch(FetchRequest("uvxy"))  # the directory is read first, once
    assert uvxy is not None and urls == [FILE_URL]
    assert adapter.fetch(FetchRequest("SVXY")) is not None and urls == [FILE_URL]
    assert adapter.fetch(FetchRequest("SPY")) is None  # not a ProShares fund
    assert uvxy.startswith(b"PORTFOLIO HOLDINGS INFORMATION\nAS OF 10/2/2026\n")
    assert b"SVXY" not in uvxy and b"CBOE VIX FUTURE" in uvxy


def test_weights_are_each_lines_share_of_the_funds_gross_exposure() -> None:
    result = holdings("UVXY")
    assert result.session_date == date(2026, 10, 2)
    frame = result.parsed["holdings"].set_index("holding_name")
    assert abs(frame["weight"].sum() - 1.0) < 1e-9  # a long-only fund adds up to 100%
    other = frame.loc["Net Other Assets (Liabilities)"]
    assert (other["asset_class"], other["weight"]) == ("Cash", pytest.approx(0.4, abs=0.1))
    assert frame.loc["CBOE VIX FUTURE Nov26", "asset_class"] == "Futures"
    assert frame["weight"].is_monotonic_decreasing  # largest first


def test_an_inverse_fund_keeps_its_short_lines_negative() -> None:
    frame = holdings("SVXY").parsed["holdings"].set_index("holding_name")
    assert (frame["weight"] < 0).sum() == 2 and frame["weight"].abs().sum() == pytest.approx(1.0)
    assert frame.loc["CBOE VIX FUTURE Nov26", "weight"] < 0


def test_swaps_stocks_and_etfs_are_told_apart() -> None:
    frame = holdings("ACQQ").parsed["holdings"].set_index("holding_name")
    swap = frame.loc["NDX100 35% VOLATILITY AUTOCALLABLE SWAP Bank of America NA"]
    assert swap["asset_class"] == "Derivative" and not swap["us_listed"]
    etf = frame.loc["PROSHARES GENIUS MNY MKT ETF"]
    assert (etf["holding_symbol"], etf["asset_class"], bool(etf["us_listed"])) == (
        "IQMM", "Equity", True,
    )  # fmt: skip
    assert etf["shares"] == 170000


@pytest.mark.parametrize(
    ("description", "ticker", "expected"),
    [
        ("NASDAQ 100 Index SWAP Barclays Capital", "", "Derivative"),
        ("NATURAL GAS FUTR NOV26", "", "Futures"),
        ("GOLD 100 OZ FUTR DEC26", "", "Futures"),
        ("DJIA MINI E-CBOT EQUITY INDEX 18/DEC/2026 DMZ6 INDEX", "", "Other"),
        ("Net Other Assets (Liabilities)", "", "Cash"),
        ("PROSHARES GENIUS MNY MKT ETF", "", "Money Market"),
        ("U.S. TREASURY BILL 11/12/26", "", "Bond"),
        ("EURO FX FORWARD", "", "FX"),
        ("DANAHER CORP", "DHR", "Equity"),
        ("ZURA BIO LTD COMMON STOCK", "", "Other"),
    ],
)
def test_asset_class_comes_from_the_description_and_the_ticker(
    description: str, ticker: str, expected: str
) -> None:
    line = {"Security Description": description, "Security Ticker": ticker}
    assert asset_class(line) == expected


def test_a_changed_layout_is_an_error_not_an_empty_fund() -> None:
    with pytest.raises(ValueError, match="what date"):
        parse_file(FILE.replace(b"AS OF", b"UPDATED"))
    with pytest.raises(ValueError, match="no column"):
        parse_file(FILE.replace(b"Market Value", b"Mkt Val"))
    with pytest.raises(ValueError, match="no lines"):
        parse_file(b"\n".join(FILE.split(b"\n")[:4]) + b"\n")


def test_a_fund_with_no_readable_value_is_an_error() -> None:
    header = b"\n".join(FILE.split(b"\n")[:4])
    empty = header + b'\n"ZZZZ","Z Fund","","","Net Other Assets",,,1,,,\n'
    adapter = source(empty)
    adapter.fetch(FetchRequest("directory"))
    payload = adapter.fetch(FetchRequest("ZZZZ"))
    with pytest.raises(ValueError, match="readable value"):
        adapter.normalize(FetchRequest("ZZZZ"), payload or b"")
