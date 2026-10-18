"""income_statement@v2: TTM of each line, the financial-company rule, tags and look-ahead."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.features.rollups.statements import income_statement as inc
from algotrade.features.rollups.statements.lines import (
    COMPANY,
    PRICE_STATS,
    STATEMENTS,
    StatementParams,
)
from algotrade_sources.vendors.sec.statement_concepts import STATEMENT_CONCEPTS
from tests.helpers.stored_frames import quarter_facts, statement_frame

SESSION = date(2025, 6, 30)
FIRST_END = date(2024, 6, 30)  # four quarters end 2024-06-30 .. 2025-03-30, filed 40 days later
P = StatementParams()
CORE = ("operating_income", "pretax_income", "income_tax")


def run(
    facts: list, ids: tuple[str, ...] = ("EQ:A",), sic: dict[str, str] | None = None,
    session: date = SESSION,
) -> pd.DataFrame:  # fmt: skip
    stats = pd.DataFrame({"instrument_id": list(ids), "session_date": session})
    company = pd.DataFrame({"instrument_id": list(sic or {}), "sic": list((sic or {}).values())})
    inputs = {PRICE_STATS: stats, STATEMENTS: statement_frame(facts), COMPANY: company}
    return (
        inc.compute(inputs, session, P)
        .set_index("instrument_id")
        .reindex(columns=list(inc.COLUMNS))
    )


def quarters(concept: str, values: list[float], iid: str = "EQ:A", tag: str | None = None) -> list:
    return quarter_facts(iid, concept, tag or inc.CONCEPT_TAGS[concept][0], values, FIRST_END)


def test_a_normal_filer_gets_the_ttm_of_four_quarters() -> None:
    facts = [
        f for c in CORE for f in quarters(c, [10.0, 20.0, 30.0, 40.0])
    ] + quarters("gross_profit", [1.0, 2.0, 3.0, 4.0])  # fmt: skip
    row = run(facts).loc["EQ:A"]
    assert row["ebit_ttm"] == 100.0 and row["pretax_income_ttm"] == 100.0
    assert row["income_tax_ttm"] == 100.0 and row["gross_profit_ttm"] == 10.0
    assert pd.isna(row["cost_of_revenue_ttm"]) and pd.isna(row["da_ttm"])  # untagged is null
    assert row["is_status"] == "OK" and row["is_ttm_as_of"] == date(2025, 3, 30)


def test_a_bank_is_financial_with_the_ebit_family_null() -> None:
    facts = [
        f
        for c in (*CORE, "da", "interest_expense")
        for f in quarters(c, [1.0, 1.0, 1.0, 1.0], iid="EQ:B")
    ]
    row = run(facts, ids=("EQ:B",), sic={"EQ:B": "6021"}).loc["EQ:B"]
    assert row["is_status"] == "FINANCIAL"
    assert all(pd.isna(row[c]) for c in ("ebit_ttm", "da_ttm", "interest_expense_ttm"))
    assert row["pretax_income_ttm"] == 4.0 and row["income_tax_ttm"] == 4.0
    insurer = run(facts, ids=("EQ:B",), sic={"EQ:B": "6411"}).loc["EQ:B"]
    assert insurer["is_status"] == "FINANCIAL"
    other = run(facts, ids=("EQ:B",), sic={"EQ:B": "6412"}).loc["EQ:B"]  # just outside the range
    assert other["is_status"] == "OK" and other["ebit_ttm"] == 4.0


def test_a_period_takes_the_first_tag_that_reports_it_and_never_mixes_tags() -> None:
    first, third = inc.CONCEPT_TAGS["cost_of_revenue"][0], inc.CONCEPT_TAGS["cost_of_revenue"][2]
    early = quarters("cost_of_revenue", [1.0, 2.0, 3.0, 4.0], tag=first)[:2]
    late = quarters("cost_of_revenue", [3.0, 4.0], tag=third)  # reported for the same first two
    later = quarter_facts(
        "EQ:A", "cost_of_revenue", third, [30.0, 40.0], FIRST_END + timedelta(days=182)
    )
    rows = [*early, *late, *later]  # Q1 Q2 under the best tag; Q3 Q4 only under the third
    row = run(rows).loc["EQ:A"]
    assert row["cost_of_revenue_ttm"] == 1.0 + 2.0 + 30.0 + 40.0  # the best tag wins per period
    # a six-month figure of one tag is never reduced by the three-month figure of another
    start = date(2024, 1, 1)
    ytd = [
        ("EQ:C", "operating_income", inc.CONCEPT_TAGS["operating_income"][0], start,
         date(2024, 6, 30), date(2024, 8, 5), 50.0),
        ("EQ:C", "operating_income", "OtherTag", start, date(2024, 3, 31), date(2024, 5, 5), 20.0),
    ]  # fmt: skip
    assert inc.lines(statement_frame(ytd), inc.RANKS, SESSION, P) == {
        "EQ:C": {"operating_income": [(19723, 19904, 50.0, 19940, 0)]}
    }  # the unknown tag is dropped, so no quarter can be derived from the two


def test_a_missing_quarter_gives_partial_and_no_ttm_never_a_wrong_sum() -> None:
    facts = quarters("operating_income", [10.0, 20.0, 30.0]) + [
        f for c in ("pretax_income", "income_tax") for f in quarters(c, [1.0, 1.0, 1.0, 1.0])
    ]
    row = run(facts).loc["EQ:A"]
    assert pd.isna(row["ebit_ttm"]) and row["pretax_income_ttm"] == 4.0
    assert row["is_status"] == "PARTIAL"
    gap = [f for i, f in enumerate(quarters("operating_income", [1.0] * 4)) if i != 1]
    assert pd.isna(run(gap).loc["EQ:A", "ebit_ttm"])  # a hole in the quarters
    nothing = run(quarters("operating_income", [10.0, 20.0, 30.0]))
    assert nothing.loc["EQ:A", "is_status"] == "NO_TTM"  # facts filed, no TTM can be formed


def test_an_instrument_without_facts_is_no_facts() -> None:
    row = run([], ids=("EQ:Z",)).loc["EQ:Z"]
    assert row["is_status"] == "NO_FACTS" and np.isnan(row["ebit_ttm"])


def test_a_restatement_or_filing_after_the_session_never_moves_it() -> None:
    facts = quarters("operating_income", [10.0, 20.0, 30.0, 40.0])
    end = FIRST_END + timedelta(days=91 * 3)
    tag = inc.CONCEPT_TAGS["operating_income"][0]
    after = SESSION + timedelta(days=3)
    facts.append(("EQ:A", "operating_income", tag, end - timedelta(days=89), end, after, 400.0))
    assert run(facts).loc["EQ:A", "ebit_ttm"] == 100.0  # filed three days after the session
    assert run(facts, session=after + timedelta(days=1)).loc["EQ:A", "ebit_ttm"] == 460.0
    late = quarters("operating_income", [10.0, 20.0, 30.0, 40.0], tag=None)
    late[-1] = (*late[-1][:5], after, late[-1][6])  # the fourth quarter itself filed after S
    assert pd.isna(run(late).loc["EQ:A", "ebit_ttm"])


def test_year_to_date_facts_of_a_10q_give_the_quarters() -> None:
    tag, start = inc.CONCEPT_TAGS["operating_income"][0], date(2024, 1, 1)
    ytd = [(date(2024, 3, 31), 10.0), (date(2024, 6, 30), 30.0), (date(2024, 9, 30), 60.0),
           (date(2024, 12, 31), 100.0)]  # fmt: skip
    facts = [
        ("EQ:A", "operating_income", tag, start, end, end + timedelta(days=45), v) for end, v in ytd
    ]
    row = run(facts, session=date(2025, 3, 1)).loc["EQ:A"]
    assert row["ebit_ttm"] == 100.0  # 10 + (30 - 10) + (60 - 30) + (100 - 60)


def test_an_old_ttm_is_stale_but_shown() -> None:
    facts = [f for c in CORE for f in quarters(c, [1.0] * 4)]
    row = run(facts, session=date(2026, 12, 1)).loc["EQ:A"]
    assert row["is_status"] == "STALE" and row["ebit_ttm"] == 4.0


def test_the_tag_lists_are_the_ones_the_parser_stores() -> None:
    for concept, tags in inc.CONCEPT_TAGS.items():
        assert tags == STATEMENT_CONCEPTS[concept][1], concept


def test_lines_ending_on_different_periods_are_partial_not_ok() -> None:
    tag = inc.CONCEPT_TAGS["pretax_income"][0]
    year = (
        "EQ:A",
        "pretax_income",
        tag,
        date(2024, 1, 1),
        date(2024, 12, 31),
        date(2025, 2, 15),
        7.0,
    )
    facts = quarters("operating_income", [1.0] * 4) + quarters("income_tax", [1.0] * 4) + [year]
    row = run(facts).loc["EQ:A"]
    assert row["pretax_income_ttm"] == 7.0 and row["ebit_ttm"] == 4.0  # the fiscal-year fallback
    assert row["is_status"] == "PARTIAL"  # one line ends 2024-12-31, the others 2025-03-30


def test_an_old_bank_is_stale_not_financial() -> None:
    facts = [f for c in CORE for f in quarters(c, [1.0] * 4, iid="EQ:B")]
    old = run(facts, ids=("EQ:B",), sic={"EQ:B": "6021"}, session=date(2026, 12, 1))
    assert old.loc["EQ:B", "is_status"] == "STALE"
    assert run(facts, ids=("EQ:B",), sic={"EQ:B": "6021"}).loc["EQ:B", "is_status"] == "FINANCIAL"
