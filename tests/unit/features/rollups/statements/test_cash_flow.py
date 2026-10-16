"""cash_flow@v1: quarters from cumulative 10-Q figures, capex as a positive payment, look-ahead."""

from datetime import date, timedelta

import pandas as pd

from algotrade.features.rollups.statements import cash_flow as cf
from algotrade.features.rollups.statements.lines import PRICE_STATS, STATEMENTS, StatementParams
from algotrade_sources.vendors.sec.statement_concepts import STATEMENT_CONCEPTS
from tests.helpers.stored_frames import statement_frame

SESSION = date(2025, 3, 1)
OCF, CAPEX = cf.CONCEPT_TAGS["ocf"][0], cf.CONCEPT_TAGS["capex"][0]
START = date(2024, 1, 1)
ENDS = (date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31))


def ytd(concept: str, tag: str, values: list[float], filed_after: int = 45) -> list:
    """The cumulative figures a fiscal year 2024 filer reports: 3, 6, 9 and 12 months."""
    return [
        ("EQ:A", concept, tag, START, end, end + timedelta(days=filed_after), v)
        for end, v in zip(ENDS, values, strict=True)
    ]


def run(facts: list, session: date = SESSION) -> pd.Series:
    stats = pd.DataFrame({"instrument_id": ["EQ:A"], "session_date": session})
    inputs = {PRICE_STATS: stats, STATEMENTS: statement_frame(facts)}
    frame = cf.compute(inputs, session, StatementParams()).set_index("instrument_id")
    return frame.reindex(columns=list(cf.COLUMNS)).loc["EQ:A"]


def test_the_year_to_date_figures_of_a_10q_give_the_quarters_and_the_ttm() -> None:
    row = run(
        ytd("ocf", OCF, [10.0, 30.0, 60.0, 100.0]) + ytd("capex", CAPEX, [1.0, 3.0, 6.0, 10.0])
    )
    assert row["ocf_ttm"] == 100.0 and row["capex_ttm"] == 10.0  # 10 + 20 + 30 + 40
    assert row["cf_status"] == "OK" and row["cf_as_of"] == date(2024, 12, 31)
    assert row["capex_ttm"] > 0  # the payment as stored, never a negative cash flow


def test_a_quarter_is_never_derived_across_tags() -> None:
    other = cf.CONCEPT_TAGS["ocf"][1]
    mixed = ytd("ocf", OCF, [10.0, 30.0, 60.0, 100.0])
    mixed[2] = (*mixed[2][:2], other, *mixed[2][3:])  # the nine months under another tag
    assert run(mixed[:3])["cf_status"] == "NO_FACTS"  # no Q3 (nine minus six) across two tags
    assert run(mixed)["ocf_ttm"] == 100.0  # only the fiscal year itself: not a sum of mixed parts


def test_one_line_gives_partial_and_none_gives_no_facts() -> None:
    row = run(ytd("ocf", OCF, [10.0, 30.0, 60.0, 100.0]))
    assert row["cf_status"] == "PARTIAL" and pd.isna(row["capex_ttm"])
    assert run([])["cf_status"] == "NO_FACTS"


def test_a_figure_filed_after_the_session_is_never_read() -> None:
    facts = ytd("ocf", OCF, [10.0, 30.0, 60.0, 100.0], filed_after=45)
    assert run(facts, session=date(2025, 2, 15))["ocf_ttm"] == 100.0
    assert pd.isna(run(facts, session=date(2025, 2, 13))["ocf_ttm"])  # the annual not yet filed
    facts.append(("EQ:A", "ocf", f"us-gaap:{OCF}", START, ENDS[3], date(2025, 3, 5), 900.0))
    assert run(facts)["ocf_ttm"] == 100.0  # a restatement filed after the session


def test_an_old_ttm_is_stale() -> None:
    facts = ytd("ocf", OCF, [10.0, 30.0, 60.0, 100.0]) + ytd("capex", CAPEX, [1.0, 3.0, 6.0, 10.0])
    assert run(facts, session=date(2026, 9, 1))["cf_status"] == "STALE"


def test_the_tag_lists_are_the_ones_the_parser_stores() -> None:
    for concept, tags in cf.CONCEPT_TAGS.items():
        assert tags == STATEMENT_CONCEPTS[concept][1], concept
