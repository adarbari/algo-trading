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
