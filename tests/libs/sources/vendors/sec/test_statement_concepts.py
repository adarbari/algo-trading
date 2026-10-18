"""The statement concepts and their parse (ADR 0067), on recorded (trimmed) companyfacts
documents of Apple, US Bancorp (a bank) and Power Integrations (no debt), and on small made-up
ones for the rules a recording does not show: instants against durations, the tag kept on every
row, a restatement keeping both rows, comparatives and non-periodic forms dropped."""

import json
from pathlib import Path

import pandas as pd
import pytest

from algotrade_sources.framework.base import FetchRequest
from algotrade_sources.vendors.sec import company_facts
from algotrade_sources.vendors.sec.company_facts import (
    STATEMENT_COLUMNS,
    SecCompanyFacts,
    parse_statements,
)
from algotrade_sources.vendors.sec.statement_concepts import (
    DURATION,
    INSTANT,
    STATEMENT_CONCEPTS,
    STATEMENT_TAGS_VERSION_DATE,
)
from tests.conftest import REPO_ROOT

SEC = REPO_ROOT / "tests" / "fixtures" / "sources" / "sec"


def recorded(cik: str) -> bytes:
    return (SEC / f"statements_CIK{cik}.json").read_bytes()


AAPL, BANK, DEBT_FREE = (recorded(c) for c in ("0000320193", "0000036104", "0000833640"))
ALL_TAGS = [t for _, tags in STATEMENT_CONCEPTS.values() for t in tags]


def test_the_concepts_and_their_tags_are_the_planned_ones() -> None:
    assert {c: kind for c, (kind, _) in STATEMENT_CONCEPTS.items()} == {
        **dict.fromkeys(
            ("cost_of_revenue", "gross_profit", "operating_income", "pretax_income",
             "income_tax", "interest_expense", "da", "ocf", "capex"), DURATION,
        ),
        **dict.fromkeys(
            ("cash", "sti", "debt", "assets", "liabilities", "equity", "current"), INSTANT
        ),
    }  # fmt: skip
    assert STATEMENT_CONCEPTS["cost_of_revenue"][1][0] == "CostOfRevenue"  # best tag first
    assert "LiabilitiesAndStockholdersEquity" in STATEMENT_CONCEPTS["liabilities"][1]
    assert len(ALL_TAGS) == len(set(ALL_TAGS)) == 39  # one concept per tag


def test_the_recordings_read_the_alternative_tags_of_a_concept() -> None:
    """Real filers use different tags for one concept (cost of revenue, short-term
    investments): the recordings carry both kinds, so a tag name that does not exist in the
    documents would show here."""
    found = set()
    for payload in (AAPL, BANK, DEBT_FREE):
        found |= set(parse_statements(payload)["tag"].str.removeprefix("us-gaap:"))
    assert found <= set(ALL_TAGS)
    assert {"CostOfRevenue", "CostOfGoodsAndServicesSold", "LongTermDebt", "ShortTermBorrowings",
            "MarketableSecuritiesCurrent", "ShortTermInvestments"} <= found  # fmt: skip


def test_instants_have_no_start_and_durations_span_a_quarter_to_a_year() -> None:
    rows = parse_statements(AAPL)
    assert list(rows.columns) == list(STATEMENT_COLUMNS)
    instants = rows[rows["period_type"] == INSTANT]
    assert instants["period_start"].isna().all() and set(instants["concept"]) >= {"cash", "assets"}
    durations = rows[rows["period_type"] == DURATION]
    span = (
        pd.to_datetime(durations["period_end"]) - pd.to_datetime(durations["period_start"])
    ).dt.days
    assert set(durations["concept"]) >= {"ocf", "capex", "operating_income", "cost_of_revenue"}
    assert ((span.between(75, 105)) | span.between(160, 200) | span.between(250, 290)
            | span.between(340, 380)).all()  # fmt: skip
    assert set(rows["unit"]) == {"usd"} and set(rows["form"]) == {"10-K", "10-Q"}
    assert set(rows["cik"]) == {"0000320193"}


def test_the_tag_is_kept_on_every_row_and_a_concept_keeps_all_its_tags() -> None:
    rows = parse_statements(AAPL)
    assert rows["tag"].str.startswith("us-gaap:").all()
    cash = rows[rows["concept"] == "cash"]
    assert set(cash["tag"]) == {
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    }  # the narrower tag is not dropped for the wider one
    year_end = cash[
        cash["tag"].str.endswith("CarryingValue") & (cash["period_end"] == "2025-09-27")
    ]
    assert [(r.form, r.value) for r in year_end.itertuples()] == [("10-K", 35934000000.0)]
    cost = rows[rows["concept"] == "cost_of_revenue"]
    assert set(cost["tag"]) == {"us-gaap:CostOfGoodsAndServicesSold"}  # one tag filed, one kept
    assert set(parse_statements(DEBT_FREE).query("concept == 'cost_of_revenue'")["tag"]) == {
        "us-gaap:CostOfRevenue"
    }


def test_a_comparative_is_dropped_and_a_changed_value_keeps_both_rows() -> None:
    """Apple's 2025-09-27 long-term debt: the 10-K, then a 10-Q's comparative with a rounded
    (different) value: both stay, each with its filing date. Its 2025-09-27 cash is reported
    again in later filings with the same value: one row."""
    rows = parse_statements(AAPL)
    debt = rows[(rows["tag"] == "us-gaap:LongTermDebt") & (rows["period_end"] == "2025-09-27")]
    assert [(r.filed, r.form, r.value) for r in debt.itertuples()] == [
        ("2025-10-31", "10-K", 90678000000.0),
        ("2026-01-30", "10-Q", 90700000000.0),
    ]
    key = ["concept", "tag", "period_start", "period_end"]
    same = rows.fillna({"period_start": ""}).groupby([*key, "value"]).size()
    assert (same == 1).all()  # never the same figure twice for one period


def test_a_bank_has_no_cost_or_operating_lines_and_its_short_debt_is_kept() -> None:
    rows = parse_statements(BANK)
    assert not set(rows["concept"]) & {"cost_of_revenue", "gross_profit", "operating_income"}
    assert set(rows["concept"]) >= {"assets", "liabilities", "equity", "pretax_income", "ocf"}
    assert set(rows[rows["concept"] == "debt"]["tag"]) == {"us-gaap:ShortTermBorrowings"}
    equity = rows[rows["concept"] == "equity"]
    assert len(set(equity["tag"])) == 2  # with and without the noncontrolling interest


def test_a_filer_without_debt_tags_has_no_debt_rows_not_zero_rows() -> None:
    rows = parse_statements(DEBT_FREE)
    assert "debt" not in set(rows["concept"])
    assert not rows["tag"].str.contains("Debt|Borrowings|CommercialPaper").any()
    assert {"assets", "liabilities", "cash", "ocf"} <= set(rows["concept"])
    forms = {x["form"] for v in json.loads(DEBT_FREE)["facts"]["us-gaap"].values()
             for rs in v["units"].values() for x in rs}  # fmt: skip
    assert "DEF 14A" in forms and "DEF 14A" not in set(rows["form"])  # not a periodic filing


def _row(
    end: str, val: float, filed: str, form: str = "10-Q", start: str | None = None
) -> dict[str, object]:
    row = {"end": end, "val": val, "accn": f"A-{filed}-{form}", "fy": 2026, "fp": "Q1",
           "form": form, "filed": filed}  # fmt: skip
    return {**row, "start": start} if start else row


def _doc(**tags: list[dict[str, object]]) -> bytes:
    facts = {t: {"units": {"USD": rows}} for t, rows in tags.items()}
    return json.dumps({"cik": 7, "facts": {"us-gaap": facts}}).encode()


def test_instants_are_deduplicated_per_tag_and_date_with_restatements_kept() -> None:
    rows = parse_statements(_doc(
        Assets=[
            _row("2026-03-31", 100, "2026-05-01"),
            _row("2026-03-31", 100, "2027-05-01"),  # the comparative a year later: dropped
            _row("2026-03-31", 110, "2027-08-01", "10-Q/A"),  # a restatement: kept
            _row("2026-06-30", 120, "2026-08-01", "8-K"),  # not periodic: dropped
            _row("2026-06-30", 130, "2026-08-02", start="2026-04-01"),  # a duration: dropped
            {"end": "2026-09-30", "filed": "2026-11-01"},  # no value: dropped
        ],
        LiabilitiesAndStockholdersEquity=[_row("2026-03-31", 100, "2026-05-01")],
    ))  # fmt: skip
    assets = rows[rows["concept"] == "assets"]
    assert [(r.filed, r.value, r.form) for r in assets.itertuples()] == [
        ("2026-05-01", 100.0, "10-Q"),
        ("2027-08-01", 110.0, "10-Q/A"),
    ]
    assert list(rows[rows["concept"] == "liabilities"]["tag"]) == [
        "us-gaap:LiabilitiesAndStockholdersEquity"
    ]  # stored under liabilities, its own tag
    assert set(rows["period_type"]) == {INSTANT}


def test_the_lease_inclusive_and_all_debt_tags_are_stored_as_debt() -> None:
    """The parser keeps only listed tags: these four were the gap that left half the
    operating companies without a debt total (ADR 0067)."""
    tags = (
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        "DebtLongtermAndShorttermCombinedAmount",
    )
    rows = parse_statements(_doc(**{t: [_row("2026-03-31", 5, "2026-05-01")] for t in tags}))
    assert set(rows["concept"]) == {"debt"} and set(rows["tag"]) == {f"us-gaap:{t}" for t in tags}


def test_the_source_carries_the_tag_list_date_the_shares_task_reads() -> None:
    assert SecCompanyFacts.statements_tags_date == STATEMENT_TAGS_VERSION_DATE


def test_durations_follow_the_flow_rule_and_a_loss_and_zero_are_kept() -> None:
    q1 = {"start": "2026-01-01", "end": "2026-03-31"}
    rows = parse_statements(_doc(
        OperatingIncomeLoss=[
            _row(**q1, val=-40, filed="2026-05-01"),
            _row(**q1, val=-40, filed="2027-05-01"),  # comparative
            _row(**q1, val=-41, filed="2027-08-01"),  # restated
            _row("2026-03-31", 5, "2026-05-01", start="2026-03-01"),  # a month
            _row("2026-12-31", 0, "2027-02-20", "10-K", start="2026-01-01"),  # a year, zero
        ],
    ))  # fmt: skip
    assert [(r.period_end, r.filed, r.value) for r in rows.itertuples()] == [
        ("2026-03-31", "2026-05-01", -40.0),
        ("2026-12-31", "2027-02-20", 0.0),
        ("2026-03-31", "2027-08-01", -41.0),
    ]
    assert set(rows["period_type"]) == {DURATION}


def test_other_currencies_and_no_statement_tags_give_nothing() -> None:
    doc = {
        "cik": 7,
        "facts": {"us-gaap": {"Assets": {"units": {"CNY": [_row("2026-03-31", 1, "2026-05-01")]}}}},
    }
    assert parse_statements(json.dumps(doc).encode()).empty
    assert list(parse_statements(b'{"cik": 7, "facts": {}}').columns) == list(STATEMENT_COLUMNS)
    with pytest.raises(ValueError, match="no CIK"):
        parse_statements(b'{"facts": {}}')


def test_one_fetch_feeds_both_tables() -> None:
    source = SecCompanyFacts(None)  # type: ignore[arg-type]  # normalize never uses the transport
    normalized = source.normalize(FetchRequest("320193"), AAPL)
    assert normalized is not None
    assert set(normalized.parsed) == {"shares", "statements"}
    assert len(normalized.parsed["statements"]) == len(parse_statements(AAPL)) > 0
    assert len(normalized.parsed["shares"]) > 0
    assert Path(SEC / "statements_CIK0000320193.json").stat().st_size < 100_000  # a small recording


def test_a_statements_parse_error_leaves_the_shares_and_is_noted(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(company_facts, "_statement_rows", lambda doc, cik: 1 / 0)
    normalized = SecCompanyFacts(None).normalize(FetchRequest("320193"), AAPL)  # type: ignore[arg-type]
    assert normalized is not None
    assert set(normalized.parsed) == {"shares"} and len(normalized.parsed["shares"]) > 0
    assert normalized.notes == {"statements_parse_error": 1}
