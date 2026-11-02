"""A named option sleeve's book (E8b): the ladder's depth from the placed entries alone, the
cohorts on fixed slots and the drawdown and worst month over realised exits, by hand."""

from datetime import date

import pytest

from algotrade.core.time.calendar import sessions_between
from algotrade.services.evaluation.cross_section.portfolio.ladder import (
    Cohort,
    book_figures,
    cohorts,
    ladder_depth,
)

DAYS = sessions_between(date(2024, 1, 2), date(2024, 3, 28))


def test_the_depth_is_how_many_entries_one_hold_overlaps() -> None:
    every_fifth = DAYS[::5]
    assert ladder_depth(every_fifth, 5, DAYS) == 1  # spaced by the hold: never two open
    assert ladder_depth(every_fifth, 10, DAYS) == 2
    assert ladder_depth(DAYS[:10], 3, DAYS) == 3  # every session, a three-session hold
    assert ladder_depth([], 5, DAYS) == 0


def test_each_trade_holds_one_slot_and_an_unfilled_slot_is_cash() -> None:
    a, b = DAYS[0], DAYS[5]
    trades = [("SPY", a, DAYS[4], 0.02), ("QQQ", a, DAYS[4], -0.04), ("SPY", b, DAYS[9], 0.03)]
    book = cohorts(trades, names=2, depth=1)
    assert [(c.entry, c.exit) for c in book] == [(a, DAYS[4]), (b, DAYS[9])]
    assert [c.value for c in book] == pytest.approx([(0.02 - 0.04) / 2, 0.03 / 2])
    deeper = cohorts(trades, names=2, depth=2)  # twice the slots: each trade half as large
    assert [c.value for c in deeper] == pytest.approx([-0.005, 0.0075])


def test_the_drawdown_and_worst_month_are_over_realised_exits() -> None:
    book = [
        Cohort(date(2024, 1, 2), date(2024, 1, 30), 0.10),
        Cohort(date(2024, 2, 1), date(2024, 2, 27), -0.22),
        Cohort(date(2024, 2, 28), date(2024, 3, 26), 0.05),
        Cohort(date(2024, 1, 31), date(2024, 2, 28), -0.03),
    ]
    got = book_figures(book, slots=1)
    # equity 1 -> 1.10 (Jan) -> 0.88 -> 0.85 (Feb) -> 0.90 (Mar): from the 1.10 peak to 0.85
    assert got["max_drawdown"] == pytest.approx(1 - 0.85 / 1.10)
    assert (got["worst_month"], got["worst_month_of"]) == (pytest.approx(-0.25), "2024-02")
    assert (got["cohorts"], got["slots"]) == (4, 1)
    assert book_figures([], slots=3)["max_drawdown"] is None
