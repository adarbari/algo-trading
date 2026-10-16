"""``FinnhubRecommendations`` on a RECORDED ``stock/recommendation`` answer (AAPL, 2026-10-16)."""

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.vendors.finnhub.recommendations import (
    RECOMMENDATION_COLUMNS,
    FinnhubRecommendations,
    parse_recommendations,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

PAYLOAD = (REPO_ROOT / "tests/fixtures/sources/finnhub/recommendation_aapl.json").read_bytes()


def test_the_request_is_one_symbol() -> None:
    urls: list[str] = []
    source = FinnhubRecommendations(http_for(lambda url: urls.append(url) or PAYLOAD))
    assert source.fetch(FetchRequest("aapl")) == PAYLOAD
    assert urls == ["https://finnhub.io/api/v1/stock/recommendation?symbol=AAPL"]


def test_each_recorded_month_is_one_row_oldest_first() -> None:
    frame = parse_recommendations(PAYLOAD)
    assert list(frame.columns) == RECOMMENDATION_COLUMNS
    assert [p.date().isoformat() for p in frame["period"]] == [
        "2026-07-01",
        "2026-08-01",
        "2026-09-01",
    ]
    newest = frame.iloc[-1]
    assert newest["symbol"] == "AAPL"
    assert [newest[c] for c in ("strong_buy", "buy", "hold", "sell", "strong_sell")] == [
        12, 22, 15, 3, 1,
    ]  # fmt: skip


def test_a_record_without_a_period_is_dropped_and_a_repeat_kept_once() -> None:
    raw = (
        b'[{"symbol": "x", "period": "2026-01-01", "buy": 1},'
        b' {"symbol": "x", "period": "2026-01-01", "buy": 9}, {"symbol": "x", "buy": 2}]'
    )
    frame = parse_recommendations(raw)
    assert list(frame["buy"]) == [1] and frame["sell"].isna().all()


def test_an_unknown_symbol_answers_an_empty_list_and_a_non_list_is_an_error() -> None:
    assert parse_recommendations(b"[]").empty
    with pytest.raises(ValueError, match="JSON list"):
        parse_recommendations(b'{"error": "x"}')


def test_normalize_exposes_the_frame_as_parsed_and_stores_nothing() -> None:
    normalized = FinnhubRecommendations(http_for(lambda url: b"")).normalize(
        FetchRequest("AAPL"), PAYLOAD
    )
    assert normalized is not None and normalized.tables == {}
    assert len(normalized.parsed["recommendations"]) == 3
