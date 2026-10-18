"""EDGAR full-text search of 424B4 prospectuses that mention a lock-up (edge build D8): the URL of
a window and page, paging, one row per accession, the 10,000-hit cap and the refused request."""

from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.series import HIT_COLUMNS, HITS_FRAME, ProspectusSearchRequest
from algotrade_sources.vendors.sec_prospectus.prospectus_search import (
    MAX_HITS,
    SecProspectusSearch,
    parse_hits,
    search_url,
)
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import sec as payloads

START, END = date(2026, 9, 1), date(2026, 9, 30)


def request() -> ProspectusSearchRequest:
    return ProspectusSearchRequest(key=f"{START}..{END}", start=START, end=END)


def test_the_url_asks_the_form_the_phrase_the_window_and_the_page() -> None:
    query = parse_qs(urlparse(search_url(START, END, 200)).query)
    assert query["q"] == ['"lock-up"'] and query["forms"] == ["424B4"]
    assert query["startdt"] == ["2026-09-01"] and query["enddt"] == ["2026-09-30"]
    assert query["from"] == ["200"] and query["size"] == ["100"]


def test_one_row_per_accession_with_a_padded_cik_sorted_by_filing() -> None:
    page = payloads.search_page(
        [
            ("0001-26-000002", "1234", "2026-09-10", "Beta Inc"),
            ("0001-26-000001", "99", "2026-09-02", "Alpha Corp"),
            ("0001-26-000002", "1234", "2026-09-10", "Beta Inc"),  # a second document
        ]
    )
    frame = parse_hits(page)
    assert list(frame.columns) == list(HIT_COLUMNS)
    assert frame["accession"].tolist() == ["0001-26-000001", "0001-26-000002"]
    assert frame["cik"].tolist() == ["0000000099", "0000001234"]
    assert frame["name"].tolist() == ["Alpha Corp", "Beta Inc"]
    assert frame["filing_date"].dt.date.tolist() == [date(2026, 9, 2), date(2026, 9, 10)]


def test_an_empty_window_is_an_empty_frame() -> None:
    assert parse_hits(payloads.search_page([])).empty


def test_a_hit_without_an_accession_is_an_error() -> None:
    bad = b'{"hits": {"total": {"value": 1}, "hits": [{"_source": {"ciks": ["1"]}}]}}'
    with pytest.raises(ValueError, match="without a filer"):
        parse_hits(bad)


def test_pages_are_fetched_until_the_total_and_read_as_one_frame() -> None:
    first = [(f"0001-26-{i:06d}", "5", "2026-09-03", "Gamma") for i in range(100)]
    second = [("0001-26-000100", "5", "2026-09-04", "Gamma")]
    asked: list[str] = []

    def transport(url: str) -> bytes:
        asked.append(parse_qs(urlparse(url).query)["from"][0])
        return payloads.search_page(first if asked[-1] == "0" else second, total=101)

    source = SecProspectusSearch(http_for(transport))
    normalized = source.normalize(request(), source.fetch(request()) or b"")
    assert asked == ["0", "100"]
    assert normalized is not None and len(normalized.parsed[HITS_FRAME]) == 101


def test_a_window_over_the_search_cap_is_an_error() -> None:
    source = SecProspectusSearch(http_for(lambda url: payloads.search_page([], total=MAX_HITS + 1)))
    with pytest.raises(ValueError, match="shorter window"):
        source.fetch(request())


def test_a_plain_request_is_refused() -> None:
    source = SecProspectusSearch(http_for(lambda url: b"{}"))
    with pytest.raises(TypeError, match="ProspectusSearchRequest"):
        source.fetch(FetchRequest("2026-09"))
