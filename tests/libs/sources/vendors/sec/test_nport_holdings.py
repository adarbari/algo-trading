"""SEC N-PORT holdings against recorded responses (no network)."""

from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest, HoldingsSource, Normalized
from algotrade_sources.vendors.sec.nport_holdings import (
    NportHoldings,
    parse_filings,
    parse_funds,
    parse_report,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
FUNDS = (FIXTURES / "company_tickers_mf.json").read_bytes()
SUBMISSIONS = (FIXTURES / "submissions_vanguard_index_funds.json").read_bytes()
REPORT = (FIXTURES / "nport_total_stock_market_trimmed.xml").read_bytes()
HEADER = (FIXTURES / "nport_header_0000036405-26-000480.html").read_bytes()
OTHER_SERIES = {  # the three newer filings of the trust belong to other funds
    "0000036405-26-000483": b"<SERIES-ID>S000002900 headers of another fund",
    "0000036405-26-000482": b"<SERIES-ID>S000002901 headers of another fund",
    "0000036405-26-000481": b"<SERIES-ID>S000002902 headers of another fund",
}


def source(urls: list[str] | None = None) -> NportHoldings:
    def transport(url: str) -> bytes:
        if urls is not None:
            urls.append(url)
        if url.endswith("company_tickers_mf.json"):
            return FUNDS
        if "submissions/CIK0000036405" in url:
            return SUBMISSIONS
        if url.endswith("-index-headers.html"):
            accession = url.rsplit("/", 1)[1].removesuffix("-index-headers.html")
            return HEADER if accession.endswith("000480") else OTHER_SERIES[accession]
        if url.endswith("/000003640526000480/primary_doc.xml"):
            return REPORT
        raise AssertionError(url)

    return NportHoldings(http_for(transport))


def test_the_directory_maps_tickers_to_a_trust_and_series() -> None:
    funds = parse_funds(FUNDS)
    assert funds["VTI"] == ("0000036405", "S000002848")
    assert funds["QQQ"] == ("0001067839", "S000101292")
    assert funds["VOO"][1] == funds["VFIAX"][1]  # share classes of one series


def test_filings_are_the_nport_p_forms_newest_first() -> None:
    filings = parse_filings(SUBMISSIONS)
    assert [a for a, _ in filings] == [
        "0000036405-26-000483",
        "0000036405-26-000482",
        "0000036405-26-000481",
        "0000036405-26-000480",
    ]  # the 497K is not a portfolio report
    assert filings[0][1] == date(2026, 8, 28)


def test_the_report_has_names_cusips_and_fractional_weights_but_no_tickers() -> None:
    as_of, series, rows = parse_report(REPORT)
    assert series == "S000002848"
    assert as_of == date(2026, 6, 30) and len(rows) == 5
    first = rows[0]
    assert first["holding_name"] == "NVIDIA Corp"
    assert first["identifier"] == "67066G104" and first["asset_class"] == "Equity"
    assert first["weight"] == pytest.approx(0.063554, abs=1e-6)  # pctVal 6.3554 (percent)
    assert first["holding_symbol"] is None and not first["us_listed"]  # linked by the task
    assert first["shares"] == pytest.approx(729853903.0)


def test_normalize_orders_by_weight_and_sets_the_report_date() -> None:
    normalized = source().normalize(FetchRequest("VTI"), REPORT)
    assert normalized is not None and normalized.session_date == date(2026, 6, 30)
    assert normalized.parsed["holdings"]["weight"].is_monotonic_decreasing


def test_a_funds_filing_is_found_by_reading_headers_newest_first_and_cached() -> None:
    urls: list[str] = []
    src = source(urls)
    assert isinstance(src, HoldingsSource) and src.cadence_days == 90 and src.scope_limited
    assert src.fetch(FetchRequest("directory")) == FUNDS
    assert src.fetch(FetchRequest("vti")) == REPORT
    headers = [u for u in urls if u.endswith("-index-headers.html")]
    assert len(headers) == 4  # three other funds' filings, then VTI's
    urls.clear()
    assert src.fetch(FetchRequest("VOO")) is None  # its series filed nothing in the list
    assert not any(u.endswith("-index-headers.html") for u in urls)  # all four were cached
    assert src.fetch(FetchRequest("SCHD")) is None  # not in the directory: no request at all


def test_rows_carry_the_filing_date_so_readers_can_hide_them_until_then() -> None:
    src = source()
    src.fetch(FetchRequest("directory"))
    payload = src.fetch(FetchRequest("VTI")) or b""
    holdings = (src.normalize(FetchRequest("VTI"), payload) or Normalized(None, {})).parsed[
        "holdings"
    ]
    assert set(holdings["filed"]) == {date(2026, 8, 28)}  # from the trust's filing list


def test_a_replay_from_raw_assumes_the_filing_deadline() -> None:
    """No filing list in hand: 60 days after the period is when an N-PORT-P is due."""
    holdings = source().normalize(FetchRequest("VTI"), REPORT).parsed["holdings"]  # type: ignore[union-attr]
    assert set(holdings["filed"]) == {date(2026, 8, 29)}


def test_unreadable_weights_are_dropped_not_read_as_zero() -> None:
    broken = REPORT.replace(b"<pctVal>6.355382492074<", b"<pctVal>n/a<", 1)
    assert broken != REPORT
    normalized = source().normalize(FetchRequest("VTI"), broken)
    assert normalized is not None and normalized.notes["unreadable_lines"] == 1
    assert len(normalized.parsed["holdings"]) == 4


def test_a_report_without_holdings_is_a_parse_failure_not_an_empty_read() -> None:
    with pytest.raises(ValueError, match="no holdings"):
        source().normalize(FetchRequest("VTI"), REPORT.replace(b"invstOrSec", b"other"))
