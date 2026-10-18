"""``insider_buys@v1``: distinct recent buyers, opportunistic against routine (Cohen, Malloy and
Pomorski), unclassified with a short record, the 10b5-1 flag, null (no row) with no purchase."""

from datetime import date

import pandas as pd

from algotrade.data.insiders.reading import BUY_WINDOW_DAYS as LOADER_DAYS
from algotrade.features.rollups.events import insider_buys as ib

SESSION = date(2026, 10, 2)
A, B, C = "EQ:A", "EQ:B", "EQ:C"


def line(iid: str, owner: str, traded: date, code: str = "P", known: date | None = None,
         plan: bool | None = None, accession: str | None = None,
         owners: int = 1) -> dict[str, object]:  # fmt: skip
    return {
        "instrument_id": iid, "owner_cik": owner, "transaction_date": traded,
        "transaction_code": code, "derivative": False, "plan_10b5_1": plan,
        "known_from": known or date(2026, 9, 28), "as_of": SESSION,
        "accession": accession or f"{owner}-{traded}-{code}", "owner_count": owners,
    }  # fmt: skip


def compute(*lines: dict[str, object]) -> pd.DataFrame:
    frame = pd.DataFrame(lines)
    return ib.compute({ib.EVENTS: frame}, SESSION, None).set_index("instrument_id")


def is_false(value: object) -> bool:
    return not pd.isna(value) and not value  # type: ignore[arg-type]


def is_true(value: object) -> bool:
    return not pd.isna(value) and bool(value)  # type: ignore[arg-type]


def test_the_window_matches_the_loaders() -> None:
    assert ib.BUY_WINDOW_DAYS == LOADER_DAYS


def test_three_buyers_are_a_cluster_and_one_owner_with_two_lines_counts_once() -> None:
    out = compute(
        line(A, "o1", date(2026, 9, 25)), line(A, "o1", date(2026, 9, 26)),
        line(A, "o2", date(2026, 9, 25)), line(A, "o3", date(2026, 9, 25)),
        line(B, "o4", date(2026, 9, 25)),
    )  # fmt: skip
    assert (
        out.at[A, "insider_cluster_buy_count"] == 3 and out.at[B, "insider_cluster_buy_count"] == 1
    )


def test_a_purchase_known_before_the_window_or_a_sale_alone_gives_no_row() -> None:
    old = line(A, "o1", date(2026, 8, 1), known=date(2026, 8, 3))  # 60 days ago
    sale = line(B, "o2", date(2026, 9, 25), code="S")
    assert compute(old, sale).empty
    assert ib.compute({ib.EVENTS: None}, SESSION, None).empty


def test_a_trader_in_the_same_month_every_year_is_routine_and_the_rest_opportunistic() -> None:
    routine = [line(A, "r", date(y, 9, 20), code="S") for y in (2023, 2024, 2025)]
    a_buy = line(A, "r", date(2026, 9, 25))
    # opportunistic: a trade in each of the three years, but not in the purchase's month
    odd = [line(B, "o", date(2023, 9, 20), code="S"), line(B, "o", date(2024, 3, 2), code="S"),
           line(B, "o", date(2025, 3, 2), code="S")]  # fmt: skip
    b_buy = line(B, "o", date(2026, 9, 25))
    out = compute(*routine, a_buy, *odd, b_buy)
    assert is_false(out.at[A, "insider_opportunistic_flag"])
    assert is_true(out.at[B, "insider_opportunistic_flag"])


def test_an_owner_missing_a_year_is_unclassified_never_opportunistic() -> None:
    # no record at all, a short record, and a gap year (2024 missing): none can be called
    short = [line(A, "new", date(2025, 6, 1), code="S")]
    gap = [line(B, "gap", date(2023, 9, 20), code="S"), line(B, "gap", date(2025, 9, 20), code="S")]
    out = compute(
        line(A, "new", date(2026, 9, 25)), *short, line(B, "gap", date(2026, 9, 25)), *gap
    )
    assert pd.isna(out.at[A, "insider_opportunistic_flag"])
    assert pd.isna(out.at[B, "insider_opportunistic_flag"])
    # one classed routine buyer beside an unclassed one: false, the unclassed ignored
    rows = [line(C, "r", date(y, 9, 20), code="S") for y in (2023, 2024, 2025)]
    out = compute(*rows, line(C, "r", date(2026, 9, 25)), line(C, "new", date(2026, 9, 26)))
    assert is_false(out.at[C, "insider_opportunistic_flag"])


def test_a_joint_filing_counts_one_buyer_so_it_cannot_make_a_cluster_alone() -> None:
    joint = [line(A, o, date(2026, 9, 25), accession="J1", owners=3) for o in ("f", "g", "m")]
    out = compute(*joint)
    assert out.at[A, "insider_cluster_buy_count"] == 1
    mixed = [*joint, line(A, "o2", date(2026, 9, 25)), line(A, "o3", date(2026, 9, 26))]
    assert compute(*mixed).at[A, "insider_cluster_buy_count"] == 3


def test_the_plan_flag_is_true_with_a_plan_buy_false_without_and_null_when_never_stated() -> None:
    out = compute(
        line(A, "o1", date(2026, 9, 25), plan=True), line(A, "o2", date(2026, 9, 25), plan=False),
        line(B, "o3", date(2026, 9, 25), plan=False), line(C, "o4", date(2026, 9, 25)),
    )  # fmt: skip
    assert is_true(out.at[A, "plan_10b5_1_flag"]) and is_false(out.at[B, "plan_10b5_1_flag"])
    assert pd.isna(out.at[C, "plan_10b5_1_flag"])
