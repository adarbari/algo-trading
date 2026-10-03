"""SEC company facts against a recorded (trimmed) payload: only share counts are kept, one
cover count per filing (classes summed), one weighted average per filing (its current
period), amendments as their own rows, zero counts dropped."""

import json
from datetime import date

import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.framework.http import HttpError, RetryPolicy
from algotrade_sources.vendors.sec.company_facts import (
    FACTS_URL,
    SHARE_COLUMNS,
    SecCompanyFacts,
    parse_company_facts,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import http_for

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec" / "companyfacts_CIK0000320193.json"
PAYLOAD = FIXTURE.read_bytes()


def test_keeps_only_share_counts() -> None:
    rows = parse_company_facts(PAYLOAD)
    assert list(rows.columns) == list(SHARE_COLUMNS)
    assert set(rows["concept"]) == {"dei", "weighted_basic"}
    assert set(rows["cik"]) == {"0000320193"}
    assert (rows["shares"] > 0).all()  # the 2009 zero is dropped


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
    assert normalized is not None and len(normalized.parsed["shares"]) == 7
    with pytest.raises(ValueError, match="not a CIK"):
        source.fetch(FetchRequest("AAPL"))
