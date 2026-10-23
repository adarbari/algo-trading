"""``YahooAnalyst`` on RECORDED answers (ARX, TSM and an unknown symbol, 2026-10-22)."""

import json
from datetime import date

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.yahoo.analyst import (
    ESTIMATE_COLUMNS,
    RECOMMENDATION_COLUMNS,
    TARGET_COLUMNS,
    YahooAnalyst,
    number,
)
from algotrade_sources.vendors.yahoo.client import refused, url, vendor_symbol
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "sources" / "yahoo"
ARX = (FIXTURES / "quote_summary_arx.json").read_bytes()
TSM = (FIXTURES / "quote_summary_tsm.json").read_bytes()
NOT_FOUND = (FIXTURES / "not_found_404.json").read_bytes()
SESSION = date(2026, 10, 22)


def parsed(payload: bytes, symbol: str = "ARX") -> dict[str, pd.DataFrame]:
    source = YahooAnalyst(http_for(lambda u: b""))
    normalized = source.normalize(FetchRequest(symbol, None, SESSION), payload)
    assert normalized is not None and normalized.tables == {}
    return normalized.parsed


def test_the_recorded_targets_are_one_row_of_floats() -> None:
    frame = parsed(ARX)["price_target"]
    assert list(frame.columns) == TARGET_COLUMNS
    row = frame.iloc[0]
    assert row["symbol"] == "ARX" and row["target_consensus"] == 20.25
    assert (row["target_median"], row["target_high"], row["target_low"]) == (20.25, 20.25, 20.25)


def test_the_annual_estimates_are_the_0y_and_plus_1y_periods_by_end_date() -> None:
    frame = parsed(ARX)["estimates_annual"]
    assert list(frame.columns) == ESTIMATE_COLUMNS
    assert [d.strftime("%Y-%m-%d") for d in frame["fiscal_date"]] == ["2026-12-31", "2027-12-31"]
    first = frame.iloc[0]
    assert first["eps_avg"] == pytest.approx(0.8925) and first["num_analysts_eps"] == 8
    assert first["revenue_avg"] > 1e9 and first["currency"] == "USD"  # the quarters are dropped


def test_the_recommendation_is_the_current_month_dated_the_first_of_the_session_month() -> None:
    frame = parsed(ARX)["recommendation"]
    assert list(frame.columns) == RECOMMENDATION_COLUMNS
    row = frame.iloc[0]
    assert row["period"] == pd.Timestamp("2026-10-01", tz="UTC")
    assert [row[c] for c in RECOMMENDATION_COLUMNS[2:]] == [0, 0, 5, 0, 1]


def test_a_non_usd_name_stores_no_estimates_and_no_targets_but_keeps_the_counts() -> None:
    got = parsed(TSM, "TSM")  # financialCurrency TWD, revenue in TWD
    assert got["estimates_annual"].empty and got["price_target"].empty
    assert list(got["recommendation"].iloc[0][RECOMMENDATION_COLUMNS[2:]]) == [6, 14, 1, 0, 0]


def edited(change) -> bytes:  # type: ignore[no-untyped-def]
    data = json.loads(ARX)
    change(data["quoteSummary"]["result"][0])
    return json.dumps(data).encode()


def test_a_period_without_an_end_date_is_dropped() -> None:
    def drop(result: dict) -> None:  # type: ignore[type-arg]
        result["earningsTrend"]["trend"][2]["endDate"] = None

    frame = parsed(edited(drop))["estimates_annual"]
    assert [d.year for d in frame["fiscal_date"]] == [2027]


def test_bare_numbers_and_empty_values_are_read() -> None:
    assert number({"raw": 1.5, "fmt": "1.5"}) == 1.5 and number(2) == 2.0
    assert number({}) is None and number(None) is None and number("x") is None

    def plain(result: dict) -> None:  # type: ignore[type-arg]
        data = result["financialData"]
        data["targetMeanPrice"] = {"raw": data["targetMeanPrice"], "fmt": "20.25"}
        data["targetHighPrice"] = {}

    row = parsed(edited(plain))["price_target"].iloc[0]
    assert row["target_consensus"] == 20.25 and pd.isna(row["target_high"])


def test_no_estimates_at_all_is_an_empty_frame_not_an_error() -> None:
    def strip(result: dict) -> None:  # type: ignore[type-arg]
        del result["earningsTrend"], result["financialData"]

    got = parsed(edited(strip))
    assert got["estimates_annual"].empty and got["price_target"].empty
    assert not got["recommendation"].empty


def test_an_answer_without_a_result_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="no quoteSummary result"):
        parsed(NOT_FOUND)


def test_the_request_is_one_quote_summary_with_the_hyphenated_class_symbol() -> None:
    urls: list[str] = []
    http = http_for(lambda u: urls.append(u) or ARX)
    YahooAnalyst(http).fetch(FetchRequest("BRK.B"))
    assert urls == [
        "https://query2.finance.yahoo.com/v10/finance/quoteSummary/BRK-B"
        "?modules=financialData%2CearningsTrend%2CrecommendationTrend&formatted=false"
    ]
    assert vendor_symbol(" brk.b ") == "BRK-B" and url("ARX").count("quoteSummary/ARX?") == 1


def test_a_404_is_refused_at_once_and_a_server_error_is_not() -> None:
    calls: list[int] = []

    def get(u: str) -> bytes:
        calls.append(1)
        raise HttpError(404, body=NOT_FOUND)

    source = YahooAnalyst(http_for(get, RetryPolicy(rejected=refused)))
    with pytest.raises(HttpError) as caught:
        source.fetch(FetchRequest("ZZZZQ9"))
    assert caught.value.status == 404 and b"Not Found" in caught.value.body and len(calls) == 1
    assert refused(HttpError(404)) and not refused(HttpError(401)) and not refused(HttpError(500))
