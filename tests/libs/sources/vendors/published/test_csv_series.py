"""Published series files (Stooq, Fed EBP, OFR FSI, Shiller) against documented formats."""

from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.series import SERIES_COLUMNS, SERIES_FRAME, SeriesRequest
from algotrade_sources.vendors.published.csv_series import PublishedSeries, parse_series
from algotrade_sources.vendors.published.parsers import PARSERS
from tests.helpers.ingest_fakes import CountingLimiter, http_for
from tests.helpers.payloads import published as files

STOOQ = SeriesRequest(
    "SPX", code="^spx", url="https://stooq.com/q/d/l/?s=^spx&i=d", date_column="Date",
    value_column="Close",
)  # fmt: skip
EBP = SeriesRequest(
    "EBP", url="https://example.org/ebp_csv.csv", date_column="date", value_column="ebp"
)
OFR = SeriesRequest(
    "OFR_FSI", url="https://example.org/fsi.csv", date_column="Date", value_column="OFR FSI"
)


def test_stooq_close_becomes_a_series_without_vintages() -> None:
    frame = parse_series(STOOQ, files.STOOQ)
    assert tuple(frame.columns) == SERIES_COLUMNS and len(frame) == 4
    assert frame["vintage_date"].isna().all()  # a published file has none: lagged downstream
    assert frame["value"].tolist() == [5721.33, 5709.91, 5666.64, 5698.2]
    assert frame["obs_date"].dt.date.tolist()[0] == date(2026, 9, 28)
    assert set(frame["series"]) == {"SPX"} and set(frame["code"]) == {"^spx"}


def test_ebp_and_ofr_read_the_column_the_request_names() -> None:
    ebp = parse_series(EBP, files.EBP)
    assert ebp["value"].tolist() == [0.1131, 0.1524, 2.2183, -0.0214]
    assert set(ebp["code"]) == {"ebp"}  # no code in the request: the column name
    ofr = parse_series(OFR, files.OFR_FSI)
    assert ofr["value"].tolist() == [-1.2, 29.6, -2.5]
    assert ofr["obs_date"].dt.date.tolist()[1] == date(2008, 10, 10)


def test_start_and_end_bound_the_rows() -> None:
    bounded = SeriesRequest(**{**vars(STOOQ), "start": date(2026, 9, 29), "end": date(2026, 9, 30)})
    frame = parse_series(bounded, files.STOOQ)
    assert frame["obs_date"].dt.date.tolist() == [date(2026, 9, 29), date(2026, 9, 30)]


def test_unreadable_values_are_null_and_unreadable_dates_are_dropped() -> None:
    payload = b"date,ebp\n2026-01-31,\n2026-02-28,n/a\nnot a date,1.0\n2026-03-31,0.5\n"
    frame = parse_series(EBP, payload)
    assert frame["value"].isna().tolist() == [True, True, False] and len(frame) == 3


def test_a_file_without_the_columns_or_with_an_unknown_parser_raises() -> None:
    with pytest.raises(ValueError, match="no column"):
        parse_series(STOOQ, files.NO_DATA)
    with pytest.raises(ValueError, match="no column"):
        parse_series(STOOQ, files.EBP)
    with pytest.raises(ValueError, match="unknown parser"):
        parse_series(SeriesRequest("X", parser="nope"), files.EBP)


def test_an_empty_file_is_an_empty_frame() -> None:
    frame = parse_series(STOOQ, b"")
    assert frame.empty and tuple(frame.columns) == SERIES_COLUMNS


def test_shiller_xls_is_not_readable_yet() -> None:
    assert "shiller_xls" in PARSERS
    request = SeriesRequest("CAPE", parser="shiller_xls", url="https://example.org/ie_data.xls")
    with pytest.raises(NotImplementedError, match="xlrd"):
        parse_series(request, b"\xd0\xcf\x11\xe0")


def test_source_fetches_the_url_through_the_limiter_and_normalises() -> None:
    urls: list[str] = []
    limiter = CountingLimiter()

    def transport(url: str) -> bytes:
        urls.append(url)
        return files.STOOQ

    source = PublishedSeries(http_for(transport, limiter=limiter))
    payload = source.fetch(STOOQ)
    assert payload == files.STOOQ and urls == [STOOQ.url] and limiter.waits == 1
    normalized = source.normalize(STOOQ, payload)
    assert normalized is not None and normalized.session_date is None and not normalized.tables
    assert len(normalized.parsed[SERIES_FRAME]) == 4
    assert isinstance(normalized.parsed[SERIES_FRAME], pd.DataFrame)


def test_an_empty_body_is_nothing_there_and_a_bad_url_is_refused() -> None:
    assert PublishedSeries(http_for(lambda url: b"  \n")).fetch(STOOQ) is None
    source = PublishedSeries(http_for(lambda url: files.STOOQ))
    with pytest.raises(ValueError, match="http"):
        source.fetch(SeriesRequest("X", url="file:///etc/passwd"))
    with pytest.raises(ValueError, match="http"):
        source.fetch(SeriesRequest("X"))
