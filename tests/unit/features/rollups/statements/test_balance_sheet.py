"""balance_sheet@v1: latest instant, look-ahead, tag rank, debt rules a to g in one filing,
derived liabilities, the statuses and the financial flag."""

from datetime import date, timedelta

import pandas as pd

from algotrade.features.rollups.statements import balance_sheet as bs
from algotrade.features.rollups.statements import instants
from algotrade.features.rollups.statements.lines import (
    COMPANY,
    PRICE_STATS,
    STATEMENTS,
    StatementParams,
)
from algotrade_sources.vendors.sec.statement_concepts import INSTANT, STATEMENT_CONCEPTS

SESSION = date(2025, 6, 30)
Q1, Q4 = date(2025, 3, 31), date(2024, 12, 31)
COLUMNS = [
    "instrument_id",
    "concept",
    "tag",
    "period_start",
    "period_end",
    "filed",
    "value",
    "accn",
]


def fact(concept: str, tag: str, value: float, end: date = Q1, filed: date | None = None,
         accn: str = "A1", iid: str = "EQ:A") -> tuple:  # fmt: skip
    """One INSTANT row (no period start); filed 40 days after the period end by default."""
    when = filed or end + timedelta(days=40)
    return (iid, concept, f"us-gaap:{tag}", None, end, when, value, accn)


def core(end: date = Q1, **kw) -> list:
    return [
        fact("cash", "CashAndCashEquivalentsAtCarryingValue", 10.0, end, **kw),
        fact("assets", "Assets", 100.0, end, **kw),
        fact("equity", "StockholdersEquity", 40.0, end, **kw),
    ]


def run(facts: list, session: date = SESSION, sic: str | None = None) -> pd.Series:
    stats = pd.DataFrame({"instrument_id": ["EQ:A"], "session_date": session})
    company = pd.DataFrame({"instrument_id": ["EQ:A"], "sic": [sic or "3571"]})
    inputs = {
        PRICE_STATS: stats,
        STATEMENTS: pd.DataFrame(facts, columns=COLUMNS),
        COMPANY: company,
    }
    frame = bs.compute(inputs, session, StatementParams()).set_index("instrument_id")
    return frame.reindex(columns=list(bs.COLUMNS)).loc["EQ:A"]


def debt(*parts: tuple[str, float], accn: str = "A1") -> list:
    return [fact("debt", t, v, accn=accn) for t, v in parts]


def test_the_latest_instant_wins_over_an_older_one() -> None:
    older = [fact("cash", "CashAndCashEquivalentsAtCarryingValue", 5.0, Q4)]
    row = run(older + core())
    assert row["cash"] == 10.0 and row["bs_as_of"] == Q1
    assert row["bs_filed"] == Q1 + timedelta(days=40) and row["bs_status"] == "OK"


def test_a_restatement_filed_after_the_session_is_ignored() -> None:
    late = fact("cash", "CashAndCashEquivalentsAtCarryingValue", 999.0, Q1, SESSION + timedelta(1))
    assert late[5] > SESSION  # the fixture really is a lookahead
    assert run([*core(), late])["cash"] == 10.0
    assert run([*core(), late], session=SESSION + timedelta(days=1))["cash"] == 999.0  # then read
    assert pd.isna(run([late])["cash"]) and run([late])["bs_status"] == "NO_FACTS"


def test_a_restatement_filed_by_the_session_replaces_the_figure() -> None:
    fixed = fact("cash", "CashAndCashEquivalentsAtCarryingValue", 11.0, Q1, date(2025, 6, 1))
    assert run([*core(), fixed])["cash"] == 11.0


def test_a_tag_is_ranked_and_never_mixed() -> None:
    first, second = instants.LINES["cash"]
    row = run([fact("cash", second, 12.0), fact("cash", first, 10.0)])
    assert row["cash"] == 10.0  # the better tag when both report the date
    # the newer date under the second tag beats the older date under the first
    row = run([fact("cash", first, 10.0, Q4), fact("cash", second, 12.0, Q1)])
    assert row["cash"] == 12.0 and row["bs_as_of"] == Q1
    sti = run(
        [fact("sti", "MarketableSecuritiesCurrent", 3.0), fact("sti", "ShortTermInvestments", 7.0)]
    )
    assert sti["sti"] == 7.0  # never both summed
    eq = run([fact("equity", instants.LINES["equity"][1], 55.0)])
    assert (
        eq["stockholders_equity"] == 55.0
    )  # the including-noncontrolling tag when it is the only one


def test_debt_rule_a_adds_short_term_borrowings_not_commercial_paper_too() -> None:
    row = run(
        debt(("LongTermDebt", 100.0), ("ShortTermBorrowings", 10.0), ("CommercialPaper", 5.0))
    )
    assert row["total_debt"] == 110.0 and row["debt_basis"] == "a"
    paper = run(debt(("LongTermDebt", 100.0), ("CommercialPaper", 5.0)))
    assert paper["total_debt"] == 105.0 and paper["debt_basis"] == "a"
    assert run(debt(("LongTermDebt", 100.0)))["total_debt"] == 100.0


def test_debt_rule_b_and_c() -> None:
    parts = (("LongTermDebtNoncurrent", 80.0), ("LongTermDebtCurrent", 20.0))
    b = run(debt(*parts, ("CommercialPaper", 4.0)))
    assert b["total_debt"] == 104.0 and b["debt_basis"] == "b"
    c = run(debt(("LongTermDebtNoncurrent", 80.0), ("DebtCurrent", 30.0)))
    assert c["total_debt"] == 110.0 and c["debt_basis"] == "c"
    both = run(debt(*parts, ("DebtCurrent", 30.0)))
    assert both["debt_basis"] == "b"  # b before c


N, C = instants.LEASE_NONCURRENT, instants.LEASE_CURRENT
T, ALL = instants.LEASE_TOTAL, instants.ALL_DEBT


def test_debt_rule_d_adds_the_noncurrent_and_current_parts_and_short_term_borrowings() -> None:
    d = run(debt((N, 700.0), (C, 50.0), ("ShortTermBorrowings", 10.0), ("CommercialPaper", 5.0)))
    assert d["total_debt"] == 760.0 and d["debt_basis"] == "d"  # never both short-term parts
    assert run(debt((N, 700.0), (C, 50.0)))["total_debt"] == 750.0
    paper = run(debt((N, 700.0), (C, 50.0), ("CommercialPaper", 5.0)))
    assert paper["total_debt"] == 755.0
    first = run(debt(("LongTermDebt", 1.0), (N, 700.0), (C, 50.0)))
    assert first["debt_basis"] == "a"  # a, b and c come first: the older rules never move


def test_debt_rule_e_f_and_g() -> None:
    e = run(debt((N, 700.0), ("DebtCurrent", 60.0), ("ShortTermBorrowings", 9.0)))
    assert e["total_debt"] == 760.0 and e["debt_basis"] == "e"  # DebtCurrent already has the 9
    f = run(debt((T, 750.0), ("ShortTermBorrowings", 10.0)))
    assert f["total_debt"] == 760.0 and f["debt_basis"] == "f"
    g = run(debt((ALL, 900.0), ("ShortTermBorrowings", 10.0), (N, 700.0)))
    assert g["total_debt"] == 900.0 and g["debt_basis"] == "g"  # a total is never added to parts
    assert run(debt((N, 700.0), (C, 50.0), (T, 750.0)))["total_debt"] == 750.0  # d, not 1500
    assert run(debt((N, 700.0), (C, 50.0), (ALL, 99.0)))["debt_basis"] == "d"


def test_rules_b_and_c_keep_winning_when_all_four_new_tags_are_in_the_same_filing() -> None:
    new = ((N, 700.0), (C, 50.0), (T, 750.0), (ALL, 900.0))
    b = run(debt(("LongTermDebtNoncurrent", 80.0), ("LongTermDebtCurrent", 20.0), *new))
    assert b["total_debt"] == 100.0 and b["debt_basis"] == "b"
    c = run(debt(("LongTermDebtNoncurrent", 80.0), ("DebtCurrent", 30.0), *new))
    assert c["total_debt"] == 110.0 and c["debt_basis"] == "c"
    a = run(debt(("LongTermDebt", 95.0), ("ShortTermBorrowings", 5.0), *new))
    assert a["total_debt"] == 100.0 and a["debt_basis"] == "a"
    d = run(debt((N, 700.0), (C, 50.0), ("DebtCurrent", 60.0), (T, 750.0), (ALL, 900.0)))
    assert d["total_debt"] == 750.0 and d["debt_basis"] == "d"  # d before e, f and g


def test_an_incomplete_lease_inclusive_set_stays_not_tagged() -> None:
    for parts in (
        (N,), (C,), (N, "ShortTermBorrowings"), (N, "LongTermDebtCurrent"),
        ("LongTermDebtNoncurrent", "ShortTermBorrowings"), ("DebtCurrent", "ShortTermBorrowings"),
        ("LineOfCredit", "NotesPayable", "FinanceLeaseLiability"),
    ):  # fmt: skip
        row = run([*core(), *debt(*((t, 5.0) for t in parts))])
        assert pd.isna(row["total_debt"]) and row["debt_basis"] == "NOT_TAGGED", parts


def test_lease_inclusive_parts_of_two_filings_never_combine() -> None:
    row = run(debt((N, 700.0), accn="A1") + debt((C, 50.0), accn="A2"))
    assert pd.isna(row["total_debt"]) and row["debt_basis"] == "NOT_TAGGED"
    row = run(debt((N, 700.0), accn="A1") + debt(("DebtCurrent", 60.0), accn="A2"))
    assert pd.isna(row["total_debt"]) and row["debt_basis"] == "NOT_TAGGED"


def test_a_newer_filing_with_a_new_rule_is_read_before_an_older_one() -> None:
    both = debt(("LongTermDebt", 100.0), accn="A1") + [
        fact("debt", t, v, filed=Q1 + timedelta(days=50), accn="A2")
        for t, v in ((N, 7.0), (C, 3.0))
    ]
    row = run(both)
    assert row["total_debt"] == 10.0 and row["debt_basis"] == "d"  # the newest filing, as before


def test_a_debt_part_filed_after_the_session_is_never_read() -> None:
    late = Q1 + timedelta(days=200)
    assert late > SESSION
    parts = [fact("debt", N, 700.0), fact("debt", C, 50.0, filed=late)]
    row = run([*core(), *parts])
    assert pd.isna(row["total_debt"]) and row["debt_basis"] == "NOT_TAGGED"  # d needs the part
    assert run([*core(), *parts], session=late)["total_debt"] == 750.0  # read once it is public
    total = [fact("debt", ALL, 1.0, filed=late)]
    assert run([*core(), *total])["debt_basis"] == "NOT_TAGGED"
    assert run([*core(), *total], session=late)["debt_basis"] == "g"


def test_debt_parts_of_two_filings_never_combine() -> None:
    mixed = debt(("LongTermDebtNoncurrent", 80.0), accn="A1") + debt(
        ("LongTermDebtCurrent", 20.0), accn="A2"
    )
    row = run(mixed)
    assert pd.isna(row["total_debt"]) and row["debt_basis"] == "NOT_TAGGED"
    extra = run(
        debt(("LongTermDebt", 100.0), accn="A1") + debt(("ShortTermBorrowings", 9.0), accn="A2")
    )
    assert extra["total_debt"] == 100.0  # the borrowings of another filing are not added


def test_no_debt_tag_is_null_never_zero() -> None:
    row = run(core())
    assert pd.isna(row["total_debt"]) and row["debt_basis"] == "NOT_TAGGED"
    assert row["bs_status"] == "OK"  # debt is not a core line
    zero = run([*core(), *debt(("LongTermDebt", 0.0))])
    assert zero["total_debt"] == 0.0 and zero["debt_basis"] == "a"  # a reported zero is a zero


def test_liabilities_reported_derived_or_none() -> None:
    reported = run([*core(), fact("liabilities", "Liabilities", 60.0)])
    assert reported["total_liabilities"] == 60.0 and reported["liabilities_basis"] == "REPORTED"
    total = fact("liabilities", "LiabilitiesAndStockholdersEquity", 100.0)
    derived = run([*core(), total])
    assert derived["total_liabilities"] == 60.0 and derived["liabilities_basis"] == "DERIVED"
    other_date = run([*core(Q4), total])  # the equity ends on another date: never mixed
    assert pd.isna(other_date["total_liabilities"]) and other_date["liabilities_basis"] == "NONE"
    assert run(core())["liabilities_basis"] == "NONE"


def test_partial_when_the_core_lines_end_on_different_dates() -> None:
    row = run([*core(Q1)[:2], fact("equity", "StockholdersEquity", 38.0, Q4)])
    assert (
        row["bs_status"] == "PARTIAL"
        and row["bs_as_of"] == Q1
        and row["stockholders_equity"] == 38.0
    )
    assert run(core()[:2])["bs_status"] == "PARTIAL"  # equity missing


def test_stale_is_checked_before_anything_else() -> None:
    old = date(2023, 12, 31)  # 546 days before the session: older than 480
    row = run(core(old), session=date(2025, 6, 30))
    assert row["bs_status"] == "STALE" and row["cash"] == 10.0  # still shown
    partial = run(core(old)[:2], session=date(2025, 6, 30))
    assert partial["bs_status"] == "STALE"  # not PARTIAL


def test_a_bank_keeps_its_balance_sheet_and_is_flagged() -> None:
    row = run([*core(), *debt(("LongTermDebt", 100.0))], sic="6021")
    assert bool(row["is_financial"]) is True and row["bs_status"] == "OK"
    assert (
        row["total_assets"] == 100.0
        and row["stockholders_equity"] == 40.0
        and row["total_debt"] == 100.0
    )
    assert bool(run(core())["is_financial"]) is False


def test_no_facts() -> None:
    row = run([])
    assert row["bs_status"] == "NO_FACTS" and pd.isna(row["cash"]) and pd.isna(row["debt_basis"])


def test_the_tag_lists_match_the_parser_concepts() -> None:
    for line, tags in instants.LINES.items():
        concept_tags = STATEMENT_CONCEPTS[instants.LINE_CONCEPT[line]][1]
        assert [t for t in concept_tags if t in tags] == list(tags), line
    instant = {t for c, (kind, tags) in STATEMENT_CONCEPTS.items() if kind == INSTANT for t in tags}
    assert instant == instants.ALL_TAGS  # every stored instant tag is read by the group


def test_a_line_not_reported_at_the_balance_sheet_date_is_null_with_status_ok() -> None:
    older = [
        fact("sti", "ShortTermInvestments", 7.0, Q4),
        fact("current_assets", "AssetsCurrent", 50.0, Q4),
        fact("debt", "LongTermDebt", 100.0, Q4),
        fact("liabilities", "Liabilities", 60.0, Q4),
    ]
    row = run([*core(), *older])
    assert row["bs_status"] == "OK" and row["bs_as_of"] == Q1
    assert pd.isna(row["sti"]) and pd.isna(row["current_assets"])  # not an older figure
    assert pd.isna(row["total_debt"]) and row["debt_basis"] == "NOT_TAGGED"
    assert pd.isna(row["total_liabilities"]) and row["liabilities_basis"] == "NONE"


def test_derived_liabilities_subtract_the_equity_including_the_noncontrolling_interest() -> None:
    total = fact("liabilities", "LiabilitiesAndStockholdersEquity", 100.0)
    nci = fact("equity", instants.LINES["equity"][1], 45.0)  # parent 40 + minority 5
    both = run([*core(), nci, total])
    assert both["total_liabilities"] == 55.0 and both["liabilities_basis"] == "DERIVED"
    assert both["stockholders_equity"] == 40.0  # the column keeps the parent-only figure first
    assert run([*core(), total])["total_liabilities"] == 60.0  # parent-only when that is all


def test_filings_of_one_day_are_ordered_by_accession_not_by_input_order() -> None:
    one = fact("cash", "CashAndCashEquivalentsAtCarryingValue", 1.0, accn="A1")
    two = fact("cash", "CashAndCashEquivalentsAtCarryingValue", 2.0, accn="A2")
    assert run([one, two])["cash"] == run([two, one])["cash"] == 2.0
