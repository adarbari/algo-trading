"""``draft_screen`` (ADR 0041): the model's criteria become a valid draft; an invented field,
a bad op or value and one the validator rejects are dropped with their reason; the tie-break
and notes come through; the sentence is bounded; a model that cannot answer is unavailable;
nothing is written."""

import json
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.completion import Completion
from algotrade.core.model.errors import ConfigurationError, ModelUnavailableError
from algotrade.services.configs import resolve_rule_draft
from algotrade.services.drafting.screens import (
    MAX_TEXT,
    DroppedCriterion,
    draft_screen,
    parse_answer,
)
from algotrade.services.read.context import ReadContext, open_context
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.screening.test_rule_screens import (
    ACTIVE as ACTIVE_SELECTION,
)
from tests.unit.services.screening.test_rule_screens import (
    DAY,
    LIQ,
    SCREEN,
    configs,
    seeded,
)

ALICE = "alice"
PRICE = f"{LIQ}.underlying_price"
OI = f"{LIQ}.chain_oi"


class Canned:
    """A ``TextModel`` with one answer; keeps what it was asked."""

    names = ("canned",)

    def __init__(self, answer: Any) -> None:
        self.answer = answer if isinstance(answer, str) else json.dumps(answer)
        self.asked: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> Completion:
        self.asked.append((system, user))
        return Completion(self.answer, "canned", "canned")


class Down:
    names = ("down",)

    def complete(self, system: str, user: str) -> Completion:
        raise ModelUnavailableError("llama at http://localhost:11434/v1: timed out")


@pytest.fixture
def ctx() -> ReadContext:
    reader, _ = seeded()
    return open_context(reader, configs(), UserContext(ALICE), DAY)


def proposal(*criteria: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"criteria": list(criteria), "tie_break": None, "notes": [], **extra}


ACTIVE = {"id": "active", "field": "instrument.status", "op": "eq", "value": "ACTIVE"}
PRICE_GT = {"id": "price", "field": PRICE, "op": "gt", "value": 50, "why": "over $50"}


def test_the_answer_becomes_a_valid_draft(ctx: ReadContext) -> None:
    model = Canned(
        proposal(
            ACTIVE,
            PRICE_GT,
            {
                "id": "oi",
                "field": OI,
                "op": "gte",
                "value": 1000,
                "mode": "soft",
                "tolerance": {"relative": 0.5},
                "on_miss": "LIQUIDITY_RISK",
            },
            {
                "id": "kind",
                "field": "instrument.security_type",
                "op": "in",
                "value": ["COMMON_STOCK", "ADR"],
            },
            tie_break={"field": PRICE, "descending": False},
            notes=["assumed US dollars"],
        )
    )
    draft = draft_screen(ctx, model, "my_screen", "active stocks over $50 with open interest")
    assert (
        draft.screener_id == "my_screen"
        and draft.dropped == ()
        and draft.notes == ("assumed US dollars",)
    )
    doc = draft.document
    assert (doc["id"], doc["kind"], doc["impl"]) == ("my_screen", "screener", "rules")
    assert doc["criteria"] == {
        "active": {"field": "instrument.status", "op": "eq", "value": "ACTIVE"},
        "price": {"field": PRICE, "op": "gt", "value": 50},
        "oi": {
            "field": OI,
            "op": "gte",
            "value": 1000,
            "mode": "soft",
            "tolerance": {"relative": 0.5},
            "on_miss": "LIQUIDITY_RISK",
        },
        "kind": {"field": "instrument.security_type", "op": "in", "value": ["COMMON_STOCK", "ADR"]},
    }
    assert doc["rank"] == {"tie_break": PRICE, "tie_break_order": "asc"}
    resolve_rule_draft(ctx.configs, "my_screen", ctx.user, doc)  # as finalise validates
    system, user = model.asked[0]
    assert PRICE in system and "instrument.status" in system  # the catalogue
    assert user.endswith("Sentence: active stocks over $50 with open interest\n")


def test_invented_fields_bad_ops_and_bad_values_are_dropped_with_reasons(ctx: ReadContext) -> None:
    model = Canned(
        proposal(
            PRICE_GT,
            {
                "id": "iv",
                "field": "rollup.made_up@v9.iv_rank",
                "op": "gte",
                "value": 0.5,
                "why": "IV rank above 50%",
            },
            {"id": "weird", "field": PRICE, "op": "like", "value": 1},
            {"id": "range", "field": PRICE, "op": "between", "value": [1]},
            {"id": "mode", "field": PRICE, "op": "lt", "value": 9, "mode": "fuzzy"},
            {"field": OI, "op": "gte", "value": {"n": 1}},
            tie_break={"field": "rollup.made_up@v9.iv_rank", "descending": True},
        )
    )
    draft = draft_screen(ctx, model, "s", "stocks over $50 with IV rank above 50%")
    assert set(draft.document["criteria"]) == {"price"} and "rank" not in draft.document
    assert draft.dropped == (
        DroppedCriterion(
            "iv",
            "rollup.made_up@v9.iv_rank",
            "field 'rollup.made_up@v9.iv_rank' is not in the catalogue (IV rank above 50%)",
        ),
        DroppedCriterion("weird", PRICE, "unknown op 'like'"),
        DroppedCriterion("range", PRICE, "between needs a list of two numbers"),
        DroppedCriterion("mode", PRICE, "unknown mode 'fuzzy'"),
        DroppedCriterion("chain_oi", OI, "value {'n': 1} is not a number, text or boolean"),
    )


def test_a_criterion_the_validator_rejects_is_dropped_and_the_rest_kept(ctx: ReadContext) -> None:
    # A text comparison on a number: the catalogue has the field, the validator rejects the value.
    model = Canned(proposal(PRICE_GT, {"id": "bad", "field": PRICE, "op": "gt", "value": "high"}))
    draft = draft_screen(ctx, model, "s", "price over 50, high price")
    assert list(draft.document["criteria"]) == ["price"]
    (gone,) = draft.dropped
    assert gone.id == "bad" and gone.field == PRICE and "high" in gone.reason
    resolve_rule_draft(ctx.configs, "s", ctx.user, draft.document)


def test_an_empty_draft_when_nothing_maps(ctx: ReadContext) -> None:
    model = Canned(
        proposal(
            {"id": "x", "field": "feature.nope", "op": "gt", "value": 1}, notes=["no such field"]
        )
    )
    draft = draft_screen(ctx, model, "s", "something the catalogue lacks")
    assert draft.document["criteria"] == {} and len(draft.dropped) == 1
    assert draft.notes == ("no such field",)


def test_ids_are_slugs_and_unique(ctx: ReadContext) -> None:
    model = Canned(
        proposal(
            {"id": "not a slug!", "field": PRICE, "op": "gt", "value": 1},
            {"id": "underlying_price", "field": PRICE, "op": "lt", "value": 100},
            {"field": PRICE, "op": "gte", "value": 2},
        )
    )
    draft = draft_screen(ctx, model, "s", "price between")
    assert list(draft.document["criteria"]) == [
        "underlying_price",
        "underlying_price_2",
        "underlying_price_3",
    ]


def test_a_fenced_answer_is_read_and_a_non_draft_is_unavailable() -> None:
    assert parse_answer('```json\n{"criteria": []}\n```')["criteria"] == []
    with pytest.raises(ModelUnavailableError, match="not JSON"):
        parse_answer("Sure! Here is the screen: ...")
    with pytest.raises(ModelUnavailableError, match="no criteria"):
        parse_answer('{"screen": 1}')


def test_the_sentence_is_bounded_and_the_model_can_be_down(ctx: ReadContext) -> None:
    with pytest.raises(ConfigurationError, match="empty"):
        draft_screen(ctx, Canned(proposal()), "s", "   ")
    with pytest.raises(ConfigurationError, match=str(MAX_TEXT)):
        draft_screen(ctx, Canned(proposal()), "s", "x" * (MAX_TEXT + 1))
    with pytest.raises(ModelUnavailableError, match="timed out"):
        draft_screen(ctx, Down(), "s", "stocks")


def test_the_site_phrasebook_goes_to_the_model() -> None:
    reader, _ = seeded()
    phrasebook = {
        "phrase": [
            {"say": ["liquid"], "fields": [OI, "feature.nope"], "hint": "chain_oi gte 1000"},
            {"say": ["yield"], "fields": ["feature.nope"]},
        ]
    }
    store = MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE_SELECTION,
            ("site", "strategies", "big_liquid"): SCREEN,
            ("site", "settings", "phrasebook"): phrasebook,
        }
    )
    ctx = open_context(reader, store, UserContext(ALICE), DAY)
    model = Canned(proposal(PRICE_GT))
    draft_screen(ctx, model, "s", "liquid names over 50")
    system = model.asked[0][0]
    assert f"liquid | {OI} | chain_oi gte 1000" in system
    assert "\nyield | " not in system  # a phrase with none of the catalogue's fields is left out


def test_the_current_criteria_go_to_the_model(ctx: ReadContext) -> None:
    model = Canned(proposal(PRICE_GT))
    current = {"id": "s", "criteria": {"price": {"field": PRICE, "op": "gt", "value": 5}}}
    draft_screen(ctx, model, "s", "raise the price floor to 50", current)
    assert f'"price": {{"field": "{PRICE}", "op": "gt", "value": 5}}' in model.asked[0][1]
