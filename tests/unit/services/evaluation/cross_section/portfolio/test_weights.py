"""The weights of a portfolio_return book (ADR 0074): each rule, the cash position and the
refusals (no volatility or score for a pick: no book, never a book of the names that have one)."""

import pytest

from algotrade.services.evaluation.cross_section.portfolio.weights import (
    NO_SCORE,
    NO_VOL,
    average_books,
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


def test_slots_a_book_does_not_fill_are_cash_not_renormalised() -> None:
    weights, _ = book_weights(["A"], "equal", {}, {}, slots=4)
    assert dict(weights) == pytest.approx({"A": 0.25, "CASH": 0.75})  # not all in A
    weights, _ = book_weights(["A", "B"], "inverse_vol", {}, {"A": 0.1, "B": 0.2}, slots=4)
    assert dict(weights) == pytest.approx({"A": 1 / 3, "B": 1 / 6, "CASH": 0.5})
    assert book_weights([], "equal", {}, {}, slots=3) == ((("CASH", 1.0),), "")
    full, _ = book_weights(["A", "B"], "equal", {}, {}, slots=2)
    assert dict(full) == {"A": 0.5, "B": 0.5}  # a full book has no cash
    explicit, _ = book_weights(["A", "CASH"], "equal", {}, {}, slots=4)
    assert dict(explicit) == pytest.approx({"A": 0.25, "CASH": 0.75})  # CASH is a slot too


def test_an_ensemble_averages_its_members_books_name_by_name() -> None:
    a = (("X", 0.5), ("Y", 0.5))
    b = (("X", 0.5), ("Z", 0.25), ("CASH", 0.25))
    avg = dict(average_books([a, b]))
    assert avg == pytest.approx({"X": 0.5, "Y": 0.25, "Z": 0.125, "CASH": 0.125})
    assert sum(avg.values()) == pytest.approx(1.0)  # an average of books that add to one
    assert average_books([a, b]) == average_books([b, a])  # never depends on the members' order
    assert [i for i, _ in average_books([a, b])] == ["X", "Y", "CASH", "Z"]  # best weight, then id
    assert average_books([]) == ()
