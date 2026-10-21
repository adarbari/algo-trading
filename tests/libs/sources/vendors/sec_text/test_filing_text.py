"""The SEC filing-text source (edge build D10): the archive URL built from the accession and the
submissions JSON's file name, the payload being the extraction (never the HTML), a 404, an empty
body or a block page an error, and a short or textless document one NO_ITEMS row (never guessed
text)."""

import json

import pandas as pd
import pytest

from algotrade_sources.framework.base import TransientFetchError
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.framework.series import (
    DEFAULT_10K,
    FILING_TEXT_COLUMNS,
    FILING_TEXT_FRAME,
    FilingTextRequest,
)
from algotrade_sources.vendors.sec_text.filing_text import SecFilingText, document_url
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

SEC = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"
TEN_K = (SEC / "10k_items_trimmed.htm").read_bytes()
ACCESSION = "0000320193-24-000123"
URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm"


def request(**kw: object) -> FilingTextRequest:
    args = {
        "key": ACCESSION,
        "cik": "0000320193",
        "form": "10-K",
        "primary_document": "aapl-20240928.htm",
    }
    return FilingTextRequest(**{**args, **kw})  # type: ignore[arg-type]


def source(body: bytes | None, urls: list[str] | None = None) -> SecFilingText:
    def transport(url: str) -> bytes:
        (urls if urls is not None else []).append(url)
        if body is None:
            raise HttpError(404)
        return body

    return SecFilingText(http_for(transport, RetryPolicy(tries=1)))


def test_the_url_is_the_archive_folder_of_the_accession_without_dashes_and_leading_zeros() -> None:
    assert document_url(request()) == URL


@pytest.mark.parametrize(
    "bad",
    [
        {"primary_document": "../../etc/passwd.htm"},
        {"primary_document": "a/b.htm"},
        {"primary_document": "report.exe"},
        {"primary_document": "scan.paper"},
        {"key": "0000320193-24-12"},
        {"cik": "abc"},
    ],
)
def test_a_malformed_accession_cik_or_file_name_is_refused_before_any_request(
    bad: dict[str, str],
) -> None:
    urls: list[str] = []
    with pytest.raises(ValueError):
        source(TEN_K, urls).fetch(request(**bad))
    assert urls == []


@pytest.mark.parametrize("name", ["D12345.HTM", "d12345.Html", "FORM10K.TXT"])
def test_an_uppercase_extension_primary_document_is_accepted_as_named(name: str) -> None:
    url = document_url(request(primary_document=name))
    assert url == URL.rsplit("/", 1)[0] + "/" + name  # SEC paths are case-sensitive: kept as is


def test_the_raw_payload_is_the_extraction_never_the_html() -> None:
    urls: list[str] = []
    payload = source(TEN_K, urls).fetch(request())
    assert urls == [URL] and payload is not None
    document = json.loads(payload)
    assert document["accession"] == ACCESSION and document["form"] == "10-K"
    assert document["parser_version"] == 1 and document["document_bytes"] == len(TEN_K)
    assert [r["item"] for r in document["items"]] == list(DEFAULT_10K)
    assert b"<html" not in payload and b"<div" not in payload and b"ix:header" not in payload
    assert len(payload) < len(TEN_K)  # the kept items only


def test_normalize_rebuilds_the_frame_from_the_raw_payload_alone() -> None:
    adapter = source(TEN_K)
    payload = adapter.fetch(request())
    assert payload is not None
    frame = adapter.normalize(request(), payload).parsed[FILING_TEXT_FRAME]  # type: ignore[union-attr]
    assert tuple(frame.columns) == FILING_TEXT_COLUMNS
    assert frame["char_count"].dtype == "int64" and frame["parser_version"].dtype == "int64"
    assert frame.loc[frame["item"] == "1A", "quality"].iloc[0] == "OK"
    assert frame["item"].tolist() == list(DEFAULT_10K) and not pd.isna(frame["text"]).any()


def test_the_items_asked_are_the_ones_kept() -> None:
    payload = source(TEN_K).fetch(request(items=("1a", "7")))
    assert [r["item"] for r in json.loads(payload or b"")["items"]] == ["1A", "7"]


def test_a_404_is_no_response_not_an_empty_answer() -> None:
    assert source(None).fetch(request()) is None  # the task fails the item on it


@pytest.mark.parametrize(
    "body",
    [b"<html>" + b"Request Rate Threshold Exceeded " * 300 + b"</html>", b"  \n "],
    ids=["block page", "empty body"],
)
def test_a_block_page_or_an_empty_body_is_an_error(body: bytes) -> None:
    with pytest.raises(TransientFetchError):
        source(body).fetch(request())


@pytest.mark.parametrize(
    "body",
    [
        b"<html><body>stub</body></html>",
        b"<html><body>" + b"<script>var x = 1;</script>" * 400 + b"</body></html>",
    ],
    ids=["stub", "no report text"],
)
def test_a_short_or_textless_document_is_one_no_items_row_never_an_error(body: bytes) -> None:
    adapter = source(body)
    payload = adapter.fetch(request(form="10-K/A"))
    assert payload is not None
    frame = adapter.normalize(request(), payload).parsed[FILING_TEXT_FRAME]  # type: ignore[union-attr]
    assert len(frame) == 1 and pd.isna(frame["item"].iloc[0]) and pd.isna(frame["text"].iloc[0])
    assert (
        frame["quality"].iloc[0] == "NO_ITEMS" and "characters of text" in frame["reason"].iloc[0]
    )


def test_a_server_error_is_an_error() -> None:
    def transport(url: str) -> bytes:
        raise HttpError(500)

    adapter = SecFilingText(http_for(transport, RetryPolicy(tries=1)))
    with pytest.raises(Exception):  # noqa: B017  (the http client's own give-up error)
        adapter.fetch(request())
