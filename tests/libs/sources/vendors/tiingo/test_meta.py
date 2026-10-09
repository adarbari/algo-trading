"""``TiingoListingMeta`` on the HAND-BUILT meta payload (shape verified by hand 2026-10-09)."""

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.vendors.tiingo.meta import (
    COLUMNS,
    TABLE,
    TiingoListingMeta,
    parse_meta,
    vendor_symbol,
)
from tests.helpers.ingest_fakes import http_for
from tests.helpers.payloads import tiingo as payloads


def test_the_batch_is_one_request_with_lowercase_tickers() -> None:
    urls: list[str] = []
    body = payloads.meta_payload()
    source = TiingoListingMeta(http_for(lambda url: urls.append(url) or body))
    assert source.fetch(FetchRequest("PRM,AAPL,BRK.B")) == body
    assert urls == ["https://api.tiingo.com/tiingo/fundamentals/meta?tickers=prm,aapl,brk-b"]
    assert vendor_symbol(" BRK.B ") == "brk-b"


def test_one_row_per_listing_a_recycled_ticker_answers_with_several() -> None:
    meta = parse_meta(payloads.meta_payload())
    assert list(meta.columns) == COLUMNS
    prm = meta[meta["ticker"] == "PRM"].set_index("perma_ticker")
    assert dict(prm["is_active"]) == {"US000000041372": False, "US000000101493": True}
    assert prm.loc["US000000041372", "name"] == "PRIMEDIA Inc"
    assert len(meta[meta["ticker"] == "AAC"]) == 3 and "ZZZZ" not in set(meta["ticker"])


def test_rows_without_a_perma_ticker_are_dropped_and_repeats_kept_once() -> None:
    raw = (
        b'[{"permaTicker": "", "ticker": "x", "isActive": true},'
        b' {"permaTicker": "US1", "ticker": "y", "isActive": "true"},'
        b' {"permaTicker": "US1", "ticker": "y", "isActive": "true"}]'
    )
    meta = parse_meta(raw)
    assert list(meta["perma_ticker"]) == ["US1"] and bool(meta["is_active"].iloc[0])


def test_normalize_exposes_the_frame_as_parsed_and_stores_nothing() -> None:
    source = TiingoListingMeta(http_for(lambda url: b""))
    normalized = source.normalize(FetchRequest("PRM"), payloads.meta_payload())
    assert normalized is not None and normalized.tables == {}
    assert len(normalized.parsed[TABLE]) == 7


def test_a_non_list_answer_is_an_error() -> None:
    with pytest.raises(ValueError, match="JSON list"):
        parse_meta(b'{"detail": "Not found."}')
