"""State Street ETF holdings against recorded workbooks and fund finder (no network)."""

import io
from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest, HoldingsSource
from algotrade_sources.framework.holdings import HOLDING_COLUMNS
from algotrade_sources.vendors.ssga.etf_holdings import SsgaHoldings, parse_finder
from algotrade_sources.vendors.ssga.workbook import read_workbook
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources" / "ssga"
FINDER = (FIXTURES / "fundfinder.json").read_bytes()
XLK = (FIXTURES / "holdings-daily-us-en-xlk.xlsx").read_bytes()
BIL = (FIXTURES / "holdings-daily-us-en-bil.xlsx").read_bytes()


def source(urls: list[str] | None = None) -> SsgaHoldings:
    files = {"xlk": XLK, "bil": BIL}

    def transport(url: str) -> bytes:
        if urls is not None:
            urls.append(url)
        if "fundfinder" in url:
            return FINDER
        return files[url.rsplit("-", 1)[1].removesuffix(".xlsx")]

    return SsgaHoldings(http_for(transport))


def test_the_finder_lists_funds_with_a_daily_file_only() -> None:
    funds = parse_finder(FINDER)
    assert sorted(funds) == ["BIL", "DIA", "XLK"]  # GLD has no Holdings-daily document
    assert funds["XLK"][1].endswith("holdings-daily-us-en-xlk.xlsx")
    assert "®" not in funds["XLK"][0]


def test_an_equity_fund_has_tickers_cusips_and_fractional_weights() -> None:
    src = source()
    normalized = src.normalize(FetchRequest("XLK"), XLK)
    assert normalized is not None and normalized.session_date == date(2026, 10, 1)
    holdings = normalized.parsed["holdings"]
    assert tuple(holdings.columns) == HOLDING_COLUMNS
    top = holdings.iloc[0]
    assert (top["holding_symbol"], top["holding_name"]) == ("NVDA", "NVIDIA CORP")
    assert top["weight"] == pytest.approx(0.15470648)
    assert (top["identifier"], top["asset_class"], bool(top["us_listed"])) == (
        "67066G104",
        "Equity",
        True,
    )
    assert holdings["weight"].is_monotonic_decreasing


def test_a_bond_fund_has_no_tickers_and_keeps_isins() -> None:
    normalized = source().normalize(FetchRequest("BIL"), BIL)
    assert normalized is not None
    holdings = normalized.parsed["holdings"]
    assert holdings["holding_symbol"].isna().all() and not holdings["us_listed"].any()
    assert holdings["asset_class"].eq("Fixed Income").all()
    assert holdings["identifier"].iloc[0].startswith("US912797")


def test_the_directory_and_one_fund_are_fetched_through_the_finder() -> None:
    urls: list[str] = []
    src = source(urls)
    assert isinstance(src, HoldingsSource)
    directory = src.fetch(FetchRequest(src.directory_key))
    assert directory == FINDER
    funds = src.normalize(FetchRequest(src.directory_key), directory)
    assert funds is not None and list(funds.parsed["funds"]["symbol"]) == ["BIL", "DIA", "XLK"]
    assert src.fetch(FetchRequest("xlk")) == XLK
    assert src.fetch(FetchRequest("GLD")) is None  # not listed: no request is made for it
    assert urls[-1] == (
        "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xlk.xlsx"
    )
    assert len(urls) == 2


def test_a_fund_fetch_reads_the_directory_first_when_it_has_not() -> None:
    urls: list[str] = []
    assert source(urls).fetch(FetchRequest("BIL")) == BIL
    assert "fundfinder" in urls[0] and len(urls) == 2


def workbook(header: str = "Weight", weight: object = 1.5, name: str = "Name") -> bytes:
    import openpyxl  # noqa: PLC0415

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["Fund Name:", "SPDR Test"])
    sheet.append(["Ticker Symbol:", "XLK"])
    sheet.append(["Holdings:", "As of 01-Oct-2026"])
    sheet.append(
        [name, "Ticker", "Identifier", "SEDOL", header, "Sector", "Shares Held", "Local Currency"]
    )
    sheet.append(["ALPHA INC", "AAA", "037833100", "x", 60.0, "-", 10.0, "USD"])
    sheet.append(["BETA INC", "BBB", "594918104", "x", weight, "-", 10.0, "USD"])
    sheet.append(["Past performance is not a reliable indicator of future performance."])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_a_table_without_a_weight_column_is_a_parse_failure_not_a_guess() -> None:
    """It used to fall back to the first column, so the disclaimer row became a holding."""
    with pytest.raises(ValueError, match="no Weight column"):
        read_workbook(workbook(header="Wt"))
    with pytest.raises(ValueError, match="no Weight column"):
        source().normalize(FetchRequest("XLK"), workbook(header="Wt"))
    with pytest.raises(ValueError, match="no table"):
        read_workbook(workbook(name="Nome"))


def test_a_weight_that_does_not_read_drops_the_line_and_is_counted() -> None:
    normalized = source().normalize(FetchRequest("XLK"), workbook(weight="n/a"))
    assert normalized is not None and normalized.notes["unreadable_lines"] == 1
    holdings = normalized.parsed["holdings"]
    assert list(holdings["holding_name"]) == ["ALPHA INC"]  # BETA is not a 0% holding
    assert holdings["filed"].isna().all()  # a daily file is public on its own date


def test_a_file_for_another_fund_is_rejected() -> None:
    with pytest.raises(ValueError, match="the file is for XLK"):
        source().normalize(FetchRequest("DIA"), XLK)
