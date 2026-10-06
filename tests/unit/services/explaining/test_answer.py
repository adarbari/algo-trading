"""``explain`` (ADR 0041, amended): links outside the allowed list are dropped, every number in
the answer must be one of the facts (to the precision it shows), markdown marks go, and an
answer that fails the check is withheld with a note."""

import json

import pytest

from algotrade.core.model.errors import ModelUnavailableError
from algotrade.services.explaining.answer import (
    Citation,
    explain,
    numbers_in,
    parse,
    unverified,
    verify,
)
from algotrade.services.explaining.prompt import WHAT_IS_HAPPENING, Facts, regime_facts
from algotrade.services.read.regime.regime import MarketRegime
from tests.unit.services.explaining.conftest import Canned, Down

CURVE = "https://example.org/curve"


def answer(text: str, *links: str) -> str:
    return json.dumps({"text": text, "links": list(links)})


def test_a_good_answer_is_checked_with_its_allowed_citations(regime: MarketRegime) -> None:
    model = Canned(answer("The market is in a storm: macro risk is 62 out of 100.", CURVE))
    found = explain(model, regime, WHAT_IS_HAPPENING)
    assert found.checked and found.note is None
    assert found.text == "The market is in a storm: macro risk is 62 out of 100."
    assert found.citations == (Citation("curve page", CURVE),)
    system, user = model.asked[0]
    assert "FACTS" in system and CURVE in system and user == WHAT_IS_HAPPENING


def test_a_link_outside_the_allowed_list_is_dropped(regime: MarketRegime) -> None:
    text = f"Credit is stressed. See https://evil.example/x and {CURVE}, then stop."
    found = verify(answer(text, "https://evil.example/y", CURVE + "/"), regime_facts(regime))
    assert found.checked
    assert found.citations == (Citation("curve page", CURVE),)
    assert "http" not in found.text and found.text == "Credit is stressed. See and then stop."


def test_an_invented_number_withholds_the_answer_with_a_note(regime: MarketRegime) -> None:
    found = explain(Canned(answer("Macro risk is 81 out of 100.", CURVE)), regime, "q")
    assert not found.checked
    assert found.text == "" and found.citations == ()
    assert found.note is not None and "81" in found.note and "not shown" in found.note


@pytest.mark.parametrize(
    ("text", "checked"),
    [
        ("Stress is 71 out of 100.", True),  # exact
        ("Stress is about 71.0.", True),  # same value, more places
        ("Macro risk is 62.5.", False),  # more precise than the 62 the facts show
        ("Macro risk is about 63.", False),  # not what the facts say
        ("Macro risk is about 65.", False),  # not a rounding of any fact
        ("Stress is 71.4.", False),  # more precise than the fact
        ("As of 1 Oct 2026 it is 1 of 1.", True),  # the date and counts are facts
        ("Numbers like 1,000 are not facts.", False),
        ("No numbers at all, only words.", True),
    ],
)
def test_numbers_are_checked_against_the_facts_to_the_precision_shown(
    regime: MarketRegime, text: str, checked: bool
) -> None:
    assert verify(answer(text), regime_facts(regime)).checked is checked


def test_numbers_are_read_with_their_places() -> None:
    assert numbers_in("a 6.80 and 1,234.5, then 3.") == [
        (6.8, 2, "6.80"),
        (1234.5, 1, "1,234.5"),
        (3.0, 0, "3"),
    ]
    facts = regime_facts_text("Value 6.8.")
    assert unverified("It is 7 or 6.8 or 7.4", facts) == ["7.4"]


def regime_facts_text(text: str) -> Facts:  # a Facts over plain text
    return Facts(text, ())


def test_markdown_marks_are_removed_and_plain_text_is_accepted(regime: MarketRegime) -> None:
    marked = answer("# Weather\n**Storm** with `71` stress\n- one\n- two")
    assert verify(marked, regime_facts(regime)).text == "Weather Storm with 71 stress one two"
    raw = verify("A storm, no JSON at all.", regime_facts(regime))
    assert raw.checked and raw.text == "A storm, no JSON at all." and raw.citations == ()
    fenced = verify('```json\n{"text": "Fenced.", "links": []}\n```', regime_facts(regime))
    assert fenced.text == "Fenced."


def test_parse_takes_the_envelope_or_the_text() -> None:
    assert parse('{"text": "x", "links": ["u", 3]}') == ("x", ["u"])
    assert parse('{"text": "x"}') == ("x", [])
    assert parse('{"nothing": 1}') == ('{"nothing": 1}', [])
    assert parse("plain") == ("plain", [])


def test_an_empty_answer_is_the_model_not_answering(regime: MarketRegime) -> None:
    with pytest.raises(ModelUnavailableError, match="empty"):
        verify(answer("   "), regime_facts(regime))


def test_a_model_that_is_down_propagates(regime: MarketRegime) -> None:
    with pytest.raises(ModelUnavailableError, match="timed out"):
        explain(Down(), regime, WHAT_IS_HAPPENING)
