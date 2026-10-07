"""FRED release dates against a recorded payload (release 10, the CPI, fetched 2026-10-06 for
the real-time period 2025-09-01..2027-12-31): the dates in order, the scheduled future ones
included, the request FRED is asked, paging and the unknown release."""

from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest, TransientFetchError
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.framework.series import RELEASE_FRAME, ReleaseRequest
from algotrade_sources.vendors.fred.observations import BASE_URL
from algotrade_sources.vendors.fred.releases import (
    RELEASE_COLUMNS,
    FredReleaseDates,
    parse_release_dates,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import CountingLimiter, http_for

PAYLOAD = (
    REPO_ROOT / "tests" / "fixtures" / "sources" / "fred" / "release_dates_10_cpi.json"
).read_bytes()
REQUEST = ReleaseRequest("10", start=date(2025, 9, 1), end=date(2027, 12, 31))


def page(rows: list[tuple[int, str]], count: int, offset: int, limit: int) -> bytes:
    body = ",".join(f'{{"release_id":{i},"date":"{d}"}}' for i, d in rows)
    return (
        f'{{"count":{count},"offset":{offset},"limit":{limit},"release_dates":[{body}]}}'
    ).encode()


def test_the_recorded_cpi_dates_are_typed_sorted_and_include_the_scheduled_future() -> None:
    frame = parse_release_dates(PAYLOAD)
    assert tuple(frame.columns) == RELEASE_COLUMNS and len(frame) == 15
    assert frame["release_id"].dtype == "int64" and set(frame["release_id"]) == {10}
    assert frame["release_date"].dtype == "datetime64[ns]"
    assert frame["release_date"].is_monotonic_increasing
    assert frame["release_date"].iloc[0] == pd.Timestamp("2025-09-11")
    future = frame[frame["release_date"] > pd.Timestamp("2026-10-06")]
    assert future["release_date"].dt.date.tolist() == [
        date(2026, 10, 14),
        date(2026, 11, 10),
        date(2026, 12, 10),
    ]


def test_rows_are_sorted_and_duplicates_dropped() -> None:
    rows = [(10, "2026-02-13"), (10, "2026-01-13"), (10, "2026-02-13")]
    frame = parse_release_dates(page(rows, count=3, offset=0, limit=10000))
    assert frame["release_date"].dt.date.tolist() == [date(2026, 1, 13), date(2026, 2, 13)]
    assert parse_release_dates(page([], 0, 0, 10000)).empty


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "empty"),
        (b"<html>maintenance</html>", "not JSON"),
        (b'{"error_code":400,"error_message":"Bad Request."}', "Bad Request"),
        (b'{"count": 0}', "no 'release_dates'"),
    ],
)
def test_malformed_answers_raise(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_release_dates(payload)


def test_fetch_asks_for_scheduled_dates_in_the_period_and_never_puts_the_key_in_the_url() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()

    def transport(url: str) -> bytes:
        urls.append(url)
        return PAYLOAD

    source = FredReleaseDates(
        http_for(transport, RetryPolicy(tries=1), limiter), base_url=BASE_URL + "/"
    )
    payload = source.fetch(REQUEST)
    assert payload == PAYLOAD and limiter.waits == 1
    (url,) = urls
    assert url.startswith("https://api.stlouisfed.org/fred/release/dates?")
    for fragment in (
        "release_id=10",
        "include_release_dates_with_no_data=true",
        "file_type=json",
        "realtime_start=2025-09-01",
        "realtime_end=2027-12-31",
        "limit=10000",
        "offset=0",
    ):
        assert fragment in url
    assert "api_key" not in url
    normalized = source.normalize(REQUEST, payload)
    assert normalized is not None and normalized.session_date is None and not normalized.tables
    assert len(normalized.parsed[RELEASE_FRAME]) == 15


def test_a_plain_request_leaves_the_period_out() -> None:
    urls: list[str] = []

    def transport(url: str) -> bytes:
        urls.append(url)
        return PAYLOAD

    FredReleaseDates(http_for(transport)).fetch(FetchRequest("10"))
    assert "realtime" not in urls[0] and "release_id=10" in urls[0]


def test_a_long_release_is_paged_and_saved_as_its_pages() -> None:
    rows = [(10, f"2026-0{n}-10") for n in range(1, 6)]
    pages = {
        0: page(rows[:2], count=5, offset=0, limit=2),
        2: page(rows[2:4], count=5, offset=2, limit=2),
        4: page(rows[4:], count=5, offset=4, limit=2),
    }
    offsets: list[int] = []

    def transport(url: str) -> bytes:
        offset = int(url.split("offset=")[1].split("&", maxsplit=1)[0])
        offsets.append(offset)
        return pages[offset]

    source = FredReleaseDates(http_for(transport, RetryPolicy(tries=1)), page_limit=2)
    payload = source.fetch(REQUEST)
    assert offsets == [0, 2, 4] and payload is not None
    normalized = source.normalize(REQUEST, payload)
    assert normalized is not None
    assert len(normalized.parsed[RELEASE_FRAME]) == 5


def test_a_page_that_vanishes_midway_is_a_transient_error_not_nothing() -> None:
    answers: list[bytes | None] = [page([(10, "2026-01-10")], count=5, offset=0, limit=2), None]

    def transport(url: str) -> bytes:
        body = answers.pop(0)
        if body is None:
            raise HttpError(404)  # the policy gives up on a 404: ``http.get`` answers None
        return body

    source = FredReleaseDates(http_for(transport, RetryPolicy(tries=1)), page_limit=2)
    with pytest.raises(TransientFetchError):
        source.fetch(REQUEST)


def test_an_unknown_release_is_an_empty_answer_and_a_bad_id_is_an_error() -> None:
    empty = page([], count=0, offset=0, limit=10000)
    source = FredReleaseDates(http_for(lambda url: empty))
    payload = source.fetch(FetchRequest("99999999"))
    normalized = source.normalize(FetchRequest("99999999"), payload or b"")
    assert normalized is not None and normalized.parsed[RELEASE_FRAME].empty
    with pytest.raises(ValueError, match="release id"):
        source.fetch(FetchRequest("CPI"))
