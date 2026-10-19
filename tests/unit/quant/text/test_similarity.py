"""Cosine on raw term counts and Jaccard on word sets: hand-computed golden values, the empty
text, order independence and the range."""

import math

import pytest

from algotrade.quant.text.similarity import merge_counts, term_cosine, term_jaccard


def test_cosine_golden_values() -> None:
    a = {"x": 1, "y": 2}
    b = {"x": 2, "y": 1, "z": 2}
    assert term_cosine(a, a) == 1.0  # exactly, not 0.9999999999999998
    assert term_cosine(a, b) == pytest.approx(4 / (math.sqrt(5) * 3))  # (2 + 2) / (|a| |b|)
    assert term_cosine({"x": 1}, {"y": 1}) == 0.0
    assert term_cosine({"x": 3}, {"x": 7}) == pytest.approx(1.0)  # proportions, not size


def test_jaccard_golden_values() -> None:
    assert term_jaccard({"x": 1, "y": 9}, {"y": 1, "z": 1}) == pytest.approx(1 / 3)
    assert term_jaccard({"x": 1}, {"x": 5}) == 1.0
    assert term_jaccard({"x": 1}, {"y": 1}) == 0.0


def test_a_text_with_no_words_has_no_similarity_never_zero() -> None:
    assert term_cosine({}, {"x": 1}) is None and term_cosine({"x": 1}, {}) is None
    assert term_jaccard({}, {}) is None
    assert term_jaccard({}, {"x": 1}) == 0.0


def test_the_result_does_not_depend_on_insertion_order() -> None:
    words = [f"w{i}" for i in range(200)]
    a = {w: (i % 7) + 1 for i, w in enumerate(words)}
    b = {w: (i % 5) + 1 for i, w in enumerate(reversed(words))}
    forward = term_cosine(a, b)
    backward = term_cosine(dict(reversed(a.items())), dict(reversed(b.items())))
    assert forward == backward and forward is not None and 0.0 <= forward <= 1.0


def test_merge_counts_sums_per_word() -> None:
    assert merge_counts([{"x": 1, "y": 2}, {"y": 3}, {}]) == {"x": 1, "y": 5}


def test_identical_large_counts_give_exactly_one() -> None:
    """Review of #720: the product of two large squares passes 2^53 and rounds."""
    counts = {f"w{i}": 3_000_000 + i for i in range(40)}
    assert term_cosine(counts, dict(counts)) == 1.0
