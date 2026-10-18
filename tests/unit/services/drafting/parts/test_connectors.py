"""The connector vocabulary (ADR 0041, amended 2026-10-17): longest phrase wins, whole words, the
join logic of a stretch; fitness: the prompt lists exactly ``JOINS`` (no drift), and no word of
``GLUE`` or ``JOINS`` ever yields a not-understood part, however the model cut the sentence."""

import pytest

from algotrade.services.drafting.parts.build import build_parts
from algotrade.services.drafting.parts.connectors import (
    GLUE,
    GLUE_WORDS,
    JOIN_KINDS,
    JOINS,
    NEGATIONS,
    exclusion_text,
    join_text,
    merged,
    read,
)
from algotrade.services.drafting.phrasebook.resolve import MEANING_WORDS
from algotrade.services.drafting.prompt import TASK


def test_the_prompt_lists_exactly_the_joins() -> None:
    """Left out between two parts: the and-type joins, the or-words and the exclusion words; kept
    in the words of one condition: the bare negations (ADR 0071)."""
    ands = [p for p, logic in JOINS.items() if logic == "and"]
    ors = [p for p, logic in JOINS.items() if logic == "or"]
    excludes = [p for p, logic in JOINS.items() if logic == "and_not" and p not in NEGATIONS]
    assert join_text() in TASK and join_text("or") in TASK and exclusion_text() in TASK
    assert join_text().split(", ") == ands  # no drift between prompt and server
    assert join_text("or").split(", ") == ors
    assert exclusion_text().split(", ") == excludes
    assert set(NEGATIONS) <= {p for p, logic in JOINS.items() if logic == "and_not"}
    assert set(ands) | set(ors) | set(excludes) | set(NEGATIONS) == set(JOINS)
    assert "@@" not in TASK


def test_every_join_has_a_known_logic_and_glue_never_overlaps_a_join() -> None:
    assert set(JOINS.values()) == set(JOIN_KINDS)
    assert not GLUE & set(JOINS)
    assert GLUE_WORDS <= GLUE


def test_negation_and_or_are_joins_never_glue_so_the_shortcut_does_not_treat_them_as_filler() -> (
    None
):
    assert not {"not", "no", "or", "except", "without"} & GLUE
    assert {"not", "no", "or", "except", "without"} <= set(JOINS)
    assert {"but", "except", "or"} <= MEANING_WORDS  # the phrasebook still sends them to the model


def test_the_longest_phrase_wins_and_only_whole_words_match() -> None:
    assert read(["but", "not"]) == [("join", "and_not")] * 2
    assert read(["but", "liquid"]) == [("join", "and"), ("content", None)]
    assert read(["as", "long", "as"]) == [("join", "and")] * 3
    assert read(["notable", "android"]) == [("content", None)] * 2
    assert read(["show", "me"]) == [("glue", None)] * 2
    assert merged(["and", "or"]) == "or" and merged(["and", "and_not"]) == "and_not"


AND_PHRASES = [p for p, logic in JOINS.items() if logic == "and"]
KEPT_PHRASES = [p for p, logic in JOINS.items() if logic != "and"]
RAW = [{"id": "p1", "words": "liquid stocks"}, {"id": "p2", "words": "high yield"}]


@pytest.mark.parametrize("phrase", [*AND_PHRASES, *sorted(GLUE)])
def test_no_and_connector_or_glue_word_yields_a_not_understood_part(phrase: str) -> None:
    got = build_parts(f"liquid stocks {phrase} high yield", RAW, [], [])
    assert got is not None
    assert [p.id for p in got[0]] == ["p1", "p2"]  # no gap: it is a join or glue


JOINING = [p for p in KEPT_PHRASES if JOINS[p] == "or" or p not in NEGATIONS]


@pytest.mark.parametrize("phrase", JOINING)
def test_an_or_or_a_negation_between_parts_is_the_join_of_the_next(phrase: str) -> None:
    """ADR 0071: left out between two parts it is read as the next part's join (never a chip),
    so the server can group them."""
    got = build_parts(f"liquid stocks {phrase} high yield", RAW, [], [])
    assert got is not None
    assert [p.id for p in got[0]] == ["p1", "p2"]
    assert (got[0][1].join, got[0][1].join_words) == (JOINS[phrase], phrase)


@pytest.mark.parametrize("phrase", [p for p in KEPT_PHRASES if JOINS[p] == "and_not"])
def test_a_negation_the_model_left_out_after_the_last_part_stays_visible_as_a_gap(
    phrase: str,
) -> None:
    """Fail closed: a lost negation with nothing after it must never be silent."""
    got = build_parts(f"liquid stocks {phrase}", RAW[:1], [], [])
    assert got is not None
    gaps = [p for p in got[0] if p.origin == "gap"]
    assert [(g.words, g.kind, g.join) for g in gaps] == [(phrase, "not_understood", "and_not")]


def test_a_curly_apostrophe_is_the_same_filler() -> None:
    assert read(["i\u2019m", "looking", "for"]) == [("glue", None)] * 3
    sentence = "I\u2019m looking for liquid stocks"
    got = build_parts(sentence, [{"id": "p1", "words": "liquid stocks"}], [], [])
    assert got is not None and [p.origin for p in got[0]] == ["words"]


def test_like_is_never_glue() -> None:
    assert "like" not in GLUE  # "stocks like NVDA" means similar to


@pytest.mark.parametrize("phrase", ["all but", "anything but", "everything but"])
def test_all_but_is_an_except_not_a_but(phrase: str) -> None:
    assert JOINS[phrase] == "and_not"
    assert {logic for _, logic in read(phrase.split())} == {"and_not"}


@pytest.mark.parametrize("phrase", NEGATIONS)
def test_a_bare_negation_between_parts_is_a_gap_the_verifier_doubts(phrase: str) -> None:
    got = build_parts(f"liquid stocks {phrase} high yield", RAW, [], [])
    assert got is not None
    gaps = [p for p in got[0] if p.origin == "gap"]
    assert [(g.words, g.kind) for g in gaps] == [(phrase, "not_understood")]
