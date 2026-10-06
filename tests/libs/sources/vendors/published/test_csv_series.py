"""Published series files (Stooq, Fed EBP, OFR FSI, EPU, Shiller) against documented formats,
and every published series of ``config/site/macro.toml`` against its recorded file (trimmed from
the real download, ``tests/fixtures/sources/published``; CI never calls the network)."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from algotrade.config.site.settings import load_macro
from algotrade.storage.configs.files import FileConfigStore
from algotrade_sources.framework.base import TransientFetchError
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
REPO = Path(__file__).resolve().parents[5]
RECORDED = REPO / "tests" / "fixtures" / "sources" / "published"
RECORDED_FILES = {"ebp_csv.csv", "fsi.csv", "All_Daily_Policy_Data.csv"}  # named as served
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
    with pytest.raises(TransientFetchError, match="no column"):
        parse_series(STOOQ, files.NO_DATA)
    with pytest.raises(TransientFetchError, match="no column"):
        parse_series(STOOQ, files.EBP)
    with pytest.raises(ValueError, match="unknown parser"):
        parse_series(SeriesRequest("X", parser="nope"), files.EBP)


def test_an_empty_file_is_an_error_not_an_empty_series() -> None:
    with pytest.raises(TransientFetchError, match="empty"):
        parse_series(STOOQ, b"  \n")


def test_an_html_page_raises_with_the_start_of_the_body() -> None:
    """Stooq's download now answers a browser-verification page (a 200 with HTML)."""
    with pytest.raises(TransientFetchError) as caught:
        parse_series(STOOQ, files.JS_CHALLENGE)
    message = str(caught.value)
    assert "'SPX'" in message and "HTML" in message
    assert files.JS_CHALLENGE.decode()[:80] in message
    assert files.JS_CHALLENGE.decode()[:81] not in message  # only the first 80 characters


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


def test_epu_daily_builds_the_date_from_its_three_columns() -> None:
    payload = b"day,month,year,daily_policy_index\n1,1,1985,103.83\n31,2,1985,5\n16,9,2008,307.09\n"
    request = SeriesRequest(
        "EPU_DAILY", parser="epu_daily", date_column="date", value_column="daily_policy_index"
    )
    frame = parse_series(request, payload)
    assert frame["obs_date"].dt.date.tolist() == [date(1985, 1, 1), date(2008, 9, 16)]
    assert frame["value"].tolist() == [103.83, 307.09]  # 31 February is no date: dropped
    assert PARSERS["epu_daily"](b"").empty
    with pytest.raises(ValueError, match="EPU"):
        PARSERS["epu_daily"](b"date,value\n2026-01-02,1\n")


@pytest.mark.parametrize(
    ("key", "rows", "first", "value"),
    [
        ("EBP", 9, date(1973, 1, 1), -0.046854494),
        ("EBP_RECESSION_PROB", 9, date(1973, 1, 1), 0.18496912088474687),
        ("OFR_FSI", 6, date(2000, 1, 3), 2.14),
        ("EPU_DAILY", 6, date(1985, 1, 1), 103.83),
    ],
)
def test_each_registry_file_loads_from_its_recorded_response(
    key: str, rows: int, first: date, value: float
) -> None:
    spec = load_macro(FileConfigStore(REPO / "config")).by_key(key)
    name = spec.url.rsplit("/", 1)[-1]
    assert spec.source == "published" and spec.pit == "lag" and name in RECORDED_FILES
    request = SeriesRequest(
        spec.key, code=spec.vendor_code, url=spec.url, date_column=spec.date_column,
        value_column=spec.value_column, parser=spec.parser,
    )  # fmt: skip
    payload = (RECORDED / name).read_bytes()
    normalized = PublishedSeries(http_for(lambda url: payload)).normalize(request, payload)
    assert normalized is not None
    frame = normalized.parsed[SERIES_FRAME]
    assert len(frame) == rows and frame["value"].notna().all()
    assert frame["obs_date"].dt.date.iloc[0] == first
    assert frame["value"].iloc[0] == pytest.approx(value)
    assert frame["obs_date"].is_monotonic_increasing
