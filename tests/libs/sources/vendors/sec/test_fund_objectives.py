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
    assert len(frame) == 11  # the risk text and headings in the sample are not objectives
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


def test_quoted_values_and_lost_glyphs_in_real_exhibits_are_repaired() -> None:
    """Recorded rows of the 2026q2 data set: a CSV-quoted value with doubled quotes, and the
    exports that turned curly quotes and apostrophes into ``?``."""
    got = parse_objectives(ZIP).set_index("series_id")["objective"]
    assert got["S000104900"].startswith('The Corgi TPL 2x Daily ETF (the "Fund") seeks daily')
    assert "\\" not in got["S000104900"] and '""' not in got["S000104900"]
    assert got["S000029185"] == "The Fund's investment objective is capital appreciation."
    assert got["S000066116"] == (
        'The Quantified Evolution Plus Fund (the "Fund") seeks capital appreciation.'
    )
    assert got["S000051599"] == (
        'The Fund seeks long-term "total return" on capital, primarily through capital'
        " appreciation."
    )
    assert got["S000010926"].startswith('The Boyar Value Fund Inc.\'s (the "Fund") investment')
    assert got["S000007716"].startswith("VIP Equity-Income Portfolio seeks reasonable income.")
    assert got["S000004808"] == "The Blue Chip Investor Fund seeks long-term growth of capital."
    assert not any("?" in text for text in got)


def test_escaped_quotes_are_undone_if_a_value_arrives_escaped() -> None:
    raw = '\\"The Corgi ETF (the \\"\\"Fund\\"\\") seeks daily results.\\"'
    assert clean_text(raw) == 'The Corgi ETF (the "Fund") seeks daily results.'
    assert clean_text('"VanEck ETF (the ""Fund"") seeks growth."') == (
        'VanEck ETF (the "Fund") seeks growth.'
    )


def test_a_plural_is_not_turned_into_a_possessive() -> None:
    underlying = "The Fund invests in Underlying Funds principal investment strategies matter."
    assert clean_text(underlying) == underlying
    assert clean_text("Each of the Funds investment objective is growth.") == (
        "Each of the Funds investment objective is growth."
    )
    assert clean_text("The Funds investment objective is growth.") == (
        "The Fund's investment objective is growth."
    )


def test_other_artifacts_are_repaired() -> None:
    raw = "It seeks long -term growth (the ?Fund?) of capital -5% and Fund?s total return ?on top."
    assert clean_text(raw) == (
        'It seeks long-term growth (the "Fund") of capital -5% and Fund\'s total return on top.'
    )
    assert clean_text("The Fund seeks income. ?") == "The Fund seeks income."
    assert clean_text("Contrafund? Portfolio seeks income") == "Contrafund Portfolio seeks income"


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


def test_a_ticker_under_two_series_keeps_both() -> None:
    payload = (
        b'{"fields": ["cik", "seriesId", "classId", "symbol"], "data": ['
        b'[1, "S000000001", "C000000001", "AAA"], [1, "S000000002", "C000000002", "AAA"],'
        b'[1, "S000000002", "C000000002", "AAA"]]}'
    )
    funds = parse_fund_tickers(payload)
    assert list(funds["series_id"]) == ["S000000001", "S000000002"]  # not the first only


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
    assert normalized is not None and len(normalized.parsed["objectives"]) == 11
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
