"""``portfolio_row``: only trades with ``entry_session <= D < exit_session`` are open, every
missing fact is None (UNKNOWN, never a pass), a personal book reads None whole."""

from datetime import date

import pytest

from algotrade.services.evaluation.portfolio_level.book import (
    EXIT_UNKNOWN,
    PERSONAL_BOOK,
    OpenTrade,
    portfolio_row,
)

D = date(2026, 9, 10)
BEFORE, AFTER = date(2026, 9, 9), date(2026, 9, 11)
SECTORS = {"A": "tech", "B": "tech", "C": "energy"}


def _t(name: str, entry: date, exit_: date | None, cap: float | None = 100.0, lic: str = "open"):
    return OpenTrade(name, entry, exit_, AFTER if exit_ is None else exit_, cap, lic)


def test_the_boundaries_entry_day_is_open_exit_day_is_closed_pending_is_out() -> None:
    trades = [_t("A", D, AFTER), _t("B", BEFORE, D), _t("C", AFTER, date(2026, 9, 20))]
    row = portfolio_row(trades, D, SECTORS)
    assert row.values["portfolio.open_positions"] == 1  # A only: B exits at D, C is pending
    assert row.reason is None


def test_concentration_over_equal_positions() -> None:
    trades = [_t("A", BEFORE, AFTER), _t("B", BEFORE, AFTER), _t("C", BEFORE, AFTER)]
    v = portfolio_row(trades, D, SECTORS, option=True).values
    assert v["portfolio.open_positions"] == 3
    assert v["portfolio.effective_bets"] == pytest.approx(3.0)
    assert v["portfolio.max_name_share"] == pytest.approx(1 / 3)
    assert v["portfolio.max_sector_share"] == pytest.approx(2 / 3)
    assert v["portfolio.open_collateral"] == 300.0


def test_one_name_held_twice_is_one_bet() -> None:
    v = portfolio_row([_t("A", BEFORE, AFTER), _t("A", BEFORE, AFTER)], D, SECTORS).values
    assert v["portfolio.effective_bets"] == pytest.approx(1.0)
    assert v["portfolio.max_name_share"] == 1.0


def test_an_empty_book_is_known_and_a_share_book_has_no_collateral_field() -> None:
    v = portfolio_row([], D, SECTORS).values
    assert v == {
        "portfolio.open_positions": 0, "portfolio.effective_bets": 0.0,
        "portfolio.max_sector_share": 0.0, "portfolio.max_name_share": 0.0,
    }  # fmt: skip
    assert portfolio_row([], D, SECTORS, option=True).values["portfolio.open_collateral"] == 0.0


def test_a_missing_sector_or_collateral_is_none_for_that_field_only() -> None:
    v = portfolio_row([_t("Z", BEFORE, AFTER, cap=None)], D, SECTORS, option=True).values
    assert v["portfolio.max_sector_share"] is None
    assert v["portfolio.open_collateral"] is None
    assert v["portfolio.open_positions"] == 1


def test_a_trade_past_its_plan_with_no_exit_known_makes_the_book_unknown() -> None:
    stale = OpenTrade("A", BEFORE, None, BEFORE, 1.0, "open")
    row = portfolio_row([stale], D, SECTORS)
    assert row.reason == EXIT_UNKNOWN
    assert all(v is None for v in row.values.values())


def test_a_trade_not_yet_due_with_no_exit_is_open() -> None:
    row = portfolio_row([OpenTrade("A", BEFORE, None, AFTER, 1.0, "open")], D, SECTORS)
    assert row.values["portfolio.open_positions"] == 1


@pytest.mark.parametrize("licence", ["personal", "yahoo"])
def test_a_book_with_a_trade_priced_from_licensed_history_is_unknown(licence: str) -> None:
    row = portfolio_row([_t("A", BEFORE, AFTER), _t("B", BEFORE, AFTER, lic=licence)], D, SECTORS)
    assert row.reason == PERSONAL_BOOK
    assert all(v is None for v in row.values.values())


def test_a_personal_trade_no_longer_open_does_not_taint_the_row() -> None:
    row = portfolio_row([_t("A", BEFORE, D, lic="personal")], D, SECTORS)
    assert row.reason is None
