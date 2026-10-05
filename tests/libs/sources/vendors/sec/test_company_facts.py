"""SEC company facts against a recorded (trimmed) payload: share counts are kept, one cover
count per filing (classes summed), one weighted average per filing (its current period),
amendments as their own rows, zero counts dropped; and the revenue / net income / diluted EPS
flows: periodic forms and quarter-to-year spans only, the best revenue tag per period, the
first filing of a period plus restatements, losses kept."""

import json
from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sec.company_facts import (
    FACT_COLUMNS,
    FACTS_URL,
    SecCompanyFacts,
    parse_company_facts,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec" / "companyfacts_CIK0000320193.json"
PAYLOAD = FIXTURE.read_bytes()


def test_keeps_share_counts_and_the_flows_and_nothing_else() -> None:
    rows = parse_company_facts(PAYLOAD)
    assert list(rows.columns) == list(FACT_COLUMNS)
    assert set(rows["concept"]) == {"dei", "weighted_basic", "revenue"}  # not the public float
    counts = rows[rows["concept"] != "revenue"]
    assert counts["value"].isna().all() and counts["unit"].isna().all()
    revenue = rows[rows["concept"] == "revenue"].iloc[0]
    assert (revenue["value"], revenue["unit"], revenue["shares"]) == (95359000000.0, "usd", None)
    assert set(rows["cik"]) == {"0000320193"}
    assert (rows["shares"].dropna() > 0).all()  # the 2009 zero is dropped


def test_cover_counts_one_per_filing_classes_summed_amendments_kept() -> None:
    dei = parse_company_facts(PAYLOAD).query("concept == 'dei'").set_index("accn")
    assert len(dei) == 5
    q3 = dei.loc["0000320193-26-000020"]
    assert (q3["shares"], q3["class_values"], q3["period_end"]) == (14594180000.0, 2, "2026-07-17")
    assert q3["period_start"] is None and q3["tag"] == "dei:EntityCommonStockSharesOutstanding"
    amended = dei.loc["0000320193-25-000099"]
    assert (amended["form"], amended["filed"], amended["period_end"]) == (
        "10-K/A",
        "2025-11-20",
        "2025-10-17",
    )
    assert dei.loc["0000320193-25-000079", "shares"] == 14776353000.0


def test_weighted_average_is_the_filings_current_quarter() -> None:
    weighted = parse_company_facts(PAYLOAD).query("concept == 'weighted_basic'")
    by_accn = weighted.set_index("accn")
    assert len(by_accn) == 2  # comparatives and year-to-date periods dropped
    q2 = by_accn.loc["0000320193-26-000013"]
    assert (q2["period_start"], q2["period_end"], q2["shares"]) == (
        "2025-12-28",
        "2026-03-28",
        14673278000.0,
    )
    assert by_accn.loc["0000320193-26-000020", "shares"] == 14656110000.0


def test_no_share_facts_is_an_empty_frame() -> None:
    doc = {"cik": 884394, "entityName": "SPDR S&P 500 ETF TRUST", "facts": {"dei": {}}}
    assert parse_company_facts(json.dumps(doc).encode()).empty
    with pytest.raises(ValueError, match="no CIK"):
        parse_company_facts(b'{"facts": {}}')


def test_source_fetches_by_padded_cik_and_404_is_none() -> None:
    seen: list[str] = []

    def transport(url: str) -> bytes:
        seen.append(url)
        if "0000884394" in url:
            raise HttpError(404)
        return PAYLOAD

    source = SecCompanyFacts(http_for(transport, RetryPolicy(tries=1)))
    assert source.fetch(FetchRequest("320193")) == PAYLOAD
    assert seen == [FACTS_URL.format(cik="0000320193")]
    assert source.fetch(FetchRequest("884394", session_date=date(2026, 10, 2))) is None
    normalized = source.normalize(FetchRequest("320193"), PAYLOAD)
    assert normalized is not None and len(normalized.parsed["shares"]) == 8
    with pytest.raises(ValueError, match="not a CIK"):
        source.fetch(FetchRequest("AAPL"))


def _entry(unit: str, *rows: dict[str, object]) -> dict[str, object]:
    return {"units": {unit: list(rows)}}


def _row(start: str, end: str, val: float, filed: str, form: str = "10-Q", **extra: object):  # type: ignore[no-untyped-def]
    return {
        "start": start, "end": end, "val": val, "accn": f"A-{filed}-{form}-{start}", "fy": 2026,
        "fp": "Q1", "form": form, "filed": filed, **extra,
    }  # fmt: skip


def _financials_doc() -> bytes:
    q1 = ("2026-01-01", "2026-03-31")
    doc = {
        "cik": 1234,
        "facts": {
            "us-gaap": {
                "Revenues": _entry(
                    "USD",
                    _row(*q1, 100, "2026-05-01"),
                    _row(*q1, 100, "2027-05-01"),  # the comparative a year later: dropped
                    _row(*q1, 110, "2027-08-01", "10-Q/A"),  # a restatement: kept
                    _row("2026-01-01", "2026-12-31", 500, "2027-02-20", "10-K"),
                    _row("2026-03-01", "2026-03-31", 30, "2026-05-01"),  # a month: dropped
                    _row(*q1, 7, "2026-05-02", "8-K"),  # not a periodic filing: dropped
                    _row(*q1, 8, "2026-05-02", "DEF 14A"),
                ),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _entry(
                    "USD",
                    _row(*q1, 90, "2026-05-01"),  # Revenues has this period: it wins
                    _row("2026-04-01", "2026-06-30", 120, "2026-08-01"),  # only here: kept
                ),
                "SalesRevenueNet": _entry(
                    "USD", _row("2020-01-01", "2020-03-31", 60, "2020-05-01")
                ),
                "NetIncomeLoss": _entry(
                    "USD", _row(*q1, -40, "2026-05-01"), {"start": "2026-01-01"}
                ),  # a loss; a fact without an end or value is dropped
                "EarningsPerShareDiluted": _entry("USD/shares", _row(*q1, -0.5, "2026-05-01")),
            }
        },
    }
    doc["facts"]["us-gaap"]["EarningsPerShareBasic"] = _entry(
        "USD/shares", _row(*q1, 1, "2026-05-01")
    )  # type: ignore[index]
    return json.dumps(doc).encode()


def test_flows_one_tag_per_period_first_filing_and_restatements() -> None:
    rows = parse_company_facts(_financials_doc())
    assert list(rows.columns) == list(FACT_COLUMNS)
    revenue = rows[rows["concept"] == "revenue"].set_index(["period_start", "period_end", "filed"])
    assert sorted(revenue.index) == [
        ("2020-01-01", "2020-03-31", "2020-05-01"),
        ("2026-01-01", "2026-03-31", "2026-05-01"),
        ("2026-01-01", "2026-03-31", "2027-08-01"),
        ("2026-01-01", "2026-12-31", "2027-02-20"),
        ("2026-04-01", "2026-06-30", "2026-08-01"),
    ]
    assert revenue.loc[("2026-01-01", "2026-03-31", "2026-05-01"), "value"] == 100.0  # not 90
    assert revenue.loc[("2026-01-01", "2026-03-31", "2027-08-01"), ["value", "form"]].tolist() == [
        110.0,
        "10-Q/A",
    ]
    assert revenue.loc[("2026-04-01", "2026-06-30", "2026-08-01"), "tag"] == (
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    assert set(revenue["unit"]) == {"usd"} and revenue["shares"].isna().all()


def test_losses_and_eps_are_kept_with_their_units() -> None:
    rows = parse_company_facts(_financials_doc())
    loss = rows[rows["concept"] == "net_income"]
    assert loss["value"].tolist() == [-40.0] and loss["unit"].tolist() == ["usd"]
    eps = rows[rows["concept"] == "eps_diluted"]
    assert eps["value"].tolist() == [-0.5] and eps["unit"].tolist() == ["usd_per_share"]
    assert set(rows["concept"]) == {"revenue", "net_income", "eps_diluted"}  # basic EPS: not kept
