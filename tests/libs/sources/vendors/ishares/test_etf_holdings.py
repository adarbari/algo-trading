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


def test_text_without_a_table_is_a_parse_failure_not_an_empty_read() -> None:
    with pytest.raises(ValueError, match="what date"):
        source().normalize(FetchRequest("IVV"), b"<html>no csv here</html>")


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


HEADER = (
    "Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Quantity,Price,"
    "Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date"
)


def csv_file(*lines: tuple[str, str, str, str, str]) -> bytes:
    """(ticker, asset class, market value, weight, exchange) lines under the real header."""
    body = [
        f'"{t}","{t} CORP","Tech","{k}","{mv}","{w}","{mv}","1.00","1.00","United States","{x}",'
        '"USD","1.00","USD","-"'
        for t, k, mv, w, x in lines
    ]
    head = 'iShares Test ETF\nFund Holdings as of,"Oct 01, 2026"\n\n'
    return (head + "\n".join([HEADER, *body]) + "\n").encode()


def weights(payload: bytes) -> list[float]:
    normalized = source().normalize(FetchRequest("TEST"), payload)
    assert normalized is not None
    return list(normalized.parsed["holdings"]["weight"])


def test_weights_come_from_market_values_when_the_two_decimals_lose_precision() -> None:
    payload = csv_file(
        ("AAA", "Equity", "9,999,600.00", "100.00", "NYSE"),
        ("BBB", "Equity", "400.00", "0.00", "NYSE"),  # published as 0.00%
    )
    assert weights(payload) == [0.99996, 0.00004]


def test_published_weights_stand_when_market_values_disagree_or_are_missing() -> None:
    disagree = csv_file(
        ("AAA", "Equity", "100.00", "90.00", "NYSE"), ("BBB", "Equity", "100.00", "10.00", "NYSE")
    )
    assert weights(disagree) == [0.9, 0.1]
    missing = csv_file(
        ("AAA", "Equity", "-", "60.00", "NYSE"), ("BBB", "Equity", "100.00", "40.00", "NYSE")
    )
    assert weights(missing) == [0.6, 0.4]


def test_a_weight_that_does_not_read_drops_the_line_and_is_counted() -> None:
    payload = csv_file(("AAA", "Equity", "-", "60.00", "NYSE"), ("BBB", "Equity", "-", "-", "NYSE"))
    normalized = source().normalize(FetchRequest("TEST"), payload)
    assert normalized is not None and normalized.notes["unreadable_lines"] == 1
    assert list(normalized.parsed["holdings"]["holding_symbol"]) == ["AAA"]  # BBB is not 0%


def test_an_unlisted_line_is_not_a_us_listing() -> None:
    payload = csv_file(
        ("AAA", "Equity", "60.00", "60.00", "NYSE"),
        ("BBB", "Equity", "40.00", "40.00", "NO MARKET (E.G. UNLISTED)"),
    )
    normalized = source().normalize(FetchRequest("TEST"), payload)
    assert normalized is not None
    assert list(normalized.parsed["holdings"]["us_listed"]) == [True, False]


def test_a_renamed_weight_column_or_date_line_is_a_parse_failure_not_an_empty_read() -> None:
    good = csv_file(("AAA", "Equity", "100.00", "100.00", "NYSE"))
    with pytest.raises(ValueError, match="Weight"):
        source().normalize(FetchRequest("TEST"), good.replace(b"Weight (%)", b"Wt (%)"))
    with pytest.raises(ValueError, match="what date"):
        source().normalize(FetchRequest("TEST"), good.replace(b"Fund Holdings as of", b"Holdings"))
    with pytest.raises(ValueError, match="no lines"):
        source().normalize(FetchRequest("TEST"), csv_file())


def test_the_files_own_weights_are_reported_when_they_can_be_judged() -> None:
    """Market-value weights always add up to 100%; the published column is what shows that a
    file was cut short. A bond fund (most lines 0.00%) cannot be judged by it."""
    equity = csv_file(*[(f"A{i}", "Equity", "10.00", "2.00", "NYSE") for i in range(40)])
    normalized = source().normalize(FetchRequest("TEST"), equity)
    assert normalized is not None and normalized.notes["published_weight_bp"] == 8000  # 80%
    bonds = csv_file(*[(f"B{i}", "Fixed Income", "1.00", "0.00", "-") for i in range(40)])
    bonds_read = source().normalize(FetchRequest("TEST"), bonds)
    assert bonds_read is not None and "published_weight_bp" not in bonds_read.notes


def test_http_400_means_no_file() -> None:
    assert no_file(HttpError(400)) and not no_file(HttpError(403)) and not no_file(HttpError(500))


IJH = csv("IJH")  # real rows of the layout with Market Weight and Notional Weight


def ijh_holdings() -> pd.DataFrame:
    adapter = IsharesHoldings(http_for(lambda url: SCREENER if "screener" in url else IJH))
    normalized = adapter.normalize(FetchRequest("IJH"), IJH)
    assert normalized is not None
    return normalized.parsed["holdings"]


def test_the_futures_overlay_layout_is_read_by_its_market_weight() -> None:
    as_of, lines = parse_csv(IJH)
    assert as_of == date(2026, 10, 2) and "Weight (%)" not in lines[0]
    frame = ijh_holdings().set_index("holding_name")
    twilio = frame.loc["TWILIO CLASS A"]
    assert twilio["weight"] == pytest.approx(0.0131, abs=1e-4)  # Market Weight, not Notional 1.30
    assert twilio["holding_symbol"] == "TWLO" and bool(twilio["us_listed"])
    assert frame.loc["USD CASH", "weight"] == pytest.approx(0.0009, abs=1e-4)


def test_the_futures_line_has_no_market_weight_and_is_dropped() -> None:
    frame = ijh_holdings()
    assert not frame["holding_name"].str.contains("EMINI").any()  # notional weight only
    normalized = IsharesHoldings(http_for(lambda url: IJH)).normalize(FetchRequest("IJH"), IJH)
    assert normalized is not None and normalized.notes["unreadable_lines"] == 1


def test_a_file_with_neither_weight_column_is_a_layout_change() -> None:
    broken = IJH.replace(b"Market Weight", b"Mkt Wt").replace(b"Notional Weight", b"Not Wt")
    with pytest.raises(ValueError, match="Weight"):
        parse_csv(broken)
