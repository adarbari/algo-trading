"""The weights of a portfolio_return book (ADR 0073): each rule, the cash position and the
refusals (no volatility or score for a pick: no book, never a book of the names that have one)."""

import pytest

from algotrade.services.evaluation.cross_section.portfolio.weights import (
    NO_SCORE,
    NO_VOL,
    book_weights,
)


def test_equal_weights_split_evenly() -> None:
    weights, why = book_weights(["A", "B", "C", "D"], "equal", {}, {})
    assert why == ""
    assert dict(weights) == dict.fromkeys("ABCD", 0.25)


def test_inverse_vol_gives_calmer_names_more() -> None:
    weights, why = book_weights(["A", "B"], "inverse_vol", {}, {"A": 0.1, "B": 0.2})
    assert why == ""
    assert dict(weights) == pytest.approx({"A": 2 / 3, "B": 1 / 3})


def test_score_weights_follow_the_score() -> None:
    weights, _ = book_weights(["A", "B"], "score", {"A": 3.0, "B": 1.0}, {})
    assert dict(weights) == pytest.approx({"A": 0.75, "B": 0.25})


@pytest.mark.parametrize("vol", [None, 0.0, -0.1, float("nan"), float("inf")])
def test_a_pick_with_no_usable_volatility_makes_no_book(vol: float | None) -> None:
    assert book_weights(["A", "B"], "inverse_vol", {}, {"A": 0.1, "B": vol}) == ((), NO_VOL)
    assert book_weights(["A", "B"], "inverse_vol", {}, {"A": 0.1}) == ((), NO_VOL)  # not read


@pytest.mark.parametrize("score", [None, 0.0, -2.0])
def test_a_pick_with_no_positive_score_makes_no_book(score: float | None) -> None:
    scores = {"A": 1.0} if score is None else {"A": 1.0, "B": score}
    assert book_weights(["A", "B"], "score", scores, {}) == ((), NO_SCORE)


def test_no_picks_is_a_cash_book() -> None:
    assert book_weights([], "equal", {}, {}) == ((("CASH", 1.0),), "")
    assert book_weights([], "inverse_vol", {}, {}) == ((("CASH", 1.0),), "")  # nothing to size


def test_cash_takes_an_equal_share_and_the_names_split_the_rest_by_the_weighting() -> None:
    weights, why = book_weights(["A", "CASH", "B"], "inverse_vol", {}, {"A": 0.1, "B": 0.2})
    assert why == ""
    assert dict(weights) == pytest.approx({"A": 2 / 3 * 2 / 3, "B": 1 / 3 * 2 / 3, "CASH": 1 / 3})
    assert sum(w for _, w in weights) == pytest.approx(1.0)
    assert book_weights(["CASH"], "score", {}, {}) == ((("CASH", 1.0),), "")  # all cash


def test_a_pick_listed_twice_counts_once_and_weights_add_to_one() -> None:
    weights, _ = book_weights(["A", "B", "A"], "equal", {}, {})
    assert dict(weights) == {"A": 0.5, "B": 0.5}


def test_an_unknown_weighting_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="no weighting"):
        book_weights(["A"], "kelly", {}, {})
