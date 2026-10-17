"""Clause splitting and the per-clause resolution of the phrasebook (ADR 0041, amended
2026-10-17): an and-type connector splits a sentence, an or / a negation never does, a range or a
wording that holds the connector stays whole; every clause must resolve, on fields of its own."""

import re
from collections.abc import Sequence

import pytest

from algotrade.config.site.drafting.criteria import PhraseCriterion
from algotrade.config.site.llm import Phrase
from algotrade.config.site.settings import load_phrasebook
from algotrade.services.drafting.phrasebook.clauses import split
from algotrade.services.drafting.phrasebook.resolve import resolve, resolve_clauses
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT

BOOK = load_phrasebook(open_config_store(REPO_ROOT / "config")).phrases


def clauses(sentence: str, taken: Sequence[int] = ()) -> list[str]:
    found = list(re.finditer(r"[a-z0-9]+", sentence.lower()))
    mask = [i in taken for i in range(len(found))]
    return [sentence[found[a].start() : found[b - 1].end()] for a, b in split(found, mask)]


def test_and_type_connectors_split_and_leave_no_words_of_their_own() -> None:
    assert clauses("oversold but with rising volume", taken=(0, 3, 4)) == [
        "oversold",
        "rising volume",
    ]
    assert clauses("oversold and also uptrend", taken=(0, 3)) == ["oversold", "uptrend"]
    assert clauses("oversold, yet uptrend", taken=(0, 2)) == ["oversold", "uptrend"]


def test_a_boundary_needs_a_claimed_word_on_both_sides() -> None:
    assert clauses("oversold but zzz", taken=(0,)) == ["oversold but zzz"]
    assert clauses("zzz but oversold", taken=(2,)) == ["zzz but oversold"]


def test_a_negation_or_an_or_is_never_a_boundary() -> None:
    assert clauses("oversold but not uptrend") == ["oversold but not uptrend"]
    assert clauses("oversold and not uptrend") == ["oversold and not uptrend"]
    assert clauses("oversold or overbought") == ["oversold or overbought"]
    assert clauses("oversold except uptrend") == ["oversold except uptrend"]


def test_a_sequence_is_never_a_boundary() -> None:
    assert clauses("oversold, then breakout") == ["oversold, then breakout"]
    assert clauses("oversold and then breakout") == ["oversold and then breakout"]


def test_a_range_or_two_numbers_stay_whole() -> None:
    assert clauses("rsi between 40 and 60 and uptrend", taken=(4, 6)) == [
        "rsi between 40 and 60",
        "uptrend",
    ]
    assert clauses("rsi 40 and 60") == ["rsi 40 and 60"]


def test_a_wording_that_holds_the_connector_is_claimed_whole() -> None:
    # tokens: cheap(0) and(1) liquid(2) but(3) uptrend(4); a wording claims cheap and liquid
    assert clauses("cheap and liquid but uptrend", taken=(0, 1, 2, 4)) == [
        "cheap and liquid",
        "uptrend",
    ]


def test_a_leading_or_trailing_connector_is_no_boundary() -> None:
    assert clauses("and oversold", taken=(1,)) == ["and oversold"]  # nothing before it
    assert clauses("oversold but", taken=(0,)) == ["oversold but"]


def test_a_curly_apostrophe_leaves_an_uncovered_word_so_the_model_answers() -> None:
    # "I\u2019m" tokenises to "i" and "m": the stray "m" is no glue and no entry's word
    assert resolve_clauses("I\u2019m looking for oversold but uptrend", BOOK) is None


def test_every_clause_resolves_and_each_is_one_part() -> None:
    sentence = "large caps near the 52-week high but with rising volume"
    assert resolve(sentence, BOOK) is None  # "but" is a meaning word: the whole does not
    got = resolve_clauses(sentence, BOOK)
    assert got is not None
    assert [(c["field"], c["op"]) for c in got.criteria] == [
        ("feature.pct_from_high_52w", "gte"),  # a clause's criteria in file order
        ("feature.market_cap", "gte"),
        ("feature.volume_trend_20_60", "gt"),
    ]
    assert [sentence[c.start : c.end] for c in got.claims] == [
        "large caps near the 52-week high",
        "rising volume",
    ]
    assert len(got.claims[0].answers()) == 2  # a clause of two entries is one claim


@pytest.mark.parametrize(
    "sentence",
    [
        "oversold stocks but not in a downtrend",  # a negation stays with its condition
        "oversold or overbought but uptrend",  # an or needs a formula
        "oversold but zzz",  # a clause no entry says
        "large caps all but volatile",  # "all but" is an except
        "oversold, all but downtrend",
        "oversold stocks",  # one clause: the whole-sentence path has it
        "oversold but overbought",  # one field twice, never both
        "oversold and then uptrend and downtrend",  # trend_state in two clauses
    ],
)
def test_a_sentence_with_any_clause_in_doubt_is_not_resolved_by_clause(sentence: str) -> None:
    assert resolve_clauses(sentence, BOOK) is None


def test_a_sentence_whose_lowercase_changes_length_is_left_alone() -> None:
    assert resolve_clauses("OVERSOLD but İ uptrend", BOOK) is None


def test_two_clauses_that_cannot_both_hold_are_refused() -> None:
    low = Phrase(("lowcap",), (), "", (PhraseCriterion("feature.market_cap", "lt", 1),))
    high = Phrase(("highcap",), (), "", (PhraseCriterion("feature.atr_pct", "gt", 1),))
    clash = Phrase(("clash",), (), "", (PhraseCriterion("feature.atr_pct", "lt", 0),))
    assert resolve_clauses("lowcap but highcap", (low, high)) is not None
    assert resolve_clauses("highcap but clash", (high, clash)) is None  # the same field
