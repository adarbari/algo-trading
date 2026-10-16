"""``FmpPriceTargets`` and ``FmpRatings`` on RECORDED answers (AAPL, 2026-10-16)."""

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.fmp.client import refused
from algotrade_sources.vendors.fmp.targets import (
    RATING_COLUMNS,
    TARGET_COLUMNS,
    FmpPriceTargets,
    FmpRatings,
    parse_ratings,
    parse_targets,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources" / "fmp"
TARGETS = (FIXTURES / "price_target_consensus_aapl.json").read_bytes()
RATINGS = (FIXTURES / "grades_consensus_aapl.json").read_bytes()
PREMIUM = (FIXTURES / "premium_402.txt").read_bytes()


def test_the_recorded_price_target_is_one_row_of_floats() -> None:
    frame = parse_targets(TARGETS)
    assert list(frame.columns) == TARGET_COLUMNS
    row = frame.iloc[0]
    assert row["symbol"] == "AAPL" and row["target_high"] == 400.0 and row["target_low"] == 245.0
    assert (row["target_consensus"], row["target_median"]) == (341.68, 357.5)


def test_the_recorded_rating_summary_is_one_row_of_counts_and_a_label() -> None:
    frame = parse_ratings(RATINGS)
    assert list(frame.columns) == RATING_COLUMNS
    row = frame.iloc[0]
    assert (row["strong_buy"], row["buy"], row["hold"], row["sell"], row["strong_sell"]) == (
        1, 70, 32, 9, 0,
    )  # fmt: skip
    assert row["consensus"] == "Buy"


def test_a_record_without_a_symbol_is_dropped() -> None:
    assert parse_targets(b'[{"targetHigh": 1}]').empty
    assert parse_ratings(b"[]").empty


def test_the_requests_are_one_symbol_and_carry_no_key() -> None:
    urls: list[str] = []
    http = http_for(lambda url: urls.append(url) or TARGETS)
    FmpPriceTargets(http).fetch(FetchRequest("BRK.B"))
    FmpRatings(http).fetch(FetchRequest("AAPL"))
    assert urls == [
        "https://financialmodelingprep.com/stable/price-target-consensus?symbol=BRK-B",
        "https://financialmodelingprep.com/stable/grades-consensus?symbol=AAPL",
    ]


def test_normalize_exposes_the_frames_as_parsed_and_stores_nothing() -> None:
    targets = FmpPriceTargets(http_for(lambda url: b"")).normalize(FetchRequest("AAPL"), TARGETS)
    ratings = FmpRatings(http_for(lambda url: b"")).normalize(FetchRequest("AAPL"), RATINGS)
    assert targets is not None and targets.tables == {} and len(targets.parsed["targets"]) == 1
    assert ratings is not None and ratings.tables == {} and len(ratings.parsed["ratings"]) == 1


def test_a_premium_402_is_a_refusal_raised_at_once_not_retried() -> None:
    calls: list[str] = []

    def transport(url: str) -> bytes:
        calls.append(url)
        raise HttpError(402, body=PREMIUM)

    http = http_for(transport, RetryPolicy(tries=7, rejected=refused))
    with pytest.raises(HttpError) as raised:
        FmpPriceTargets(http).fetch(FetchRequest("ZZZZ"))
    assert raised.value.status == 402 and len(calls) == 1  # a retry would spend the day's budget
