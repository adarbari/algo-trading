"""SEC filing history against Micron's real submissions (CIK 723125, fetched 2026-10-06, trimmed
to a handful of filings of every kind: the recent block and the one older page): only 8-K and
8-K/A rows are kept, with the form; acceptance is UTC; the older page is read only when
``since`` reaches before the recent block."""

import json
from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest, TransientFetchError
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.framework.series import FILING_COLUMNS, FILINGS_FRAME, FilingsRequest
from algotrade_sources.vendors.sec.submissions import (
    PAGES_URL,
    SUBMISSIONS_URL,
    SecFilings,
    older_pages,
    parse_documents,
    parse_filings,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import CountingLimiter, http_for

SOURCES = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
MAIN = (SOURCES / "submissions_CIK0000723125.json").read_bytes()
PAGE_NAME = "CIK0000723125-submissions-001.json"
PAGE = (SOURCES / "submissions_CIK0000723125-submissions-001.json").read_bytes()
MAIN_URL = SUBMISSIONS_URL.format(cik="0000723125")
PAGE_URL = PAGES_URL.format(name=PAGE_NAME)
OLDEST_RECENT = date(2017, 8, 18)  # the oldest filing in the recent block of the fixture


def transport_for(urls: list[str]):  # type: ignore[no-untyped-def]
    def transport(url: str) -> bytes:
        urls.append(url)
        return {MAIN_URL: MAIN, PAGE_URL: PAGE}[url]

    return transport


def test_only_8k_and_8ka_are_kept_with_their_form_and_the_columns_typed() -> None:
    frame = parse_filings(MAIN)
    assert tuple(frame.columns) == FILING_COLUMNS
    assert frame["form"].tolist() == ["8-K/A", "8-K", "8-K", "8-K", "8-K"]  # not the 4, 144, 10-Q
    assert set(frame["cik"]) == {"0000723125"}
    assert frame["filing_date"].dtype == "datetime64[ns]"
    assert frame["acceptance_ts"].dtype == "datetime64[ns, UTC]"
    assert frame["acceptance_ts"].is_monotonic_increasing  # sorted by acceptance, oldest first
    assert frame["accession"].is_unique


def test_the_earnings_filing_row_as_sec_gives_it() -> None:
    frame = parse_filings(MAIN).set_index("accession")
    row = frame.loc["0000723125-26-000018"]
    assert row["form"] == "8-K" and row["items"] == "2.02,9.01"  # the string, not a list
    assert row["filing_date"] == pd.Timestamp("2026-09-30")
    assert row["report_date"] == pd.Timestamp("2026-09-30")
    assert row["primary_document"] == "mu-20260930.htm"
    amended = frame.loc[frame["form"] == "8-K/A"].iloc[0]
    assert amended["items"] == "5.03,5.07,9.01" and amended["filing_date"] == pd.Timestamp(
        "2020-01-23"
    )


def test_acceptance_is_utc_not_the_filing_dates_midnight_or_eastern_time() -> None:
    frame = parse_filings(MAIN).set_index("accession")
    accepted = frame.loc["0000723125-26-000018", "acceptance_ts"]
    assert accepted == pd.Timestamp("2026-09-30T20:02:22Z") and str(accepted.tzinfo) == "UTC"
    assert accepted.tz_convert("America/New_York").hour == 16  # after the close
    august = frame.loc["0001104659-26-101067", "acceptance_ts"]  # EDT: UTC-4
    assert august.tz_convert("America/New_York") == pd.Timestamp("2026-08-26T08:06:55-04:00")


def test_a_filing_without_a_report_date_or_items_is_null_and_empty() -> None:
    doc = json.loads(MAIN)
    recent = doc["filings"]["recent"]
    n = recent["form"].index("8-K")
    recent["reportDate"][n] = ""
    recent["items"][n] = ""
    frame = parse_filings(json.dumps(doc).encode())
    row = frame.set_index("accession").loc[recent["accessionNumber"][n]]
    assert pd.isna(row["report_date"]) and row["items"] == ""
    assert frame["report_date"].dtype == "datetime64[ns]"


def test_since_drops_older_rows_and_an_empty_result_keeps_the_columns() -> None:
    frame = parse_filings(MAIN, since=date(2026, 7, 1))
    assert frame["filing_date"].min() == pd.Timestamp("2026-08-26")
    none = parse_filings(MAIN, since=date(2030, 1, 1))
    assert none.empty and tuple(none.columns) == FILING_COLUMNS


def test_an_older_page_is_read_as_the_same_arrays_without_the_company() -> None:
    frame = parse_filings(b"\n".join([MAIN, PAGE]))
    assert len(frame) == 8 and frame["accession"].is_unique
    assert frame["acceptance_ts"].is_monotonic_increasing
    assert frame["filing_date"].min() == pd.Timestamp("2017-06-28")
    assert set(frame["cik"]) == {"0000723125"}
    assert len(parse_documents(b"\n".join([MAIN, PAGE]))) == 2


def test_paging_decision_follows_since_against_the_oldest_recent_filing() -> None:
    doc = parse_documents(MAIN)[0]
    assert older_pages(doc, None) == []
    assert older_pages(doc, date(2026, 1, 1)) == []
    assert older_pages(doc, OLDEST_RECENT) == []  # not before it: the recent block has it
    assert older_pages(doc, date(2017, 8, 17)) == [PAGE_NAME]
    assert older_pages(doc, date(2000, 1, 1)) == [PAGE_NAME]
    assert older_pages(doc, date(2018, 1, 1)) == []


def test_only_pages_that_reach_since_are_read_and_names_stay_under_submissions() -> None:
    doc = parse_documents(MAIN)[0]
    doc["filings"]["files"] = [
        {
            "name": "CIK0000723125-submissions-002.json",
            "filingFrom": "2018-01-01",
            "filingTo": "2017-01-02",
        },
        {"name": PAGE_NAME, "filingFrom": "1994-01-06", "filingTo": "2017-08-17"},
        {
            "name": "CIK0000723125-submissions-003.json",
            "filingFrom": "1990-01-01",
            "filingTo": "1996-01-01",
        },
    ]
    assert older_pages(doc, date(2017, 1, 1)) == [
        "CIK0000723125-submissions-002.json",
        PAGE_NAME,
    ]
    doc["filings"]["files"] = [{"name": "../../other.json", "filingTo": "2017-08-17"}]
    with pytest.raises(ValueError, match="page name"):
        older_pages(doc, date(2017, 1, 1))


def test_fetch_reads_only_the_recent_block_when_since_is_inside_it() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()
    source = SecFilings(http_for(transport_for(urls), RetryPolicy(tries=1), limiter))
    payload = source.fetch(FilingsRequest("723125", since=date(2026, 1, 1)))
    assert payload == MAIN and urls == [MAIN_URL] and limiter.waits == 1
    assert source.fetch(FetchRequest("0000723125")) == MAIN  # no since: no older pages


def test_fetch_reads_the_older_page_when_since_is_before_the_recent_block() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()
    source = SecFilings(http_for(transport_for(urls), RetryPolicy(tries=1), limiter))
    request = FilingsRequest("723125", since=date(2017, 1, 1))
    payload = source.fetch(request)
    assert urls == [MAIN_URL, PAGE_URL] and limiter.waits == 2  # every request is paced
    assert payload == b"\n".join([MAIN, PAGE])
    normalized = source.normalize(request, payload)
    assert normalized is not None and normalized.session_date is None and not normalized.tables
    frame = normalized.parsed[FILINGS_FRAME]
    assert frame["filing_date"].min() == pd.Timestamp("2017-06-28") and len(frame) == 8
    # the 2016 10-K on the page is not an 8-K, and ``since`` cuts what it brought
    assert normalized.parsed[FILINGS_FRAME]["form"].isin(["8-K", "8-K/A"]).all()


def test_no_filings_is_none_a_vanished_page_is_transient_and_a_bad_cik_raises() -> None:
    def gone(url: str) -> bytes:
        raise HttpError(404)

    assert SecFilings(http_for(gone, RetryPolicy(tries=1))).fetch(FetchRequest("884394")) is None

    def page_gone(url: str) -> bytes:
        if url == MAIN_URL:
            return MAIN
        raise HttpError(404)

    source = SecFilings(http_for(page_gone, RetryPolicy(tries=1)))
    with pytest.raises(TransientFetchError):
        source.fetch(FilingsRequest("723125", since=date(2017, 1, 1)))
    with pytest.raises(ValueError, match="not a CIK"):
        source.fetch(FetchRequest("MU"))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "empty"),
        (b"<html>blocked</html>", "not JSON"),
        (b"[1]", "not a JSON object"),
        (b'{"cik": "1", "filings": {"recent": {}}}', "no filing arrays"),
        (b'{"filings": {"recent": {"form": []}}}', "no CIK"),
    ],
)
def test_malformed_answers_raise(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_filings(payload)


def test_arrays_of_different_lengths_raise() -> None:
    doc = {"cik": "1", "filings": {"recent": {"form": ["8-K", "8-K"], "items": ["2.02"]}}}
    with pytest.raises(ValueError, match="differ in length"):
        parse_filings(json.dumps(doc).encode())
