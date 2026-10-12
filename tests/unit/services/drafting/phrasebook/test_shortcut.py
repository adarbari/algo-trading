"""The phrasebook shortcut of ``draft_screen`` (ADR 0041, lever 3): a sentence every clause of
which structured entries with exact thresholds say is drafted with no model call, by the same
``_draft`` as a model's answer (validators, the ``current`` criteria, the explained parts); any
doubt (a negation, an "or", a comparative, a sequence, a field ``current`` already has, a
criterion the catalogue or the validator refuses) asks the model."""

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

from algotrade.config.site.drafting.criteria import PhraseCriterion
from algotrade.config.site.llm import Phrase
from algotrade.config.site.settings import load_phrasebook
from algotrade.config.user import UserContext
from algotrade.core.model.completion import Completion
from algotrade.services.drafting import screens
from algotrade.services.drafting.golden.golden import load_cases
from algotrade.services.drafting.phrasebook.resolve import resolve
from algotrade.services.drafting.phrasebook.shortcut import phrasebook_version, shortcut
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


def criteria_of(draft: screens.ScreenDraft) -> list[str]:
    """The draft's criteria as sorted JSON, so a wrong extra or a missing one fails a test."""
    return sorted(json.dumps(c, sort_keys=True) for c in draft.document["criteria"].values())


def expect(*criteria: dict[str, Any]) -> list[str]:
    return sorted(json.dumps(c, sort_keys=True) for c in criteria)


STOCKS = {"field": "instrument.security_type", "op": "in", "value": ["COMMON_STOCK", "ADR"]}
ETFS = {"field": "instrument.security_type", "op": "in", "value": ["ETF"]}
ACTIVE = {"field": "instrument.status", "op": "eq", "value": "ACTIVE"}
# sentences of structured wordings only, and exactly the criteria they ask for (nothing else)
RESOLVED = [
    (
        "oversold stocks in an uptrend",
        expect(
            {"field": RSI, "op": "lt", "value": 30},
            {"field": "feature.trend_state", "op": "eq", "value": "UPTREND"},
            STOCKS, ACTIVE,
        ),
    ),
    (
        "volatile small caps",
        expect(
            {"field": CAP, "op": "lt", "value": 2_000_000_000},
            {"field": "feature.atr_pct", "op": "gte", "value": 0.03},
            ACTIVE,
        ),
    ),
    (
        "low implied volatility ETFs",
        expect({"field": "feature.iv_rank", "op": "lte", "value": 0.3}, ETFS, ACTIVE),
    ),
    (
        "large cap stocks near the 52-week high",
        expect(
            {"field": CAP, "op": "gte", "value": 10_000_000_000},
            {
                "field": "feature.pct_from_high_52w", "op": "gte", "value": -0.1,
                "mode": "soft", "tolerance": 0.05,
            },
            STOCKS, ACTIVE,
        ),
    ),
    (
        "stocks with earnings this week",
        expect(
            {"field": "rollup.earnings@v1.days_to_earnings", "op": "lte", "value": 5},
            STOCKS, ACTIVE,
        ),
    ),
]  # fmt: skip


@pytest.mark.parametrize(("sentence", "asked"), RESOLVED, ids=[s for s, _ in RESOLVED])
def test_a_sentence_the_phrasebook_resolves_is_drafted_without_the_model(
    ctx: ReadContext, sentence: str, asked: list[str]
) -> None:
    draft = draft_screen(ctx, Forbidden(), "mine", sentence)
    assert draft.stage == "phrasebook" and draft.call_id is None  # no call, no ledger row to name
    assert criteria_of(draft) == asked  # what the words ask for, thresholds exact, nothing more
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
    assert criteria_of(draft) == expect({"field": RSI, "op": "lt", "value": 30}, ACTIVE)
    (active,) = [p for p in draft.parts or () if p.origin == "unplaced"]
    assert active.criteria == ("active",) and active.words == ""
    stocks = draft_screen(ctx, Forbidden(), "mine", "oversold stocks")  # "stocks" says it
    assert criteria_of(stocks) == expect({"field": RSI, "op": "lt", "value": 30}, STOCKS, ACTIVE)


@pytest.mark.parametrize(
    "sentence",
    [
        "oversold stocks without earnings this week",  # a negation
        "oversold or overbought stocks",  # "or"
        "less volatile small caps",  # a comparative: only "less" is not covered
        "pullback in a downtrend",  # the pullback implies an uptrend: two regimes
        "volatile to squeeze",  # a range: "to" is never filler
        "from oversold to uptrend",
        "around oversold",
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


PULLBACK = {"criteria": {"pb": {"field": "feature.pullback_to_sma20", "op": "eq", "value": True}}}


def test_a_current_pullback_and_a_downtrend_in_the_sentence_are_the_models(
    ctx: ReadContext,
) -> None:
    """The pullback entry implies an uptrend: the Builder's pullback row contradicts the words."""
    model = Canned()
    draft = draft_screen(ctx, model, "mine", "downtrend", PULLBACK)
    assert model.asked == 1 and draft.stage == "model"
    ok = draft_screen(ctx, Forbidden(), "mine", "oversold", PULLBACK)  # nothing contradicts
    assert ok.stage == "phrasebook" and "pb" in ok.document["criteria"]


def test_the_status_scaffolding_the_builder_already_has_does_not_stop_the_shortcut(
    ctx: ReadContext,
) -> None:
    current = {"criteria": {"active": dict(ACTIVE)}}
    draft = draft_screen(ctx, Forbidden(), "mine", "oversold ETFs", current)
    assert draft.stage == "phrasebook"
    assert criteria_of(draft) == expect({"field": RSI, "op": "lt", "value": 30}, ETFS, ACTIVE)
    assert all(p.kind == "applied" for p in draft.parts or ())  # the row sits with the words


def test_a_no_model_draft_is_stamped_with_the_book_that_made_it(ctx: ReadContext) -> None:
    draft = draft_screen(ctx, Forbidden(), "mine", "oversold")
    assert draft.prompt_version == phrasebook_version(BOOK) != screens.PROMPT_VERSION
    assert draft.prompt_version.startswith("phrasebook:") and len(draft.prompt_version) == 19
    i = next(n for n, p in enumerate(BOOK) if p.criteria)
    other = [*BOOK]
    other[i] = replace(BOOK[i], criteria=())  # an entry's criteria are what the book says
    assert phrasebook_version(other) != phrasebook_version(BOOK)
    other[i] = replace(BOOK[i], hint="reworded")  # a hint is not read by the shortcut
    assert phrasebook_version(other) == phrasebook_version(BOOK)


def test_a_model_draft_keeps_the_prompt_version(ctx: ReadContext) -> None:
    assert draft_screen(ctx, Canned(), "mine", "oversold or overbought").prompt_version == (
        screens.PROMPT_VERSION
    )


@pytest.mark.parametrize(
    "current",
    [
        {"criteria": [{"field": CAP}]},  # not a table of criteria
        {"criteria": {"cap": "gte"}},  # not a criterion
        {"criteria": {"cap": {"field": CAP, "op": "gte", "value": {"x": 1}}}},  # not a value
    ],
)
def test_a_malformed_current_never_fails_the_draft(
    ctx: ReadContext, current: Mapping[str, Any]
) -> None:
    """A Builder document is whatever the client sent: the model answers, no error."""
    model = Canned()
    draft_screen(ctx, model, "mine", "oversold", current)
    assert model.asked == 1


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
