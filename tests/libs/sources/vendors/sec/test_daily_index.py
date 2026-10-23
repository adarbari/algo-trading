"""SEC daily form index against a real day (2026-09-30, trimmed to a few lines of every kind):
only the 8-K and 8-K/A lines are kept, with the CIK padded and the accession from the file name;
a day without an index (S3's 403 AccessDenied, or 404) is ``None``, never an empty day; a block
or an 8-K line that does not parse is an error."""

from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import GaveUpError, HttpError, RetryPolicy
from algotrade_sources.framework.series import (
    DAILY_INDEX_COLUMNS,
    DAILY_INDEX_FRAME,
    DailyIndexRequest,
)
from algotrade_sources.vendors.sec.daily_index import (
    SecDailyIndex,
    full_index_url,
    index_url,
    missing_index,
    parse_index,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
INDEX = (FIXTURE / "daily_index_form_20260930_trimmed.idx").read_bytes()
DAY = date(2026, 9, 30)
DENIED = b'<?xml version="1.0"?><Error><Code>AccessDenied</Code></Error>'


def request(day: date = DAY) -> DailyIndexRequest:
    return DailyIndexRequest(key=day.isoformat(), day=day)


def test_the_url_names_the_quarter_and_the_day() -> None:
    assert index_url(DAY).endswith("/daily-index/2026/QTR3/form.20260930.idx")
    assert index_url(date(2026, 1, 2)).endswith("/2026/QTR1/form.20260102.idx")
    assert index_url(date(2026, 10, 7)).endswith("/2026/QTR4/form.20261007.idx")


def test_only_8k_and_8ka_lines_are_kept() -> None:
    frame = parse_index(INDEX)
    assert list(frame.columns) == list(DAILY_INDEX_COLUMNS)
    assert set(frame["form"]) == {"8-K", "8-K/A"} and len(frame) == 5  # not 10-K, 4, 424B2, D, S-1
    micron = frame[frame["cik"] == "0000723125"].iloc[0]
    assert micron["accession"] == "0000723125-26-000018" and micron["form"] == "8-K"
    assert micron["filing_date"] == pd.Timestamp("2026-09-30")
    assert str(frame["filing_date"].dtype) == "datetime64[ns]"
    assert list(frame["accession"]) == sorted(frame["accession"])
    assert frame.loc[frame["form"] == "8-K/A", "cik"].tolist() == ["0001108134", "0002152423"]


def test_a_day_without_8ks_is_an_empty_frame() -> None:
    header = INDEX.split(b"10-K", 1)[0]
    frame = parse_index(header)
    assert frame.empty and list(frame.columns) == list(DAILY_INDEX_COLUMNS)


def test_an_8k_line_that_does_not_parse_is_an_error() -> None:
    with pytest.raises(ValueError, match="unexpected daily index line"):
        parse_index(INDEX + b"8-K   no cik or date here\n")


def test_fetch_and_normalize_over_a_fake_transport() -> None:
    urls: list[str] = []

    def transport(url: str) -> bytes:
        urls.append(url)
        return INDEX

    source = SecDailyIndex(http_for(transport))
    payload = source.fetch(request())
    assert payload == INDEX and urls == [index_url(DAY)]
    normalized = source.normalize(request(), payload)
    assert normalized is not None and len(normalized.parsed[DAILY_INDEX_FRAME]) == 5


@pytest.mark.parametrize("error", [HttpError(404), HttpError(403, body=DENIED)])
def test_a_day_without_an_index_is_none(error: HttpError) -> None:
    def transport(url: str) -> bytes:
        raise error

    source = SecDailyIndex(http_for(transport, RetryPolicy(tries=1, not_found=missing_index)))
    assert source.fetch(request()) is None


def test_a_block_is_an_error_not_a_missing_day() -> None:
    assert missing_index(HttpError(403, body=DENIED)) and not missing_index(HttpError(404))
    assert not missing_index(HttpError(403, body=b"<html>Request Rate Threshold Exceeded</html>"))

    def transport(url: str) -> bytes:
        raise HttpError(403, body=b"<html>blocked</html>")

    source = SecDailyIndex(http_for(transport, RetryPolicy(tries=1, not_found=missing_index)))
    with pytest.raises(GaveUpError):
        source.fetch(request())


def test_a_plain_request_is_refused() -> None:
    with pytest.raises(TypeError, match="DailyIndexRequest"):
        SecDailyIndex(http_for(lambda url: INDEX)).fetch(FetchRequest("2026-09-30"))


EVENT_FORMS = (FIXTURE / "daily_index_event_forms_trimmed.idx").read_bytes()  # real lines, 4 days


def test_event_forms_are_kept_with_spaces_in_the_form_and_the_longest_form_wins() -> None:
    frame = parse_index(EVENT_FORMS)
    by_form = frame.groupby("form")["cik"].apply(list).to_dict()
    kept = {"10-12B", "424B4", "SC TO-I", "25-NSE", "NT 10-K", "NT 10-Q", "8-K", "25"}
    assert set(by_form) == kept
    assert len(frame) == 11 and frame["accession"].is_unique
    assert "0002101664" in by_form["10-12B"]  # Form 10 of a spin-off candidate
    assert "0001893219" in by_form["25-NSE"]  # the issuer
    assert "0000876661" in by_form["25-NSE"]  # the exchange's own line
    assert len(by_form["25"]) == 1  # the issuer's own Form 25 is not the 25-NSE line
    assert len(by_form["SC TO-I"]) == 1  # its SC TO-I/A amendment is left out
    assert "0001744494" in by_form["NT 10-K"] and len(by_form["NT 10-Q"]) == 2


def test_forms_that_only_start_like_an_event_form_are_skipped() -> None:
    line = "{:<17}{:<62}{:<12}20260930    edgar/data/5/0000000005-26-000001.txt\n"
    for form in ("NT 10-K/A", "NT 11-K", "25-NSE/A", "424B40", "SC TO-I/A", "8-KT"):
        assert parse_index(line.format(form, "SOME CO", "5").encode()).empty, form


def test_the_insider_forms_are_read_from_the_same_index_and_424b4_is_not_a_form_4() -> None:
    lines = (
        b"4                   ACME CORP                                         111       20260930"
        b"    edgar/data/111/0000111-26-000001.txt\n"
        b"4/A                 ACME CORP                                         111       20260930"
        b"    edgar/data/111/0000111-26-000002.txt\n"
        b"424B4               ACME CORP                                         111       20260930"
        b"    edgar/data/111/0000111-26-000003.txt\n"
        b"8-K                 ACME CORP                                         111       20260930"
        b"    edgar/data/111/0000111-26-000004.txt\n"
    )
    frame = parse_index(lines, ("4", "4/A"))
    assert frame["form"].tolist() == ["4", "4/A"]
    assert frame["accession"].tolist() == ["0000111-26-000001", "0000111-26-000002"]
    assert parse_index(lines)["form"].tolist() == ["424B4", "8-K"]  # the event forms, no Form 4
    source = SecDailyIndex(http_for(lambda url: lines))
    asked = DailyIndexRequest(key="2026-09-30", day=DAY, forms=("4", "4/A"))
    normalized = source.normalize(asked, lines)
    assert normalized is not None and len(normalized.parsed[DAILY_INDEX_FRAME]) == 2


def test_the_full_index_url_names_the_quarter() -> None:
    assert full_index_url(date(2011, 7, 5)).endswith("/full-index/2011/QTR3/form.idx")
    assert full_index_url(date(2026, 1, 2)).endswith("/full-index/2026/QTR1/form.idx")


def test_fetch_full_asks_for_the_quarters_full_index() -> None:
    urls: list[str] = []

    def transport(url: str) -> bytes:
        urls.append(url)
        return INDEX

    day = date(2011, 7, 5)
    asked = DailyIndexRequest(key="2011Q3", day=day, full=True)
    SecDailyIndex(http_for(transport)).fetch(asked)
    assert urls == [full_index_url(day)] and "daily-index" not in urls[0]


def test_parse_full_index_reads_dashed_dates_per_line() -> None:
    payload = (FIXTURE / "full_index_form_2011q3_hand_built.idx").read_bytes()
    frame = parse_index(payload, ("10-K", "10-Q", "10-K/A"), full=True)
    assert set(frame["filing_date"].dt.date) == {
        date(2011, 7, 1),
        date(2011, 7, 5),
        date(2011, 7, 6),
    }
    assert "8-K" not in set(frame["form"]) and len(frame) == 4
    with pytest.raises(ValueError, match="unexpected daily index line"):
        parse_index(payload, ("10-K",), full=False)  # the daily layout wants YYYYMMDD
