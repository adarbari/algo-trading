"""``walk_in_order``: deterministic, no lookahead, a decision at D sees only earlier decisions'
trades, and unordered sessions are refused (ADR 0088, G15)."""

from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from algotrade.services.evaluation.portfolio_level.book import OpenTrade, PortfolioRow
from algotrade.services.evaluation.portfolio_level.walk import Book, walk_in_order

START = date(2026, 1, 5)
DAYS = st.lists(st.integers(0, 60), min_size=1, max_size=15, unique=True).map(
    lambda xs: [START + timedelta(days=x) for x in sorted(xs)]
)
HOLD = st.integers(1, 10)


def _decide(hold: int, seen: list[tuple[date, int]]):
    def decide(day: date, row: PortfolioRow) -> list[OpenTrade]:
        opened = row.values["portfolio.open_positions"]
        seen.append((day, opened))  # type: ignore[arg-type]
        if opened >= 3:  # a portfolio rule: no new trade while three are open
            return []
        end = day + timedelta(days=hold)
        return [OpenTrade(f"N{day.toordinal()}", day, end, end, None, "open")]

    return decide


def _sectors(_day: date, ids):  # type: ignore[no-untyped-def]
    return dict.fromkeys(ids, "s")


@given(DAYS, HOLD)
def test_the_same_inputs_give_the_same_rows(days: list[date], hold: int) -> None:
    a = walk_in_order(days, _decide(hold, []), _sectors)
    b = walk_in_order(days, _decide(hold, []), _sectors)
    assert a == b


@given(DAYS, HOLD)
def test_a_decision_sees_only_trades_of_earlier_sessions(days: list[date], hold: int) -> None:
    seen: list[tuple[date, int]] = []
    rows = walk_in_order(days, _decide(hold, seen), _sectors)
    assert list(rows) == days
    assert rows[days[0]].values["portfolio.open_positions"] == 0
    for (_day, opened), earlier in zip(
        seen, [[], *(days[:i] for i in range(1, len(days)))], strict=True
    ):
        assert opened <= len(earlier)  # never more open than decided before it


@given(DAYS, HOLD)
def test_a_prefix_of_the_sessions_gives_the_same_rows_as_the_whole(
    days: list[date], hold: int
) -> None:
    whole = walk_in_order(days, _decide(hold, []), _sectors)
    cut = days[: max(1, len(days) // 2)]
    assert {d: whole[d] for d in cut} == walk_in_order(cut, _decide(hold, []), _sectors)


def test_unsorted_or_repeated_sessions_are_refused() -> None:
    with pytest.raises(ValueError, match="ascending"):
        walk_in_order([START + timedelta(days=1), START], _decide(1, []), _sectors)
    with pytest.raises(ValueError, match="ascending"):
        walk_in_order([START, START], _decide(1, []), _sectors)


def test_a_book_adds_trades_and_a_lost_leg_makes_every_row_unknown_until_its_date() -> None:

    book = Book()
    d0, d1, d2 = START, START + timedelta(days=1), START + timedelta(days=2)
    assert book.row_at(d0, _sectors).values["portfolio.open_positions"] == 0
    book.add([OpenTrade("A", d1, d2 + timedelta(days=5), d2 + timedelta(days=5), None, "open")])
    book.lost(d1)
    lost = book.row_at(d1, _sectors)
    assert lost.reason == "leg_lost" and set(lost.values.values()) == {None}
    assert book.row_at(d2, _sectors).values["portfolio.open_positions"] == 1  # known again


def test_a_later_lost_leg_never_shortens_an_earlier_unknown_stretch() -> None:
    book = Book()
    far, near = START + timedelta(days=5), START + timedelta(days=1)
    book.lost(far)
    book.lost(near)
    assert book.row_at(START + timedelta(days=3), _sectors).reason == "leg_lost"


@given(DAYS, HOLD, st.integers(1, 6))
def test_the_rows_are_the_same_whatever_the_chunk_size(
    days: list[date], hold: int, size: int
) -> None:
    """The harness measures a leg between sessions in chunks (one session each when it reads the
    book): feeding a ``Book`` chunk by chunk gives the rows of the whole walk."""
    whole = walk_in_order(days, _decide(hold, []), _sectors)
    book, decide, rows = Book(), _decide(hold, []), {}
    for at in range(0, len(days), size):
        for day in days[at : at + size]:
            rows[day] = book.row_at(day, _sectors)
            book.add(decide(day, rows[day]))
    assert rows == whole
