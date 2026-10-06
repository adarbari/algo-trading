"""FRED / ALFRED observations against payloads written from the documented format (no network)."""

from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest, TransientFetchError
from algotrade_sources.framework.http import GaveUpError, HttpError, RetryPolicy
from algotrade_sources.framework.series import SERIES_COLUMNS, SERIES_FRAME, SeriesRequest
from algotrade_sources.vendors.fred.observations import (
    BASE_URL,
    FredObservations,
    missing_series,
    parse_documents,
    parse_observations,
)
from tests.helpers.ingest_fakes import CountingLimiter, http_for
from tests.helpers.payloads import fred as fred_payloads

REQUEST = SeriesRequest("GDP_REAL", code="GDPC1")


def test_one_row_per_value_change_with_the_vintage_and_a_null_for_a_dot() -> None:
    frame = parse_observations(REQUEST, fred_payloads.payload())
    assert tuple(frame.columns) == SERIES_COLUMNS and len(frame) == 6
    q1 = frame[frame["obs_date"] == pd.Timestamp("2020-01-01")]
    assert q1["vintage_date"].dt.date.tolist() == [
        date(2020, 4, 29),
        date(2020, 5, 28),
        date(2020, 6, 25),
    ]
    assert q1["value"].tolist() == [18951.9, 18924.3, 18560.0]  # the revision across vintages
    assert set(frame["series"]) == {"GDP_REAL"} and set(frame["code"]) == {"GDPC1"}
    missing = frame[frame["obs_date"] == pd.Timestamp("2020-07-01")]
    assert len(missing) == 1 and missing["value"].isna().all()  # "." kept, as null
    assert frame["value"].dtype == "float64"
    assert frame["obs_date"].dtype == "datetime64[ns]" and frame["vintage_date"].notna().all()


def test_rows_are_sorted_and_exact_duplicates_dropped() -> None:
    rows = list(reversed(fred_payloads.OBSERVATIONS)) + fred_payloads.OBSERVATIONS[:2]
    frame = parse_observations(REQUEST, fred_payloads.page(rows))
    assert len(frame) == 6
    keys = list(zip(frame["obs_date"], frame["vintage_date"], strict=True))
    assert keys == sorted(keys)


def test_an_empty_series_is_an_empty_frame() -> None:
    frame = parse_observations(REQUEST, fred_payloads.page([]))
    assert frame.empty and tuple(frame.columns) == SERIES_COLUMNS


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "empty"),
        (b"<html>maintenance</html>", "not JSON"),
        (b"[1, 2]", "not a JSON object"),
        (fred_payloads.UNKNOWN_SERIES, "does not exist"),
        (b'{"count": 0}', "no 'observations'"),
    ],
)
def test_malformed_answers_raise(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_observations(REQUEST, payload)


def test_fetch_asks_for_the_full_realtime_period_and_never_puts_the_key_in_the_url() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()

    def transport(url: str) -> bytes:
        urls.append(url)
        return fred_payloads.payload()

    http = http_for(transport, RetryPolicy(tries=1), limiter)
    source = FredObservations(http, base_url=BASE_URL + "/")
    request = SeriesRequest("GDP_REAL", code="GDPC1", start=date(2000, 1, 1), end=date(2026, 9, 30))
    payload = source.fetch(request)
    assert payload == fred_payloads.payload() and limiter.waits == 1
    (url,) = urls
    assert url.startswith("https://api.stlouisfed.org/fred/series/observations?")
    for fragment in (
        "series_id=GDPC1",
        "file_type=json",
        "realtime_start=1776-07-04",
        "realtime_end=9999-12-31",
        "limit=100000",
        "offset=0",
        "observation_start=2000-01-01",
        "observation_end=2026-09-30",
    ):
        assert fragment in url
    assert "api_key" not in url
    normalized = source.normalize(request, payload)
    assert normalized is not None and normalized.session_date is None
    assert not normalized.tables and len(normalized.parsed[SERIES_FRAME]) == 6


def test_a_long_series_is_paged_and_saved_as_its_pages() -> None:
    rows = [fred_payloads.row(f"2020-0{n}-01", f"2020-0{n}-20", str(n)) for n in range(1, 6)]
    pages = {
        0: fred_payloads.page(rows[:2], count=5, offset=0, limit=2),
        2: fred_payloads.page(rows[2:4], count=5, offset=2, limit=2),
        4: fred_payloads.page(rows[4:], count=5, offset=4, limit=2),
    }
    offsets: list[int] = []

    def transport(url: str) -> bytes:
        offset = int(url.split("offset=")[1].split("&", maxsplit=1)[0])
        offsets.append(offset)
        return pages[offset]

    source = FredObservations(http_for(transport, RetryPolicy(tries=1)), page_limit=2)
    payload = source.fetch(REQUEST)
    assert offsets == [0, 2, 4] and payload is not None
    assert len(parse_documents(payload)) == 3
    normalized = source.normalize(REQUEST, payload)
    assert normalized is not None
    assert normalized.parsed[SERIES_FRAME]["value"].tolist() == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_a_page_that_vanishes_midway_is_a_transient_error_not_nothing() -> None:
    first = fred_payloads.page(fred_payloads.OBSERVATIONS[:2], count=5, offset=0, limit=2)
    answers: list[bytes | None] = [first, None]

    def transport(url: str) -> bytes:
        answer = answers.pop(0)
        if answer is None:
            raise HttpError(400, body=fred_payloads.UNKNOWN_SERIES)
        return answer

    policy = RetryPolicy(tries=1, not_found=missing_series)
    source = FredObservations(http_for(transport, policy), page_limit=2)
    with pytest.raises(TransientFetchError):
        source.fetch(REQUEST)


def test_an_unknown_series_is_nothing_there_but_a_bad_key_is_an_error() -> None:
    def unknown(url: str) -> bytes:
        raise HttpError(400, body=fred_payloads.UNKNOWN_SERIES)

    def bad_key(url: str) -> bytes:
        raise HttpError(400, body=fred_payloads.BAD_KEY)

    policy = RetryPolicy(tries=1, not_found=missing_series)
    assert FredObservations(http_for(unknown, policy)).fetch(REQUEST) is None
    with pytest.raises(GaveUpError):
        FredObservations(http_for(bad_key, policy)).fetch(REQUEST)
    assert not missing_series(HttpError(500, body=fred_payloads.UNKNOWN_SERIES))


def test_the_request_must_be_a_series_request_with_a_code() -> None:
    source = FredObservations(http_for(lambda url: fred_payloads.payload()))
    with pytest.raises(TypeError, match="SeriesRequest"):
        source.fetch(FetchRequest("GDP_REAL"))
    with pytest.raises(ValueError, match="series id"):
        source.fetch(SeriesRequest("GDP_REAL"))
