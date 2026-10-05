"""SEC fund objectives against a recorded sample of the 2026q2 prospectus data set (five series
carved from the real zip) and of ``company_tickers_mf.json``."""

import io
import zipfile
from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sec.fund_objectives import (
    SecFundObjectives,
    SecFundTickerMap,
    clean_text,
    parse_fund_tickers,
    parse_objectives,
    shorten,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
ZIP = (FIXTURES / "rr1_2026q2_sample.zip").read_bytes()
FUNDS = (FIXTURES / "company_tickers_mf_sample.json").read_bytes()


def test_objectives_are_the_latest_clean_text_per_series() -> None:
    frame = parse_objectives(ZIP).set_index("series_id")
    assert len(frame) == 5  # the risk text and headings in the sample are not objectives
    vanguard = frame.loc["S000002562"]
    assert vanguard["objective"].startswith("Vanguard Long-Term Bond Index Fund (the Fund) seeks")
    first_trust = frame.loc["S000031800"]["objective"]
    assert "&amp;" not in first_trust and "(the Fund )" not in first_trust
    assert "  " not in first_trust
    assert isinstance(vanguard["filed"], date) and vanguard["accn"] and vanguard["form"]


def test_ampersands_and_spaces_before_punctuation_are_cleaned() -> None:
    raw = "<p>The Fund seeks the S&amp;P  500 Index (the Index ) , before fees.</p>"
    assert clean_text(raw) == "The Fund seeks the S&P 500 Index (the Index), before fees."
    assert clean_text("A &amp;amp; B") == "A & B"  # escaped twice


def test_known_xbrl_artifacts_are_repaired() -> None:
    raw = "The Funds investment objective is long -term growth (the ?Fund?) of capital -5%."
    assert clean_text(raw) == (
        'The Fund\'s investment objective is long-term growth (the "Fund") of capital -5%.'
    )
    assert clean_text("Is it so?") == "Is it so?"  # a real question mark stays


def test_long_text_is_cut_at_a_sentence() -> None:
    text = "First sentence here. " * 100
    cut = shorten(text, 100)
    assert len(cut) <= 100 and cut.endswith("here.")
    assert shorten("no sentences " * 20, 50).endswith("...")
    assert shorten("short", 100) == "short"


def test_a_newer_filing_wins_within_a_quarter() -> None:
    def tsv(rows: list[list[str]]) -> str:
        return "\n".join("\t".join(r) for r in rows) + "\n"

    sub = tsv(
        [["adsh", "form", "filed"], ["a-1", "485BPOS", "20260401"], ["a-2", "497", "20260515"]]
    )
    head = ["adsh", "tag", "series", "value"]
    tag = "ObjectivePrimaryTextBlock"
    txt = tsv(
        [
            head,
            ["a-1", tag, "S000000001", "The Old Fund seeks long term growth of capital."],
            ["a-2", tag, "S000000001", "The New Fund seeks long term growth of capital."],
            ["a-2", tag, "BADSERIES", "The Fund seeks something but its series id is bad."],
            ["a-2", tag, "S000000002", "Too short"],
        ]
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("sub.tsv", sub)
        archive.writestr("txt.tsv", txt)
    frame = parse_objectives(buffer.getvalue())
    assert list(frame["series_id"]) == ["S000000001"]
    assert frame.iloc[0]["objective"].startswith("The New Fund") and frame.iloc[0]["accn"] == "a-2"
    assert frame.iloc[0]["filed"] == date(2026, 5, 15) and frame.iloc[0]["form"] == "497"


def test_fund_tickers_map_symbols_to_series() -> None:
    funds = parse_fund_tickers(FUNDS).set_index("symbol")
    assert funds.loc["QQQ", "series_id"] == "S000101292"
    assert funds.loc["VOO", "series_id"] == funds.loc["VFINX", "series_id"]  # share classes
    assert funds.loc["XLK", "cik"] == "0001064641"


def test_sources_fetch_their_files_and_report_missing_quarters() -> None:
    urls: list[str] = []

    def transport(url: str) -> bytes:
        urls.append(url)
        if "2030q1" in url:
            raise HttpError(404)  # not published yet
        return FUNDS if url.endswith(".json") else ZIP

    http = http_for(transport, RetryPolicy(tries=1))
    objectives, tickers = SecFundObjectives(http), SecFundTickerMap(http)
    request = FetchRequest("2026q2")
    payload = objectives.fetch(request)
    normalized = objectives.normalize(request, payload or b"")
    assert normalized is not None and len(normalized.parsed["objectives"]) == 5
    assert urls[0].endswith("/return-summary-data-sets/2026q2_rr1.zip")
    assert objectives.fetch(FetchRequest("2030q1")) is None
    assert tickers.fetch(FetchRequest("fund_tickers")) == FUNDS
    assert urls[-1] == "https://www.sec.gov/files/company_tickers_mf.json"
    mapped = tickers.normalize(FetchRequest("fund_tickers"), FUNDS)
    assert mapped is not None and "QQQ" in set(mapped.parsed["funds"]["symbol"])


@pytest.mark.parametrize("key", ["2026", "2026q5", "../x", "latest"])
def test_a_request_key_must_be_a_quarter(key: str) -> None:
    source = SecFundObjectives(http_for(lambda url: b"", RetryPolicy(tries=1)))
    with pytest.raises(ValueError, match="quarter"):
        source.fetch(FetchRequest(key))
