"""The overlays of a portfolio_return book (ADR 0074 amendment): the volatility of today's weights
over past returns, the scaling to the target (down only, the rest cash, never negative, adding to
one) and the refusal when a name has no return on a day of the window."""

import math
from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from algotrade.services.evaluation.cross_section.portfolio.overlays import (
    book_volatility,
    vol_scaled,
)

DAYS = [date(2026, 3, 2) + timedelta(i) for i in range(6)]
RETURNS = [0.01, -0.01, 0.02, -0.02, 0.01, -0.01]


def _history(**by_name: list[float | None]) -> dict[date, dict[str, float | None]]:
    return {d: {n: r[i] for n, r in by_name.items()} for i, d in enumerate(DAYS)}


def test_book_volatility_is_the_annualised_std_of_the_weighted_daily_returns() -> None:
    book = (("A", 0.5), ("B", 0.25), ("CASH", 0.25))
    hist = _history(A=RETURNS, B=[r * 2 for r in RETURNS])
    daily = [0.5 * r + 0.25 * 2 * r for r in RETURNS]  # = RETURNS: cash adds no variation
    mean = sum(daily) / len(daily)
    std = math.sqrt(sum((x - mean) ** 2 for x in daily) / (len(daily) - 1))
    assert book_volatility(book, hist, DAYS) == pytest.approx(std * math.sqrt(252))


def test_a_name_with_no_return_on_a_day_gives_no_volatility() -> None:
    book = (("A", 0.5), ("B", 0.5))
    hole = [*RETURNS[:-1], None]
    assert book_volatility(book, _history(A=RETURNS, B=hole), DAYS) is None
    assert book_volatility(book, _history(A=RETURNS, B=[*RETURNS[:-1], math.nan]), DAYS) is None
    assert book_volatility(book, {d: {"A": 0.0} for d in DAYS}, DAYS) is None  # B not read
    assert book_volatility(book, _history(A=RETURNS, B=RETURNS), DAYS[:1]) is None  # one day


def test_an_all_cash_book_has_no_volatility_to_measure() -> None:
    assert book_volatility((("CASH", 1.0),), {}, DAYS) == 0.0


def test_a_book_over_the_target_is_scaled_down_and_the_rest_is_cash() -> None:
    book = (("A", 0.6), ("B", 0.2), ("CASH", 0.2))
    scaled = dict(vol_scaled(book, sigma=0.20, target=0.10))
    assert scaled == pytest.approx(
        {"A": 0.3, "B": 0.1, "CASH": 0.6}
    )  # half the names, the rest cash


def test_a_book_under_the_target_is_left_alone_never_levered() -> None:
    book = (("A", 0.6), ("B", 0.4))
    assert vol_scaled(book, sigma=0.05, target=0.10) == book
    assert vol_scaled(book, sigma=0.10, target=0.10) == book
    assert vol_scaled(book, sigma=0.0, target=0.10) == book


@given(
    weights=st.lists(st.floats(0.01, 1.0), min_size=1, max_size=6),
    cash=st.floats(0.0, 0.5),
    sigma=st.floats(0.0, 3.0),
    target=st.floats(0.01, 1.0),
)
def test_a_scaled_book_is_long_only_adds_to_one_and_never_exceeds_the_names_it_had(
    weights: list[float], cash: float, sigma: float, target: float
) -> None:
    total = sum(weights)
    names = [(f"N{i}", (1 - cash) * w / total) for i, w in enumerate(weights)]
    book = (*names, ("CASH", cash))
    scaled = vol_scaled(book, sigma, target)
    held = dict(scaled)
    assert all(w >= -1e-12 for w in held.values())
    assert sum(held.values()) == pytest.approx(1.0, abs=1e-12)
    invested = sum(w for n, w in scaled if n != "CASH")
    assert invested <= sum(w for _, w in names) + 1e-12
    assert {n for n, _ in scaled if n != "CASH"} == {n for n, _ in names}
    reversed_book = vol_scaled(tuple(reversed(book)), sigma, target)
    assert dict(reversed_book) == pytest.approx(held)  # the order of the names does not matter
