"""``FmpAnalystEstimates`` on a RECORDED ``analyst-estimates`` answer (AAPL, annual, 2026-10-16)."""

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.vendors.fmp.estimates import (
    ESTIMATE_COLUMNS,
    FmpAnalystEstimates,
    parse_estimates,
    parse_key,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

PAYLOAD = (REPO_ROOT / "tests/fixtures/sources/fmp/analyst_estimates_annual_aapl.json").read_bytes()


def test_the_request_is_one_symbol_one_period_and_carries_no_key() -> None:
    urls: list[str] = []
    source = FmpAnalystEstimates(http_for(lambda url: urls.append(url) or PAYLOAD))
    assert source.fetch(FetchRequest("BRK.B:quarter")) == PAYLOAD
    assert urls == [
        "https://financialmodelingprep.com/stable/analyst-estimates"
        "?symbol=BRK-B&period=quarter&page=0&limit=8"
    ]
    assert "apikey" not in urls[0]


def test_the_period_defaults_to_annual_and_an_unknown_one_is_an_error() -> None:
    assert parse_key("AAPL") == ("AAPL", "annual")
    with pytest.raises(ValueError, match="period must be"):
        parse_key("AAPL:monthly")


def test_each_recorded_row_becomes_one_fiscal_period_oldest_first() -> None:
    frame = parse_estimates(PAYLOAD, "annual")
    assert list(frame.columns) == ESTIMATE_COLUMNS
    assert [d.date().isoformat() for d in frame["fiscal_date"]] == ["2029-09-27", "2030-09-27"]
    last = frame.iloc[-1]
    assert (last["symbol"], last["period"]) == ("AAPL", "annual")
    assert last["revenue_avg"] == 647707000000 and last["eps_avg"] == 12.905
    assert last["net_income_low"] == 181463654543 and last["sga_expense_high"] == 45330314173
    assert (last["num_analysts_revenue"], last["num_analysts_eps"]) == (1, 1)


def test_a_row_without_a_date_is_dropped_and_a_repeat_kept_once() -> None:
    raw = (
        b'[{"symbol": "x", "date": "2027-01-01", "epsAvg": 1.5},'
        b' {"symbol": "x", "date": "2027-01-01", "epsAvg": 9},'
        b' {"symbol": "x", "epsAvg": 2}, {"symbol": "x", "date": "bad"}]'
    )
    frame = parse_estimates(raw, "quarter")
    assert list(frame["symbol"]) == ["X"] and list(frame["eps_avg"]) == [1.5]


def test_normalize_exposes_the_frame_as_parsed_and_stores_nothing() -> None:
    normalized = FmpAnalystEstimates(http_for(lambda url: b"")).normalize(
        FetchRequest("AAPL:annual"), PAYLOAD
    )
    assert normalized is not None and normalized.tables == {}
    assert len(normalized.parsed["estimates"]) == 2


def test_a_non_list_answer_is_an_error() -> None:
    with pytest.raises(ValueError, match="JSON list"):
        parse_estimates(b'{"Error Message": "x"}', "annual")
