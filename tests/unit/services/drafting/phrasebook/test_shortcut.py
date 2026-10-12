"""The phrasebook shortcut of ``draft_screen`` (ADR 0041, lever 3): a sentence every clause of
which structured entries with exact thresholds say is drafted with no model call, by the same
``_draft`` as a model's answer (validators, the ``current`` criteria, the explained parts); any
doubt (a negation, an "or", a comparative, a sequence, a field ``current`` already has, a
criterion the catalogue or the validator refuses) asks the model."""

import json
from collections.abc import Mapping
from typing import Any

import pytest

from algotrade.config.site.drafting.criteria import PhraseCriterion
from algotrade.config.site.llm import Phrase
from algotrade.config.site.settings import load_phrasebook
from algotrade.config.user import UserContext
from algotrade.core.model.completion import Completion
from algotrade.services.drafting import screens
from algotrade.services.drafting.golden import load_cases
from algotrade.services.drafting.phrasebook.resolve import resolve
from algotrade.services.drafting.phrasebook.shortcut import shortcut
from algotrade.services.drafting.screens import draft_screen
from algotrade.services.read.context import ReadContext, open_context
from algotrade.storage.factory import open_config_store
from algotrade_sources.framework.base import FixtureSource
from tests.conftest import REPO_ROOT
from tests.helpers.api_store import api_store

BOOK = load_phrasebook(open_config_store(REPO_ROOT / "config")).phrases
GOLDEN_ROOT = REPO_ROOT / "tests" / "fixtures" / "drafting" / "golden"
RSI = "rollup.momentum@v1.rsi_14"
CAP = "feature.market_cap"
MODEL_ANSWER = {
    "criteria": [{"id": "rsi_14", "field": RSI, "op": "lt", "value": 30, "part": "p1"}],
    "tie_break": None,
    "notes": [],
    "parts": [{"id": "p1", "words": "oversold", "reading": "RSI below 30"}],
}


class Forbidden:
    """A ``TextModel`` that fails the test if it is asked."""

    names = ("forbidden",)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def complete(self, system: str, user: str, **_: object) -> Completion:
        raise AssertionError("the phrasebook resolves this sentence: no model call")


class Canned:
    names = ("canned",)

    def __init__(self) -> None:
        self.asked = 0

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def complete(self, system: str, user: str, **_: object) -> Completion:
        self.asked += 1
        return Completion(json.dumps(MODEL_ANSWER), "canned", "canned")


@pytest.fixture(scope="module")
def ctx(golden_source: FixtureSource) -> ReadContext:
    store = api_store(golden_source)[0]
    return open_context(store.reader, store.configs, UserContext(store.user.user_id))


def fields_of(draft: screens.ScreenDraft) -> list[tuple[str, str, Any]]:
    return [(c["field"], c["op"], c.get("value")) for c in draft.document["criteria"].values()]


# sentences of structured wordings only: (sentence, the criteria its words ask for, in file order)
RESOLVED = [
    ("oversold stocks in an uptrend", [(RSI, "lt", 30), ("feature.trend_state", "eq", "UPTREND")]),
    ("volatile small caps", [(CAP, "lt", 2_000_000_000), ("feature.atr_pct", "gte", 0.03)]),
    ("low implied volatility ETFs", [("feature.iv_rank", "lte", 0.3)]),
    ("large cap stocks near the 52-week high", [(CAP, "gte", 10_000_000_000)]),
    ("stocks with earnings this week", [("rollup.earnings@v1.days_to_earnings", "lte", 5)]),
]


@pytest.mark.parametrize(("sentence", "asked"), RESOLVED, ids=[s for s, _ in RESOLVED])
def test_a_sentence_the_phrasebook_resolves_is_drafted_without_the_model(
    ctx: ReadContext, sentence: str, asked: list[tuple[str, str, Any]]
) -> None:
    draft = draft_screen(ctx, Forbidden(), "mine", sentence)
    assert draft.stage == "phrasebook" and draft.call_id is None  # no call, no ledger row to name
    assert all(a in fields_of(draft) for a in asked)  # what the words ask for, thresholds exact
    assert not draft.dropped and not draft.formulas and not draft.missing and not draft.unresolved
    assert draft.document["id"] == "mine" and draft.sentence == sentence
    assert draft.parts and draft.parts_stats is None  # no model made them
    for part in draft.parts:
        assert part.kind == "applied" and part.reading_source == "server"
        assert set(part.criteria) <= set(draft.document["criteria"])
        if part.origin == "words":
            assert draft.sentence[part.start : part.end] == part.words and part.reading
    placed = [c for p in draft.parts for c in p.criteria]
    assert sorted(placed) == sorted(draft.document["criteria"])  # every criterion has a part


def test_the_scaffolding_the_prompt_asks_of_the_model_is_there_without_words(
    ctx: ReadContext,
) -> None:
    draft = draft_screen(ctx, Forbidden(), "mine", "oversold")
    assert ("instrument.status", "eq", "ACTIVE") in fields_of(draft)
    (active,) = [p for p in draft.parts or () if p.origin == "unplaced"]
    assert active.criteria == ("active",) and active.words == ""
    stocks = draft_screen(ctx, Forbidden(), "mine", "oversold stocks")  # "stocks" says it
    assert [f for f, _, _ in fields_of(stocks)].count("instrument.status") == 1


@pytest.mark.parametrize(
    "sentence",
    [
        "oversold stocks without earnings this week",  # a negation
        "oversold or overbought stocks",  # "or"
        "stocks cheaper than their peers that are oversold",  # a comparative
        "stocks that are oversold, then breakout",  # a sequence
        "oversold stocks over 5 dollars",  # a number nobody covers
        "oversold stocks with a good story",  # a word nobody covers
        "oversold and oversold",  # one entry said twice
    ],
)
def test_a_sentence_with_a_doubt_asks_the_model_once(ctx: ReadContext, sentence: str) -> None:
    model = Canned()
    draft = draft_screen(ctx, model, "mine", sentence)
    assert model.asked == 1 and draft.stage == "model"


def test_a_cover_two_entries_share_is_the_models(ctx: ReadContext) -> None:
    both = Phrase(("alpha",), (RSI,), "", (PhraseCriterion(RSI, "lt", 30),))
    twin = Phrase(("beta",), (RSI,), "", (PhraseCriterion(RSI, "lt", 30),))
    resolution = resolve("alpha beta", (both, twin))
    assert resolution is not None and len(resolution.claims) == 2
    assert shortcut(resolution, "alpha beta", None) is None  # one criterion, two parts


def test_a_phrase_on_a_field_current_has_is_the_models(ctx: ReadContext) -> None:
    current = {"criteria": {"cap": {"field": CAP, "op": "gte", "value": 1_000_000_000}}}
    model = Canned()
    draft_screen(ctx, model, "mine", "small caps", current)  # "change my cap": ambiguous
    assert model.asked == 1


def test_current_criteria_are_kept_and_added_to(ctx: ReadContext) -> None:
    current = {"criteria": {"cap": {"field": CAP, "op": "gte", "value": 1_000_000_000}}}
    draft = draft_screen(ctx, Forbidden(), "mine", "oversold", current)
    assert draft.stage == "phrasebook"
    assert draft.document["criteria"]["cap"] == current["criteria"]["cap"]  # as the Builder had it
    assert next(iter(draft.document["criteria"])) == "cap"
    assert {c for p in draft.parts or () if p.origin == "kept" for c in p.criteria} == {"cap"}
    assert any(p.words == "oversold" and p.criteria == ("rsi_14",) for p in draft.parts or ())


@pytest.mark.parametrize(
    "current",
    [
        {"criteria": {"not an id!": {"field": CAP, "op": "gte", "value": 1}}},  # no id to keep
        {"criteria": {"cap": {"field": "feature.gone", "op": "gte", "value": 1}}},  # dropped
    ],
)
def test_current_the_draft_would_not_carry_over_as_it_is_the_models(
    ctx: ReadContext, current: Mapping[str, Any]
) -> None:
    model = Canned()
    draft_screen(ctx, model, "mine", "oversold", current)
    assert model.asked == 1


@pytest.mark.parametrize(
    "current",
    [
        {"criteria": [{"field": CAP}]},  # not a table of criteria
        {"criteria": {"cap": "gte"}},  # not a criterion
        {"criteria": {"cap": {"field": CAP, "op": "gte", "value": {"x": 1}}}},  # not a value
    ],
)
def test_a_current_of_another_shape_is_never_carried_over(current: Mapping[str, Any]) -> None:
    resolution = resolve("oversold", BOOK)
    assert resolution is not None and shortcut(resolution, "oversold", current) is None


@pytest.mark.parametrize(
    "criterion",
    [
        PhraseCriterion("feature.not_in_this_catalogue", "gt", 1),  # a field the caller lacks
        PhraseCriterion("feature.trend_state", "gt", 3),  # the validator refuses a text field
    ],
)
def test_a_criterion_the_draft_refuses_is_not_served_from_the_phrasebook(
    ctx: ReadContext, criterion: PhraseCriterion
) -> None:
    book = (Phrase(("zzz",), (criterion.field,), "", (criterion,)),)
    infos = screens.feature_infos(ctx.features)
    assert screens._from_phrasebook(ctx, "mine", "zzz", infos, book, None) is None


def test_every_phrasebook_sentence_of_the_golden_set_is_a_valid_draft(ctx: ReadContext) -> None:
    """The golden sentences the book resolves in full (train cases may grow it) draft cleanly."""
    done = 0
    for case in load_cases(GOLDEN_ROOT):
        if resolve(case.sentence, BOOK) is None:
            continue
        draft = draft_screen(ctx, Forbidden(), "g", case.sentence, case.current)
        assert draft.stage == "phrasebook" and draft.document["criteria"], case.id
        done += 1
    assert done >= 1
