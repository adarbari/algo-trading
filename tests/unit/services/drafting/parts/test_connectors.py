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
    join_text,
    merged,
    read,
)
from algotrade.services.drafting.phrasebook.resolve import MEANING_WORDS
from algotrade.services.drafting.prompt import TASK


def test_the_prompt_lists_exactly_the_joins() -> None:
    assert join_text() in TASK
    assert join_text().split(", ") == list(JOINS)  # no drift between prompt and server
    assert "@@JOINS@@" not in TASK


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


@pytest.mark.parametrize("phrase", [*JOINS, *sorted(GLUE)])
def test_no_connector_or_glue_word_yields_a_not_understood_part(phrase: str) -> None:
    sentence = f"liquid stocks {phrase} high yield"
    raw = [{"id": "p1", "words": "liquid stocks"}, {"id": "p2", "words": "high yield"}]
    got = build_parts(sentence, raw, [], [])
    assert got is not None
    assert [p.id for p in got[0]] == ["p1", "p2"] and got[1].not_understood == 2  # no items
    assert all(p.origin == "words" for p in got[0])
